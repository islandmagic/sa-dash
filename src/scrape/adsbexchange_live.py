import csv
import html
import json
import math
import os
import re
import struct
import time
import zipfile
from typing import Any

import httpx
import zstandard as zstd

from src.scrape.base import now_iso


ADSBEXCHANGE_BASE = "https://globe.adsbexchange.com"
ADSBEXCHANGE_WARMUP_URL = "https://globe.adsbexchange.com/"
ADSBEXCHANGE_RE_API = "https://globe.adsbexchange.com/re-api/"
DEFAULT_BOX = "21.143471,22.533340,-160.669246,-158.453936" # Kauai
#DEFAULT_BOX = "19.193752,24.130461,-161.461093,-156.327954"
FAA_RELEASABLE_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15"
)

TYPE_AIRCRAFT = {
    "1": "Glider",
    "2": "Balloon",
    "3": "Blimp/Dirigible",
    "4": "Fixed wing single engine",
    "5": "Fixed wing multi engine",
    "6": "Rotorcraft",
    "7": "Weight-shift-control",
    "8": "Powered Parachute",
    "9": "Gyroplane",
    "H": "Hybrid Lift",
    "O": "Other",
}

TYPE_ENGINE = {
    "0": "None",
    "1": "Reciprocating",
    "2": "Turbo-prop",
    "3": "Turbo-shaft",
    "4": "Turbo-jet",
    "5": "Turbo-fan",
    "6": "Ramjet",
    "7": "2 Cycle",
    "8": "4 Cycle",
    "9": "Unknown",
    "10": "Electric",
    "11": "Rotary",
}

FAA_CACHE_DAYS = 7
COMMERCIAL_JET_MAKERS = ("AIRBUS", "BOEING", "EMBRAER", "BOMBARDIER", "MCDONNELL")
SPECIAL_MODEL_OVERRIDES = {
    "C2002": ("LOCKHEED MARTIN C-130J Super Hercules", "Military"),
}
SPECIAL_ADSB_TYPE_OVERRIDES = {
    "C30J": ("LOCKHEED MARTIN C-130J Super Hercules", "Military"),
    "H47": ("BOEING-VERTOL CH-47 Chinook", "Military"),
}
MILITARY_OWNER_KEYWORDS = (
    "USAF",
    "US ARMY",
    "US NAVY",
    "US MARINE",
    "ARMY",
    "NAVY",
    "AIR FORCE",
    "MARINES",
    "UNITED STATES",
    "DEPARTMENT OF DEFENSE",
    "DOD",
    "NATIONAL GUARD",
)
COAST_GUARD_KEYWORDS = ("COAST GUARD", "USCG")
FIRE_DEPT_KEYWORDS = ("FIRE DEPT", "FIRE DEPARTMENT", "FIRE DIST", "FIRE PROTECTION")
TOWN_RADIUS_MILES = 5.0
TOWN_COORDS = {
    "Hanalei": (22.205, -159.500),
    "Princeville": (22.220, -159.473),
    "Kilauea": (22.209, -159.406),
    "Anahola": (22.142, -159.315),
    "Kealia": (22.096, -159.318),
    "Kapaa": (22.088, -159.338),
    "Lihue": (21.981, -159.368),
    "Koloa": (21.902, -159.469),
    "Lawai": (21.907, -159.481),
    "Kalaheo": (21.913, -159.535),
    "Eleele": (21.913, -159.586),
    "Hanapepe": (21.905, -159.592),
    "Makaweli": (21.916, -159.631),
    "Kaumakani": (21.914, -159.628),
    "Waimea": (21.953, -159.672),
    "Kekaha": (21.973, -159.719),
}
NA_PALI_COORD = (22.172, -159.643)


def _debug_enabled() -> bool:
    return os.getenv("ADSBEXCHANGE_DEBUG", "").lower() in {"1", "true", "yes", "on"}


def _debug(message: str) -> None:
    if _debug_enabled():
        print(f"[adsbexchange] {message}")


