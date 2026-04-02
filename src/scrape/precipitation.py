import html
from datetime import date, datetime, timedelta

import httpx

from src.hcdp.client import HCDP_BASE_URL, MesonetClient
from src.hcdp.parse import pivot_latest_measurements
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

HCDP_DOCS_URL = "https://hcdp.github.io/hcdp_api_docs/"
HCDP_STATION_IDS = ("0603", "0601", "0602", "0611", "0641", "0621")
HCDP_RAIN_VAR_ID = "RF_1_Tot300s"  # 5-minute total rainfall, mm

# Compact labels (also used in weather module)
HCDP_STATION_NAMES = {
    "0603": "Lower Limahuli",
    "0601": "Waipa",
    "0602": "Common Ground",
    "0611": "Kealia",
    "0641": "Hanamaulu",
    "0621": "Lawai NTBG",
}


def _mm_to_inches(value_mm: float | None) -> str:
    if value_mm is None:
        return "—"
    try:
        inches = float(value_mm) / 25.4
        return f"{inches:.2f}"
    except (TypeError, ValueError):
        return "—"


def _sum_mm(values: list[float]) -> float:
    total = 0.0
    for v in values:
        try:
            total += float(v)
        except (TypeError, ValueError):
            continue
    return total


def _build_mesonet_rain_table() -> str:
    # HCDP endpoint can intermittently 504; fail fast so the whole module renders.
    client = MesonetClient(timeout=20.0)
    if not client.has_credentials:
        return (
            "<p class=\"info\">Mesonet rainfall is available when <code>HCDP_API_KEY</code> is set.</p>"
        )

    # Rolling window totals (RF_1_Tot3600s / RF_1_Tot86400s) were not available in measurements
    # for Kauai stations; compute closest match by summing the 5-minute totals.
    from datetime import timezone

    now_utc = datetime.now(tz=timezone.utc)
    start_utc = now_utc - timedelta(hours=24, minutes=15)
    start_date = start_utc.isoformat(timespec="seconds").replace("+00:00", "Z")

    try:
        raw = client.get_measurements(
            station_ids=HCDP_STATION_IDS,
            var_ids=(HCDP_RAIN_VAR_ID,),
            start_date=start_date,
            limit=8000,
            join_metadata=False,
        )
    except Exception as exc:
        return f"<p>Mesonet rainfall unavailable: {html.escape(str(exc))}</p>"

    # Group 5-min totals by station and time.
    by_station: dict[str, list[tuple[datetime, float]]] = {}
    for row in raw:
        if row.get("variable") != HCDP_RAIN_VAR_ID:
            continue
        sid = str(row.get("station_id") or "").strip()
        if not sid:
            continue
        ts_raw = str(row.get("timestamp") or "").strip()
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        try:
            v = float(str(row.get("value") or "").strip())
        except (TypeError, ValueError):
            continue
        by_station.setdefault(sid, []).append((ts, v))

    rows_html = []
    for sid in HCDP_STATION_IDS:
        series = by_station.get(sid, [])
        if not series:
            continue
        # Compute last 1h and last 24h based on timestamps.
        series.sort(key=lambda x: x[0], reverse=True)
        cutoff_1h = now_utc - timedelta(hours=1)
        cutoff_24h = now_utc - timedelta(hours=24)
        mm_1h = _sum_mm([v for ts, v in series if ts >= cutoff_1h])
        mm_24h = _sum_mm([v for ts, v in series if ts >= cutoff_24h])
        name = html.escape(HCDP_STATION_NAMES.get(sid, sid))
        last_1h = _mm_to_inches(mm_1h)
        last_24h = _mm_to_inches(mm_24h)
        rows_html.append(
            "<tr>"
            f"<td>{name}</td>"
            f"<td style=\"text-align:right;\">{html.escape(last_1h)}</td>"
            f"<td style=\"text-align:right;\">{html.escape(last_24h)}</td>"
            "</tr>"
        )

    if not rows_html:
        return "<p>No Mesonet rainfall values for configured stations.</p>"

    return (
        "<table>"
        "<thead><tr><th>Station</th><th>Last 1h [in]</th><th>Last 24h [in]</th></tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )


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
                        "today": _extract_gauge_for_date(json_payload, today),
                        "yesterday": _extract_gauge_for_date(json_payload, yesterday),
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
        f"<td style=\"text-align:right;\">{html.escape(row['today'])}</td>"
        f"<td style=\"text-align:right;\">{html.escape(row['yesterday'])}</td>"
        f"<td style=\"text-align:right;\">{html.escape(row['last_72h'])}</td>"
        f"<td style=\"text-align:right;\">{html.escape(row['month_current'])}</td>"
        f"<td style=\"text-align:right;\">{html.escape(row['month_prev'])}</td>"
        "</tr>"
        for row in sorted_rows
    )
    prev_month = today.replace(day=1) - timedelta(days=1)
    prev_label = prev_month.strftime("%B")
    return (
        "<table>"
        "<thead><tr><th>Location</th><th>Station ID</th><th>Today [in]</th><th>Yesterday [in]</th><th>Last 72h [in]</th><th>This Month [in]</th>"
        f"<th>{html.escape(prev_label)} [in]</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
    )


def scrape() -> dict:
    today = datetime.now().date()
    body = (
        "<h3>Precipitation</h3>"
        f"{_build_precip_table(today)}"
        "<h3>Mesonet rainfall</h3>"
        f"{_build_mesonet_rain_table()}"
    )
    return {
        "id": "precipitation",
        "label": (
            f'Precipitation (<a href="{COCORAS_MAP_URL}">CoCoRaHS</a>, '
            f'<a href="{HCDP_DOCS_URL}">HCDP Mesonet</a>)'
        ),
        "retrieved_at": now_iso(),
        "source_urls": [
            DEX_STATION_URL,
            DEX_PRECIP_URL,
            HCDP_BASE_URL + "/mesonet/db/measurements",
            HCDP_DOCS_URL,
        ],
        "html": body,
        "error": None,
        "stale": False,
    }
