import html
from datetime import datetime, timedelta, timezone

from src.scrape.base import clean_text, fetch_json, now_iso
from src.hcdp.client import HCDP_BASE_URL, MesonetClient
from src.hcdp.parse import pivot_latest_measurements

POINTS_URL = "https://api.weather.gov/points/22.2,-159.42"
ALERTS_URL = "https://api.weather.gov/alerts?active=true&point=22.21%2C-159.41&limit=500"
MAP_URL = "https://forecast.weather.gov/MapClick.php?lat=22.2&lon=-159.42"
PHLI_STATION_URL = "https://api.weather.gov/stations/PHLI"
PHLI_LATEST_URL = "https://api.weather.gov/stations/PHLI/observations/latest"

HCDP_DOCS_URL = "https://hcdp.github.io/hcdp_api_docs/"
HCDP_MAP_URL = "https://www.hawaii.edu/climate-data-portal/hawaii-mesonet-data/#/data-map"
HCDP_STATION_IDS = ("0603", "0601", "0602", "0611", "0641", "0621")
HCDP_WEATHER_VAR_IDS = (
    "Tair_1_Avg",
    "RH_1_Avg",
    "Psl_hPa_1_Avg",
    "P_hPa_1_Avg",
    "P_1_Avg",
    "WS_1_Avg",
    "WDrs_1_Avg",
    "WG_1_Max",
)


def _format_temp_f(value_c: float | None) -> str:
    if value_c is None:
        return "N/A"
    try:
        temp_f = value_c * 9 / 5 + 32
        return f"{temp_f:.0f}"
    except (TypeError, ValueError):
        return "N/A"


def _pressure_indicator(inhg: float) -> str:
    if inhg < 29.53:
        return "(Low)"
    if inhg > 30.27:
        return "(High)"
    return ""


def _format_pressure_inhg(value_pa: float | None) -> str:
    if value_pa is None:
        return "N/A"
    try:
        inhg = value_pa * 0.0002953
        indicator = _pressure_indicator(inhg)
        return f"{inhg:.2f} {indicator}"
    except (TypeError, ValueError):
        return "N/A"


def _format_pressure_from_hpa(value_hpa: float | None) -> str:
    if value_hpa is None:
        return "N/A"
    try:
        inhg = float(value_hpa) * 0.02953
        indicator = _pressure_indicator(inhg)
        return f"{inhg:.2f} {indicator}".strip()
    except (TypeError, ValueError):
        return "N/A"


def _format_pressure_from_kpa(value_kpa: float | None) -> str:
    if value_kpa is None:
        return "N/A"
    try:
        inhg = float(value_kpa) * 0.2953
        indicator = _pressure_indicator(inhg)
        return f"{inhg:.2f} {indicator}".strip()
    except (TypeError, ValueError):
        return "N/A"


def _format_wind_mph(value_kmh: float | None) -> str:
    if value_kmh is None:
        return "N/A"
    try:
        mph = value_kmh * 0.621371
        return f"{mph:.0f}"
    except (TypeError, ValueError):
        return "N/A"


def _format_wind_mph_from_ms(value_ms: float | None) -> str:
    if value_ms is None:
        return "N/A"
    try:
        mph = float(value_ms) * 2.23694
        return f"{mph:.0f}"
    except (TypeError, ValueError):
        return "N/A"


def _format_humidity(value: float | None) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{value:.0f}%"
    except (TypeError, ValueError):
        return "N/A"


