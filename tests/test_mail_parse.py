"""Tests for county alert email parsing against Lowell fixtures."""

from __future__ import annotations

import email
from pathlib import Path

from src.mail.client import decode_header_value, extract_body
from src.mail.parse import (
    clean_body,
    detect_family,
    extract_facts,
    merge_status_board,
    parse_headline,
    parse_message,
    sender_allowed,
    strip_everbridge,
    strip_govdelivery,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mail"


def _load_eml(name: str) -> dict:
    raw = (FIXTURES / name).read_bytes()
    msg = email.message_from_bytes(raw)
    plain, html = extract_body(msg)
    return {
        "message_id": (msg.get("Message-ID") or name).strip(),
        "from": decode_header_value(msg.get("From")),
        "raw_from": msg.get("From") or "",
        "subject": decode_header_value(msg.get("Subject")),
        "date": msg.get("Date") or "",
        "plain": plain,
        "html": html,
    }


def test_family_detection_gd_pio():
    raw = _load_eml("gd_pio_glance.eml")
    assert detect_family(raw["raw_from"], raw["subject"], raw["plain"]).startswith("GD-")


def test_family_detection_eb_kiuc():
    raw = _load_eml("eb_kiuc.eml")
    assert detect_family(raw["raw_from"], raw["subject"], raw["plain"]) == "EB-KIUC"


def test_family_detection_eb_alert():
    raw = _load_eml("eb_alert_greenwaste.eml")
    fam = detect_family(raw["raw_from"], raw["subject"], raw["plain"])
    assert fam == "EB-AlertKauai"


def test_family_detection_gd_kpd():
    raw = _load_eml("gd_kpd_roads.eml")
    assert detect_family(raw["raw_from"], raw["subject"], raw["plain"]) == "GD-KPD"


def test_family_detection_gd_dow():
    raw = _load_eml("gd_dow_boil.eml")
    assert detect_family(raw["raw_from"], raw["subject"], raw["plain"]) == "GD-DOW"


def test_govdelivery_strips_footer():
    raw = _load_eml("gd_pio_glance.eml")
    cleaned = strip_govdelivery(raw["plain"], raw["subject"])
    assert "SUBSCRIBER SERVICES" not in cleaned
    assert "Manage Subscriptions" not in cleaned
    assert "This email was sent to" not in cleaned
    assert "Granicus" not in cleaned


def test_everbridge_strips_boilerplate():
    raw = _load_eml("eb_alert_greenwaste.eml")
    cleaned = strip_everbridge(raw["plain"])
    assert "Message Sender:" not in cleaned
    assert "Notification Status:" not in cleaned
    assert "To stop receiving" not in cleaned


def test_headline_nr_and_revision():
    h = parse_headline(
        "NR 09-14-26 (Sept. 14, 5:40 p.m., County of Kauaʻi, Hurricane Lowell Recovery Update)"
    )
    assert h["id"].upper().startswith("NR")
    assert "Hurricane" in h["title"] or "Recovery" in h["title"] or "Sept" in h["title"]

    rev = parse_headline(
        "Revision: NR 09-21-26 (Sept. 21, 4 p.m., County of Kauaʻi, Hurricane Lowell Recovery Update)"
    )
    assert rev["revision"] is True


def test_pio_glance_and_power_facts():
    parsed = parse_message(_load_eml("gd_pio_glance.eml"))
    assert parsed["family"].startswith("GD-")
    # Glance bullets or power facts should be present
    keys = {f["key"] for f in parsed["facts"]}
    assert "power_restored_pct" in keys or "customers_out" in keys or parsed["glance"]
    assert "SUBSCRIBER SERVICES" not in parsed["body"]


def test_kpd_road_closures():
    parsed = parse_message(_load_eml("gd_kpd_roads.eml"))
    assert parsed["family"] == "GD-KPD"
    assert "roads" in parsed["topics"] or any(
        f["key"] == "road_closures" for f in parsed["facts"]
    )


def test_boil_water_cancel():
    parsed = parse_message(_load_eml("gd_dow_boil.eml"))
    boil = [f for f in parsed["facts"] if f["key"].startswith("boil_water")]
    assert boil
    assert any(f["value"] == "canceled" for f in boil)


def test_green_waste_site_status_from_subject():
    parsed = parse_message(_load_eml("eb_alert_greenwaste_close.eml"))
    site_facts = [f for f in parsed["facts"] if f["key"].startswith("site_status")]
    # Subject mentions Kilauea closed / Kapaa open — at least one site fact
    assert site_facts or "debris" in parsed["topics"]


def test_status_board_supersession():
    board: dict = {}
    older = [{"key": "power_restored_pct", "value": 75, "label": "75%", "at": "2026-09-12T00:00:00+00:00"}]
    newer = [{"key": "power_restored_pct", "value": 82, "label": "82%", "at": "2026-09-15T00:00:00+00:00"}]
    board = merge_status_board(board, older)
    board = merge_status_board(board, newer)
    assert board["power_restored_pct"]["value"] == 82


def test_sender_allow_list_matches_relayed_from():
    assert sender_allowed(
        "CountyofKauaiPIO_at_public_govdelivery_com_9@icloud.com",
        ["govdelivery.com"],
    )
    assert sender_allowed(
        "CountyofKauaiPIO_at_public_govdelivery.com_9@icloud.com",
        ["govdelivery.com"],
    )
    assert sender_allowed("noreply@everbridge.net", ["everbridge.net"])
    assert not sender_allowed("friend@gmail.com", ["govdelivery.com", "everbridge.net"])


def test_clean_body_dispatch():
    raw = _load_eml("eb_kiuc.eml")
    body = clean_body("EB-KIUC", raw["plain"], raw["subject"])
    assert "confidential" not in body.lower() or "ALERT SYSTEM" not in body
    assert len(body) > 20
