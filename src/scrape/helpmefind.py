"""Crowd-sourced supply reports from helpmefind.app."""

from __future__ import annotations

import datetime as dt
import html as html_module
import re

from src.scrape.base import fetch_json, now_iso

SITE_URL = "https://helpmefind.app"
REPORTS_URL = "https://helpmefind.app/api/reports"
ACTIVITY_URL = "https://helpmefind.app/api/activity"

KAUAI_LAT = 22.05
KAUAI_LNG = -159.5
RADIUS_M = 60_000
ITEMS = ("ice", "water", "gas", "propane", "generators")
MAX_AGE_HOURS = 72
HST = dt.timezone(dt.timedelta(hours=-10))

STATUS_CLASS = {
    "in_stock": "status-green",
    "low": "status-yellow",
    "running_low": "status-yellow",
    "out": "status-red",
}


def _parse_town(address: str | None) -> str:
    if not address:
        return ""
    # "2535 Kolo Rd, Kilauea, HI 96754, USA" -> Kilauea
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 2:
        # Prefer the part before HI / state
        for part in parts[1:]:
            if re.match(r"^[A-Za-zʻ''\-\s]+$", part) and part.upper() not in {"HI", "USA", "US"}:
                return part
    return ""


def _age_label(created_at: str | None, now: dt.datetime | None = None) -> str:
    if not created_at:
        return "?"
    try:
        parsed = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return "?"
    now = now or dt.datetime.now(tz=dt.timezone.utc)
    delta = now - parsed.astimezone(dt.timezone.utc)
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "<1h"
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def _is_fresh(created_at: str | None, now: dt.datetime | None = None) -> bool:
    if not created_at:
        return False
    try:
        parsed = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    now = now or dt.datetime.now(tz=dt.timezone.utc)
    return (now - parsed.astimezone(dt.timezone.utc)) <= dt.timedelta(hours=MAX_AGE_HOURS)


def _fetch_item(item: str) -> list[dict]:
    url = (
        f"{REPORTS_URL}?lat={KAUAI_LAT}&lng={KAUAI_LNG}"
        f"&item={item}&radius={RADIUS_M}"
    )
    payload = fetch_json(url)
    results = payload.get("results") or []
    out = []
    for row in results:
        if not row.get("report_id"):
            continue
        if not _is_fresh(row.get("created_at")):
            continue
        out.append(row)
    return out


def scrape() -> dict:
    by_item: dict[str, list[dict]] = {}
    errors: list[str] = []
    for item in ITEMS:
        try:
            by_item[item] = _fetch_item(item)
        except Exception as exc:  # noqa: BLE001
            by_item[item] = []
            errors.append(f"{item}: {exc}")

    parts: list[str] = [
        f'<p class="info">Crowd-sourced via <a href="{SITE_URL}">helpmefind.app</a>. '
        "Unverified — confirm before driving. "
        f'<a href="{SITE_URL}">Report what you find</a>.</p>'
    ]
    text_lines: list[str] = ["Supplies (helpmefind.app, last 72h):"]

    for item in ITEMS:
        rows = by_item.get(item) or []
        parts.append(f"<h3>{html_module.escape(item.title())}</h3>")
        if not rows:
            parts.append("<p>No recent reports.</p>")
            text_lines.append(f"- {item}: no recent reports")
            continue
        # Sort newest first, cap
        rows = sorted(rows, key=lambda r: r.get("created_at") or "", reverse=True)[:12]
        trs = []
        for r in rows:
            name = html_module.escape(r.get("name") or "?")
            town = html_module.escape(_parse_town(r.get("address")))
            status = (r.get("status") or "").lower()
            css = STATUS_CLASS.get(status, "")
            age = _age_label(r.get("created_at"))
            note = html_module.escape(r.get("note") or "")
            trs.append(
                "<tr>"
                f"<td>{name}</td>"
                f"<td>{town}</td>"
                f'<td class="status-cell {css}">{html_module.escape(status or "?")}</td>'
                f"<td>{html_module.escape(age)}</td>"
                f"<td>{note}</td>"
                "</tr>"
            )
            text_lines.append(
                f"- {item}: {r.get('name')} ({_parse_town(r.get('address'))}) "
                f"{status} {age}"
            )
        parts.append(
            "<table><thead><tr>"
            "<th>Store</th><th>Town</th><th>Status</th><th>Age</th><th>Note</th>"
            "</tr></thead>"
            f"<tbody>{''.join(trs)}</tbody></table>"
        )

    return {
        "id": "helpmefind",
        "label": f'Supplies (<a href="{SITE_URL}">helpmefind.app</a>)',
        "retrieved_at": now_iso(),
        "source_urls": [SITE_URL, REPORTS_URL, ACTIVITY_URL],
        "html": "".join(parts),
        "text": "\n".join(text_lines),
        "error": "; ".join(errors) if errors else None,
        "stale": False,
        "layout": "full",
    }
