import html
from datetime import datetime, timedelta, timezone

from src.scrape.base import fetch_json, now_iso


KIUC_URL = "https://kiuc.outagemap.coop"
KIUC_SUMMARY_URL = (
    "https://outagemap-data.cloud.coop/kiuc/Hosted_Outage_Map/summary.json"
)

ZIP_ORDER = [
    ("96714", "Hanalei"),
    ("96722", "Princeville"),
    ("96754", "Kilauea"),
    ("96703", "Anahola"),
    ("96751", "Kealia"),
    ("96746", "Kapaa"),
    ("96766", "Lihue"),
    ("96756", "Koloa"),
    ("96765", "Lawai"),
    ("96741", "Kalaheo"),
    ("96705", "Eleele"),
    ("96716", "Hanapepe"),
    ("96769", "Makaweli"),
    ("96747", "Kaumakani"),
    ("96796", "Waimea"),
    ("96752", "Kekaha"),
]

ZIP_NAME = {zip_code: name for zip_code, name in ZIP_ORDER}
ZIP_INDEX = {zip_code: index for index, (zip_code, _) in enumerate(ZIP_ORDER)}


def _format_ts(epoch_ms: int | None) -> str:
    if not epoch_ms:
        return "unknown"
    hst = timezone(timedelta(hours=-10))
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=hst)
    return dt.strftime("%Y-%m-%d %H:%M HST")


def _extract_zip_rows(summary: dict) -> list[tuple[str, str, int, int, float]]:
    region_sets = summary.get("regionDataSets", [])
    for dataset in region_sets:
        if dataset.get("id") == "omszip":
            rows = []
            for region in dataset.get("regions", []):
                zip_code = region.get("id")
                number_out = region.get("numberOut", 0)
                number_served = region.get("numberServed", 0)
                if not zip_code:
                    continue
                name = ZIP_NAME.get(zip_code, "Unknown")
                pct_out = (number_out / number_served * 100) if number_served else 0.0
                rows.append((zip_code, name, number_out, number_served, pct_out))
            rows.sort(key=lambda row: ZIP_INDEX.get(row[0], 999))
            return rows
    return []


def scrape() -> dict:
    summary = fetch_json(KIUC_SUMMARY_URL)
    link_label = "KIUC Outage Center"

    rows = _extract_zip_rows(summary)
    last_update = _format_ts(summary.get("lastUpdate"))
    total_served = summary.get("totalServed")
    outages = summary.get("outages", [])
    total_out = sum(outage.get("nbrOut", 0) for outage in outages)
    parts = []

    if rows:
        table_rows = "".join(
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{affected}</td>"
            f"<td>{pct_out:.0f}%</td>"
            "</tr>"
            for zip_code, name, affected, served, pct_out in rows
        )
        parts.append(
            f"<h3>{total_out or 0} Outages</h3>"
            "<table>"
            "<thead><tr>"
            "<th>Area</th><th>Outage</th><th></th>"
            "</tr></thead>"
            f"<tbody>{table_rows}</tbody></table>"
        )
    else:
        parts.append("<p>Status data unavailable.</p>")

    parts.append(
        "<p>"
        f"Last update: {html.escape(last_update)}"
        + "</p>"
    )

    block_html = "".join(parts)

    return {
        "id": "kiuc",
        "label": f"Power (<a href=\"{KIUC_URL}\">KIUC</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [KIUC_URL, KIUC_SUMMARY_URL],
        "html": block_html,
        "error": None,
        "stale": False,
    }
