import html
import json
from pathlib import Path

from src.scrape.base import now_iso


DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "propagation.json"


def _format_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    if value.endswith("Z"):
        return value.replace("Z", "+00:00")
    return value


def _band_rows(bands: dict) -> str:
    rows = []
    for band, info in bands.items():
        median = info.get("median_snr_db")
        median_text = f"{median:.1f} dB" if isinstance(median, (int, float)) else "—"
        paths = info.get("paths", 0)
        rows.append(
            "<tr>"
            f"<td>{html.escape(band)}</td>"
            f"<td>{median_text}</td>"
            f"<td>{paths}</td>"
            "</tr>"
        )
    return "".join(rows)


def scrape() -> dict:
    if not DATA_PATH.exists():
        return {
            "id": "propagation",
            "label": "Radio Propagation",
            "retrieved_at": now_iso(),
            "source_urls": [],
            "html": "<p>Propagation data not available.</p>",
            "error": "Propagation JSON missing.",
            "stale": True,
        }
    try:
        payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "id": "propagation",
            "label": "Radio Propagation",
            "retrieved_at": now_iso(),
            "source_urls": [],
            "html": "<p>Propagation data could not be parsed.</p>",
            "error": "Propagation JSON invalid.",
            "stale": True,
        }

    nvis_payload = payload.get("nvis", {}) or {}
    mainland_payload = payload.get("mainland", {}) or {}
    nvis = nvis_payload.get("bands", {})
    mainland = mainland_payload.get("bands", {})
    updated_at = _format_timestamp(payload.get("timestamp_utc")) or now_iso()

    interisland_rows = _band_rows(nvis)
    mainland_rows = _band_rows(mainland)
    nvis_meta = (
        f"Status: {html.escape(str(nvis_payload.get('status', 'UNKNOWN')))} | "
        f"Confidence: {html.escape(str(nvis_payload.get('confidence', 'UNKNOWN')))}"
    )
    mainland_meta = (
        f"Status: {html.escape(str(mainland_payload.get('status', 'UNKNOWN')))} | "
        f"Confidence: {html.escape(str(mainland_payload.get('confidence', 'UNKNOWN')))}"
    )
    body = (
        "<p class=\"info\">Methodology: Aggregated PSKReporter spots over a last 60-minute window, "
        "grouped by band and region. Median SNR is from reported spots; total paths "
        "counts unique sender/receiver pairs.</p>"
        "<h3>Interisland</h3>"
        f"<p class=\"status\">{nvis_meta}</p>"
        "<table>"
        "<thead><tr><th>Band</th><th>Median SNR</th><th>Paths</th></tr></thead>"
        f"<tbody>{interisland_rows}</tbody>"
        "</table>"
        "<h3>Hawaii &larr;&rarr; Mainland</h3>"
        f"<p class=\"status\">{mainland_meta}</p>"
        "<table>"
        "<thead><tr><th>Band</th><th>Median SNR</th><th>Paths</th></tr></thead>"
        f"<tbody>{mainland_rows}</tbody>"
        "</table>"
    )

    return {
        "id": "propagation",
        "label": "Radio Propagation (<a href=\"https://pskreporter.info\">PSKReporter</a>)",
        "retrieved_at": updated_at,
        "source_urls": ["https://pskreporter.info"],
        "html": body,
        "error": None,
        "stale": False,
        "layout": "full",
    }
