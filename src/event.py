"""Event-mode detection with hysteresis for digest push gating."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

HST = dt.timezone(dt.timedelta(hours=-10))

ALERT_EVENTS = {
    "Hurricane Warning",
    "Hurricane Watch",
    "Tropical Storm Warning",
    "Tropical Storm Watch",
    "Flash Flood Warning",
    "Flood Warning",
    "High Wind Warning",
    "High Surf Warning",
}
TSUNAMI_PREFIX = "Tsunami"

DEFAULT_OUTAGE_FLOOR = 1500
DEFAULT_OUTAGE_PCT = 0.05
DEFAULT_HYSTERESIS_HOURS = 72
DEFAULT_SEND_HOURS = (6, 18)
DEFAULT_MIN_SEND_GAP_HOURS = 6


def _now_hst(now: dt.datetime | None = None) -> dt.datetime:
    if now is None:
        return dt.datetime.now(tz=HST)
    if now.tzinfo is None:
        return now.replace(tzinfo=HST)
    return now.astimezone(HST)


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HST)
    return parsed


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "active": False,
            "active_since": None,
            "last_trigger_at": None,
            "last_sent_at": None,
            "reasons": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "active": False,
            "active_since": None,
            "last_trigger_at": None,
            "last_sent_at": None,
            "reasons": [],
        }
    return {
        "active": bool(data.get("active")),
        "active_since": data.get("active_since"),
        "last_trigger_at": data.get("last_trigger_at"),
        "last_sent_at": data.get("last_sent_at"),
        "reasons": list(data.get("reasons") or []),
    }


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _collect_triggers(providers: list[dict]) -> list[str]:
    reasons: list[str] = []
    by_id = {p.get("id"): p for p in providers if p.get("id")}

    weather = by_id.get("weather_kauai") or {}
    alert_events = (weather.get("signals") or {}).get("alert_events") or []
    for name in alert_events:
        if not name:
            continue
        if name in ALERT_EVENTS or str(name).startswith(TSUNAMI_PREFIX):
            reasons.append(f"NWS: {name}")

    kiuc = by_id.get("kiuc") or {}
    signals = kiuc.get("signals") or {}
    customers_out = signals.get("customers_out")
    customers_served = signals.get("customers_served") or 0
    try:
        out = int(customers_out) if customers_out is not None else 0
        served = int(customers_served) if customers_served else 0
    except (TypeError, ValueError):
        out, served = 0, 0
    threshold = max(DEFAULT_OUTAGE_FLOOR, int(served * DEFAULT_OUTAGE_PCT) if served else DEFAULT_OUTAGE_FLOOR)
    if out >= threshold:
        reasons.append(f"KIUC: {out} customers out")

    tropical = by_id.get("tropical_outlook") or {}
    if (tropical.get("signals") or {}).get("cp_active"):
        reasons.append("CPHC: active cyclone")

    breaking = by_id.get("breaking_news") or {}
    if breaking and not breaking.get("skip") and (breaking.get("html") or "").strip():
        reasons.append("Breaking news banner set")

    return reasons


def evaluate(
    providers: list[dict],
    state: dict[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Evaluate event mode. Returns updated state dict."""
    now_hst = _now_hst(now)
    now_iso = now_hst.replace(microsecond=0).isoformat()
    state = dict(state or {})
    mode = (os.environ.get("EVENT_MODE") or "auto").strip().lower()

    triggers = _collect_triggers(providers)
    hysteresis_hours = DEFAULT_HYSTERESIS_HOURS
    try:
        hysteresis_hours = int(os.environ.get("EVENT_HYSTERESIS_HOURS") or DEFAULT_HYSTERESIS_HOURS)
    except ValueError:
        pass

    if mode == "on":
        return {
            "active": True,
            "active_since": state.get("active_since") or now_iso,
            "last_trigger_at": now_iso if triggers else state.get("last_trigger_at") or now_iso,
            "last_sent_at": state.get("last_sent_at"),
            "reasons": triggers or ["manual EVENT_MODE=on"],
        }
    if mode == "off":
        return {
            "active": False,
            "active_since": None,
            "last_trigger_at": state.get("last_trigger_at"),
            "last_sent_at": state.get("last_sent_at"),
            "reasons": [],
        }

    # auto
    if triggers:
        return {
            "active": True,
            "active_since": state.get("active_since") if state.get("active") else now_iso,
            "last_trigger_at": now_iso,
            "last_sent_at": state.get("last_sent_at"),
            "reasons": triggers,
        }

    last_trigger = _parse_iso(state.get("last_trigger_at"))
    if state.get("active") and last_trigger is not None:
        age = now_hst - last_trigger.astimezone(HST)
        if age <= dt.timedelta(hours=hysteresis_hours):
            return {
                "active": True,
                "active_since": state.get("active_since"),
                "last_trigger_at": state.get("last_trigger_at"),
                "last_sent_at": state.get("last_sent_at"),
                "reasons": list(state.get("reasons") or []) or ["hysteresis"],
            }

    return {
        "active": False,
        "active_since": None,
        "last_trigger_at": state.get("last_trigger_at"),
        "last_sent_at": state.get("last_sent_at"),
        "reasons": [],
    }


def send_hours_hst() -> tuple[int, ...]:
    raw = os.environ.get("DIGEST_SEND_HOURS_HST") or ""
    if not raw.strip():
        return DEFAULT_SEND_HOURS
    hours: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if token.isdigit():
            hours.append(int(token))
    return tuple(hours) if hours else DEFAULT_SEND_HOURS


def should_send_digest(state: dict[str, Any], now: dt.datetime | None = None) -> bool:
    """True when event is active, current HST hour is a send hour, and gap elapsed."""
    if not state.get("active"):
        return False
    now_hst = _now_hst(now)
    if now_hst.hour not in send_hours_hst():
        return False
    last_sent = _parse_iso(state.get("last_sent_at"))
    if last_sent is None:
        return True
    gap = dt.timedelta(hours=DEFAULT_MIN_SEND_GAP_HOURS)
    return now_hst - last_sent.astimezone(HST) >= gap
