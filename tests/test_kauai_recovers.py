from pathlib import Path

from src.scrape.kauai_recovers import (
    _parse_debris,
    _parse_food_schedule,
    _parse_pharmacies,
)

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def test_parse_debris_sites():
    html = (FIXTURES / "kr_debris.html").read_text(encoding="utf-8")
    sites, notes, updated = _parse_debris(html)
    assert sites, "expected debris sites"
    names = " ".join(s["name"].lower() for s in sites)
    assert "hanalei" in names or "kīlauea" in names or "kilauea" in names
    assert any(s.get("hours") for s in sites)
    # At least one accepts list
    assert any(s.get("accepts") for s in sites)


def test_parse_food_schedule():
    html = (FIXTURES / "kr_help.html").read_text(encoding="utf-8")
    last_updated, food = _parse_food_schedule(html)
    assert food
    assert "211" in food or "Food" in food or "distribution" in food.lower()


def test_parse_pharmacies():
    html = (FIXTURES / "kr_health.html").read_text(encoding="utf-8")
    pharmacies = _parse_pharmacies(html)
    assert pharmacies
    assert any("808" in (p.get("phone") or p.get("name") or "") for p in pharmacies)


def test_skip_on_empty_debris(monkeypatch):
    from src.scrape import kauai_recovers as mod

    monkeypatch.setattr(mod, "_safe_fetch", lambda url: "<html><body><p>gone</p></body></html>")
    result = mod.scrape()
    assert result.get("skip") is True
