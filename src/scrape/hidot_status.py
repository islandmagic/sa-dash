"""HDOT roads, harbors, lane closures, and Kauai highway news — combined module."""

from __future__ import annotations

import html as html_module
import re

from bs4 import BeautifulSoup

from src.scrape.base import clean_text, fetch_html, now_iso
from src.scrape.hidot_highways_news import FEED_URL, SITE_URL, fetch_kauai_news
from src.scrape.rss import render_rss_html

WEATHER_URL = "https://hidot.hawaii.gov/weather-traffic/"
LANE_URL = "https://hidot.hawaii.gov/highways/roadwork/kauai/"


def _status_class(status: str) -> str:
    s = (status or "").lower()
    if "closed" in s:
        return "status-red"
    if "local access" in s or "limited" in s or "one-lane" in s or "restriction" in s:
        return "status-yellow"
    if "open" in s:
        return "status-green"
    return ""


def _parse_kauai_table(page_html: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "lxml")
    # Find Kauai heading then following table
    heading = None
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "strong", "p"]):
        txt = clean_text(tag.get_text(" "))
        if re.search(r"^Kaua[ʻ']?i\s*$", txt, re.I) or txt.lower() in {
            "kauai",
            "kauaʻi",
            "kaua'i",
        }:
            heading = tag
            break
        if re.match(r"^Kaua[ʻ']?i\b", txt, re.I) and len(txt) < 20:
            heading = tag
            break

    table = None
    if heading:
        table = heading.find_next("table")
    if table is None:
        # Fallback: scan all tables for Route 50 / Kuhio content
        for t in soup.find_all("table"):
            blob = t.get_text(" ")
            if "Kuhio" in blob or "Kaumualii" in blob or "Nawiliwili" in blob:
                table = t
                break
    if table is None:
        return []

    rows: list[dict] = []
    for tr in table.find_all("tr"):
        cells = [clean_text(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        # Skip header
        if cells[0].lower() in {"facility", "type"}:
            continue
        facility = cells[0]
        ftype = cells[1] if len(cells) > 1 else ""
        status = cells[2] if len(cells) > 2 else ""
        notes = cells[3] if len(cells) > 3 else ""
        if not facility:
            continue
        rows.append(
            {"facility": facility, "type": ftype, "status": status, "notes": notes}
        )
    return rows


def _parse_lane_closures(page_html: str) -> tuple[str, list[dict]]:
    soup = BeautifulSoup(page_html, "lxml")
    main = (
        soup.find("div", class_="primary-content")
        or soup.find("main")
        or soup.body
    )
    if not main:
        return "", []
    blob = main.get_text("\n")
    week = ""
    m = re.search(r"FOR THE WEEK OF[^\n]+", blob, re.I)
    if m:
        week = clean_text(m.group(0))

    entries: list[dict] = []
    current_route = ""
    lines = blob.splitlines()
    i = 0
    while i < len(lines):
        line = clean_text(lines[i])
        route_m = re.match(r"[—\-–]+\s*(.+?)\s*[—\-–]+\s*$", line)
        if route_m:
            current_route = route_m.group(1).strip()
            i += 1
            continue
        num_m = re.match(r"^(\d+)\)\s*(.+)$", line)
        if num_m:
            place = num_m.group(2).strip()
            # Collect following paragraph lines until next numbered or route
            para = []
            j = i + 1
            while j < len(lines):
                nxt = clean_text(lines[j])
                if re.match(r"^\d+\)\s*", nxt) or re.match(
                    r"[—\-–]+\s*.+\s*[—\-–]+\s*$", nxt
                ):
                    break
                if nxt in {"# # #", "Media contact:"} or nxt.lower().startswith(
                    "media contact"
                ):
                    break
                if nxt:
                    para.append(nxt)
                j += 1
            entries.append(
                {
                    "route": current_route,
                    "place": place,
                    "detail": " ".join(para),
                }
            )
            i = j
            continue
        i += 1
    return week, entries[:15]


def scrape() -> dict:
    weather_html = fetch_html(WEATHER_URL)
    rows = _parse_kauai_table(weather_html)

    week = ""
    closures: list[dict] = []
    try:
        lane_html = fetch_html(LANE_URL)
        week, closures = _parse_lane_closures(lane_html)
    except Exception:
        pass

    news_items: list[dict] = []
    try:
        news_items = fetch_kauai_news(limit=5)
    except Exception:
        news_items = []

    parts: list[str] = []
    text_lines: list[str] = ["Roads & harbors (HDOT):"]

    if rows:
        trs = []
        for r in rows:
            css = _status_class(r["status"])
            trs.append(
                "<tr>"
                f"<td>{html_module.escape(r['facility'])}</td>"
                f"<td>{html_module.escape(r['type'])}</td>"
                f'<td class="status-cell {css}">{html_module.escape(r["status"])}</td>'
                f"<td>{html_module.escape(r['notes'][:240])}</td>"
                "</tr>"
            )
            text_lines.append(
                f"- {r['facility']}: {r['status']} — {r['notes'][:120]}"
            )
        parts.append(
            "<table><thead><tr>"
            "<th>Facility</th><th>Type</th><th>Status</th><th>Notes</th>"
            "</tr></thead>"
            f"<tbody>{''.join(trs)}</tbody></table>"
        )
    else:
        parts.append("<p>Kauai status table unavailable.</p>")
        text_lines.append("- status table unavailable")

    if closures:
        week_label = html_module.escape(week) if week else "Weekly lane closures"
        items = []
        for c in closures:
            route = html_module.escape(c["route"])
            place = html_module.escape(c["place"])
            detail = html_module.escape(c["detail"][:300])
            items.append(f"<li><strong>{route} — {place}</strong>: {detail}</li>")
            text_lines.append(f"- Lane: {c['route']} {c['place']}")
        parts.append(
            f"<details><summary>{week_label}</summary>"
            f"<ul>{''.join(items)}</ul></details>"
        )

    if news_items:
        news_html = render_rss_html(news_items)
        parts.append(
            "<details><summary>HDOT highway news</summary>"
            f"<div>{news_html}</div></details>"
        )
        text_lines.append("News:")
        for item in news_items:
            text_lines.append(
                f"- {item.get('title')} ({item.get('published') or ''})"
            )

    return {
        "id": "hidot_status",
        "label": f'Roads &amp; Harbors (<a href="{WEATHER_URL}">HDOT</a>)',
        "retrieved_at": now_iso(),
        "source_urls": [WEATHER_URL, LANE_URL, SITE_URL, FEED_URL],
        "html": "".join(parts),
        "text": "\n".join(text_lines),
        "error": None,
        "stale": False,
        "layout": "full",
    }
