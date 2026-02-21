import datetime as dt
import html as html_module
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.scrape.base import clean_text, fetch_html, now_iso


LISTING_URL = "https://www.kauai.gov/County-Press-Releases"
HST = dt.timezone(dt.timedelta(hours=-10))


def _format_published(date_str: str) -> str:
    """Parse 'February 21, 2026' or 'Feb. 21, 2026' to '2026-02-21 00:00 HST'."""
    if not date_str:
        return ""
    date_str = date_str.strip()
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b. %d, %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            parsed = dt.datetime.strptime(date_str, fmt).replace(tzinfo=HST)
            return parsed.strftime("%Y-%m-%d %H:%M HST")
        except ValueError:
            continue
    return date_str
LIMIT = 5


def _parse_listing(html_text: str, base_url: str) -> list[dict]:
    """Parse listing page; return [{title, url, published?}] up to LIMIT."""
    soup = BeautifulSoup(html_text, "lxml")
    items = []
    for article in soup.find_all("article"):
        h2 = article.find("h2")
        link = article.find("a", href=True)
        if not h2 or not link:
            continue
        href = link.get("href", "")
        if "/County-Press-Releases/" not in href or href.endswith("/County-Press-Releases"):
            continue
        url = urljoin(base_url, href)
        title = clean_text(h2.get_text())
        if not title or len(title) < 5:
            continue
        link_text = clean_text(link.get_text())
        match = re.search(r"Published on ([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})", link_text)
        published = _format_published(match.group(1)) if match else ""
        items.append({"title": title, "url": url, "published": published})
        if len(items) >= LIMIT:
            break
    return items


def _fetch_release_body(url: str) -> str:
    """Fetch detail page and extract main content. Return plain text or empty on failure."""
    if not url:
        return ""
    try:
        html_text = fetch_html(url)
    except Exception:
        return ""
    soup = BeautifulSoup(html_text, "lxml")
    container = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_="primary-content")
        or soup.find("div", class_="content")
    )
    if not container:
        cols = soup.find_all("div", class_="col-xs-12")
        for col in cols:
            if len(col.find_all("p")) > 3:
                container = col
                break
    if not container:
        return ""
    skip_prefixes = ("Published on ", "Tagged as")
    skip_exact = ("###", "---", "Media Releases")
    parts = []
    for tag in container.find_all(["p", "li", "h3", "h4"]):
        text = clean_text(tag.get_text(" "))
        if not text or text in skip_exact:
            continue
        if any(text.startswith(p) for p in skip_prefixes):
            continue
        parts.append(text)
    return "\n\n".join(parts) if parts else ""


def scrape() -> dict:
    try:
        html_text = fetch_html(LISTING_URL)
    except Exception as exc:
        return {
            "id": "kauai_county_press",
            "label": "Press Releases (Kauai County)",
            "retrieved_at": now_iso(),
            "source_urls": [LISTING_URL],
            "html": f"<p>{html_module.escape(str(exc))}</p>",
            "error": str(exc),
            "stale": True,
        }

    items = _parse_listing(html_text, LISTING_URL)
    detail_items = []
    for item in items:
        body = _fetch_release_body(item.get("url", ""))
        detail_items.append(
            {
                "title": item["title"],
                "url": item["url"],
                "published": item.get("published", ""),
                "body": body or "Content unavailable.",
            }
        )

    blocks = []
    for d in detail_items:
        headline_html = html_module.escape(d["title"])
        if d.get("url"):
            headline_html = f'<a href="{html_module.escape(d["url"])}">{headline_html}</a>'
        published = d.get("published", "")
        meta_html = f'<br/><span class="meta">{html_module.escape(published)}</span>' if published else ""
        body_html = html_module.escape(d["body"]).replace("\n", "<br>")
        blocks.append(
            "<details>"
            f"<summary>{headline_html}{meta_html}</summary>"
            f"<div>{body_html}</div>"
            "</details>"
        )

    body_html = "".join(blocks) if blocks else "<p>No press releases found.</p>"
    return {
        "id": "kauai_county_press",
        "label": f"Press Releases (<a href=\"{LISTING_URL}\">Kauai County</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [LISTING_URL],
        "html": body_html,
        "error": None,
        "stale": False,
        "layout": "full",
    }
