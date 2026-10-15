from pathlib import Path
from unittest.mock import patch

from src.scrape.hidot_highways_news import _is_kauai_item
from src.scrape.hidot_status import _parse_kauai_table, _parse_lane_closures, _status_class, scrape

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def test_status_class_colors():
    assert _status_class("Open") == "status-green"
    assert _status_class("Closed") == "status-red"
    assert _status_class("Local access only from Hanalei") == "status-yellow"


def test_parse_kauai_weather_table():
    html = (FIXTURES / "hidot_weather.html").read_text(encoding="utf-8")
    rows = _parse_kauai_table(html)
    assert rows
    facilities = " ".join(r["facility"].lower() for r in rows)
    assert "route" in facilities or "kuhio" in facilities or "nawiliwili" in facilities or "kaumualii" in facilities


def test_parse_lane_closures():
    html = (FIXTURES / "hidot_lane.html").read_text(encoding="utf-8")
    week, entries = _parse_lane_closures(html)
    assert week or entries
    if entries:
        assert entries[0].get("place") or entries[0].get("detail")


def test_is_kauai_news_item():
    assert _is_kauai_item({"title": "Update", "summary": "LĪHUʻE – crews clearing debris"})
    assert _is_kauai_item({"title": "Kauai lane closures", "summary": ""})
    assert not _is_kauai_item({"title": "Oahu project", "summary": "HONOLULU – work continues"})


def test_combined_scrape_includes_news_and_status():
    weather = (FIXTURES / "hidot_weather.html").read_text(encoding="utf-8")
    lane = (FIXTURES / "hidot_lane.html").read_text(encoding="utf-8")
    news = [
        {
            "title": "Kauai bridge update",
            "url": "https://example.com/n",
            "summary": "LĪHUʻE – detail",
            "published": "2026-10-14 00:00 HST",
        }
    ]

    def fake_fetch(url, *args, **kwargs):
        if "weather-traffic" in url:
            return weather
        if "roadwork" in url:
            return lane
        return ""

    with (
        patch("src.scrape.hidot_status.fetch_html", side_effect=fake_fetch),
        patch("src.scrape.hidot_status.fetch_kauai_news", return_value=news),
    ):
        result = scrape()
    assert result["id"] == "hidot_status"
    assert "Roads" in result["label"]
    assert "HDOT highway news" in result["html"]
    assert "Kauai bridge update" in result["html"]
    assert "Facility" in result["html"] or "Route" in result["html"]
    assert "hidot_highways_news" not in result["id"]
