import os
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from src.scrape.base import fetch_json, now_iso

USGS_URL = "https://waterdata.usgs.gov/state/Hawaii/"
USGS_API_KEY = os.getenv("USGS_API_KEY", "")
USGS_LATEST_URL = (
    "https://api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous/items"
)
USGS_LOCATION_URL = (
    "https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items"
)
USGS_DAILY_URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items"

USGS_LOCATIONS = [
    "16103000",  # Hanalei River 
    "16104200",  # Hanalei River at Hwy 56 Bridge
    "16097500",  # Kilauea Stream
    "16094150",  # Kaloko reservoir
    "16060000",  # Wailua River
]

BASELINE_YEARS = 15
WINDOW_DAYS = 15
MIN_BASELINE_SAMPLES = 100

FLOW_CODE = "00060"
LEVEL_CODES = {"00065"}
# Sites where the level reading is representative enough to classify/report.
LEVEL_CONDITION_LOCATIONS = {"16104200", "16094150"}
DAILY_MEAN_STAT = "00003"

PARAMETER_LABELS = {
    "00065": "Level",
    "00060": "Flow",
}

CONDITION_CLASSES = {
    "High": "status-red",
    "Much above normal": "status-yellow",
    "Above normal": "",
    "Normal": "status-green",
    "Below normal": "status-green",
    "Low": "status-green",
    "Unknown": "",
}

FLOOD_THRESHOLDS_FT = {
    "16104200": {"minor": 7.3},
    "16060000": {"minor": 15.0, "major": 22.9},
    "16097500": {"minor": 7.0, "major": 10.2},
    "16103000": {"minor": 5.0, "major": 15.8},
}

FLOOD_CLASSES = {
    "Minor": "status-yellow",
    "Major": "status-red",
}


def _format_time_hst(time_str: str | None) -> str:
    if not time_str:
        return "unknown"
    if time_str.endswith("Z"):
        time_str = time_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(time_str)
    hst = timezone(timedelta(hours=-10))
    dt = dt.astimezone(hst)
    return dt.strftime("%Y-%m-%d %H:%M HST")


def _build_url(base: str, params: dict) -> str:
    return f"{base}?{urlencode(params)}"


def _with_api_key(params: dict) -> dict:
    if USGS_API_KEY:
        return {**params, "api_key": USGS_API_KEY}
    return params


def _parse_time(time_str: str | None) -> datetime | None:
    if not time_str:
        return None
    if time_str.endswith("Z"):
        time_str = time_str.replace("Z", "+00:00")
    return datetime.fromisoformat(time_str)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    position = (len(sorted_vals) - 1) * pct
    lower = int(position)
    upper = min(lower + 1, len(sorted_vals) - 1)
    weight = position - lower
    return sorted_vals[lower] + (sorted_vals[upper] - sorted_vals[lower]) * weight


def _flood_status(location_id: str, value: float | None) -> str | None:
    if value is None:
        return None
    thresholds = FLOOD_THRESHOLDS_FT.get(location_id)
    if not thresholds:
        return None
    major = thresholds.get("major")
    minor = thresholds.get("minor")
    if major is not None and value >= major:
        return "Major"
    if minor is not None and value >= minor:
        return "Minor"
    return None


def _should_classify(location_id: str, parameter_code: str | None) -> bool:
    if parameter_code == FLOW_CODE:
        return True
    return parameter_code in LEVEL_CODES and location_id in LEVEL_CONDITION_LOCATIONS


def _should_omit_row(location_id: str, parameter_code: str | None) -> bool:
    """Level readings at sites where the datum is not representative are dropped."""
    return parameter_code in LEVEL_CODES and location_id not in LEVEL_CONDITION_LOCATIONS


def _classify_percentile(value: float | None, pcts: dict[str, float]) -> str:
    if value is None:
        return "Unknown"
    if value >= pcts["p98"]:
        return "High"
    if value >= pcts["p90"]:
        return "Much above normal"
    if value >= pcts["p75"]:
        return "Above normal"
    if value >= pcts["p25"]:
        return "Normal"
    if value >= pcts["p10"]:
        return "Below normal"
    return "Low"


