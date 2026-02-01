import html
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import httpx

from src.scrape.base import clean_text, now_iso


COCORAS_URL = "https://www.cocorahs.org/ViewData/ListDailyPrecipReports.aspx"
COCORAS_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.cocorahs.org",
    "Referer": "https://www.cocorahs.org/ViewData/ListDailyPrecipReports.aspx",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15",
}
COCORAS_COOKIES = {"statecodekey": "15", "unitscodekey": "usunits"}
COCORAS_STATION_URL = "https://dex.cocorahs.org/stations"


def _format_cocorahs_date(value: date) -> tuple[str, str]:
    display = f"{value.month}/{value.day}/{value.year}"
    return display, value.isoformat()


def _parse_cocorahs_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def _build_cocorahs_form(start: date, end: date, hidden: dict[str, str]) -> dict:
    start_display, start_iso = _format_cocorahs_date(start)
    end_display, end_iso = _format_cocorahs_date(end)
    return {
        **hidden,
        "__EVENTTARGET": hidden.get("__EVENTTARGET", ""),
        "__EVENTARGUMENT": hidden.get("__EVENTARGUMENT", ""),
        "__LASTFOCUS": hidden.get("__LASTFOCUS", ""),
        "VAM_Group": hidden.get("VAM_Group", ""),
        "VAM_JSE": hidden.get("VAM_JSE", "1"),
        "obsSwitcher:ddlObsUnits": "usunits",
        "frmPrecipReportSearch:ucStationTextFieldsFilter:tbTextFieldValue": "",
        "frmPrecipReportSearch:ucStateCountyFilter:ddlCountry": "840",
        "frmPrecipReportSearch:ucStateCountyFilter:ddlState": "15",
        "frmPrecipReportSearch:ucStateCountyFilter:ddlCounty": "7",
        "frmPrecipReportSearch:ucDateRangeFilter:dcStartDate:di": start_display,
        "frmPrecipReportSearch:ucDateRangeFilter:dcStartDate:hfDate": start_iso,
        "frmPrecipReportSearch:ucDateRangeFilter:dcEndDate:di": end_display,
        "frmPrecipReportSearch:ucDateRangeFilter:dcEndDate:hfDate": end_iso,
        "frmPrecipReportSearch:ddlPrecipField": "",
        "frmPrecipReportSearch:ucPrecipValueFilter:ddlOperator": "GreaterThan",
        "frmPrecipReportSearch:ucPrecipValueFilter:tbPrecipValue:tbPrecip": "",
        "frmPrecipReportSearch:btnSearch": "Search",
    }


def _fetch_cocorahs_rows(start: date, end: date) -> list[dict]:
    with httpx.Client(timeout=20.0, cookies=COCORAS_COOKIES) as client:
        landing = client.get(COCORAS_URL)
        landing.raise_for_status()
        hidden = _extract_hidden_fields(landing.text)
        form = _build_cocorahs_form(start, end, hidden)
        encoded = urlencode(form)
        response = client.post(COCORAS_URL, content=encoded, headers=COCORAS_HEADERS)
        response.raise_for_status()
        html_text = response.text

    rows = []
    for match in re.finditer(r"<tr[^>]*>(.*?)</tr>", html_text, re.DOTALL | re.IGNORECASE):
        row_html = match.group(1)
        if "ReportGrid" not in row_html and "DailyPrecipReportID" not in row_html:
            continue
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.DOTALL | re.IGNORECASE)
        if len(cells) < 5:
            continue
        obs_date = _clean_cell(cells[0])
        station_number = _clean_cell(cells[2])
        station_name = _clean_cell(cells[3])
        gauge_catch = _clean_cell(cells[4])
        if not obs_date or not station_number:
            continue
        rows.append(
            {
                "obs_date": obs_date,
                "station_number": station_number,
                "station_name": station_name,
                "gauge_catch": gauge_catch,
            }
        )
    return rows


def _extract_hidden_fields(html_text: str) -> dict[str, str]:
    hidden = {}
    for match in re.finditer(
        r'<input[^>]+type="hidden"[^>]*>',
        html_text,
        flags=re.IGNORECASE,
    ):
        tag = match.group(0)
        name_match = re.search(r'name="([^"]+)"', tag, flags=re.IGNORECASE)
        value_match = re.search(r'value="([^"]*)"', tag, flags=re.IGNORECASE)
        if not name_match:
            continue
        name = name_match.group(1)
        value = value_match.group(1) if value_match else ""
        hidden[name] = value
    return hidden


def _clean_cell(value: str) -> str:
    stripped = re.sub(r"<[^>]+>", "", value)
    return clean_text(html.unescape(stripped))


def _build_precip_table(today: date) -> str:
    yesterday = today - timedelta(days=1)
    try:
        rows = _fetch_cocorahs_rows(yesterday, today)
    except Exception:
        return "<p>Daily precipitation reports unavailable.</p>"

    bucket: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        obs_date = _parse_cocorahs_date(row["obs_date"])
        if not obs_date:
            continue
        if obs_date not in (yesterday, today):
            continue
        key = (row["station_name"], row["station_number"])
        station = bucket.setdefault(
            key,
            {"yesterday": "—", "today": "—"},
        )
        value = row["gauge_catch"] or "—"
        if obs_date == yesterday:
            station["yesterday"] = value
        else:
            station["today"] = value

    if not bucket:
        return "<p>No precipitation reports for Kauai stations.</p>"

    sorted_rows = sorted(bucket.items(), key=lambda item: item[0][0].lower())
    table_rows = "".join(
        "<tr>"
        f"<td>{html.escape(station_name)}</td>"
        f"<td><a href=\"{COCORAS_STATION_URL}/{html.escape(station_number)}\">"
        f"{html.escape(station_number)}</a></td>"
        f"<td style=\"text-align:right;\">{html.escape(values['yesterday'])}</td>"
        f"<td style=\"text-align:right;\">{html.escape(values['today'])}</td>"
        "</tr>"
        for (station_name, station_number), values in sorted_rows
    )
    return (
        "<table>"
        "<thead><tr><th>Location</th><th>Station ID</th><th>Yesterday (in)</th><th>Today (in)</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
    )


def scrape() -> dict:
    today = datetime.now().date()
    body = (
        "<h3>Daily Precipitation (CoCoRaHS)</h3>"
        f"{_build_precip_table(today)}"
    )
    return {
        "id": "precipitation",
        "label": "Precipitation",
        "retrieved_at": now_iso(),
        "source_urls": [COCORAS_URL],
        "html": body,
        "error": None,
        "stale": False,
    }
