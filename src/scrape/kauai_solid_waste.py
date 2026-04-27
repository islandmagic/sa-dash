import html as html_module
import re
import unicodedata

from bs4 import BeautifulSoup

from src.scrape.base import clean_text, fetch_html, now_iso


STATUS_URL = (
    "https://www.kauai.gov/Government/Departments-Agencies/Public-Works/"
    "Solid-Waste/Landfill-Refuse-Transfer-Station-Status"
)
TRANSFER_STATIONS_URL = (
    "https://www.kauai.gov/Government/Departments-Agencies/Public-Works/"
    "Solid-Waste/Transfer-Stations"
)
GREEN_WASTE_URL = (
    "https://www.kauai.gov/Government/Departments-Agencies/Public-Works/"
    "Solid-Waste/Recycling/Green-Waste"
)

LOCATIONS = [
    "Hanalei Refuse Transfer Station",
    "Hanapēpē Refuse Transfer Station",
    "Kapaʻa Refuse Transfer Station",
    "Kekaha Landfill",
    "Līhuʻe Refuse Transfer Station",
    "Residential Route Delays",
]


def _norm_key(text: str) -> str:
    """
    Normalize for matching headings that may vary in Unicode composition
    (e.g. precomposed ē vs e + combining macron, okina/apostrophe variants).
    """
    text = clean_text(text).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("ʻ", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _find_results_container(soup: BeautifulSoup):
    marker = soup.find(string=re.compile(r"Result\(s\) Found", re.I))
    if not marker:
        return None
    return marker.find_parent("div") or marker.parent


def _extract_status_text(h2) -> str:
    parts: list[str] = []
    for el in h2.next_elements:
        if getattr(el, "name", None) == "h2":
            break
        if getattr(el, "name", None) not in {"p", "div", "span", "li"}:
            continue
        txt = clean_text(el.get_text(" "))
        if not txt or txt == ".":
            continue
        parts.append(txt)
        if len(parts) >= 2:
            break

    if not parts:
        return ""

    status = parts[0]
    status = re.sub(r"^\s*\.\s*", "", status)
    status = re.sub(r"^\s*Announcement\s*:\s*", "", status, flags=re.I)

    # Sometimes the first captured string can include the next header text;
    # keep it concise by cutting at the first known location name.
    for loc in LOCATIONS:
        if loc != h2.get_text(" ", strip=True) and loc in status:
            status = status.split(loc, 1)[0].strip()
            break

    return status.strip()


def _extract_statuses(page_html: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "lxml")
    container = _find_results_container(soup) or soup

    rows: list[dict] = []
    location_map = {_norm_key(loc): loc for loc in LOCATIONS}
    # The "Result(s) Found" marker lives in a container that precedes the actual
    # facility headings, so we need to walk forward in document order.
    for h2 in container.find_all_next("h2"):
        raw_name = h2.get_text(" ")
        if _norm_key(raw_name) == _norm_key("Search Works & Projects"):
            break
        name_norm = _norm_key(raw_name)
        canonical = location_map.get(name_norm)
        if not canonical:
            continue
        rows.append(
            {
                "location": canonical,
                "status": _extract_status_text(h2) or "Status unavailable.",
            }
        )
    return rows


def _extract_hours(transfer_html: str, green_waste_html: str) -> dict[str, str]:
    transfer_text = " ".join(BeautifulSoup(transfer_html, "lxml").stripped_strings)
    green_text = " ".join(BeautifulSoup(green_waste_html, "lxml").stripped_strings)

    rts_hours = None
    hanalei_green_note = None
    m = re.search(
        r"Operating hours are\s+([^()\.]+?)(?:\s*\(([^)]+)\))?\.",
        transfer_text,
        flags=re.I,
    )
    if m:
        rts_hours = clean_text(m.group(1))
        if m.group(2):
            hanalei_green_note = clean_text(m.group(2))

    kekaha_hours = None
    m = re.search(r"Kekaha Landfill hours:\s*([^\.]+)\.", green_text, flags=re.I)
    if m:
        kekaha_hours = clean_text(m.group(1))

    # Reasonable fallbacks if the County text shifts.
    rts_hours = rts_hours or "7:15 am to 3:15 pm, 7 days a week except for County holidays"
    kekaha_hours = kekaha_hours or "8 am to 4 pm (closed for lunch from 12 pm to 12:30 pm)"
    hanalei_green_note = hanalei_green_note or "Hanalei green waste hours: 8:00 am to 3:00 pm"

    return {
        "Hanalei Refuse Transfer Station": f"{rts_hours} ({hanalei_green_note})",
        "Hanapēpē Refuse Transfer Station": rts_hours,
        "Kapaʻa Refuse Transfer Station": rts_hours,
        "Līhuʻe Refuse Transfer Station": rts_hours,
        "Kekaha Landfill": kekaha_hours,
        "Residential Route Delays": "N/A",
    }


def scrape() -> dict:
    try:
        status_html = fetch_html(STATUS_URL)
        transfer_html = fetch_html(TRANSFER_STATIONS_URL)
        green_waste_html = fetch_html(GREEN_WASTE_URL)
    except Exception as exc:
        return {
            "id": "kauai_solid_waste",
            "label": "Solid Waste (Kauai County)",
            "retrieved_at": now_iso(),
            "source_urls": [STATUS_URL, TRANSFER_STATIONS_URL, GREEN_WASTE_URL],
            "html": f"<p>{html_module.escape(str(exc))}</p>",
            "error": str(exc),
            "stale": True,
            "layout": "full",
        }

    rows = _extract_statuses(status_html)
    hours_by_location = _extract_hours(transfer_html, green_waste_html)

    def display_location(name: str) -> str:
        return name.replace("Refuse Transfer Station", "RTS")

    table_rows = "".join(
        "<tr>"
        f"<td>{html_module.escape(display_location(r['location']))}</td>"
        f"<td>{html_module.escape(r['status'])}</td>"
        f"<td class=\"solid-waste-hours\">{html_module.escape(hours_by_location.get(r['location'], ''))}</td>"
        "</tr>"
        for r in rows
    )

    css = """
.solid-waste-table { border-collapse: collapse; width: 100%; }
.solid-waste-table th, .solid-waste-table td { padding: 0.35rem 0.5rem; vertical-align: top; }
.solid-waste-table th:first-child,
.solid-waste-table td:first-child { width: 20%; min-width: 10rem; }
.solid-waste-table td.solid-waste-hours { white-space: nowrap; }
.solid-waste-table tbody tr + tr td { border-top: 1px solid rgba(0,0,0,0.08); }
"""

    body = (
        "<style>" + css + "</style>"
        "<table class=\"solid-waste-table\">"
        "<thead><tr><th>Location</th><th>Status</th><th>Hours</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
    )

    return {
        "id": "kauai_solid_waste",
        "label": f"Solid Waste (<a href=\"{STATUS_URL}\">Kauai County</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [STATUS_URL, TRANSFER_STATIONS_URL, GREEN_WASTE_URL],
        "html": body,
        "error": None,
        "stale": False,
        "layout": "full",
    }

