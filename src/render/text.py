"""Plain-text digest renderer for low-bandwidth / Winlink delivery."""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup

DIGEST_SECTION_IDS = (
    "breaking_news",
    "kauai_recovers",
    "weather_kauai",
    "tropical_outlook",
    "kiuc",
    "kauai_water",
    "hidot_status",
    "kauai_solid_waste",
    "county_alerts",
    "kauai_county_press",
    "verizon_mobile",
    "att_mobile",
    "helpmefind",
)

SECTION_CHAR_CAP = 2000
DIGEST_CHAR_CAP = 12_000
SOURCE_URL = "http://kauai.islandmagic.co/digest.txt"


_HAWAIIAN_MAP = str.maketrans(
    {
        "ʻ": "'",
        "ʼ": "'",
        "‘": "'",
        "’": "'",
        "ā": "a",
        "Ā": "A",
        "ē": "e",
        "Ē": "E",
        "ī": "i",
        "Ī": "I",
        "ō": "o",
        "Ō": "O",
        "ū": "u",
        "Ū": "U",
        "—": "-",
        "–": "-",
        "…": "...",
    }
)


def ascii_fold(text: str) -> str:
    """Strip Hawaiian diacritics and non-ASCII for radio-friendliness."""
    if not text:
        return ""
    text = text.translate(_HAWAIIAN_MAP)
    normalized = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return folded.encode("ascii", "replace").decode("ascii")


def html_to_text(fragment: str) -> str:
    """Convert an HTML fragment to compact plain text."""
    if not fragment:
        return ""
    soup = BeautifulSoup(f"<body>{fragment}</body>", "lxml")
    body = soup.body
    if not body:
        return ""

    for tag in body.find_all(["script", "style"]):
        tag.decompose()

    lines: list[str] = []

    def _emit(text: str) -> None:
        text = re.sub(r"[ \t]+", " ", text).strip()
        if text:
            lines.append(text)

    for el in body.descendants:
        if getattr(el, "name", None) is None:
            continue
        name = el.name
        if name in {"h1", "h2", "h3", "h4"}:
            _emit(el.get_text(" ", strip=True).upper())
        elif name == "p":
            _emit(el.get_text(" ", strip=True))
        elif name == "li":
            _emit(f"- {el.get_text(' ', strip=True)}")
        elif name == "tr":
            cells = [
                c.get_text(" ", strip=True)
                for c in el.find_all(["th", "td"], recursive=False)
            ]
            if cells:
                _emit(" | ".join(cells))
        elif name == "details":
            summary = el.find("summary")
            title = summary.get_text(" ", strip=True) if summary else "Details"
            # Body without the summary
            clone_parts = []
            for child in el.children:
                if getattr(child, "name", None) == "summary":
                    continue
                if hasattr(child, "get_text"):
                    clone_parts.append(child.get_text(" ", strip=True))
                elif isinstance(child, str):
                    clone_parts.append(child.strip())
            body_txt = " ".join(p for p in clone_parts if p)
            if body_txt:
                _emit(f"{title}: {body_txt}")
            else:
                _emit(title)
        elif name == "br":
            lines.append("")

    # Fallback if nothing structured was emitted
    if not lines:
        _emit(body.get_text(" ", strip=True))

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _label_plain(label: str) -> str:
    return re.sub(r"<[^>]+>", "", label or "").strip() or "Section"


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _provider_text(provider: dict) -> str:
    if provider.get("text"):
        return str(provider["text"]).strip()
    return html_to_text(provider.get("html") or "")


def _mobile_summary(body: str) -> str:
    """Collapse carrier tables into one useful line.

    Prefer an existing scraper `text` summary. When falling back from HTML
    tables, skip the header row and join Town: Status pairs.
    """
    lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    # Already a compact summary from the scraper
    if len(lines) == 1 and " | " not in lines[0]:
        return lines[0]
    if lines[0].lower().startswith(("verizon:", "at&t:", "att:")):
        return lines[0]

    rows = lines
    if rows and rows[0].lower().startswith("town |"):
        rows = rows[1:]
    pairs: list[str] = []
    for row in rows:
        cells = [c.strip() for c in row.split("|")]
        if len(cells) >= 2 and cells[0] and cells[1]:
            pairs.append(f"{cells[0]}: {cells[1]}")
    return "; ".join(pairs) if pairs else (lines[0] if lines else "")


def render_digest(
    island_name: str,
    providers: list[dict],
    generated_at: str,
    event: dict | None = None,
) -> str:
    """Build a plain-text situational digest for low-bandwidth delivery."""
    by_id = {p.get("id"): p for p in providers if p.get("id")}
    event = event or {}

    stale = [
        p.get("id")
        for p in providers
        if p.get("stale") and not p.get("skip") and p.get("id")
    ]
    header_bits = [
        f"{island_name} DIGEST",
        generated_at or "unknown",
    ]
    if event.get("active"):
        reasons = ", ".join(event.get("reasons") or []) or "active"
        header_bits.append(f"EVENT: {reasons}")
    else:
        header_bits.append("status: normal")
    if stale:
        header_bits.append(f"stale: {', '.join(stale)}")

    parts = [" | ".join(header_bits), ""]

    for section_id in DIGEST_SECTION_IDS:
        provider = by_id.get(section_id)
        if not provider or provider.get("skip"):
            continue
        body = _provider_text(provider)
        if not body:
            continue
        # Mobile carriers: compact one-line summary (skip table header-only noise)
        if section_id in {"verizon_mobile", "att_mobile"}:
            body = _mobile_summary(body)
            if not body:
                continue
        body = _cap(body, SECTION_CHAR_CAP)
        label = _label_plain(str(provider.get("label", section_id)))
        parts.append(f"== {label} ==")
        parts.append(body)
        parts.append("")

    parts.append(f"-- {SOURCE_URL}")
    digest = "\n".join(parts).strip() + "\n"
    digest = ascii_fold(digest)
    if len(digest) > DIGEST_CHAR_CAP:
        digest = digest[: DIGEST_CHAR_CAP - 20].rstrip() + "\n...(truncated)\n"
    return digest
