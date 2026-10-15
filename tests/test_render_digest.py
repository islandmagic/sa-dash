from src.render.text import ascii_fold, html_to_text, render_digest, _mobile_summary


def test_ascii_fold_strips_diacritics():
    folded = ascii_fold("Kauaʻi")
    assert folded in {"Kauai", "Kaua'i"}
    assert all(ord(c) < 128 for c in folded)
    assert all(ord(c) < 128 for c in ascii_fold("Hanapēpē — green waste"))
    assert "Hanapepe" in ascii_fold("Hanapēpē")


def test_html_to_text_table_and_details():
    html = """
    <table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
    <details><summary>Title</summary><div>Body text here</div></details>
    """
    text = html_to_text(html)
    assert "1 | 2" in text or "A | B" in text
    assert "Title" in text
    assert "Body text" in text


def test_render_digest_ordering_and_cap():
    providers = [
        {
            "id": "global_events_wire",
            "label": "Global",
            "html": "<p>should be excluded</p>",
            "text": "excluded",
        },
        {
            "id": "kiuc",
            "label": "Power (KIUC)",
            "html": "<p>outages</p>",
            "text": "Power outages: 100",
        },
        {
            "id": "weather_kauai",
            "label": "Weather",
            "html": "<p>sunny</p>",
            "text": "Weather: sunny\n" + ("x" * 5000),
        },
        {
            "id": "time_wheel",
            "label": "Timezones",
            "html": "<p>skip me</p>",
            "text": "time",
        },
    ]
    digest = render_digest(
        "Kauai",
        providers,
        "2026-10-14T12:00:00-10:00",
        event={"active": True, "reasons": ["test"]},
    )
    assert "EVENT:" in digest
    assert "Power" in digest
    assert "Weather" in digest
    assert "excluded" not in digest.lower() or "Global" not in digest
    assert "time_wheel" not in digest.lower()
    assert "digest.txt" in digest
    assert len(digest) <= 12_500


def test_mobile_summary_from_table_skips_header():
    table_text = (
        "Town | Status | Detail\n"
        "Princeville | Degraded | limited\n"
        "Kilauea | OK |\n"
    )
    assert _mobile_summary(table_text) == "Princeville: Degraded; Kilauea: OK"


def test_mobile_summary_keeps_scraper_text():
    assert (
        _mobile_summary("Verizon: Princeville: Degraded; Kilauea: OK")
        == "Verizon: Princeville: Degraded; Kilauea: OK"
    )


def test_digest_includes_mobile_status_not_just_header():
    providers = [
        {
            "id": "verizon_mobile",
            "label": "Verizon Mobile (Verizon)",
            "html": (
                "<table><thead><tr><th>Town</th><th>Status</th><th>Detail</th></tr></thead>"
                "<tbody><tr><td>Princeville</td><td>Degraded</td><td>x</td></tr>"
                "<tr><td>Kilauea</td><td>OK</td><td></td></tr></tbody></table>"
            ),
        },
        {
            "id": "att_mobile",
            "label": "AT&T Mobile (AT&T)",
            "text": "AT&T: Princeville: OK; Kilauea: OK",
            "html": "<p>ignored</p>",
        },
    ]
    digest = render_digest("Kauai", providers, "2026-10-14T12:00:00-10:00")
    assert "Princeville: Degraded" in digest
    assert "Kilauea: OK" in digest
    assert "AT&T: Princeville: OK" in digest
    assert "Town | Status | Detail" not in digest
