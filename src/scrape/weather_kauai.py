import html
import re

from src.scrape.base import clean_text, fetch_json, now_iso


POINTS_URL = "https://api.weather.gov/points/22.2,-159.42"
ALERTS_URL = "https://api.weather.gov/alerts?active=true&point=22.21%2C-159.41&limit=500"
MAP_URL = "https://forecast.weather.gov/MapClick.php?lat=22.2&lon=-159.42"

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

    block_html = (
        "<table>"
        "<thead><tr><th></th><th>Day</th><th>Night</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
        "<h3>Hazards</h3>"
        f"{hazard_html}"
    )

    return {
        "id": "weather_kauai",
        "label": f"Weather (<a href=\"{MAP_URL}\">NWS {html.escape(location_name)}</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [POINTS_URL, forecast_url, ALERTS_URL],
        "html": block_html,
        "error": None,
        "stale": False,
    }