def _parse_box(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("Box must be south,north,west,east.")
    south, north, west, east = (float(part) for part in parts)
    return south, north, west, east


def _box_center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    south, north, west, east = box
    return (south + north) / 2, (west + east) / 2


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _heading_to_cardinal(value: float | None) -> str:
    if value is None:
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
    index = int((value % 360) / 22.5 + 0.5) % 16
    return directions[index]


def _vicinity_label(lat: float, lon: float) -> str | None:
    best_label = None
    best_distance = None
    for label, coords in TOWN_COORDS.items():
        distance = _haversine_miles(lat, lon, coords[0], coords[1])
        if distance <= TOWN_RADIUS_MILES and (
            best_distance is None or distance < best_distance
        ):
            best_label = label
            best_distance = distance
    np_distance = _haversine_miles(lat, lon, NA_PALI_COORD[0], NA_PALI_COORD[1])
    if np_distance <= TOWN_RADIUS_MILES and (
        best_distance is None or np_distance < best_distance
    ):
        return "Na Pali Coast"
    return best_label


def _classify_aircraft(
    faa_type: str | None,
    engine_type: str | None,
    aircraft_name: str | None,
    registrant_name: str | None,
    mfr_model_code: str | None,
    adsb_type: str | None,
    db_flags: int | None,
) -> str:
    name = (aircraft_name or "").upper()
    registrant = (registrant_name or "").upper()
    if mfr_model_code in SPECIAL_MODEL_OVERRIDES:
        return SPECIAL_MODEL_OVERRIDES[mfr_model_code][1]
    if adsb_type in SPECIAL_ADSB_TYPE_OVERRIDES:
        return SPECIAL_ADSB_TYPE_OVERRIDES[adsb_type][1]
    if isinstance(db_flags, int) and db_flags & 1:
        return "Military"
    if any(keyword in registrant for keyword in COAST_GUARD_KEYWORDS):
        return "Coast Guard"
    if any(keyword in registrant for keyword in FIRE_DEPT_KEYWORDS):
        return "Fire Dept"
    if any(keyword in registrant for keyword in MILITARY_OWNER_KEYWORDS) or "C-130" in name:
        return "Military"
    if faa_type == "Rotorcraft" or "HELICOPTER" in name:
        return "Heli"
    if engine_type in {"Reciprocating", "Turbo-prop", "2 Cycle", "4 Cycle", "Rotary"}:
        return "Prop"
    if engine_type in {"Turbo-jet", "Turbo-fan", "Turbo-shaft", "Ramjet"}:
        if name.startswith(COMMERCIAL_JET_MAKERS):
            return "Airliner"
        if faa_type == "Fixed wing multi engine":
            return "Airliner"
        return "Jet"
    return "Other"


def _read_ascii(buffer: memoryview, start: int, end: int) -> str:
    chars = []
    for i in range(start, min(end, len(buffer))):
        value = buffer[i]
        if value == 0:
            break
        chars.append(chr(value))
    return "".join(chars)


def _decode_zstd(payload: bytes) -> bytes:
    decompressor = zstd.ZstdDecompressor()
    return decompressor.decompress(payload)


def _cache_dir() -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache")
    return os.path.abspath(base)


def _is_stale(path: str, days: int) -> bool:
    if not os.path.exists(path):
        return True
    age_seconds = time.time() - os.path.getmtime(path)
    return age_seconds > days * 86400


def _normalize_mode_s(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(cleaned) < 6:
        return None
    return cleaned[-6:].lower()


def _normalize_n_number(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    return cleaned if cleaned.startswith("N") else f"N{cleaned}"


def _slice_fixed(line: str, start: int, end: int) -> str:
    return line[start - 1 : end].strip()


def _parse_faa_fixed_width(path: str) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if len(line) < 200:
                continue
            n_number = _normalize_n_number(_slice_fixed(line, 1, 5))
            mfr_model_code = _slice_fixed(line, 38, 44)
            year_mfr = _slice_fixed(line, 52, 55)
            type_aircraft = _slice_fixed(line, 249, 249)
            type_engine = _slice_fixed(line, 251, 252)
            registrant_name = _slice_fixed(line, 59, 108)
            mode_s_hex = _normalize_mode_s(_slice_fixed(line, 602, 611))
            if not mode_s_hex:
                continue
            registry[mode_s_hex] = {
                "n_number": n_number,
                "mfr_model_code": mfr_model_code or None,
                "year_mfr": year_mfr or None,
                "type_aircraft": TYPE_AIRCRAFT.get(type_aircraft, type_aircraft or None),
                "type_engine": TYPE_ENGINE.get(type_engine, type_engine or None),
                "registrant_name": registrant_name or None,
            }
    return registry


def _parse_faa_csv(path: str) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header:
            return registry
        norm = {
            re.sub(r"[^a-z0-9]", "", name.lower()): idx
            for idx, name in enumerate(header)
        }

        def idx_for(*names: str) -> int | None:
            for name in names:
                key = re.sub(r"[^a-z0-9]", "", name.lower())
                if key in norm:
                    return norm[key]
            return None

        idx_n = idx_for("N-NUMBER", "NNumber")
        idx_mode_s = idx_for("MODE S CODE HEX", "MODE_S_CODE_HEX", "Mode S Code Hex")
        idx_mfr = idx_for("AIRCRAFT MFR MODEL CODE", "MFR_MDL_CODE")
        idx_year = idx_for("YEAR MFR", "YEAR_MFR")
        idx_type_aircraft = idx_for("TYPE AIRCRAFT", "TYPE_AIRCRAFT")
        idx_type_engine = idx_for("TYPE ENGINE", "TYPE_ENGINE")
        idx_name = idx_for("NAME", "REGISTRANT NAME", "REGISTRANTS NAME")

        for row in reader:
            if idx_mode_s is None or idx_mode_s >= len(row):
                continue
            mode_s_hex = _normalize_mode_s(row[idx_mode_s])
            if not mode_s_hex:
                continue
            n_number = (
                _normalize_n_number(row[idx_n]) if idx_n is not None else None
            )
            mfr_model_code = row[idx_mfr].strip() if idx_mfr is not None else None
            year_mfr = row[idx_year].strip() if idx_year is not None else None
            type_aircraft = (
                row[idx_type_aircraft].strip() if idx_type_aircraft is not None else None
            )
            type_engine = (
                row[idx_type_engine].strip() if idx_type_engine is not None else None
            )
            registrant_name = row[idx_name].strip() if idx_name is not None else None
            registry[mode_s_hex] = {
                "n_number": n_number,
                "mfr_model_code": mfr_model_code or None,
                "year_mfr": year_mfr or None,
                "type_aircraft": TYPE_AIRCRAFT.get(type_aircraft, type_aircraft or None),
                "type_engine": TYPE_ENGINE.get(type_engine, type_engine or None),
                "registrant_name": registrant_name or None,
            }
    return registry


def _parse_acftref(path: str) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    with open(path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header:
            return mapping
        norm = {
            re.sub(r"[^a-z0-9]", "", name.lower()): idx
            for idx, name in enumerate(header)
        }
        idx_code = norm.get("code")
        idx_mfr = norm.get("mfr")
        idx_model = norm.get("model")
        if idx_code is None:
            return mapping
        for row in reader:
            if idx_code >= len(row):
                continue
            code = row[idx_code].strip()
            if not code:
                continue
            mfr = row[idx_mfr].strip() if idx_mfr is not None and idx_mfr < len(row) else ""
            model = (
                row[idx_model].strip()
                if idx_model is not None and idx_model < len(row)
                else ""
            )
            mapping[code] = {"mfr": mfr, "model": model}
    return mapping


def _load_faa_registry() -> dict[str, dict[str, Any]]:
    cache_dir = _cache_dir()
    os.makedirs(cache_dir, exist_ok=True)

    zip_path = os.path.join(cache_dir, "faa_releasable_aircraft.zip")
    master_path = os.path.join(cache_dir, "faa_releasable_aircraft_master.txt")
    acftref_path = os.path.join(cache_dir, "faa_releasable_aircraft_acftref.txt")
    cache_path = os.path.join(cache_dir, "faa_releasable_aircraft.json")

    if not _is_stale(cache_path, FAA_CACHE_DAYS):
        try:
            with open(cache_path, "r", encoding="utf-8") as handle:
                data = handle.read()
            cached = json.loads(data)
            if isinstance(cached, dict) and cached:
                return cached
            _debug("FAA cache JSON empty; rebuilding.")
        except Exception:
            _debug("Failed reading FAA cache JSON; rebuilding.")

    if _is_stale(zip_path, FAA_CACHE_DAYS):
        try:
            _debug("Downloading FAA ReleasableAircraft.zip.")
            headers = {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/zip,application/octet-stream,*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://registry.faa.gov/",
            }
            with httpx.Client(timeout=180.0, follow_redirects=True) as client:
                response = client.get(FAA_RELEASABLE_URL, headers=headers)
                response.raise_for_status()
                with open(zip_path, "wb") as handle:
                    handle.write(response.content)
        except Exception as exc:
            _debug(f"FAA download failed: {exc}")
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "r", encoding="utf-8") as handle:
                        data = handle.read()
                    return json.loads(data)
                except Exception:
                    _debug("Failed reading FAA cache JSON after download error.")
            return {}

    if _is_stale(master_path, FAA_CACHE_DAYS) or _is_stale(acftref_path, FAA_CACHE_DAYS):
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = {name.lower(): name for name in zf.namelist()}
                master_name = names.get("master.txt")
                acftref_name = names.get("acftref.txt")
                if not master_name:
                    _debug("FAA zip missing MASTER.txt.")
                    return {}
                with zf.open(master_name) as src, open(master_path, "wb") as dst:
                    dst.write(src.read())
                if acftref_name:
                    with zf.open(acftref_name) as src, open(acftref_path, "wb") as dst:
                        dst.write(src.read())
            try:
                os.remove(zip_path)
            except OSError:
                _debug("Failed to remove FAA zip after extraction.")
        except Exception as exc:
            _debug(f"FAA unzip failed: {exc}")
            return {}

    try:
        with open(master_path, "r", encoding="utf-8", errors="ignore") as handle:
            sample = handle.readline()
        if sample.count(",") > 5:
            registry = _parse_faa_csv(master_path)
        else:
            registry = _parse_faa_fixed_width(master_path)
    except Exception as exc:
        _debug(f"FAA parse failed: {exc}")
        return {}

    acftref = _parse_acftref(acftref_path) if os.path.exists(acftref_path) else {}

    if acftref:
        for record in registry.values():
            code = record.get("mfr_model_code")
            if code and code in acftref:
                record["mfr"] = acftref[code].get("mfr")
                record["model"] = acftref[code].get("model")

    if not registry:
        _debug("FAA registry parsed empty; check input file.")
        return {}

    try:
        with open(cache_path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(registry))
    except Exception:
        _debug("Failed writing FAA cache JSON.")

    return registry

def _parse_bincraft(buffer: bytes) -> dict[str, Any]:
    if len(buffer) < 64:
        raise ValueError("BinCraft payload too small.")

    u32 = struct.unpack_from("<13I", buffer, 0)
    stride = u32[2]
    if stride <= 0 or len(buffer) < stride:
        raise ValueError("Invalid BinCraft stride.")

    limits = struct.unpack_from("<4h", buffer, 20)
    south, west, north, east = limits
    messages = u32[7] if len(u32) > 7 else None
    bin_craft_version = u32[10] if len(u32) > 10 else 0
    message_rate = u32[11] / 10 if len(u32) > 11 else None
    use_message_rate = bool(u32[12] & 1) if len(u32) > 12 else False

    s32_header = struct.unpack_from("<" + "i" * (stride // 4), buffer, 0)
    receiver_lat = s32_header[8] / 1e6 if len(s32_header) > 8 else None
    receiver_lon = s32_header[9] / 1e6 if len(s32_header) > 9 else None

    aircraft: list[dict[str, Any]] = []
    for offset in range(stride, len(buffer), stride):
        if offset + stride > len(buffer):
            break
        u32_rec = struct.unpack_from("<" + "I" * (stride // 4), buffer, offset)
        s32_rec = struct.unpack_from("<" + "i" * (stride // 4), buffer, offset)
        u16_rec = struct.unpack_from("<" + "H" * (stride // 2), buffer, offset)
        s16_rec = struct.unpack_from("<" + "h" * (stride // 2), buffer, offset)
        u8_rec = memoryview(buffer)[offset : offset + stride]

        tbit = s32_rec[0] & (1 << 24)
        hex_id = f"{s32_rec[0] & 0xFFFFFF:06x}"
        if tbit:
            hex_id = f"~{hex_id}"

        if bin_craft_version >= 20240218 and len(s32_rec) > 27:
            seen = s32_rec[1] / 10
            seen_pos = s32_rec[27] / 10
        else:
            seen_pos = u16_rec[2] / 10
            seen = u16_rec[3] / 10

        lon = s32_rec[2] / 1e6
        lat = s32_rec[3] / 1e6
        baro_rate = 8 * s16_rec[8]
        geom_rate = 8 * s16_rec[9]
        alt_baro = 25 * s16_rec[10]
        alt_geom = 25 * s16_rec[11]
        gs = s16_rec[17] / 10
        track = s16_rec[20] / 90
        mag_heading = s16_rec[22] / 90
        true_heading = s16_rec[23] / 90
        tas = u16_rec[28]
        ias = u16_rec[29]

        squawk_hex = f"{u16_rec[16]:04x}"
        if squawk_hex[0] > "9":
            squawk = str(int(squawk_hex[0], 16)) + squawk_hex[1:]
        else:
            squawk = squawk_hex

        flight = _read_ascii(u8_rec, 78, 86)
        ac_type = _read_ascii(u8_rec, 88, 92)
        registration = _read_ascii(u8_rec, 92, 104)

        flags73 = u8_rec[73]
        flags74 = u8_rec[74]
        flags75 = u8_rec[75]
        flags76 = u8_rec[76]
        flags77 = u8_rec[77]

        if not flags73 & 0x08:
            flight = None
        if not flags73 & 0x10:
            alt_baro = None
        if not flags73 & 0x20:
            alt_geom = None
        if not flags73 & 0x40:
            lat = None
            lon = None
            seen_pos = None
        if not flags73 & 0x80:
            gs = None

        if not flags74 & 0x01:
            ias = None
        if not flags74 & 0x02:
            tas = None
        if not flags74 & 0x08:
            track = None
        if not flags74 & 0x40:
            mag_heading = None
        if not flags74 & 0x80:
            true_heading = None

        if not flags75 & 0x01:
            pass
        if not flags76 & 0x04:
            squawk = None
        if not flags77 & 0x10:
            pass

        airground = u8_rec[68] & 0x0F
        if airground == 1:
            alt_baro = "ground"

        aircraft.append(
            {
                "hex": hex_id,
                "flight": flight,
                "alt_baro": alt_baro,
                "alt_geom": alt_geom,
                "baro_rate": baro_rate,
                "geom_rate": geom_rate,
                "gs": gs,
                "track": track,
                "mag_heading": mag_heading,
                "true_heading": true_heading,
                "tas": tas,
                "ias": ias,
                "lat": lat,
                "lon": lon,
                "seen": seen,
                "seen_pos": seen_pos,
                "squawk": squawk,
                "type": ac_type,
                "registration": registration,
                "db_flags": u16_rec[43] if len(u16_rec) > 43 else None,
            }
        )

    return {
        "aircraft": aircraft,
        "south": south,
        "west": west,
        "north": north,
        "east": east,
        "receiver_lat": receiver_lat,
        "receiver_lon": receiver_lon,
        "messages": messages,
        "message_rate": message_rate if use_message_rate else None,
    }


def scrape() -> dict:
    box_value = os.getenv("ADSBEXCHANGE_BOX", DEFAULT_BOX)
    try:
        box = _parse_box(box_value)
    except ValueError as exc:
        return {
            "id": "adsbexchange_live",
            "label": "Live Aircraft (ADSBExchange)",
            "retrieved_at": now_iso(),
            "source_urls": [ADSBEXCHANGE_RE_API],
            "html": f"<p>{html.escape(str(exc))}</p>",
            "error": str(exc),
            "stale": True,
        }

    south, north, west, east = box
    faa_registry = _load_faa_registry()
    _debug(f"FAA registry entries={len(faa_registry)}.")

    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": ADSBEXCHANGE_BASE + "/",
        "User-Agent": DEFAULT_USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
    }

    response = None
    try:
        with httpx.Client(timeout=20.0, headers=headers) as client:
            try:
                warmup = client.get(ADSBEXCHANGE_WARMUP_URL)
                _debug(
                    f"Warmup status={warmup.status_code} cookies={len(client.cookies)}"
                )
            except Exception as warmup_exc:
                _debug(f"Warmup failed: {warmup_exc}")

            url = (
                f"{ADSBEXCHANGE_RE_API}?binCraft&zstd&box={south},{north},{west},{east}"
            )
            response = client.get(url)
            response.raise_for_status()

        payload = response.content
        if "application/zstd" in response.headers.get("Content-Type", ""):
            payload = _decode_zstd(payload)
        elif payload.startswith(b"{") or payload.startswith(b"["):
            pass
        else:
            payload = _decode_zstd(payload)

        if payload.startswith(b"{") or payload.startswith(b"["):
            data = {
                "aircraft": [],
                "error": "Unexpected JSON payload for BinCraft.",
            }
        else:
            data = _parse_bincraft(payload)
    except Exception as exc:
        message = f"ADSBExchange fetch failed: {exc}"
        if response is not None:
            message = f"{message} (HTTP {response.status_code})."
        return {
            "id": "adsbexchange_live",
            "label": "Live Aircraft (ADSBExchange)",
            "retrieved_at": now_iso(),
            "source_urls": [ADSBEXCHANGE_RE_API],
            "html": f"<p>{html.escape(message)}</p>",
            "error": message,
            "stale": True,
        }

    aircraft = data.get("aircraft", [])
    filtered = []
    for ac in aircraft:
        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is None or lon is None:
            continue
        if not (south <= lat <= north and west <= lon <= east):
            continue

        altitude = ac.get("alt_baro")
        if altitude is None:
            altitude = ac.get("alt_geom")
        if isinstance(altitude, (int, float)) and altitude > 10000:
            continue
        rate = ac.get("baro_rate")
        if rate is None:
            rate = ac.get("geom_rate")
        rate_indicator = ""
        if isinstance(rate, (int, float)):
            if rate > 0:
                rate_indicator = "▲"
            elif rate < 0:
                rate_indicator = "▼"

        speed = ac.get("gs")
        if speed is None:
            speed = ac.get("tas") or ac.get("ias")

        heading = ac.get("track")
        if heading is None:
            heading = ac.get("true_heading") or ac.get("mag_heading")

        callsign = ac.get("flight") or ac.get("hex") or "Unknown"
        ac_type = ac.get("type") or "Unknown"
        hex_key = str(ac.get("hex") or "").lstrip("~").lower()
        faa_info = faa_registry.get(hex_key, {})
        mfr = faa_info.get("mfr")
        model = faa_info.get("model")
        year_mfr = faa_info.get("year_mfr")
        mfr_model_code = faa_info.get("mfr_model_code")
        aircraft_name = ""
        if mfr_model_code in SPECIAL_MODEL_OVERRIDES:
            aircraft_name = SPECIAL_MODEL_OVERRIDES[mfr_model_code][0]
        elif ac_type in SPECIAL_ADSB_TYPE_OVERRIDES:
            aircraft_name = SPECIAL_ADSB_TYPE_OVERRIDES[ac_type][0]
        else:
            if year_mfr:
                aircraft_name = f"{year_mfr}"
            if mfr:
                aircraft_name = f"{aircraft_name} {mfr}".strip()
            if model:
                aircraft_name = f"{aircraft_name} {model}".strip()
        heading_cardinal = _heading_to_cardinal(
            float(heading) if heading is not None else None
        )

        filtered.append(
            {
                "callsign": callsign.strip() if isinstance(callsign, str) else callsign,
                "registration": faa_info.get("n_number"),
                "aircraft_name": aircraft_name or None,
                "registrant_name": faa_info.get("registrant_name"),
                "faa_type": faa_info.get("type_aircraft"),
                "category": _classify_aircraft(
                    faa_info.get("type_aircraft"),
                    faa_info.get("type_engine"),
                    aircraft_name,
                    faa_info.get("registrant_name"),
                    mfr_model_code,
                    ac_type,
                    ac.get("db_flags"),
                ),
                "vicinity": _vicinity_label(lat, lon),
                "altitude": altitude,
                "altitude_trend": rate_indicator,
                "speed": speed,
                "heading": heading_cardinal,
                "aircraft_type": ac_type.strip() if isinstance(ac_type, str) else ac_type,
                "lat": lat,
                "lon": lon,
            }
        )

    filtered.sort(key=lambda item: item.get("callsign") or "")

    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['callsign']))}</td>"
        f"<td>{html.escape(str(item['registration'] or ''))}</td>"
        f"<td>{html.escape(str(item['aircraft_type']))}</td>"
        f"<td>{html.escape(str(item['aircraft_name'] or ''))}</td>"
        f"<td>{html.escape(str(item['registrant_name'] or ''))}</td>"
        f"<td>{html.escape(str(item['category']))}</td>"
        f"<td>{html.escape(str(item['vicinity'] or ''))}</td>"
        f"<td>{'' if item['altitude'] is None else item['altitude']} {html.escape(item['altitude_trend'])}</td>"
        f"<td>{'' if item['speed'] is None else item['speed']}</td>"
        f"<td>{html.escape(str(item['heading']))}</td>"
        "</tr>"
        for item in filtered
    )

    info_html = (
        "<p class=\"info\">Filtered to aircraft within the Kauai area and below 10,000 ft.</p>"
    )
    body = (
        info_html
        + "<table>"
        "<thead><tr><th>Callsign</th><th>Reg</th><th>Type</th><th>Aircraft</th>"
        "<th>Owner</th><th>Category</th><th>Vicinity</th><th>Altitude [ft]</th><th>Speed [kt]</th><th>Heading</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )

    return {
        "id": "adsbexchange_live",
        "label": "Air Traffic (<a href=\"https://globe.adsbexchange.com\">ADSBExchange</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [ADSBEXCHANGE_RE_API, ADSBEXCHANGE_BASE],
        "html": body,
        "error": None,
        "stale": False,
        "layout": "full",
    }
