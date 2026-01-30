import datetime as dt
import re
from typing import Iterable, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": "eoc-dash/1.0 (+https://github.com/)",
    "Accept-Language": "en-US,en;q=0.9",
}


def now_iso() -> str:
    hst = dt.timezone(dt.timedelta(hours=-10))
    return dt.datetime.now(tz=hst).replace(microsecond=0).isoformat()


def fetch_html(url: str, timeout: float = 10.0, headers: dict | None = None) -> str:
    request_headers = DEFAULT_HEADERS if headers is None else headers
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=request_headers) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def fetch_json(url: str, timeout: float = 10.0) -> dict:
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=DEFAULT_HEADERS) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def extract_page_summary(html: str) -> tuple[Optional[str], Optional[str]]:
    soup = BeautifulSoup(html, "lxml")
    title = clean_text(soup.title.get_text()) if soup.title else None
    heading = soup.find(["h1", "h2"])
    heading_text = clean_text(heading.get_text()) if heading else None
    meta_desc = soup.find("meta", attrs={"name": "description"})
    meta_text = clean_text(meta_desc.get("content")) if meta_desc else None
    summary = heading_text or meta_text
    return title, summary


def extract_headlines(html: str, base_url: str, limit: int = 8) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    candidates: Iterable = soup.find_all(["h1", "h2", "h3", "a"])
    results = []
    seen = set()
    for tag in candidates:
        link = tag if tag.name == "a" else tag.find("a")
        if not link or not link.get("href"):
            continue
        text = clean_text(link.get_text())
        if len(text) < 12 or len(text) > 160:
            continue
        href = link.get("href")
        url = urljoin(base_url, href)
        key = (text, url)
        if key in seen:
            continue
        seen.add(key)
        results.append({"title": text, "url": url})
        if len(results) >= limit:
            break
    return results


def scrape_status_provider(provider: dict) -> dict:
    items = []
    source_urls = []
    for source in provider.get("sources", []):
        url = source["url"]
        html = fetch_html(url)
        title, summary = extract_page_summary(html)
        items.append(
            {
                "title": source.get("label") or title or provider["label"],
                "summary": summary,
                "url": url,
            }
        )
        source_urls.append(url)
    return {
        "provider_id": provider["id"],
        "label": provider["label"],
        "type": provider["type"],
        "retrieved_at": now_iso(),
        "items": items,
        "source_urls": source_urls,
        "error": None,
        "stale": False,
    }


def scrape_news_provider(provider: dict) -> dict:
    sources_out = []
    limit = provider.get("limit", 8)
    source_urls = []
    for source in provider.get("sources", []):
        url = source["url"]
        html = fetch_html(url)
        headlines = extract_headlines(html, url, limit=limit)
        sources_out.append(
            {
                "source": source.get("label") or url,
                "url": url,
                "headlines": headlines,
            }
        )
        source_urls.append(url)
    return {
        "provider_id": provider["id"],
        "label": provider["label"],
        "type": provider["type"],
        "retrieved_at": now_iso(),
        "items": sources_out,
        "source_urls": source_urls,
        "error": None,
        "stale": False,
    }
