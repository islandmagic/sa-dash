from src.scrape.info_kauai import (
    _build_winlink_rows,
    _classify_hours,
    _format_last_status_hst,
    _index_gateways_by_base,
    _parse_winlink_response,
)


def test_classify_hours_ok():
    label, css = _classify_hours(0)
    assert label == "OK"
    assert css == "status-green"

    label, css = _classify_hours(12)
    assert label == "OK"
    assert css == "status-green"


def test_classify_hours_warning():
    label, css = _classify_hours(13)
    assert label == "Warning"
    assert css == "status-yellow"

    label, css = _classify_hours(24)
    assert label == "Warning"
    assert css == "status-yellow"


def test_classify_hours_error():
    label, css = _classify_hours(25)
    assert label == "Error"
    assert css == "status-red"

    label, css = _classify_hours(None)
    assert label == "Error"
    assert css == "status-red"


def test_index_gateways_by_base_picks_freshest():
    gateways = [
        {"BaseCallsign": "KH6S", "HoursSinceStatus": 10, "LastStatus": "older"},
        {"BaseCallsign": "KH6S", "HoursSinceStatus": 2, "LastStatus": "newer"},
        {"BaseCallsign": "AH7L", "HoursSinceStatus": 5, "LastStatus": "ah7l"},
    ]
    indexed = _index_gateways_by_base(gateways)

    assert indexed["KH6S"]["LastStatus"] == "newer"
    assert indexed["AH7L"]["LastStatus"] == "ah7l"
    assert "WH6FG" not in indexed


def test_build_winlink_rows_missing_station_is_error():
    rows = _build_winlink_rows(
        {
            "KH6S": {
                "HoursSinceStatus": 1,
                "LastStatus": "Sun, 14 Jun 2026 05:21:00 UTC",
                "Timestamp": "/Date(1781414460000)/",
            }
        }
    )
    assert "status-green" in rows
    assert "2026-06-13 19:21 HST" in rows
    assert "WH6FG" in rows
    assert "status-red" in rows
    assert rows.count("Error") >= 3


def test_format_last_status_hst_from_last_status_string():
    gateway = {"LastStatus": "Sun, 14 Jun 2026 05:21:00 UTC"}
    assert _format_last_status_hst(gateway) == "2026-06-13 19:21 HST"


def test_format_last_status_hst_from_timestamp():
    gateway = {"Timestamp": "/Date(1781414460000)/"}
    assert _format_last_status_hst(gateway) == "2026-06-13 19:21 HST"


def test_build_winlink_rows_fetch_failed():
    rows = _build_winlink_rows({}, fetch_failed=True)
    assert rows.count("Status unavailable") == 4
    assert rows.count("status-red") == 4


def test_parse_winlink_response_json():
    payload = _parse_winlink_response('{"Gateways": []}')
    assert payload == {"Gateways": []}


def test_parse_winlink_response_jsonp():
    payload = _parse_winlink_response('jQuery123({"Gateways": [{"BaseCallsign": "KH6S"}]})')
    assert payload["Gateways"][0]["BaseCallsign"] == "KH6S"
