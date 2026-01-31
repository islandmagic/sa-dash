import html

from bs4 import BeautifulSoup

from src.scrape.base import clean_text, fetch_html, now_iso


WATER_URL = "https://www.kauaiwater.org/service-outages/"


def _extract_reported_outages(page_html: str, limit: int = 5) -> list[dict]:
    soup = BeautifulSoup(page_html, "lxml")
    heading = soup.find(
        lambda tag: tag.name in {"h2", "h3"}
        and clean_text(tag.get_text()) == "Reported Outages"
    )
    if not heading:
        return []

    container = heading.find_parent("div") or heading.parent
    outages_list = None
    if container:
        outages_list = container.find("ul", class_="wp-block-latest-posts__list")

    if outages_list is None:
        outages_list = soup.find("ul", class_="lp-service-outages")

    if outages_list is None:
        return []

    items = []
    for li in outages_list.find_all("li", recursive=False):
        title_link = li.find("a", class_="wp-block-latest-posts__post-title")
        title = clean_text(title_link.get_text()) if title_link else None
        url = title_link.get("href") if title_link else WATER_URL
        excerpt = li.find("div", class_="wp-block-latest-posts__post-excerpt")
        summary = clean_text(excerpt.get_text()) if excerpt else None
        if title:
            items.append({"title": title, "url": url, "summary": summary})
        if len(items) >= limit:
            break
    return items


def scrape() -> dict:
    page_html = fetch_html(WATER_URL)
    items = _extract_reported_outages(page_html, limit=5)

    info_html = (
        "<p><strong>Emergencies:</strong> Nights, weekends and holidays: "
        "<a href=\"tel:+18082411711\">808-241-1711</a>. Business hours: "
        "<a href=\"tel:+18082455400\">808-245-5400</a>, option 1.</p>"
    )
    if items:
        list_items = "".join(
            "<li>"
            f"<a href=\"{item['url']}\">{html.escape(item['title'])}</a>"
            + (f": {html.escape(item['summary'])}" if item.get("summary") else "")
            + "</li>"
            for item in items
        )
        block_html = (
            f"{info_html}"
            f"<ul>{list_items}</ul>"
        )
    else:
        block_html = (
            "<p>No reported outages found.</p>"
            f"{info_html}"
        )

    return {
        "id": "kauai_water",
        "label": f"Water (<a href=\"{WATER_URL}\">Dept. of Water</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [WATER_URL],
        "html": block_html,
        "error": None,
        "stale": False,
    }
