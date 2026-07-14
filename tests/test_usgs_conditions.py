from src.scrape.usgs_water_levels import (
    _classify_percentile,
    _should_classify,
    _should_omit_row,
)

PCTS = {"p10": 10.0, "p25": 25.0, "p75": 75.0, "p90": 90.0, "p98": 98.0}


def test_classify_percentile_bands():
    assert _classify_percentile(5.0, PCTS) == "Low"
    assert _classify_percentile(10.0, PCTS) == "Below normal"
    assert _classify_percentile(25.0, PCTS) == "Normal"
    assert _classify_percentile(74.9, PCTS) == "Normal"
    assert _classify_percentile(75.0, PCTS) == "Above normal"
    assert _classify_percentile(90.0, PCTS) == "Much above normal"
    assert _classify_percentile(98.0, PCTS) == "High"
    assert _classify_percentile(150.0, PCTS) == "High"


def test_classify_percentile_none_is_unknown():
    assert _classify_percentile(None, PCTS) == "Unknown"


def test_should_classify_flow_any_site():
    assert _should_classify("16060000", "00060") is True
    assert _should_classify("16103000", "00060") is True


def test_should_classify_level_only_allowed_sites():
    assert _should_classify("16104200", "00065") is True
    assert _should_classify("16094150", "00065") is True
    assert _should_classify("16103000", "00065") is False
    assert _should_classify("16060000", "00065") is False


def test_should_omit_row_bogus_level():
    assert _should_omit_row("16103000", "00065") is True
    assert _should_omit_row("16097500", "00065") is True
    assert _should_omit_row("16060000", "00065") is True


def test_should_not_omit_allowed_level_or_flow():
    assert _should_omit_row("16104200", "00065") is False
    assert _should_omit_row("16094150", "00065") is False
    assert _should_omit_row("16060000", "00060") is False
