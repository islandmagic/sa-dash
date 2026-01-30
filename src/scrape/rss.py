import datetime as dt
import html
import email.utils

import feedparser

from src.scrape.base import clean_text, fetch_html


HST = dt.timezone(dt.timedelta(hours=-10))


def _format_published(entry) -> str:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        dt_obj = dt.datetime(*parsed[:6], tzinfo=dt.timezone.utc).astimezone(HST)
        return dt_obj.strftime("%Y-%m-%d %H:%M HST")
    raw = clean_text(getattr(entry, "published", "") or getattr(entry, "updated", ""))
    if not raw:
        return ""
    try:
        dt_obj = email.utils.parsedate_to_datetime(raw)
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=dt.timezone.utc)
        return dt_obj.astimezone(HST).strftime("%Y-%m-%d %H:%M HST")
    except (TypeError, ValueError):
        return raw


def parse_rss(xml_text: str, limit: int = 5) -> list[dict]:
    feed = feedparser.parse(xml_text)
    items = []
    for entry in feed.entries:
        title = clean_text(getattr(entry, "title", "")) or "Untitled"
        link = getattr(entry, "link", "") or ""
        summary = clean_text(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        published = _format_published(entry)
        items.append(
            {
                "title": title,
                "url": link,
                "summary": summary,
                "published": published,
            }
        )
        if len(items) >= limit:
            break
    return items


def scrape_rss(url: str, limit: int = 5) -> list[dict]:
    xml_text = fetch_html(url)
    return parse_rss(xml_text, limit=limit)


def render_rss_html(items: list[dict]) -> str:
    if not items:
        return "<p>No RSS items found.</p>"
    list_items = "".join(
        "<li>"
        f"<a href=\"{html.escape(item['url'])}\">{html.escape(item['title'])}</a>"
        + (f": {html.escape(item['summary'])}" if item.get("summary") else "")
        + (f"<br/><span class=\"meta\">{html.escape(item['published'])}</span>" if item.get("published") else "")
        + "</li>"
        for item in items
    )
    return f"<ul>{list_items}</ul>"


