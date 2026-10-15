import json
from pathlib import Path
from unittest.mock import patch

from src.scrape.helpmefind import _parse_town, _is_fresh, scrape

FIXTURES = Path(__file__).parent / "fixtures" / "json"


def test_parse_town():
    assert _parse_town("2535 Kolo Rd, Kilauea, HI 96754, USA") == "Kilauea"
    assert _parse_town(None) == ""


def test_is_fresh_old_report():
    assert _is_fresh("2020-01-01T00:00:00Z") is False


def test_scrape_groups_reports():
    payload = json.loads((FIXTURES / "helpmefind_gas.json").read_text(encoding="utf-8"))

    # Force all reports fresh by rewriting created_at
    from datetime import datetime, timezone, timedelta

    now = datetime.now(tz=timezone.utc)
    for row in payload.get("results") or []:
        if row.get("report_id"):
            row["created_at"] = (now - timedelta(hours=5)).isoformat().replace("+00:00", "Z")

    def fake_json(url, *args, **kwargs):
        if "item=" in url:
            return payload
        return {"activity": []}

    with patch("src.scrape.helpmefind.fetch_json", side_effect=fake_json):
        result = scrape()
    assert result["id"] == "helpmefind"
    assert "Ice" in result["html"] or "ice" in result["text"].lower()
    assert "helpmefind" in result["html"].lower()
