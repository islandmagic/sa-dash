import os
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

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
    "16103000",
    "16104200",  # Hanalei River at Hwy 56 Bridge
    "16097500",  # Stream
    "16094150",  # Kaloko reservoir
    "16060000",  # Wailua River
]

BASELINE_DAYS = 30
BASELINE_YEARS = 3
MIN_BASELINE_SAMPLES = 30

PARAMETER_LABELS = {
    "00065": "Level",
    "00060": "Flow",
}

INDICATOR_CLASSES = {
    "Unknown": None,
    "Normal": "status-green",
    "Elevated": "status-yellow",
    "Critical": "status-red",
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


def _fetch_daily_values(
    monitoring_location_id: str,
    start: date,
    end: date,
    parameter_code: str | None,
) -> list[float]:
    params = _with_api_key(
        {
        "f": "json",
        "lang": "en-US",
        "limit": 1000,
        "skipGeometry": "true",
        "offset": 0,
        "monitoring_location_id": f"USGS-{monitoring_location_id}",
        "time": f"{start.isoformat()}/{end.isoformat()}",
        }
    )
    url = _build_url(USGS_DAILY_URL, params)
    payload = fetch_json(url)
    values = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        if parameter_code and props.get("parameter_code") != parameter_code:
            continue
        value = props.get("value")
        if value is None:
            continue
        try:
            values.append(float(value))
        except ValueError:
            continue
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
            latest_time = _parse_time(latest.get("time"))
            baseline_samples = 0
            indicator = "Unknown"
            parameter_code = latest.get("parameter_code")

            if latest_time:
                baseline_values = []
                for year_offset in range(1, BASELINE_YEARS + 1):
                    baseline_end = (latest_time - timedelta(days=365 * year_offset)).date()
                    baseline_start = baseline_end - timedelta(days=BASELINE_DAYS)
                    baseline_values.extend(
                        _fetch_daily_values(
                            location,
                            baseline_start,
                            baseline_end,
                            parameter_code,
                        )
                    )
                baseline_samples = len(baseline_values)

                if len(baseline_values) >= MIN_BASELINE_SAMPLES:
                    p75 = _percentile(baseline_values, 0.75)
                    p95 = _percentile(baseline_values, 0.95)
                    try:
                        latest_value = (
                            float(latest.get("value"))
                            if latest.get("value") is not None
                            else None
                        )
                    except ValueError:
                        latest_value = None
                    if latest_value is not None:
                        if latest_value >= p95:
                            indicator = "Critical"
                        elif latest_value >= p75:
                            indicator = "Elevated"
                        else:
                            indicator = "Normal"

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
            latest_time = _parse_time(latest.get("time"))
            if latest_time:
                for year_offset in range(1, BASELINE_YEARS + 1):
                    baseline_end = (latest_time - timedelta(days=365 * year_offset)).date()
                    baseline_start = baseline_end - timedelta(days=BASELINE_DAYS)
                    source_urls.append(
                        _build_url(
                            USGS_DAILY_URL,
                            _with_api_key(
                                {
                                    "f": "json",
                                    "lang": "en-US",
                                    "limit": 1000,
                                    "skipGeometry": "false",
                                    "offset": 0,
                                    "monitoring_location_id": f"USGS-{location}",
                                    "time": f"{baseline_start.isoformat()}/{baseline_end.isoformat()}",
                                }
                            ),
                        )
                    )

    html_rows = []
    for item in items:
        value = item.get("value")
        unit = item.get("unit") or ""
        value_text = f"{value} {unit}".strip() if value else "unknown"
        indicator = item.get("indicator", "Unknown")
        indicator_class = INDICATOR_CLASSES.get(indicator, "")
        parameter_code = item.get("parameter_code")
        metric = PARAMETER_LABELS.get(parameter_code, parameter_code or "metric")
        samples = item.get("baseline_samples", 0)
        samples_text = str(samples) if samples else "0"
        html_rows.append(
            "<tr>"
            f"<td>{item['name']}</td>"
            f"<td>{metric}</td>"
            f"<td style=\"text-align:right;\">{value_text}</td>"
            f"<td class=\"status-cell {indicator_class}\">{indicator}</td>"
            f"<td>{item['time']}</td>"
            "</tr>"
        )

    block_html = (
        "<table>"
        "<thead><tr><th>Location</th><th>Metric</th><th>Value</th><th>Condition</th><th>Time</th></tr></thead>"
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
