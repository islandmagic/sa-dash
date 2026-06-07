from src.render.html import render_html


def test_render_html_shows_stale_and_error_for_cached_fallback():
    providers = [
        {
            "id": "kiuc",
            "label": "KIUC",
            "retrieved_at": "2026-04-26T10:00:00-10:00",
            "html": "<p>Cached outage data.</p>",
            "error": "Fetch failed: timeout. Using cached data.",
            "stale": True,
        }
    ]
    html = render_html("Kauai", providers, "2026-04-26T12:00:00-10:00")

    assert 'class="module module--stale"' in html
    assert "status-badge--stale" in html
    assert "Stale</span>" in html
    assert "Fetch failed: timeout. Using cached data." in html
    assert "Cached outage data." in html


def test_render_html_omits_stale_indicator_for_fresh_provider():
    providers = [
        {
            "id": "kiuc",
            "label": "KIUC",
            "retrieved_at": "2026-04-26T10:00:00-10:00",
            "html": "<p>Fresh data.</p>",
            "error": None,
            "stale": False,
        }
    ]
    html = render_html("Kauai", providers, "2026-04-26T12:00:00-10:00")

    assert 'class="module module--stale"' not in html
    assert "<p class=\"provider-status\">" not in html
    assert 'id="kiuc"' in html
