from src.scrape.base import now_iso
from src.scrape.rss import render_rss_html, scrape_rss


SITE_URL = "https://kauainownews.com/category/kauai-news/"
FEED_URL = "https://kauainownews.com/category/kauai-news/feed/"


def scrape() -> dict:
    items = scrape_rss(FEED_URL, limit=5)
    block_html = (
        render_rss_html(items)
    )
    return {
        "id": "kauai_now",
        "label": f"News (<a href=\"{SITE_URL}\">Kauai Now</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [SITE_URL, FEED_URL],
        "html": block_html,
        "error": None,
        "stale": False,
    }
