"""CPHC / NHC EPAC tropical cyclone outlook."""

from __future__ import annotations

import html as html_module
import re

from src.scrape.base import now_iso
from src.scrape.rss import parse_rss, scrape_rss

CPHC_URL = "https://www.nhc.noaa.gov/index-cp.xml"
EPAC_URL = "https://www.nhc.noaa.gov/index-ep.xml"


def _first_paragraph(summary: str) -> str:
    text = re.sub(r"<[^>]+>", " ", summary or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    # Split on double spaces / period+space for a short lead
    parts = re.split(r"(?<=\.)\s+", text)
    return parts[0] if parts else text[:400]


def _basin_block(label: str, items: list[dict]) -> tuple[str, bool, list[str]]:
    """Return (html, has_active_cyclone, text_lines)."""
    cyclones = [i for i in items if (i.get("title") or "").lower().startswith("summary for")]
    outlook = next(
        (i for i in items if "tropical weather outlook" in (i.get("title") or "").lower()),
        None,
    )
    active = bool(cyclones)
    parts: list[str] = [f"<h3>{html_module.escape(label)}</h3>"]
    text_lines: list[str] = [f"{label}:"]

    if cyclones:
        for c in cyclones:
            title = html_module.escape(c.get("title") or "Cyclone")
            url = html_module.escape(c.get("url") or "")
            summary = html_module.escape(_first_paragraph(c.get("summary") or ""))
            link = f'<a href="{url}">{title}</a>' if url else title
            parts.append(f"<p><strong>{link}</strong><br/>{summary}</p>")
            text_lines.append(f"- {c.get('title')}: {_first_paragraph(c.get('summary') or '')}")
    else:
        quiet = "No tropical cyclones at this time."
        if outlook and "no tropical cyclones" in (outlook.get("summary") or "").lower():
            quiet = _first_paragraph(outlook.get("summary") or "") or quiet
        parts.append(f"<p>{html_module.escape(quiet)}</p>")
        text_lines.append(f"- {quiet}")

    if outlook and active:
        lead = _first_paragraph(outlook.get("summary") or "")
        if lead:
            parts.append(f"<p class=\"info\">{html_module.escape(lead)}</p>")
            text_lines.append(f"  Outlook: {lead}")
    elif outlook and not active:
        lead = _first_paragraph(outlook.get("summary") or "")
        if lead and "no tropical cyclones" not in lead.lower():
            parts.append(f"<p class=\"info\">{html_module.escape(lead)}</p>")
            text_lines.append(f"  Outlook: {lead}")

    return "".join(parts), active, text_lines


def scrape() -> dict:
    cp_items = scrape_rss(CPHC_URL, limit=15)
    ep_items = scrape_rss(EPAC_URL, limit=15)

    cp_html, cp_active, cp_text = _basin_block("Central Pacific (CPHC)", cp_items)
    ep_html, ep_active, ep_text = _basin_block("Eastern Pacific (NHC)", ep_items)

    links_html = (
        '<p class="info">'
        '<a href="https://kiloino.org/kilauea">Kilo ʻino</a>'
        " · "
        '<a href="https://www.nhc.noaa.gov">NHC</a>'
        " · "
        '<a href="https://www.youtube.com/@WorldWideWeatherWatch/videos">World Wide Weather Watch</a>'
        "</p>"
    )
    body = links_html + cp_html + ep_html
    text = "\n".join(cp_text + [""] + ep_text)

    return {
        "id": "tropical_outlook",
        "label": 'Tropical (<a href="https://www.nhc.noaa.gov">CPHC / NHC</a>)',
        "retrieved_at": now_iso(),
        "source_urls": [CPHC_URL, EPAC_URL],
        "html": body,
        "text": text,
        "error": None,
        "stale": False,
        "signals": {"cp_active": cp_active, "ep_active": ep_active},
    }
