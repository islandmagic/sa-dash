"""HDOT Highways news RSS (Kauai / Līhuʻe district releases).

Used by the combined Roads & Harbors module (`hidot_status`). Kept as a
standalone scraper for `--scraper hidot_highways_news` debugging.
"""

from bs4 import BeautifulSoup

from src.scrape.base import clean_text, fetch_html, now_iso
from src.scrape.rss import render_rss_html, scrape_rss


SITE_URL = "https://hidot.hawaii.gov/highways/category/news/"
FEED_URL = "https://hidot.hawaii.gov/highways/category/news/feed/"


def _fetch_primary_content(url: str) -> str:
    if not url:
        return ""
    html_text = fetch_html(url)
    soup = BeautifulSoup(html_text, "lxml")
    container = soup.find("div", class_="primary-content")
    if not container:
        return ""
    paragraphs = [
        clean_text(p.get_text(" "))
        for p in container.find_all("p")
        if not p.has_attr("style")
    ]
    return " ".join([p for p in paragraphs if p])


def _is_kauai_item(item: dict) -> bool:
    blob = " ".join(
        [
            item.get("title") or "",
            item.get("summary") or "",
        ]
    ).upper()
    return any(
        token in blob
        for token in (
            "LĪHUʻE",
            "LIHUE",
            "KAUAʻI",
            "KAUAI",
            "KAUA'I",
        )
    )


def fetch_kauai_news(limit: int = 5) -> list[dict]:
    """Return recent HDOT news items relevant to Kauai, with full bodies when available."""
    items = scrape_rss(FEED_URL, limit=10)
    kauai_items = []
    for item in items:
        if not _is_kauai_item(item):
            continue
        try:
            full_summary = _fetch_primary_content(item.get("url", ""))
        except Exception:
            full_summary = ""
        if full_summary:
            item = {**item, "summary": full_summary}
        kauai_items.append(item)
        if len(kauai_items) >= limit:
            break
    return kauai_items


def scrape() -> dict:
    items = fetch_kauai_news(limit=5)
    block_html = render_rss_html(items)
    text_lines = ["HDOT news:"]
    for item in items:
        text_lines.append(f"- {item.get('title')} ({item.get('published') or ''})")
    return {
        "id": "hidot_highways_news",
        "label": f"Roads &amp; Bridges (<a href=\"{SITE_URL}\">HDOT News</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [SITE_URL, FEED_URL],
        "html": block_html,
        "text": "\n".join(text_lines),
        "error": None,
        "stale": False,
        "layout": "full",
    }
