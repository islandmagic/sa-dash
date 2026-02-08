import html
import math
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from src.scrape.base import now_iso


MARINETRAFFIC_BASE = "https://www.marinetraffic.com"
MARINETRAFFIC_TILE_URL = (
    "https://www.marinetraffic.com/getData/get_data_json_4/z:{z}/X:{x}/Y:{y}/station:0"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15"
)

KAUAI_BBOX = {
    "west": -159.95,
    "east": -159.25,
    "south": 21.80,
    "north": 22.30,
}
KAUAI_CENTER = (22.05, -159.55)
TILE_ZOOM = 10
TILE_COORD_ZOOM = 9

PORTS = {
    "Nawiliwili": (21.9569, -159.3566),
    "Port Allen": (21.8982, -159.5896),
    "Kikiaola": (22.2080, -159.6020),
}
PORT_RADIUS_NM = 2.0
PORT_SPEED_THRESHOLD = 1.0
ENROUTE_COURSE_TOLERANCE = 45.0
NM_TO_MI = 1.15078

KAUAI_PORT_KEYWORDS = ("NAWILIWILI", "PORT ALLEN", "KIKIAOLA", "KAUAI")

CATEGORY_BY_SHIPTYPE = {
    "6": "Passenger",
    "7": "Cargo",
    "8": "Tanker",
    "9": "Other",
}

SHIPTYPE_LABELS = {
    "0": "Unknown",
    "1": "Reserved",
    "2": "Wing in ground",
    "3": "Special category",
    "4": "High-speed craft",
    "5": "Pilot vessel",
    "6": "Passenger",
    "7": "Cargo",
    "8": "Tanker",
    "9": "Other",
    "10": "Fishing",
    "11": "Tug",
    "12": "Port tender",
    "13": "Anti-pollution",
    "14": "Law enforcement",
    "15": "Medical",
    "16": "Sailing",
    "17": "Pleasure craft",
    "18": "Reserved 18",
    "19": "Reserved 19",
    "20": "Service vessel",
}

KEYWORD_CATEGORIES = [
    ("Coast Guard", ("COAST GUARD", "USCG")),
    ("Barge", ("BARGE",)),
    ("Tug", ("TUG",)),
]

TUG_NAMES = ("TIGER5", "KAHU")


def _debug_enabled() -> bool:
    return os.getenv("MARINETRAFFIC_DEBUG", "").lower() in {"1", "true", "yes", "on"}


def _debug(message: str) -> None:
    if _debug_enabled():
        print(f"[marinetraffic] {message}")


