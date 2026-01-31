from src.scrape.base import now_iso
from src.scrape.rss import render_rss_html, scrape_rss


SITE_URL = "https://hidot.hawaii.gov/highways/category/news/"
FEED_URL = "https://hidot.hawaii.gov/highways/category/news/feed/"


def scrape() -> dict:
    items = scrape_rss(FEED_URL, limit=10)
    items = [
        item
        for item in items
        if item.get("summary", "").startswith("LĪHUʻE")
    ][:5]
    block_html = (
        render_rss_html(items)
    )
    return {
        "id": "hidot_highways_news",
        "label": f"Roads &amp; Bridges (<a href=\"{SITE_URL}\">HDOT News</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [SITE_URL, FEED_URL],
        "html": block_html,
        "error": None,
        "stale": False,
    }
