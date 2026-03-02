import datetime as dt
import html as html_module
import re
from typing import List, Optional

import feedparser
from bs4 import BeautifulSoup

from src.scrape.base import clean_text, fetch_html, now_iso


RSS_URL = "https://publish.obsidian.md/s2underground/rss.xml"
WIRE_LISTING_URL = (
    "https://publish.obsidian.md/s2underground/"
)
HST = dt.timezone(dt.timedelta(hours=-10))
MAX_ITEMS = 5


def _parse_wire_datetime(header_line: str) -> str:
    """
    Parse header like:
    //The Wire//2300Z January 2, 2026//
    into 'YYYY-MM-DD HH:MM HST'.
    """
    if not header_line:
        return ""

    # Extract the time+date portion between the second and third //
    match = re.search(r"//The Wire//\s*([^/]+?)\s*//", header_line)
    if not match:
        return ""

    ts_text = clean_text(match.group(1))
    # Expect formats like '2300Z January 2, 2026'
    for fmt in ("%H%MZ %B %d, %Y", "%H%MZ %B %d %Y"):
        try:
            parsed_utc = dt.datetime.strptime(ts_text, fmt).replace(
                tzinfo=dt.timezone.utc
            )
            parsed_hst = parsed_utc.astimezone(HST)
            return parsed_hst.strftime("%Y-%m-%d %H:%M HST")
        except ValueError:
            continue
    return ts_text


def _extract_precedence(lines: List[str]) -> str:
    """
    Find a precedence line like '//ROUTINE//' or '//PRIORITY//'.
    Returns normalized uppercase value (e.g. 'ROUTINE', 'PRIORITY') or ''.
    """
    for line in lines:
        text = clean_text(line)
        if not text.startswith("//") or not text.endswith("//"):
            continue
        inner = text.strip("/").strip()
        if not inner:
            continue
        upper = inner.upper()
        # Common precedence values; ignore the 'THE WIRE' header
        if upper in {"ROUTINE", "PRIORITY", "IMMEDIATE", "FLASH"}:
            return upper
    return ""


def _precedence_marker(precedence: str) -> str:
    """
    Map precedence to an ASCII marker for the headline.
    ROUTINE -> '' (no marker)
    PRIORITY -> '! '
    IMMEDIATE -> '!! '
    FLASH -> '!!! '
    Unknown non-empty precedence -> f'[{precedence}] '
    """
    if not precedence:
        return ""
    prec = precedence.upper()
    if prec == "ROUTINE":
        return ""
    if prec == "PRIORITY":
        return "! "
    if prec == "IMMEDIATE":
        return "!! "
    if prec == "FLASH":
        return "!!! "
    return f"[{prec}] "


