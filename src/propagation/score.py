from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import statistics
from typing import Iterable

from src.propagation.config import (
    BBOX_CONUS,
    BBOX_HI,
    D_TARGET_MAINLAND,
    D_TARGET_NVIS,
    HYSTERESIS,
    MAINLAND_BAND_WEIGHTS,
    MAINLAND_MAX_KM,
    MAINLAND_MIN_KM,
    MAINLAND_THRESHOLDS,
    NVIS_BAND_WEIGHTS,
    NVIS_MAX_KM,
    NVIS_THRESHOLDS,
    P_TARGET_MAINLAND,
    P_TARGET_NVIS,
    SNR_MAX,
    SNR_MIN,
    SNR_OK_MAINLAND,
    SNR_OK_NVIS,
    SNR_STRONG,
    VARA_THRESHOLDS_MAINLAND,
    VARA_THRESHOLDS_NVIS,
    W_FT8,
    W_JS8,
    W_WSPR,
)
from src.propagation.parse import ReceptionRecord


@dataclass
class IndicatorSummary:
    status: str
    score: int
    confidence: str
    bands: dict[str, dict]
    explain: str
    records_total: int


def _in_bbox(lat: float, lon: float, bbox: dict[str, float]) -> bool:
    return bbox["lat_min"] <= lat <= bbox["lat_max"] and bbox["lon_min"] <= lon <= bbox["lon_max"]


def classify_records(records: Iterable[ReceptionRecord]) -> tuple[list[ReceptionRecord], list[ReceptionRecord]]:
    nvis = []
    mainland = []
    for record in records:
        sender_in_hi = _in_bbox(record.sender_lat, record.sender_lon, BBOX_HI)
        receiver_in_hi = _in_bbox(record.receiver_lat, record.receiver_lon, BBOX_HI)
        sender_in_conus = _in_bbox(record.sender_lat, record.sender_lon, BBOX_CONUS)
        receiver_in_conus = _in_bbox(record.receiver_lat, record.receiver_lon, BBOX_CONUS)

        if (
            record.band in NVIS_BAND_WEIGHTS
            and sender_in_hi
            and receiver_in_hi
            and record.distance_km <= NVIS_MAX_KM
        ):
            nvis.append(record)
        if (
            record.band in MAINLAND_BAND_WEIGHTS
            and ((sender_in_hi and receiver_in_conus) or (sender_in_conus and receiver_in_hi))
            and MAINLAND_MIN_KM <= record.distance_km <= MAINLAND_MAX_KM
        ):
            mainland.append(record)
    return nvis, mainland


def _snr_median(records: list[ReceptionRecord]) -> float | None:
    values = [r.snr_db for r in records if r.snr_db is not None]
    if not values:
        return None
    return float(statistics.median(values))


def _weighted_pairs(records: list[ReceptionRecord]) -> tuple[float, float, float, int, int]:
    pairs = []
    sender_modes: dict[str, set[str]] = {}
    receiver_modes: dict[str, set[str]] = {}
    js8_paths = 0
    ft8_paths = 0
    for record in records:
        if record.mode == "JS8":
            weight = W_JS8
            js8_paths += 1
        elif record.mode == "WSPR":
            weight = W_WSPR
        else:
            weight = W_FT8
            ft8_paths += 1

        pairs.append(weight)
        sender_modes.setdefault(record.sender4, set()).add(record.mode)
        receiver_modes.setdefault(record.receiver4, set()).add(record.mode)

    tx_weighted = 0.0
    for modes in sender_modes.values():
        if "JS8" in modes:
            tx_weighted += W_JS8
        elif "FT8" in modes:
            tx_weighted += W_FT8
        else:
            tx_weighted += W_WSPR
    rx_weighted = 0.0
    for modes in receiver_modes.values():
        if "JS8" in modes:
            rx_weighted += W_JS8
        elif "FT8" in modes:
            rx_weighted += W_FT8
        else:
            rx_weighted += W_WSPR
    return sum(pairs), tx_weighted, rx_weighted, js8_paths, ft8_paths


def _normalize_log(value: float, target: float) -> float:
    return min(1.0, math.log(1 + value) / math.log(1 + target))


def _band_score(
    records: list[ReceptionRecord],
    p_target: float,
    d_target: float,
) -> tuple[float, float | None, float, float, int, int]:
    p_weighted, tx_weighted, rx_weighted, js8_paths, ft8_paths = _weighted_pairs(records)
    s_median = _snr_median(records)
    p_norm = _normalize_log(p_weighted, p_target)
    d_norm = _normalize_log(min(tx_weighted, rx_weighted), d_target)

    if s_median is None:
        score = 100 * (0.70 * p_norm + 0.30 * d_norm)
    else:
        s_norm = min(1.0, max(0.0, (s_median - SNR_MIN) / (SNR_MAX - SNR_MIN)))
        score = 100 * (0.45 * p_norm + 0.20 * d_norm + 0.35 * s_norm)
    return score, s_median, p_weighted, tx_weighted, rx_weighted, js8_paths, ft8_paths


