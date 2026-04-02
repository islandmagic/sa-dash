import html
from datetime import datetime, timedelta, timezone

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
        published = li.find("time", class_="wp-block-latest-posts__post-date")
        published_date = None
        if published:
            raw_datetime = published.get("datetime")
            if raw_datetime:
                try:
                    parsed = datetime.fromisoformat(raw_datetime)
                    hst = parsed.astimezone(timezone(timedelta(hours=-10)))
                    published_date = hst.strftime("%Y-%m-%d %H:%M HST")
                except ValueError:
                    published_date = clean_text(published.get_text())
            else:
                published_date = clean_text(published.get_text())
        if title:
            items.append(
                {
                    "title": title,
                    "url": url,
                    "summary": summary,
                    "published_date": published_date,
                }
            )
        if len(items) >= limit:
            break
    return items


def scrape() -> dict:
    page_html = fetch_html(WATER_URL)
    items = _extract_reported_outages(page_html, limit=5)
    if items:
        details_blocks = []
        for item in items:
            title = html.escape(item["title"])
            url = html.escape(item.get("url", ""))
            summary = (
                html.escape(item["summary"])
                if item.get("summary")
                else "No details available."
            )
            published = (
                html.escape(item["published_date"])
                if item.get("published_date")
                else ""
            )
            headline_html = f'<a href="{url}">{title}</a>' if url else title
            meta_html = f'<br/><span class="meta">{published}</span>' if published else ""
            details_blocks.append(
                "<details>"
                f"<summary>{headline_html}{meta_html}</summary>"
                f"<div>{summary}</div>"
                "</details>"
            )
        block_html = "".join(details_blocks)
    else:
        block_html = "<p>No reported outages found.</p>"

    return {
        "id": "kauai_water",
        "label": f"Water (<a href=\"{WATER_URL}\">Dept. of Water</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [WATER_URL],
        "html": block_html,
        "error": None,
        "stale": False,
    }
