from pathlib import Path
from unittest.mock import patch

from src.scrape.rss import parse_rss
from src.scrape.tropical_outlook import _basin_block, scrape

FIXTURES = Path(__file__).parent / "fixtures" / "json"


def test_quiet_cphc_basin():
    xml = (FIXTURES / "cphc.xml").read_text(encoding="utf-8")
    items = parse_rss(xml, limit=15)
    html, active, text_lines = _basin_block("Central Pacific (CPHC)", items)
    assert active is False
    assert "no tropical cyclones" in " ".join(text_lines).lower() or "No tropical" in html


def test_epac_may_have_storm():
    xml = (FIXTURES / "epac.xml").read_text(encoding="utf-8")
    items = parse_rss(xml, limit=15)
    html, active, text_lines = _basin_block("Eastern Pacific (NHC)", items)
    # Fixture may or may not have an active storm; structure should render
    assert "Eastern Pacific" in html
    assert text_lines


def test_scrape_uses_feeds():
    cp = (FIXTURES / "cphc.xml").read_text(encoding="utf-8")
    ep = (FIXTURES / "epac.xml").read_text(encoding="utf-8")

    def fake_fetch(url, *args, **kwargs):
        if "index-cp" in url:
            return cp
        return ep

    with patch("src.scrape.tropical_outlook.scrape_rss") as mock_rss:
        mock_rss.side_effect = lambda url, limit=15: parse_rss(
            cp if "index-cp" in url else ep, limit=limit
        )
        result = scrape()
    assert result["id"] == "tropical_outlook"
    assert "signals" in result
    assert "cp_active" in result["signals"]
    assert result.get("text")