def _format_wind_dir(value: float | None) -> str:
    if value is None:
        return "N/A"
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    try:
        idx = int((value + 22.5) // 45) % 8
        return directions[idx]
    except (TypeError, ValueError):
        return "N/A"


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "N/A"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    hst = timezone(timedelta(hours=-10))
    return parsed.astimezone(hst).strftime("%Y-%m-%d %H:%M HST")


def _fetch_station(station_url: str, obs_url: str) -> dict | None:
    try:
        station_payload = fetch_json(station_url)
        obs_payload = fetch_json(obs_url)
    except Exception:
        return None
    station_props = station_payload.get("properties", {})
    obs_props = obs_payload.get("properties", {})
    station_name = station_props.get("name") or station_props.get("stationIdentifier") or "Station"
    station_short = station_name.split(",", 1)[0].strip() if station_name else "Station"
    station_id = station_props.get("stationIdentifier") or obs_props.get("stationId") or ""
    temp_c = obs_props.get("temperature", {}).get("value")
    pressure_pa = (
        obs_props.get("barometricPressure", {}).get("value")
        or obs_props.get("seaLevelPressure", {}).get("value")
    )
    wind_speed = obs_props.get("windSpeed", {}).get("value")
    wind_dir = obs_props.get("windDirection", {}).get("value")
    wind_gust = obs_props.get("windGust", {}).get("value")
    humidity = obs_props.get("relativeHumidity", {}).get("value")
    timestamp = obs_props.get("timestamp")
    return {
        "station": f"{station_short} ({station_id})".strip(),
        "temperature": _format_temp_f(temp_c),
        "pressure": _format_pressure_inhg(pressure_pa),
        "wind": _format_wind_mph(wind_speed),
        "wind_dir": _format_wind_dir(wind_dir),
        "wind_gust": _format_wind_mph(wind_gust),
        "humidity": _format_humidity(humidity),
        "timestamp": _format_timestamp(timestamp),
    }


def _fetch_hcdp_stations() -> list[dict]:
    client = MesonetClient()
    if not client.has_credentials:
        return []
    n_st = len(HCDP_STATION_IDS)
    n_var = len(HCDP_WEATHER_VAR_IDS)
    limit = max(n_st * n_var * 4, 120)
    try:
        raw = client.get_measurements(
            station_ids=HCDP_STATION_IDS,
            var_ids=HCDP_WEATHER_VAR_IDS,
            limit=limit,
        )
    except Exception:
        return []
    pivoted = pivot_latest_measurements(raw)
    by_id = {p["station_id"]: p for p in pivoted}
    rows = []
    for sid in HCDP_STATION_IDS:
        p = by_id.get(sid)
        if not p:
            continue
        vals = p["values"]
        label = str(p["station_name"])
        nws = p.get("nws_id")
        if nws:
            label = f"{label} ({nws})"
        else:
            label = f"{label} ({sid})"
        ts = p["timestamp"]
        ts_str = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        pressure_hpa = vals.get("Psl_hPa_1_Avg") or vals.get("P_hPa_1_Avg")
        rows.append(
            {
                "station": label,
                "temperature": _format_temp_f(vals.get("Tair_1_Avg")),
                "humidity": _format_humidity(vals.get("RH_1_Avg")),
                "pressure": (
                    _format_pressure_from_hpa(pressure_hpa)
                    if pressure_hpa is not None
                    else _format_pressure_from_kpa(vals.get("P_1_Avg"))
                ),
                "wind": _format_wind_mph_from_ms(vals.get("WS_1_Avg")),
                "wind_dir": _format_wind_dir(vals.get("WDrs_1_Avg")),
                "wind_gust": _format_wind_mph_from_ms(vals.get("WG_1_Max")),
                "timestamp": _format_timestamp(ts_str),
            }
        )
    return rows


def _build_station_block() -> str:
    stations = [
        _fetch_station(PHLI_STATION_URL, PHLI_LATEST_URL),
    ]
    stations = [station for station in stations if station]
    stations.extend(_fetch_hcdp_stations())
    if not stations:
        return "<p>Station observations unavailable.</p>"
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(station['station'])}</td>"
        f"<td>{html.escape(station['temperature'])}</td>"
        f"<td>{html.escape(station['humidity'])}</td>"
        f"<td>{html.escape(station['pressure'])}</td>"
        f"<td>{html.escape(station['wind'])}</td>"
        f"<td>{html.escape(station['wind_dir'])}</td>"
        f"<td>{html.escape(station['wind_gust'])}</td>"
        f"<td>{html.escape(station['timestamp'])}</td>"
        "</tr>"
        for station in stations
    )
    return (
        "<h3>Stations</h3>"
        "<p class=\"info\">NWS: Līhuʻe (PHLI). Mesonet: Hawaiʻi Climate Data Portal stations "
        "(5-minute averages where available).</p>"
        "<table>"
        "<thead><tr>"
        "<th></th>"
        "<th>Temp [F]</th>"
        "<th>Humidity</th>"
        "<th>Pressure [inHg]</th>"
        "<th>Wind [mph]</th>"
        "<th>Wind Dir</th>"
        "<th>Wind Gust [mph]</th>"
        "<th></th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )

def _extract_hazards_from_api(payload: dict) -> list[dict]:
    hazards = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        headline = props.get("headline") or props.get("event")
        description = props.get("description") or ""
        instruction = props.get("instruction") or ""
        if not headline:
            continue
        hazards.append(
            {
                "headline": headline,
                "description": description,
                "instruction": instruction,
            }
        )
    return hazards


def _format_precip(value) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{int(value)}%"
    except (TypeError, ValueError):
        return "N/A"


def _format_forecast_cell(period: dict) -> str:
    temp = period.get("temperature")
    temp_unit = period.get("temperatureUnit", "")
    temp_text = f"{temp} {temp_unit}".strip() if temp is not None else "N/A"
    precip = period.get("probabilityOfPrecipitation", {}).get("value")
    pop_text = _format_precip(precip)
    wind_speed = period.get("windSpeed", "")
    wind_dir = period.get("windDirection", "")
    wind_text = " ".join(part for part in [wind_speed, wind_dir] if part).strip()
    short_fcst = clean_text(period.get("shortForecast", "")) or "N/A"
    parts = [
        f"<div><strong>{html.escape(temp_text)}</strong></div>",
        f"<div>Precip: {html.escape(pop_text)}</div>",
        f"<div>Wind: {html.escape(wind_text) if wind_text else 'N/A'}</div>",
        f"<div>{html.escape(short_fcst)}</div>",
    ]
    return "".join(parts)


def scrape() -> dict:
    points_payload = fetch_json(POINTS_URL)
    points_props = points_payload.get("properties", {})
    forecast_url = points_props.get("forecast")
    location = points_props.get("relativeLocation", {}).get("properties", {})
    location_name = location.get("city", "Kilauea")
    if not forecast_url:
        raise RuntimeError("NWS points response missing forecast URL.")

    forecast_payload = fetch_json(forecast_url)
    periods = forecast_payload.get("properties", {}).get("periods", [])
    day_periods = [p for p in periods if p.get("isDaytime")]
    rows = []
    for day in day_periods[:3]:
        day_name = clean_text(day.get("name", "")) or "Day"
        if day_name in {"This Afternoon", "This Evening"}:
            day_name = "Today"
        night = None
        try:
            day_index = periods.index(day)
        except ValueError:
            day_index = -1
        if day_index >= 0:
            night = next(
                (p for p in periods[day_index + 1 :] if not p.get("isDaytime")),
                None,
            )
        rows.append((day_name, day, night))

    table_rows = "".join(
        "<tr>"
        f"<th>{html.escape(day_name)}</th>"
        f"<td>{_format_forecast_cell(day_period)}</td>"
        f"<td>{_format_forecast_cell(night_period) if night_period else 'N/A'}</td>"
        "</tr>"
        for day_name, day_period, night_period in rows
    )

    try:
        alerts_payload = fetch_json(ALERTS_URL)
    except Exception:
        alerts_payload = {}
    hazards = _extract_hazards_from_api(alerts_payload)
    hazard_items = []
    for hazard in hazards:
        description = hazard.get("description", "")
        instruction = hazard.get("instruction", "")
        summary_parts = [description, instruction]
        summary = "\n\n".join([part for part in summary_parts if part])
        summary_html = html.escape(summary).replace("\n", "<br>")
        headline_html = html.escape(hazard["headline"])
        if summary:
            hazard_items.append(
                "<details>"
                f"<summary>{headline_html}</summary>"
                f"<div>{summary_html}</div>"
                "</details>"
            )
        else:
            hazard_items.append(headline_html)

    hazard_html = (
        "".join(hazard_items)
        if hazard_items
        else "<p>No active hazards.</p>"
    )

    station_html = _build_station_block()
    block_html = (
        f"<h3>Forecast ({html.escape(location_name)})</h3>"
        "<table>"
        "<thead><tr><th></th><th>Day</th><th>Night</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
        f"{station_html}"
        "<h3>Hazards</h3>"
        f"{hazard_html}"
    )

    return {
        "id": "weather_kauai",
        "label": f'Weather (<a href="{MAP_URL}">NWS</a>, <a href="{HCDP_MAP_URL}">HCDP Mesonet</a>)',
        "retrieved_at": now_iso(),
        "source_urls": [
            POINTS_URL,
            forecast_url,
            ALERTS_URL,
            PHLI_STATION_URL,
            PHLI_LATEST_URL,
            HCDP_BASE_URL + "/mesonet/db/measurements",
            HCDP_DOCS_URL,
        ],
        "html": block_html,
        "error": None,
        "stale": False,
    }
