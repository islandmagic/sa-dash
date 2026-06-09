from pathlib import Path
from unittest.mock import patch

from src.generate import scrape_with_cache


def test_marinetraffic_cache_fallback_is_not_stale(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "marinetraffic_kauai.json"
    cache_file.write_text(
        '{"id":"marinetraffic_kauai","label":"Marine Traffic","html":"<p>ok</p>",'
        '"retrieved_at":"2026-06-08T10:00:00-10:00","stale":false,"error":null}',
        encoding="utf-8",
    )

    def fail():
        raise RuntimeError("403 Forbidden")

    with patch("src.generate.get_scraper", return_value=fail):
        result = scrape_with_cache("marinetraffic_kauai", cache_dir, offline=False)

    assert result["stale"] is False
    assert result["error"] is None
    assert "ok" in result["html"]


def test_other_scrapers_still_mark_stale_on_cache_fallback(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "kiuc.json"
    cache_file.write_text(
        '{"id":"kiuc","label":"KIUC","html":"<p>cached</p>",'
        '"retrieved_at":"2026-06-08T10:00:00-10:00","stale":false,"error":null}',
        encoding="utf-8",
    )

    def fail():
        raise RuntimeError("timeout")

    with patch("src.generate.get_scraper", return_value=fail):
        result = scrape_with_cache("kiuc", cache_dir, offline=False)

    assert result["stale"] is True
    assert "Fetch failed" in result["error"]
