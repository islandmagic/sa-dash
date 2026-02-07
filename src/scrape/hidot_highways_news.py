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


def scrape() -> dict:
    items = scrape_rss(FEED_URL, limit=10)
    lihue_items = []
    for item in items:
        summary = item.get("summary", "")
        if "LĪHUʻE" not in summary.upper():
            continue
        try:
            full_summary = _fetch_primary_content(item.get("url", ""))
        except Exception:
            full_summary = ""
        if full_summary:
            item = {**item, "summary": full_summary}
        lihue_items.append(item)
    items = lihue_items[:5]
    info_html = (
        "<p><strong>Road and closure conditions:</strong> <a href=\"tel:+18082411725\">808-241-1725</a></p>"
        "<p><strong>Report a problem:</strong> <a href=\"tel:+18082413000\">808-241-3000</a></p>"
    )
    block_html = f"{info_html}" + render_rss_html(items)
    return {
        "id": "hidot_highways_news",
        "label": f"Roads &amp; Bridges (<a href=\"{SITE_URL}\">HDOT News</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [SITE_URL, FEED_URL],
        "html": block_html,
        "error": None,
        "stale": False,
        "layout": "full",
    }
