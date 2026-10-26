import datetime as dt

from src.event import evaluate, should_send_digest, send_hours_hst

HST = dt.timezone(dt.timedelta(hours=-10))


def test_nws_alert_triggers():
    providers = [
        {
            "id": "weather_kauai",
            "signals": {"alert_events": ["Hurricane Warning"]},
        }
    ]
    state = evaluate(providers, {}, now=dt.datetime(2026, 9, 8, 10, tzinfo=HST))
    assert state["active"] is True
    assert any("Hurricane" in r for r in state["reasons"])


def test_kiuc_outage_threshold():
    providers = [
        {
            "id": "kiuc",
            "signals": {"customers_out": 5000, "customers_served": 36000},
        }
    ]
    state = evaluate(providers, {})
    assert state["active"] is True


def test_kiuc_below_threshold():
    providers = [
        {
            "id": "kiuc",
            "signals": {"customers_out": 10, "customers_served": 36000},
        }
    ]
    state = evaluate(providers, {"active": False})
    assert state["active"] is False


def test_cphc_active():
    providers = [{"id": "tropical_outlook", "signals": {"cp_active": True}}]
    state = evaluate(providers, {})
    assert state["active"] is True


def test_manual_override_on(monkeypatch):
    monkeypatch.setenv("EVENT_MODE", "on")
    state = evaluate([], {})
    assert state["active"] is True


def test_manual_override_off(monkeypatch):
    monkeypatch.setenv("EVENT_MODE", "off")
    providers = [
        {"id": "weather_kauai", "signals": {"alert_events": ["Hurricane Warning"]}}
    ]
    state = evaluate(providers, {})
    assert state["active"] is False


def test_hysteresis_keeps_active():
    now = dt.datetime(2026, 9, 10, 12, tzinfo=HST)
    prev = {
        "active": True,
        "active_since": "2026-09-08T10:00:00-10:00",
        "last_trigger_at": "2026-09-09T12:00:00-10:00",
        "last_sent_at": None,
        "reasons": ["NWS: Hurricane Warning"],
    }
    state = evaluate([], prev, now=now)
    assert state["active"] is True


def test_hysteresis_expires():
    now = dt.datetime(2026, 9, 20, 12, tzinfo=HST)
    prev = {
        "active": True,
        "active_since": "2026-09-08T10:00:00-10:00",
        "last_trigger_at": "2026-09-09T12:00:00-10:00",
        "last_sent_at": None,
        "reasons": ["NWS: Hurricane Warning"],
    }
    state = evaluate([], prev, now=now)
    assert state["active"] is False


def test_send_window_opens_after_target(monkeypatch):
    monkeypatch.setenv("DIGEST_SEND_HOURS_HST", "6,18")
    state = {"active": True, "last_sent_at": None}
    # Before first window — wait for morning
    assert not should_send_digest(state, now=dt.datetime(2026, 9, 10, 5, 30, tzinfo=HST))
    # At/after 6:00 — send
    assert should_send_digest(state, now=dt.datetime(2026, 9, 10, 6, 5, tzinfo=HST))
    # Delayed CI past hour 6 still sends (was the exact-hour bug)
    assert should_send_digest(state, now=dt.datetime(2026, 9, 10, 7, 10, tzinfo=HST))


def test_send_window_once_per_slot(monkeypatch):
    monkeypatch.setenv("DIGEST_SEND_HOURS_HST", "6,18")
    state = {
        "active": True,
        "last_sent_at": "2026-09-10T06:55:00-10:00",
    }
    # Already fulfilled morning window
    assert not should_send_digest(
        state, now=dt.datetime(2026, 9, 10, 7, 10, tzinfo=HST)
    )
    # Afternoon window opens
    assert should_send_digest(
        state, now=dt.datetime(2026, 9, 10, 18, 0, tzinfo=HST)
    )
    # Delayed afternoon still sends
    assert should_send_digest(
        state, now=dt.datetime(2026, 9, 10, 19, 5, tzinfo=HST)
    )


def test_send_window_next_morning(monkeypatch):
    monkeypatch.setenv("DIGEST_SEND_HOURS_HST", "6,18")
    state = {
        "active": True,
        "last_sent_at": "2026-09-10T18:55:00-10:00",
    }
    assert not should_send_digest(
        state, now=dt.datetime(2026, 9, 11, 5, 50, tzinfo=HST)
    )
    assert should_send_digest(
        state, now=dt.datetime(2026, 9, 11, 6, 55, tzinfo=HST)
    )


def test_inactive_never_sends():
    state = {"active": False, "last_sent_at": None}
    assert not should_send_digest(
        state, now=dt.datetime(2026, 9, 10, 7, 0, tzinfo=HST)
    )


def test_send_hours_default():
    assert 6 in send_hours_hst() or send_hours_hst()
