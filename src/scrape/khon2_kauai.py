from src.scrape.base import now_iso
from src.scrape.rss import render_rss_html, scrape_rss


SITE_URL = "https://www.khon2.com/kauai-news/"
FEED_URL = "https://www.khon2.com/kauai-news/feed/"


def scrape() -> dict:
    items = scrape_rss(FEED_URL, limit=5)
    block_html = (
        render_rss_html(items)
    )
    return {
        "id": "khon2_kauai",
        "label": f"News (<a href=\"{SITE_URL}\">KHON2 Kauai</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [SITE_URL, FEED_URL],
        "html": block_html,
        "error": None,
        "stale": False,
    }
