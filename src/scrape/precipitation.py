import html
from datetime import date, datetime, timedelta

import httpx

from src.scrape.base import now_iso

COCORAS_MAP_URL = "https://maps.cocorahs.org/?maptype=active-stations"
DEX_STATION_URL = "https://functions-dev-dex-cocorahs-org.azurewebsites.net/api/StationHistoryReport"
DEX_PRECIP_URL = "https://dex.cocorahs.org/stations"
DEX_HEADERS = {
    "Origin": "https://dex.cocorahs.org",
    "Referer": "https://dex.cocorahs.org/",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15",
}

STATION_QUALIFIERS = {
    6: "Town",
    31: "Waiakalua",
    29: "Haena",
    24: "Wainiha",
    32: "Wainiha",
    5: "Homestead",
    19: "Homestead",
    26: "Homestead",
    41: "Town",
    39: "Town",
    9: "Airport",
}

def _format_cocorahs_date(value: date) -> tuple[str, str]:
    display = f"{value.month}/{value.day}/{value.year}"
    return display, value.isoformat()


def _fetch_station_numbers(client: httpx.Client, start: date, end: date) -> list[str]:
    start_display, _ = _format_cocorahs_date(start)
    end_display, _ = _format_cocorahs_date(end)
    params = {
        "skip": "0",
        "take": "50",
        "country": "usa",
        "state": "HI",
        "county": "KI",
        "stationstatus": "reporting",
        "lastobsdate": f"{start_display}:{end_display}",
    }
    response = client.get(DEX_STATION_URL, params=params, headers=DEX_HEADERS)
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items", [])
    return [item.get("stationNumber") for item in items if item.get("stationNumber")]


def _fetch_station_precip(client: httpx.Client, station_number: str) -> dict:
    params = {"_data": "routes/stations.$stationnumber.precip-summary"}
    url = f"{DEX_PRECIP_URL}/{station_number}/precip-summary"
    response = client.get(url, params=params, headers=DEX_HEADERS)
    response.raise_for_status()
    payload = response.json()
    return payload.get("json", {})


def _extract_gauge_for_date(json_payload: dict, target_date: date) -> str:
    chart_props = json_payload.get("chartProps", {})
    station_data = chart_props.get("stationData", {})
    daily_obs = station_data.get("dailyObs", [])
    target = target_date.isoformat()
    for obs in daily_obs:
        if obs.get("obsDate") == target:
            gauge = obs.get("gaugeCatch", {})
            return str(gauge.get("formatValue") or "0.00")
    return "—"


def _extract_72h_total(json_payload: dict, today: date) -> str:
    chart_props = json_payload.get("chartProps", {})
    station_data = chart_props.get("stationData", {})
    daily_obs = station_data.get("dailyObs", [])
    targets = {today - timedelta(days=offset) for offset in range(3)}
    total = 0.0
    found = False
    for obs in daily_obs:
        obs_date = obs.get("obsDate")
        if not obs_date:
            continue
        try:
            parsed = datetime.strptime(obs_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if parsed not in targets:
            continue
        gauge = obs.get("gaugeCatch", {})
        value = gauge.get("precipValue")
        if value is None:
            continue
        try:
            total += float(value)
            found = True
        except (TypeError, ValueError):
            continue
    return f"{total:.2f}" if found else "—"


def _month_key(value: date) -> str:
    return f"{value.year}{value.month:02d}"


def _extract_month_totals(json_payload: dict, today: date) -> tuple[str, str]:
    current_key = _month_key(today)
    prev_month = (today.replace(day=1) - timedelta(days=1))
    prev_key = _month_key(prev_month)
    monthly = json_payload.get("monthlyData", [])
    current_total = "—"
    prev_total = "—"
    for entry in monthly:
        month_key = str(entry.get("monthYearSort") or "")
        total = entry.get("totalPrecip")
        if total is None:
            continue
        total_str = f"{float(total):.2f}"
        if month_key == current_key:
            current_total = total_str
        elif month_key == prev_key:
            prev_total = total_str
    return current_total, prev_total


def _qualified_station_name(station_name: str, station_number: str) -> str:
    try:
        suffix = int(station_number.split("-")[-1])
    except (ValueError, IndexError):
        return station_name
    qualifier = STATION_QUALIFIERS.get(suffix)
    if not qualifier:
        return station_name
    return f"{station_name} ({qualifier})"


def _build_precip_table(today: date) -> str:
    yesterday = today - timedelta(days=1)
    range_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    try:
        with httpx.Client(timeout=20.0) as client:
            station_numbers = _fetch_station_numbers(client, range_start, today)
            rows = []
            for station_number in station_numbers:
                json_payload = _fetch_station_precip(client, station_number)
                meta = (
                    json_payload.get("chartProps", {})
                    .get("stationData", {})
                    .get("stationMetadata", {})
                )
                base_name = meta.get("stationName") or station_number
                station_name = _qualified_station_name(base_name, station_number)
                month_current, month_prev = _extract_month_totals(json_payload, today)
                rows.append(
                    {
                        "station_name": station_name,
                        "station_number": station_number,
                        "yesterday": _extract_gauge_for_date(json_payload, yesterday),
                        "today": _extract_gauge_for_date(json_payload, today),
                        "last_72h": _extract_72h_total(json_payload, today),
                        "month_current": month_current,
                        "month_prev": month_prev,
                    }
                )
    except Exception:
        return "<p>Daily precipitation reports unavailable.</p>"

    if not rows:
        return "<p>No precipitation reports for Kauai stations.</p>"

    town_order = ["hanalei", "princeville", "kilauea", "kapaa", "lihue"]

    def _town_rank(name: str) -> int:
        lower = name.lower()
        for idx, town in enumerate(town_order):
            if town in lower:
                return idx
        return len(town_order)

    sorted_rows = sorted(
        rows,
        key=lambda item: (_town_rank(item["station_name"]), item["station_name"].lower()),
    )
    table_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['station_name'])}</td>"
        f"<td><a href=\"{DEX_PRECIP_URL}/{html.escape(row['station_number'])}\">"
        f"{html.escape(row['station_number'])}</a></td>"
        f"<td style=\"text-align:right;\">{html.escape(row['yesterday'])}</td>"
        f"<td style=\"text-align:right;\">{html.escape(row['today'])}</td>"
        f"<td style=\"text-align:right;\">{html.escape(row['last_72h'])}</td>"
        f"<td style=\"text-align:right;\">{html.escape(row['month_current'])}</td>"
        f"<td style=\"text-align:right;\">{html.escape(row['month_prev'])}</td>"
        "</tr>"
        for row in sorted_rows
    )
    return (
        "<table>"
        "<thead><tr><th>Location</th><th>Station ID</th><th>Yesterday (in)</th><th>Today (in)</th><th>Last 72h (in)</th><th>This Month (in)</th><th>Last Month (in)</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
    )


def scrape() -> dict:
    today = datetime.now().date()
    body = (
        "<h3>Precipitation</h3>"
        f"{_build_precip_table(today)}"
    )
    return {
        "id": "precipitation",
        "label": f"Precipitation (<a href=\"{COCORAS_MAP_URL}\">CoCoRaHS</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [DEX_STATION_URL, DEX_PRECIP_URL],
        "html": body,
        "error": None,
        "stale": False,
    }