def _fetch_json_retry(url: str, attempts: int = 4, base_delay: float = 1.5) -> dict:
    """fetch_json with exponential backoff on HTTP 429 (rate limiting)."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return fetch_json(url)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 429 and attempt < attempts - 1:
                last_exc = exc
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable")


def _daily_series_url(
    monitoring_location_id: str,
    start: date,
    end: date,
    parameter_code: str | None,
    offset: int = 0,
    limit: int = 10000,
    skip_geometry: bool = True,
) -> str:
    query = {
        "f": "json",
        "lang": "en-US",
        "limit": limit,
        "skipGeometry": "true" if skip_geometry else "false",
        "offset": offset,
        "monitoring_location_id": f"USGS-{monitoring_location_id}",
        "statistic_id": DAILY_MEAN_STAT,
        "time": f"{start.isoformat()}/{end.isoformat()}",
    }
    if parameter_code:
        query["parameter_code"] = parameter_code
    return _build_url(USGS_DAILY_URL, _with_api_key(query))


def _fetch_daily_mean_series(
    monitoring_location_id: str,
    start: date,
    end: date,
    parameter_code: str | None,
    page: int = 10000,
) -> list[tuple[date, float]]:
    """Fetch the full daily-mean series for a gage/parameter in as few requests as possible.

    Uses numberMatched for pagination so a server-capped page size does not cause an
    early break. Most gages fit in a single request.
    """
    series: list[tuple[date, float]] = []
    offset = 0
    total: int | None = None
    while True:
        url = _daily_series_url(
            monitoring_location_id, start, end, parameter_code, offset=offset, limit=page
        )
        payload = _fetch_json_retry(url)
        if total is None:
            total = payload.get("numberMatched")
        features = payload.get("features", [])
        for feature in features:
            props = feature.get("properties", {})
            if parameter_code and props.get("parameter_code") != parameter_code:
                continue
            if props.get("statistic_id") != DAILY_MEAN_STAT:
                continue
            value = props.get("value")
            if value is None:
                continue
            try:
                day = date.fromisoformat(str(props.get("time"))[:10])
                series.append((day, float(value)))
            except (ValueError, TypeError):
                continue
        offset += len(features)
        if not features:
            break
        if total is not None and offset >= total:
            break
        if total is None and len(features) < page:
            break
    return series


def _doy_window_values(
    series: list[tuple[date, float]], target: date, window_days: int
) -> list[float]:
    """Values whose day-of-year is within +/- window_days of the target (wraps year end)."""
    target_doy = target.timetuple().tm_yday
    values: list[float] = []
    for day, value in series:
        doy = day.timetuple().tm_yday
        diff = abs(doy - target_doy)
        diff = min(diff, 365 - diff)
        if diff <= window_days:
            values.append(value)
    return values


def _fetch_location_name(monitoring_location_number: str) -> str:
    params = _with_api_key(
        {
        "f": "json",
        "lang": "en-US",
        "limit": 1,
        "skipGeometry": "true",
        "offset": 0,
        "monitoring_location_number": monitoring_location_number,
        }
    )
    url = _build_url(USGS_LOCATION_URL, params)
    payload = fetch_json(url)
    features = payload.get("features", [])
    if not features:
        return monitoring_location_number
    props = features[0].get("properties", {})
    name = props.get("monitoring_location_name") or monitoring_location_number
    short = name.split(",")[0].strip()
    return short


def _fetch_latest_values(monitoring_location_id: str) -> list[dict]:
    params = _with_api_key(
        {
        "f": "json",
        "monitoring_location_id": f"USGS-{monitoring_location_id}",
        }
    )
    url = _build_url(USGS_LATEST_URL, params)
    payload = fetch_json(url)
    features = payload.get("features", [])
    if not features:
        return []
    items = []
    for feature in features:
        props = feature.get("properties", {})
        items.append(
            {
                "time": props.get("time"),
                "value": props.get("value"),
                "unit": props.get("unit_of_measure"),
                "approval": props.get("approval_status"),
                "parameter_code": props.get("parameter_code"),
                "statistic_id": props.get("statistic_id"),
            }
        )
    return items


def scrape() -> dict:
    items = []
    source_urls = []
    for location in USGS_LOCATIONS:
        name = _fetch_location_name(location)
        latest_values = _fetch_latest_values(location)

        for latest in latest_values:
            parameter_code = latest.get("parameter_code")
            if _should_omit_row(location, parameter_code):
                continue

            latest_time = _parse_time(latest.get("time"))
            baseline_samples = 0
            indicator = "Unknown"

            try:
                latest_value = (
                    float(latest.get("value"))
                    if latest.get("value") is not None
                    else None
                )
            except (TypeError, ValueError):
                latest_value = None

            if latest_time and _should_classify(location, parameter_code):
                series_start = (
                    latest_time - timedelta(days=365 * BASELINE_YEARS + WINDOW_DAYS)
                ).date()
                series_end = latest_time.date()
                series = _fetch_daily_mean_series(
                    location, series_start, series_end, parameter_code
                )
                baseline_values = _doy_window_values(
                    series, latest_time.date(), WINDOW_DAYS
                )
                baseline_samples = len(baseline_values)

                if baseline_samples >= MIN_BASELINE_SAMPLES and latest_value is not None:
                    pcts = {
                        "p10": _percentile(baseline_values, 0.10),
                        "p25": _percentile(baseline_values, 0.25),
                        "p75": _percentile(baseline_values, 0.75),
                        "p90": _percentile(baseline_values, 0.90),
                        "p98": _percentile(baseline_values, 0.98),
                    }
                    indicator = _classify_percentile(latest_value, pcts)

            flood_status = None
            if parameter_code in LEVEL_CODES:
                flood_status = _flood_status(location, latest_value)

            items.append(
                {
                    "name": name,
                    "time": _format_time_hst(latest.get("time")),
                    "value": latest.get("value"),
                    "unit": latest.get("unit"),
                    "approval": latest.get("approval"),
                    "location_id": location,
                    "parameter_code": parameter_code,
                    "indicator": indicator,
                    "baseline_samples": baseline_samples,
                    "flood_status": flood_status,
                }
            )

        source_urls.append(
            _build_url(
                USGS_LOCATION_URL,
                _with_api_key(
                    {
                        "f": "json",
                        "lang": "en-US",
                        "limit": 1,
                        "skipGeometry": "false",
                        "offset": 0,
                        "monitoring_location_number": location,
                    }
                ),
            )
        )
        source_urls.append(
            _build_url(
                USGS_LATEST_URL,
                _with_api_key(
                    {
                        "f": "json",
                        "monitoring_location_id": f"USGS-{location}",
                    }
                ),
            )
        )
        for latest in latest_values:
            parameter_code = latest.get("parameter_code")
            if not _should_classify(location, parameter_code):
                continue
            latest_time = _parse_time(latest.get("time"))
            if latest_time:
                series_start = (
                    latest_time - timedelta(days=365 * BASELINE_YEARS + WINDOW_DAYS)
                ).date()
                series_end = latest_time.date()
                source_urls.append(
                    _daily_series_url(
                        location,
                        series_start,
                        series_end,
                        parameter_code,
                        skip_geometry=False,
                    )
                )

    html_rows = []
    for item in items:
        value = item.get("value")
        unit = item.get("unit") or ""
        value_text = f"{value} {unit}".strip() if value else "unknown"
        indicator = item.get("indicator", "Unknown")
        indicator_class = CONDITION_CLASSES.get(indicator, "")
        indicator_text = "—" if indicator == "Unknown" else indicator
        parameter_code = item.get("parameter_code")
        metric = PARAMETER_LABELS.get(parameter_code, parameter_code or "metric")
        flood_status = item.get("flood_status")
        flood_class = FLOOD_CLASSES.get(flood_status, "")
        flood_text = flood_status or "—"
        html_rows.append(
            "<tr>"
            f"<td>{item['name']}</td>"
            f"<td>{metric}</td>"
            f"<td style=\"text-align:right;\">{value_text}</td>"
            f"<td class=\"status-cell {indicator_class}\">{indicator_text}</td>"
            f"<td class=\"status-cell {flood_class}\">{flood_text}</td>"
            f"<td>{item['time']}</td>"
            "</tr>"
        )

    info_html = (
        "<p class=\"info\">Condition compares the latest reading to USGS WaterWatch-style percentiles of daily mean values for this time of year (period of record): "
        "Normal (25th–75th), Above normal (75th–90th), Much above normal (90th–98th), and High (≥98th percentile). "
        "Streamflow is shown for all gages; river and reservoir level is shown only where the datum is representative. "
        "Flood indicators for river level are based on USGS/NWS site-specific thresholds.</p>"
    )
    block_html = (
        f"{info_html}"
        "<table>"
        "<thead><tr><th>Location</th><th>Metric</th><th>Value</th><th>Condition</th><th>Flood</th><th>Time</th></tr></thead>"
        f"<tbody>{''.join(html_rows)}</tbody>"
        "</table>"
    )
    return {
        "id": "usgs_water_levels",
        "label": f"Rivers &amp; Reservoirs (<a href=\"{USGS_URL}\">USGS</a>)",
        "retrieved_at": now_iso(),
        "source_urls": source_urls,
        "html": block_html,
        "error": None,
        "stale": False,
    }