def _vara_score(
    band_score: float,
    js8_paths: int,
    ft8_paths: int,
    s_median: float | None,
    is_nvis: bool,
) -> float:
    total_paths = js8_paths + ft8_paths
    js8_ratio = js8_paths / max(1, total_paths)
    js8_factor = min(1.0, max(0.0, js8_ratio / 0.25))

    if s_median is None:
        snr_factor = 0.3
    else:
        snr_ok = SNR_OK_NVIS if is_nvis else SNR_OK_MAINLAND
        snr_factor = min(1.0, max(0.0, (s_median - snr_ok) / (SNR_STRONG - snr_ok)))

    base_factor = band_score / 100
    vara_band = 100 * (0.45 * js8_factor + 0.35 * snr_factor + 0.20 * base_factor)
    if js8_paths == 0:
        vara_band *= 0.70
    return vara_band


def _map_status(score: float, thresholds: dict[str, int], labels: list[str]) -> str:
    high_label = labels[0]
    mid_label = labels[1]
    low_label = labels[2]
    high_threshold = thresholds[high_label]
    mid_threshold = thresholds[mid_label]
    if score >= high_threshold:
        return high_label
    if score >= mid_threshold:
        return mid_label
    return low_label


def _apply_hysteresis(score: float, prev: str | None, thresholds: dict[str, int], labels: list[str]) -> str:
    raw = _map_status(score, thresholds, labels)
    if not prev or prev not in labels:
        return raw

    if prev == labels[2] and raw in (labels[1], labels[0]):
        upgrade_threshold = thresholds[labels[1]] + HYSTERESIS
        if raw == labels[0]:
            upgrade_threshold = thresholds[labels[0]] + HYSTERESIS
        return raw if score >= upgrade_threshold else prev

    if prev == labels[1] and raw == labels[0]:
        upgrade_threshold = thresholds[labels[0]] + HYSTERESIS
        return raw if score >= upgrade_threshold else prev

    if prev == labels[1] and raw == labels[2]:
        downgrade_threshold = thresholds[labels[1]] - HYSTERESIS
        return raw if score < downgrade_threshold else prev

    if prev == labels[0] and raw in (labels[1], labels[2]):
        downgrade_threshold = thresholds[labels[0]] - HYSTERESIS
        return raw if score < downgrade_threshold else prev

    return raw


def _apply_vara_overrides(
    vara_score: float,
    s_median_by_band: dict[str, float | None],
    js8_paths_by_band: dict[str, int],
    ft8_paths_by_band: dict[str, int],
    is_nvis: bool,
    vara_thresholds: dict[str, int],
) -> float:
    snr_ok = SNR_OK_NVIS if is_nvis else SNR_OK_MAINLAND
    js8_ok = any(
        (paths >= 1 and (s_median_by_band.get(band) or -999) >= snr_ok)
        for band, paths in js8_paths_by_band.items()
    )
    if js8_ok:
        vara_score = max(vara_score, float(vara_thresholds["POSSIBLE"]))

    if not is_nvis:
        total_js8 = sum(js8_paths_by_band.values())
        js8_band_count = sum(1 for paths in js8_paths_by_band.values() if paths >= 1)
        if js8_band_count >= 2 or total_js8 >= 3:
            vara_score = min(100.0, vara_score + 10)

    return vara_score


def _confidence_level(records_total: int, anchors_reporting: int, fresh_minutes: float) -> str:
    if records_total >= 30 and anchors_reporting >= 3 and fresh_minutes <= 10:
        return "HIGH"
    if records_total >= 10 and anchors_reporting >= 2 and fresh_minutes <= 20:
        return "MEDIUM"
    return "LOW"


def _explain(status: str, js8_paths_total: int, is_nvis: bool) -> str:
    js8_suffix = " (JS8)." if js8_paths_total >= 1 else " (FT8)."
    if is_nvis:
        if status == "GOOD":
            return f"Strong inter-island paths on 40m/80m{js8_suffix}"
        if status == "MARGINAL":
            return "Some inter-island activity; expect variability."
        if status == "POOR":
            return "Little inter-island activity."
        return "Limited recent reports."
    if status == "OPEN":
        return f"HI<->CONUS paths observed on 20m+{js8_suffix}"
    if status == "INTERMITTENT":
        return "Intermittent HI\u2194CONUS activity; openings may be brief."
    if status == "CLOSED":
        return "No recent HI\u2194CONUS paths observed."
    return "Limited recent reports."


