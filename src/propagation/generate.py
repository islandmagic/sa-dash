from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from src.propagation.config import GRID_QUERIES, WINDOW_MIN
from src.propagation.parse import dedupe_records, parse_reports
from src.propagation.pskreporter import (
    build_query_url,
    fetch_reports,
    last_fetch_utc,
    request_count_last_hour,
)
from src.propagation.score import (
    classify_records,
    default_state,
    summarize_indicators,
    update_state,
)


def _read_state(path: Path) -> dict:
    if not path.exists():
        return default_state()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_state()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def generate(output_path: Path, cache_path: Path, state_path: Path, now: datetime | None = None) -> dict:
    now_utc = (now or datetime.now(tz=timezone.utc)).astimezone(timezone.utc)
    anchors_this_run = GRID_QUERIES

    all_records = []
    anchors_reporting = set()
    notes: list[str] = []
    psk_ok = False

    for grid in anchors_this_run:
        url = build_query_url(grid)
        result = fetch_reports(url, cache_path, now_utc)
        if result.error:
            notes.append(f"{grid}: {result.error}")
        if not result.text:
            continue
        psk_ok = True
        records = parse_reports(result.text, now_utc)
        if records:
            anchors_reporting.add(grid)
        all_records.extend(records)

    deduped = dedupe_records(all_records)
    nvis_records, mainland_records = classify_records(deduped)

    prev_state = _read_state(state_path).get("last", {})
    nvis_summary, mainland_summary = summarize_indicators(
        nvis_records,
        mainland_records,
        prev_state,
        anchors_reporting=len(anchors_reporting),
        last_fetch_utc=last_fetch_utc(cache_path),
    )

    timestamp_utc = now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "timestamp_utc": timestamp_utc,
        "window_minutes": WINDOW_MIN,
        "nvis": {
            "status": nvis_summary.status,
            "vara_class": nvis_summary.vara_class,
            "score": nvis_summary.score,
            "confidence": nvis_summary.confidence,
            "bands": nvis_summary.bands,
            "explain": nvis_summary.explain,
        },
        "mainland": {
            "status": mainland_summary.status,
            "vara_class": mainland_summary.vara_class,
            "score": mainland_summary.score,
            "confidence": mainland_summary.confidence,
            "bands": mainland_summary.bands,
            "explain": mainland_summary.explain,
        },
        "sources": {
            "pskreporter": {
                "ok": psk_ok,
                "last_fetch_utc": last_fetch_utc(cache_path),
                "requests_last_hour": request_count_last_hour(cache_path, now_utc),
            },
            "notes": "; ".join(notes) if notes else "",
        },
    }

    _write_json(output_path, payload)
    new_state = update_state(
        _read_state(state_path),
        nvis_summary.status,
        mainland_summary.status,
        timestamp_utc,
    )
    _write_json(state_path, new_state)
    return payload


def _print_ip_info() -> None:
    try:
        with urlopen("https://api.ipify.org?format=json", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
            ip = payload.get("ip")
            if ip:
                print(f"Public IP: {ip}")
    except Exception:
        print("Public IP: unknown")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate propagation summary JSON.")
    parser.add_argument(
        "--output",
        default="data/propagation.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--cache-path",
        default="data/cache/propagation_pskreporter.json",
        help="Cache file for PSKReporter responses",
    )
    parser.add_argument(
        "--state-path",
        default="data/propagation_state.json",
        help="State file for hysteresis",
    )
    parser.add_argument(
        "--now",
        help="Override current UTC time (ISO format)",
    )
    args = parser.parse_args()

    now = None
    if args.now:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
    generate(Path(args.output), Path(args.cache_path), Path(args.state_path), now=now)
    _print_ip_info()


if __name__ == "__main__":
    main()
