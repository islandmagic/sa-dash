from src.scrape.base import now_iso
from src.scrape.rss import render_rss_html, scrape_rss


SITE_URL = "https://www.foxnews.com/us"
FEED_URL = "https://moxie.foxnews.com/google-publisher/us.xml"


def scrape() -> dict:
    items = scrape_rss(FEED_URL, limit=10)
    block_html = (
        render_rss_html(items)
    )
    return {
        "id": "foxnews_us",
        "label": f"News (<a href=\"{SITE_URL}\">Fox News U.S.</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [SITE_URL, FEED_URL],
        "html": block_html,
        "error": None,
        "stale": False,
    }