def _indicator_summary(
    records: list[ReceptionRecord],
    band_weights: dict[str, float],
    p_target: float,
    d_target: float,
    thresholds: dict[str, int],
    vara_thresholds: dict[str, int],
    prev_status: str | None,
    anchors_reporting: int,
    fresh_minutes: float,
    is_nvis: bool,
) -> IndicatorSummary:
    band_outputs: dict[str, dict] = {}
    weighted_score = 0.0
    weighted_vara = 0.0
    active_weight = 0.0
    js8_paths_total = 0
    records_total = 0
    s_median_by_band: dict[str, float | None] = {}
    js8_by_band: dict[str, int] = {}
    ft8_by_band: dict[str, int] = {}

    for band, weight in band_weights.items():
        band_records = [r for r in records if r.band == band]
        records_total += len(band_records)
        if not band_records:
            band_outputs[band] = {
                "score": 0,
                "paths": 0,
                "tx": 0,
                "rx": 0,
                "median_snr_db": None,
                "js8_paths": 0,
                "ft8_paths": 0,
            }
            continue

        (
            band_score,
            s_median,
            p_weighted,
            tx_weighted,
            rx_weighted,
            js8_paths,
            ft8_paths,
        ) = _band_score(
            band_records,
            p_target,
            d_target,
        )
        vara_band = _vara_score(band_score, js8_paths, ft8_paths, s_median, is_nvis)
        weighted_score += weight * band_score
        weighted_vara += weight * vara_band
        active_weight += weight
        js8_paths_total += js8_paths

        s_median_by_band[band] = s_median
        js8_by_band[band] = js8_paths
        ft8_by_band[band] = ft8_paths

        unique_pairs = {(r.sender4, r.receiver4) for r in band_records}
        band_outputs[band] = {
            "score": int(round(band_score)),
            "paths": len(unique_pairs),
            "tx": round(tx_weighted, 2),
            "rx": round(rx_weighted, 2),
            "median_snr_db": None if s_median is None else round(s_median, 1),
            "js8_paths": js8_paths,
            "ft8_paths": ft8_paths,
        }

    if active_weight > 0:
        weighted_score /= active_weight
        weighted_vara /= active_weight

    vara_score = _apply_vara_overrides(
        weighted_vara,
        s_median_by_band,
        js8_by_band,
        ft8_by_band,
        is_nvis,
        vara_thresholds,
    )

    labels = ["GOOD", "MARGINAL", "POOR"] if is_nvis else ["OPEN", "INTERMITTENT", "CLOSED"]
    status = _apply_hysteresis(weighted_score, prev_status, thresholds, labels)
    confidence = _confidence_level(records_total, anchors_reporting, fresh_minutes)
    explain = _explain(status, js8_paths_total, is_nvis)
    if confidence == "LOW":
        if records_total == 0:
            status = "UNKNOWN"
            explain = "Limited recent reports."
        else:
            explain = f"{explain} Low report volume."

    return IndicatorSummary(
        status=status,
        score=int(round(weighted_score)),
        confidence=confidence,
        bands=band_outputs,
        explain=explain,
        records_total=records_total,
    )


def summarize_indicators(
    nvis_records: list[ReceptionRecord],
    mainland_records: list[ReceptionRecord],
    prev_state: dict[str, str] | None,
    anchors_reporting: int,
    last_fetch_utc: str | None,
) -> tuple[IndicatorSummary, IndicatorSummary]:
    now = datetime.now(tz=timezone.utc)
    fresh_minutes = 9999.0
    if last_fetch_utc:
        try:
            fetched = datetime.fromisoformat(last_fetch_utc.replace("Z", "+00:00"))
            fresh_minutes = max(0.0, (now - fetched).total_seconds() / 60)
        except ValueError:
            fresh_minutes = 9999.0

    prev_nvis = prev_state.get("nvis_status") if prev_state else None
    prev_mainland = prev_state.get("mainland_status") if prev_state else None

    nvis_summary = _indicator_summary(
        nvis_records,
        NVIS_BAND_WEIGHTS,
        P_TARGET_NVIS,
        D_TARGET_NVIS,
        NVIS_THRESHOLDS,
        VARA_THRESHOLDS_NVIS,
        prev_nvis,
        anchors_reporting,
        fresh_minutes,
        True,
    )
    mainland_summary = _indicator_summary(
        mainland_records,
        MAINLAND_BAND_WEIGHTS,
        P_TARGET_MAINLAND,
        D_TARGET_MAINLAND,
        MAINLAND_THRESHOLDS,
        VARA_THRESHOLDS_MAINLAND,
        prev_mainland,
        anchors_reporting,
        fresh_minutes,
        False,
    )
    return nvis_summary, mainland_summary


def default_state() -> dict:
    return {"last": {"nvis_status": None, "mainland_status": None, "timestamp_utc": None}}


def update_state(
    state: dict,
    nvis_status: str,
    mainland_status: str,
    timestamp_utc: str,
) -> dict:
    return {"last": {"nvis_status": nvis_status, "mainland_status": mainland_status, "timestamp_utc": timestamp_utc}}
