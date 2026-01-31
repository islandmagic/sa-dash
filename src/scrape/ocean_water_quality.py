import html
from datetime import datetime

from src.scrape.base import fetch_json, now_iso


DATA_URL = "https://mmvk4falrj.execute-api.us-west-2.amazonaws.com/v1/history/lab/23"
REPORT_BASE_URL = "https://bwtf.surfrider.org/report/23"
SITE_PREFIX_WHITELIST = ("North", "East")
LOW_MAX = 35
MEDIUM_MAX = 130


def _classify(result: float | int | None) -> tuple[str, int]:
    if result is None:
        return "Unknown", 99
    if result <= LOW_MAX:
        return "Low", 0
    if result <= MEDIUM_MAX:
        return "Medium", 1
    return "High", 2


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_date(value: str | None) -> str:
    parsed = _parse_datetime(value)
    if parsed:
        return parsed.date().isoformat()
    if not value:
        return "unknown"
    return value.split("T", 1)[0]


def _is_allowed_site(name: str | None) -> bool:
    if not name:
        return False
    stripped = name.strip()
    return stripped.startswith(SITE_PREFIX_WHITELIST)


def _format_site_cell(name: str, site_id: str | None) -> str:
    escaped = html.escape(name)
    if not site_id:
        return escaped
    url = f"{REPORT_BASE_URL}/{html.escape(site_id)}"
    return f'<a href="{url}">{escaped}</a>'


def scrape() -> dict:
    try:
        payload = fetch_json(DATA_URL)
    except Exception as exc:  # noqa: BLE001 - keep generator resilient
        return {
            "id": "ocean_water_quality",
            "label": "Ocean Water Quality",
            "retrieved_at": now_iso(),
            "source_urls": [DATA_URL],
            "html": "<p>Water quality data unavailable.</p>",
            "error": f"Fetch failed: {exc}.",
            "stale": True,
        }

    records = payload.get("records", [])
    latest_by_site: dict[str, dict] = {}
    for record in records:
        location = record.get("location", {})
        site_name = location.get("name")
        site_id = location.get("id")
        if not _is_allowed_site(site_name):
            continue
        sample = record.get("sample", {})
        collected_at = sample.get("collectionTime")
        collected_dt = _parse_datetime(collected_at)
        if not collected_dt:
            continue
        result = sample.get("result")
        indicator, rank = _classify(result)
        site_key = str(site_name)
        existing = latest_by_site.get(site_key)
        if existing and existing["collected_dt"] >= collected_dt:
            continue
        latest_by_site[site_key] = {
            "site": site_key,
            "site_id": str(site_id) if site_id is not None else None,
            "date": _format_date(collected_at),
            "indicator": indicator,
            "rank": rank,
            "collected_dt": collected_dt,
        }

    rows = list(latest_by_site.values())

    rank_order = {"low": 0, "medium": 1, "high": 2, "unknown": 3}
    rows.sort(
        key=lambda row: (
            row["site"].lower(),
            rank_order.get(row["indicator"].lower(), 99),
        )
    )

    if rows:
        table_rows = "".join(
            "<tr>"
            f"<td>{_format_site_cell(row['site'], row['site_id'])}</td>"
            f"<td>{html.escape(row['date'])}</td>"
            f"<td class=\"bacteria-cell bacteria-{row['indicator'].lower()}\">"
            f"{html.escape(row['indicator'])}"
            "</td>"
            "</tr>"
            for row in rows
        )
        body = (
            "<table>"
            "<thead><tr><th>Site</th><th>Date</th><th>Bacteria</th></tr></thead>"
            f"<tbody>{table_rows}</tbody>"
            "</table>"
        )
        error = None
        stale = False
    else:
        body = "<p>No matching water quality records.</p>"
        error = None
        stale = False

    return {
        "id": "ocean_water_quality",
        "label": f"Ocean Water Quality (<a href=\"{REPORT_BASE_URL}\">Surfrider Foundation</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [DATA_URL, REPORT_BASE_URL],
        "html": body,
        "error": error,
        "stale": stale,
    }
