from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any
from xml.etree import ElementTree

from src.propagation.config import ALL_BANDS, MODES

@dataclass
class ReceptionRecord:
    t_utc: str
    mode: str
    band: str
    freq_hz: int
    snr_db: int | None
    sender_loc: str
    receiver_loc: str
    sender4: str
    receiver4: str
    sender_lat: float
    sender_lon: float
    receiver_lat: float
    receiver_lon: float
    distance_km: float


def _get_attr(attrs: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = attrs.get(key)
        if value:
            return value
    return None


def _normalize_locator(locator: str) -> str | None:
    if not locator:
        return None
    loc = locator.strip().upper()
    if len(loc) < 4:
        return None
    if not (loc[0].isalpha() and loc[1].isalpha() and loc[2].isdigit() and loc[3].isdigit()):
        return None
    return loc[:4]


def maidenhead_to_latlon(locator: str) -> tuple[float, float] | None:
    if not locator:
        return None
    loc = locator.strip().upper()
    if len(loc) < 4:
        return None
    field_lon = ord(loc[0]) - ord("A")
    field_lat = ord(loc[1]) - ord("A")
    if not (0 <= field_lon <= 17 and 0 <= field_lat <= 17):
        return None
    if not (loc[2].isdigit() and loc[3].isdigit()):
        return None
    square_lon = int(loc[2])
    square_lat = int(loc[3])
    lon = -180 + field_lon * 20 + square_lon * 2 + 1
    lat = -90 + field_lat * 10 + square_lat * 1 + 0.5
    if len(loc) >= 6 and loc[4].isalpha() and loc[5].isalpha():
        subs_lon = ord(loc[4]) - ord("A")
        subs_lat = ord(loc[5]) - ord("A")
        if 0 <= subs_lon <= 23 and 0 <= subs_lat <= 23:
            lon += (2 / 24) * subs_lon + (2 / 24) / 2
            lat += (1 / 24) * subs_lat + (1 / 24) / 2
    return lat, lon


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _parse_time(attrs: dict[str, str], now: datetime) -> datetime:
    raw_time = _get_attr(attrs, "time", "t")
    if raw_time:
        try:
            value = int(float(raw_time))
            if value > 1_000_000_000:
                return datetime.fromtimestamp(value, tz=timezone.utc)
        except ValueError:
            pass
    age_min = _get_attr(attrs, "reportAgeMinutes", "ageMinutes")
    if age_min:
        try:
            return now - timedelta(minutes=float(age_min))
        except ValueError:
            pass
    return now


def _mode_from_attrs(attrs: dict[str, str]) -> str | None:
    raw = _get_attr(attrs, "mode", "rxMode", "txMode", "reportMode")
    if not raw:
        return None
    mode = raw.strip().upper()
    if mode in MODES:
        return mode
    return None


def _band_from_freq(freq_hz: int) -> str | None:
    for band, (low, high) in ALL_BANDS.items():
        if low <= freq_hz <= high:
            return band
    return None


def parse_reports(xml_text: str, now: datetime) -> list[ReceptionRecord]:
    if not xml_text:
        return []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    records: list[ReceptionRecord] = []
    for report in root.findall(".//receptionReport"):
        attrs = report.attrib
        sender_loc = _get_attr(attrs, "senderLocator", "senderlocator", "senderGrid")
        receiver_loc = _get_attr(attrs, "receiverLocator", "receiverlocator", "receiverGrid")
        sender4 = _normalize_locator(sender_loc or "")
        receiver4 = _normalize_locator(receiver_loc or "")
        if not sender4 or not receiver4:
            continue

        sender_latlon = maidenhead_to_latlon(sender_loc or sender4)
        receiver_latlon = maidenhead_to_latlon(receiver_loc or receiver4)
        if not sender_latlon or not receiver_latlon:
            continue

        freq_raw = _get_attr(attrs, "frequency", "freq")
        if not freq_raw:
            continue
        try:
            freq_hz = int(float(freq_raw))
        except ValueError:
            continue

        mode = _mode_from_attrs(attrs)
        if not mode:
            continue

        band = _band_from_freq(freq_hz)
        if not band:
            continue

        snr_raw = _get_attr(attrs, "sNR", "snr")
        snr_db = None
        if snr_raw is not None:
            try:
                snr_db = int(float(snr_raw))
            except ValueError:
                snr_db = None

        t_utc = _parse_time(attrs, now).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        distance = haversine_km(sender_latlon[0], sender_latlon[1], receiver_latlon[0], receiver_latlon[1])

        records.append(
            ReceptionRecord(
                t_utc=t_utc,
                mode=mode,
                band=band,
                freq_hz=freq_hz,
                snr_db=snr_db,
                sender_loc=sender_loc or sender4,
                receiver_loc=receiver_loc or receiver4,
                sender4=sender4,
                receiver4=receiver4,
                sender_lat=sender_latlon[0],
                sender_lon=sender_latlon[1],
                receiver_lat=receiver_latlon[0],
                receiver_lon=receiver_latlon[1],
                distance_km=distance,
            )
        )
    return records


def dedupe_records(records: list[ReceptionRecord]) -> list[ReceptionRecord]:
    best: dict[tuple[str, str, str, str], ReceptionRecord] = {}
    for record in records:
        key = (record.mode, record.band, record.sender4, record.receiver4)
        existing = best.get(key)
        if not existing:
            best[key] = record
            continue
        if existing.snr_db is None and record.snr_db is not None:
            best[key] = record
        elif record.snr_db is None:
            continue
        elif record.snr_db > (existing.snr_db or -999):
            best[key] = record
    return list(best.values())