def _extract_bluf(lines: List[str]) -> Optional[str]:
    """
    Extract the BLUF content.

    Handles lines like:
      //BLUF: PROTESTS EXPAND...//
      BLUF: PROTESTS EXPAND...
      BLUF - PROTESTS EXPAND...

    If the label line has no trailing text, falls back to the next
    non-empty line as the BLUF content.
    """
    for idx, raw in enumerate(lines):
        if "BLUF" not in raw.upper():
            continue
        text = raw.strip()
        # strip surrounding slashes used in the template
        text = text.strip("/")
        # Try to capture text after the BLUF label on the same line
        m = re.match(
            r"\s*BLUF\s*[:\-–—]?\s*(.*)",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            tail = clean_text(m.group(1))
            if tail:
                return tail
        # Otherwise, use the next non-empty line as the BLUF content
        for j in range(idx + 1, min(idx + 4, len(lines))):
            nxt = clean_text(lines[j])
            if nxt:
                return nxt
    return None


def _extract_header_line(lines: List[str]) -> str:
    """Return the first line that looks like the //The Wire// header."""
    for line in lines:
        if "//The Wire//" in line:
            return line
    return ""


def _extract_tearline(text: str) -> str:
    """
    Extract the body between BEGIN/END TEARLINE markers.
    Returns plain text (with newlines) or ''.
    """
    if not text:
        return ""
    match = re.search(
        r"-----BEGIN TEARLINE-----([\s\S]*?)-----END TEARLINE-----", text
    )
    if not match:
        return ""
    body = match.group(1)
    # Normalize line endings and trim
    lines = [line.rstrip() for line in body.splitlines()]
    # Strip leading/trailing empty lines
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _fetch_wire_page(url: str) -> Optional[dict]:
    """
    Fetch and parse a single Wire report page.
    Returns dict with keys: bluf, tearline, precedence, header_ts, url.
    """
    if not url:
        return None
    try:
        html_text = fetch_html(url)
    except Exception:
        return None

    # Obsidian Publish pages load the actual markdown from a separate URL
    # referenced in JS, e.g.:
    #   window.preloadPage = f("https://publish-01.obsidian.md/.../The%20Wire%20-%20...md");
    md_text: Optional[str] = None
    preload_match = re.search(
        r'window\.preloadPage\s*=\s*f\("([^"]+\.md)"\)',
        html_text,
    )
    if preload_match:
        md_url = preload_match.group(1)
        try:
            md_text = fetch_html(md_url)
        except Exception:
            md_text = None

    if md_text:
        text = md_text
    else:
        # Fallback: use visible HTML text if markdown URL not found
        soup = BeautifulSoup(html_text, "lxml")
        text = soup.get_text("\n")
    lines = text.splitlines()

    header_line = _extract_header_line(lines)
    header_ts = _parse_wire_datetime(header_line) if header_line else ""
    precedence = _extract_precedence(lines)
    bluf = _extract_bluf(lines)
    tearline = _extract_tearline(text)

    # Fallbacks
    if not bluf:
        # Use a short excerpt from the tearline or overall text
        source = tearline or text
        snippet = clean_text(source)[:200]
        bluf = snippet or "No BLUF available."
    if not tearline:
        # Shorten the full text as a degraded body
        snippet = "\n".join(lines[:40])
        tearline = snippet or "Content unavailable."

    return {
        "url": url,
        "bluf": bluf,
        "tearline": tearline,
        "precedence": precedence,
        "header_ts": header_ts,
    }


def _select_wire_entries(feed) -> List[dict]:
    """Select the latest MAX_ITEMS 'The Wire - ' entries from the RSS feed."""
    entries = []
    for entry in getattr(feed, "entries", []):
        title = clean_text(getattr(entry, "title", "") or "")
        if not title.startswith("The Wire - "):
            continue
        link = getattr(entry, "link", "") or ""
        if not link:
            continue
        # Parse the Wire date from the title, e.g. "The Wire - November 7, 2025"
        date_ts: Optional[dt.datetime] = None
        m = re.match(r"The Wire - (.+)", title)
        if m:
            date_str = m.group(1).strip()
            # Remove trailing precedence qualifier like "- PRIORITY"
            date_str = re.sub(r"\s*-\s*(PRIORITY|IMMEDIATE|FLASH)\s*$", "", date_str, flags=re.IGNORECASE)
            for fmt in ("%B %d, %Y", "%B %d %Y"):
                try:
                    date_ts = dt.datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
        entries.append(
            {
                "title": title,
                "link": link,
                "ts": date_ts,
            }
        )

    # Sort newest first if we have timestamps
    def _sort_key(item):
        ts = item["ts"]
        return ts or dt.datetime.min

    entries.sort(key=_sort_key, reverse=True)
    return entries[:MAX_ITEMS]


def scrape() -> dict:
    try:
        feed = feedparser.parse(RSS_URL)
    except Exception as exc:
        return {
            "id": "global_events_wire",
            "label": "Global Events (S2 Underground Wire)",
            "retrieved_at": now_iso(),
            "source_urls": [RSS_URL],
            "html": f"<p>{html_module.escape(str(exc))}</p>",
            "error": str(exc),
            "stale": True,
            "layout": "full",
        }

    if getattr(feed, "bozo", 0):
        # feedparser sets bozo flag on parse errors
        exc = getattr(feed, "bozo_exception", None)
        msg = f"Failed to parse RSS feed: {exc}" if exc else "Failed to parse RSS feed."
        return {
            "id": "global_events_wire",
            "label": "Global Events (S2 Underground Wire)",
            "retrieved_at": now_iso(),
            "source_urls": [RSS_URL],
            "html": f"<p>{html_module.escape(msg)}</p>",
            "error": msg,
            "stale": True,
            "layout": "full",
        }

    wire_entries = _select_wire_entries(feed)
    source_urls = [RSS_URL]
    blocks: List[str] = []

    for entry in wire_entries:
        url = entry["link"]
        parsed = _fetch_wire_page(url)
        if not parsed:
            continue

        source_urls.append(url)
        bluf = parsed["bluf"]
        precedence = parsed.get("precedence", "")
        marker = _precedence_marker(precedence)
        header_ts = parsed.get("header_ts", "")
        tearline = parsed["tearline"]

        headline_html = html_module.escape(marker + bluf)
        if url:
            headline_html = (
                f'<a href="{html_module.escape(url)}">{headline_html}</a>'
            )

        meta_html = (
            f'<br/><span class="meta">{html_module.escape(header_ts)}</span>'
            if header_ts
            else ""
        )

        body_html = html_module.escape(tearline).replace("\n", "<br>")

        blocks.append(
            "<details>"
            f"<summary>{headline_html}{meta_html}</summary>"
            f"<div>{body_html}</div>"
            "</details>"
        )

    if not blocks:
        body_html = "<p>No recent Wire reports found.</p>"
        stale = True
    else:
        body_html = "".join(blocks)
        stale = False

    return {
        "id": "global_events_wire",
        "label": (
            'Global Events (<a href="'
            + html_module.escape(WIRE_LISTING_URL)
            + '">S2 Underground Wire</a>)'
        ),
        "retrieved_at": now_iso(),
        "source_urls": source_urls,
        "html": body_html,
        "error": None,
        "stale": stale,
        "layout": "full",
    }