def _deg2rad(value: float) -> float:
    return value * math.pi / 180.0


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_nm = 3440.065
    phi1 = _deg2rad(lat1)
    phi2 = _deg2rad(lat2)
    dphi = _deg2rad(lat2 - lat1)
    dlambda = _deg2rad(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return radius_nm * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _latlon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    lat_rad = _deg2rad(lat)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int(
        (1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi)
        / 2.0
        * n
    )
    return x, y


def _tile_range(bbox: dict[str, float], zoom: int) -> list[tuple[int, int]]:
    x_min, y_max = _latlon_to_tile(bbox["south"], bbox["west"], zoom)
    x_max, y_min = _latlon_to_tile(bbox["north"], bbox["east"], zoom)
    tiles = []
    for x in range(min(x_min, x_max), max(x_min, x_max) + 1):
        for y in range(min(y_min, y_max), max(y_min, y_max) + 1):
            tiles.append((x, y))
    return tiles


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_tile(client: httpx.Client, z: int, x: int, y: int) -> list[dict[str, Any]]:
    url = MARINETRAFFIC_TILE_URL.format(z=z, x=x, y=y)
    response = client.get(url)
    if response.status_code == 403:
        cf_ray = response.headers.get("cf-ray", "")
        server = response.headers.get("server", "")
        snippet = response.text[:200].replace("\n", " ")
        _debug(f"403 from tile {x},{y} (cf-ray={cf_ray}, server={server})")
        _debug(f"403 body snippet: {snippet}")
    response.raise_for_status()
    payload = response.json()
    return payload.get("data", {}).get("rows", [])


def _category_for_vessel(row: dict[str, Any]) -> str:
    shiptype = str(row.get("SHIPTYPE") or "").strip()
    name = str(row.get("SHIPNAME") or "").upper()
    destination = str(row.get("DESTINATION") or "").upper()
    if name in TUG_NAMES:
        return "Tug"
    for label, keywords in KEYWORD_CATEGORIES:
        if any(keyword in name or keyword in destination for keyword in keywords):
            return label
    return CATEGORY_BY_SHIPTYPE.get(shiptype, "Other")


def _port_status(lat: float, lon: float, speed: float | None, course: float | None) -> tuple[str | None, str | None]:
    nearest_port = None
    nearest_dist = None
    for name, coords in PORTS.items():
        dist = _haversine_nm(lat, lon, coords[0], coords[1])
        if nearest_dist is None or dist < nearest_dist:
            nearest_dist = dist
            nearest_port = name
    if nearest_dist is None or nearest_dist > PORT_RADIUS_NM:
        return None, None
    if speed is not None and speed <= PORT_SPEED_THRESHOLD:
        return nearest_port, "At port"
    if speed is not None and course is not None:
        heading_to_center = _bearing(lat, lon, PORTS[nearest_port][0], PORTS[nearest_port][1])
        diff = _bearing_diff(course, heading_to_center)
        if diff > 90:
            return nearest_port, "Departing"
    return nearest_port, None


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = _deg2rad(lat1)
    phi2 = _deg2rad(lat2)
    dlambda = _deg2rad(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360) % 360


def _bearing_diff(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return 360 - diff if diff > 180 else diff


def _course_to_cardinal(course: float | None) -> str:
    if course is None:
        return ""
    directions = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    idx = int((course % 360) / 22.5 + 0.5) % 16
    return directions[idx]


def _enroute_to_kauai(destination: str, course: float | None, lat: float, lon: float) -> bool:
    dest_upper = destination.upper()
    if not any(keyword in dest_upper for keyword in KAUAI_PORT_KEYWORDS):
        return False
    if course is None:
        return False
    bearing_to_kauai = _bearing(lat, lon, KAUAI_CENTER[0], KAUAI_CENTER[1])
    return _bearing_diff(course, bearing_to_kauai) <= ENROUTE_COURSE_TOLERANCE


def _distance_to_port_miles(lat: float, lon: float, destination: str) -> float:
    destination_upper = destination.upper()
    for port_name, coords in PORTS.items():
        if port_name.upper() in destination_upper:
            return _haversine_nm(lat, lon, coords[0], coords[1]) * NM_TO_MI
    nearest_dist = None
    for coords in PORTS.values():
        dist = _haversine_nm(lat, lon, coords[0], coords[1])
        if nearest_dist is None or dist < nearest_dist:
            nearest_dist = dist
    return (nearest_dist or 0.0) * NM_TO_MI


def scrape() -> dict:
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": USER_AGENT,
        "Referer": f"{MARINETRAFFIC_BASE}/en/ais/home/centerx:-159.3/centery:22.1/zoom:10",
        "X-Requested-With": "XMLHttpRequest",
    }
    cookie_header = os.getenv("MARINETRAFFIC_COOKIE")
    if cookie_header:
        headers["Cookie"] = cookie_header
    tiles = _tile_range(KAUAI_BBOX, TILE_COORD_ZOOM)
    vessels: dict[str, dict[str, Any]] = {}
    response = None
    try:
        with httpx.Client(timeout=20.0, headers=headers) as client:
            try:
                client.get(headers["Referer"])
            except Exception as exc:
                _debug(f"Warmup failed: {exc}")
            for x, y in tiles:
                rows = _fetch_tile(client, TILE_ZOOM, x, y)
                for row in rows:
                    ship_id = str(row.get("SHIP_ID") or "")
                    if not ship_id:
                        continue
                    vessels[ship_id] = row
    except Exception as exc:
        message = f"MarineTraffic fetch failed: {exc}"
        if response is not None:
            message = f"{message} (HTTP {response.status_code})."
        return {
            "id": "marinetraffic_kauai",
            "label": "AIS Vessels (MarineTraffic)",
            "retrieved_at": now_iso(),
            "source_urls": [MARINETRAFFIC_BASE],
            "html": f"<p>{html.escape(message)}</p>",
            "error": message,
            "stale": True,
        }

    rows = []
    for row in vessels.values():
        lat = _parse_float(row.get("LAT"))
        lon = _parse_float(row.get("LON"))
        speed = _parse_float(row.get("SPEED"))
        course = _parse_float(row.get("COURSE"))
        vessel_name = str(row.get("SHIPNAME") or "").strip()
        if str(row.get("SAT") or "").strip() == "1":
            continue
        if vessel_name.upper().startswith("[SAT-AIS]"):
            continue
        if lat is None or lon is None:
            continue
        category = _category_for_vessel(row)
        destination = str(row.get("DESTINATION") or "").strip()
        port, status = _port_status(lat, lon, speed, course)
        if status is None and destination and _enroute_to_kauai(destination, course, lat, lon):
            status = "En route"
        distance_miles = None
        if status != "At port":
            distance_miles = _distance_to_port_miles(lat, lon, destination)
        ship_type_code = str(row.get("SHIPTYPE") or row.get("GT_SHIPTYPE") or "").strip()
        ship_type = SHIPTYPE_LABELS.get(ship_type_code, ship_type_code)
        rows.append(
            {
                "name": vessel_name or "Unknown",
                "type": ship_type,
                "category": category,
                "distance": distance_miles,
                "speed": speed,
                "course": _course_to_cardinal(course),
                "destination": destination,
                "status": status or "",
                "port": port or "",
            }
        )

    rows.sort(key=lambda item: (item["status"] != "En route", item["name"]))

    table_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['name'])}</td>"
        f"<td>{html.escape(row['type'])}</td>"
        f"<td>{html.escape(row['category'])}</td>"
        f"<td>{'' if row['distance'] is None else '{:.1f}'.format(row['distance'])}</td>"
        f"<td>{'' if row['speed'] is None else row['speed']}</td>"
        f"<td>{html.escape(row['course'])}</td>"
        f"<td>{html.escape(row['destination'])}</td>"
        f"<td>{html.escape(row['status'])}</td>"
        f"<td>{html.escape(row['port'])}</td>"
        "</tr>"
        for row in rows
    )

    body = (
        "<table>"
        "<thead><tr><th>Vessel</th><th>Type</th><th>Category</th><th>Distance [mi]</th>"
        "<th>Speed [kt]</th><th>Course</th><th>Destination</th><th>Status</th><th>Port</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
    )

    return {
        "id": "marinetraffic_kauai",
        "label": "Marine Traffic (<a href=\"https://www.marinetraffic.com\">MarineTraffic</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [MARINETRAFFIC_BASE],
        "html": body,
        "error": None,
        "stale": False,
        "layout": "full",
    }
