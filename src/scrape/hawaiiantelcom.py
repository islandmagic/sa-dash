from src.scrape.base import now_iso
from src.scrape.rss import render_rss_html, scrape_rss


HAWAIIAN_TELCOM_URL = "https://www.facebook.com/hawaiiantelcom/"
RSS_URL = "https://rss.xcancel.com/HawaiianTel/rss"


def scrape() -> dict:
    items = scrape_rss(RSS_URL, limit=3)
    block_html = (
        render_rss_html(items)
    )
    return {
        "id": "hawaiiantelcom",
        "label": f"Internet (<a href=\"{HAWAIIAN_TELCOM_URL}\">Hawaiian Telcom</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [HAWAIIAN_TELCOM_URL, RSS_URL],
        "html": block_html,
        "error": None,
        "stale": False,
    }
