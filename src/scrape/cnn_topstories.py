import html

from bs4 import BeautifulSoup

from src.scrape.base import clean_text, fetch_html, now_iso


SITE_URL = "https://lite.cnn.com"


def scrape() -> dict:
    page_html = fetch_html(SITE_URL)
    soup = BeautifulSoup(page_html, "lxml")
    headlines = []

    main = soup.select_one("div.layout-homepage__lite") or soup
    latest_heading = main.find(
        lambda tag: tag.name in {"h2", "h3"}
        and "Latest Stories" in clean_text(tag.get_text())
    )
    container = latest_heading.find_parent() if latest_heading else main
    for link in container.find_all("a"):
        text = clean_text(link.get_text())
        href = link.get("href")
        if not text or not href:
            continue
        if not href.startswith("http"):
            href = f"{SITE_URL}{href}"
        headlines.append({"title": text, "url": href})
        if len(headlines) >= 10:
            break

    if headlines:
        list_items = "".join(
            f"<li><a href=\"{item['url']}\">{html.escape(item['title'])}</a></li>"
            for item in headlines
        )
        block_html = (
            f"<ul>{list_items}</ul>"
        )
    else:
        block_html = f"<p><a href=\"{SITE_URL}\">CNN Lite</a>: No headlines found.</p>"
    return {
        "id": "cnn_topstories",
        "label": f"News (<a href=\"{SITE_URL}\">CNN Lite</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [SITE_URL],
        "html": block_html,
        "error": None,
        "stale": False,
    }
