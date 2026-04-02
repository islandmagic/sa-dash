"""Normalize and pivot HCDP mesonet measurement responses."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def normalize_measurements_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict) and "data" in payload and "index" in payload:
        idx = payload["index"]
        rows = payload["data"]
        return [dict(zip(idx, row)) for row in rows if isinstance(row, (list, tuple))]
    if isinstance(payload, dict):
        return [payload]
    return []


def _parse_timestamp(raw: Any) -> datetime | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _float_value(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def pivot_latest_measurements(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Long-format input: one record per (timestamp, station_id, variable).
    Returns one dict per station with latest value per variable and metadata.
    """
    latest: dict[tuple[str, str], tuple[datetime, dict[str, Any]]] = {}
    for row in records:
        sid = str(row.get("station_id") or "").strip()
        var = str(row.get("variable") or "").strip()
        if not sid or not var:
            continue
        ts = _parse_timestamp(row.get("timestamp"))
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        key = (sid, var)
        prev = latest.get(key)
        if prev is None or ts > prev[0]:
            latest[key] = (ts, row)

    by_station: dict[str, dict[str, Any]] = {}
    for (sid, var), (ts, row) in latest.items():
        bucket = by_station.setdefault(sid, {"_points": []})
        bucket["_points"].append((ts, var, row))

    out: list[dict[str, Any]] = []
    for sid in sorted(by_station.keys()):
        bucket = by_station[sid]
        points: list[tuple[datetime, str, dict[str, Any]]] = bucket["_points"]
        ts_max = max(t for t, _, _ in points)
        meta_row = next((r for t, _, r in points if t == ts_max), points[0][2])
        values: dict[str, float | None] = {}
        for _, var, row in points:
            values[var] = _float_value(row.get("value"))

        out.append(
            {
                "station_id": sid,
                # `join_metadata` may be false, in which case station_name isn't present.
                "station_name": str(meta_row.get("station_name") or sid).strip(),
                "nws_id": meta_row.get("nws_id"),
                "timestamp": ts_max,
                "values": values,
            }
        )
    return out

