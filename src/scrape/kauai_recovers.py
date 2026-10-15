"""Scrape kauairecovers.org storm recovery pages (Squarespace)."""

from __future__ import annotations

import html as html_module
import re

from bs4 import BeautifulSoup

from src.scrape.base import clean_text, fetch_html, now_iso

BASE_URL = "https://www.kauairecovers.org"
DEBRIS_URL = f"{BASE_URL}/debris"
HELP_URL = f"{BASE_URL}/help"
INFO_URL = f"{BASE_URL}/info"
HEALTH_URL = f"{BASE_URL}/health"


def _safe_fetch(url: str) -> str | None:
    try:
        return fetch_html(url)
    except Exception:
        return None


def _main(soup: BeautifulSoup):
    return soup.find("main") or soup.find(id="page") or soup.body


def _parse_debris(page_html: str) -> tuple[list[dict], list[str], str | None]:
    soup = BeautifulSoup(page_html, "lxml")
    main = _main(soup)
    if not main:
        return [], [], None

    updated = None
    for el in main.find_all(["p", "div", "span"]):
        txt = clean_text(el.get_text(" "))
        m = re.match(r"Updated:\s*(.+)$", txt, re.I)
        if m:
            updated = m.group(1).strip()
            break

    sites: list[dict] = []
    for h4 in main.find_all("h4"):
        name = clean_text(h4.get_text(" "))
        if not name or name.lower() in {"county tipping fees waived"}:
            continue
        # Skip non-site headings
        if "tipping" in name.lower() and "fee" in name.lower():
            continue

        status = "unknown"
        if re.search(r"\(OPEN\)", name, re.I):
            status = "open"
        elif re.search(r"\(CLOSED\)", name, re.I):
            status = "closed"
        display_name = re.sub(r"\s*\((OPEN|CLOSED)\)\s*", " ", name, flags=re.I).strip()

        hours = ""
        location = ""
        accepts: list[str] = []
        notes: list[str] = []

        for sib in h4.find_all_next(["p", "h4", "h2", "h3", "ul"]):
            if sib.name in {"h4", "h2", "h3"} and sib is not h4:
                break
            if sib.name == "ul":
                for li in sib.find_all("li", recursive=False):
                    accepts.append(clean_text(li.get_text(" ")))
                continue
            txt = clean_text(sib.get_text(" "))
            if not txt:
                continue
            strong = sib.find(["strong", "b"])
            strong_txt = clean_text(strong.get_text(" ")) if strong else ""
            if strong_txt.lower().startswith("hours"):
                hours = re.sub(r"^Hours:\s*", "", txt, flags=re.I).strip()
            elif strong_txt.lower().startswith("location"):
                location = re.sub(r"^Location:\s*", "", txt, flags=re.I).strip()
            elif strong_txt.lower().startswith("accepts"):
                # Accepts list usually follows as ul; leftover text may be notes
                rest = re.sub(r"^Accepts:\s*", "", txt, flags=re.I).strip()
                if rest:
                    notes.append(rest)
            elif txt and not strong_txt:
                # Location note paragraphs
                if location and not hours:
                    notes.append(txt)
                elif hours or location:
                    notes.append(txt)

        # Default status for permanent transfer stations
        if status == "unknown":
            status = "open"

        sites.append(
            {
                "name": display_name,
                "status": status,
                "hours": hours,
                "location": location,
                "accepts": accepts,
                "notes": notes,
            }
        )

    notes_paras: list[str] = []
    text_blob = main.get_text("\n")
    for marker in (
        "REGULAR TRASH COLLECTION",
        "CURBSIDE COLLECTION",
        "County Tipping Fees Waived",
    ):
        m = re.search(rf"{re.escape(marker)}[\s\S]{{0,600}}", text_blob, re.I)
        if m:
            chunk = re.sub(r"\s+", " ", m.group(0)).strip()
            notes_paras.append(chunk[:500])

    return sites, notes_paras, updated


def _parse_food_schedule(page_html: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(page_html, "lxml")
    main = _main(soup)
    if not main:
        return None, ""
    last_updated = None
    blob = main.get_text("\n")
    m = re.search(r"Last updated:\s*([^\n]+)", blob, re.I)
    if m:
        last_updated = clean_text(m.group(1))

    # Extract between Food Assistance / Food Distribution Schedule and next major marker
    start = re.search(r"Food Distribution Schedule", blob, re.I)
    if not start:
        # Fallback: 211 block
        m211 = re.search(r"Call 211[\s\S]{0,400}", blob, re.I)
        return last_updated, clean_text(m211.group(0)) if m211 else ""
    end = re.search(
        r"For the most updated food distribution|Kaua.?i Independent Foodbank|Lost Income",
        blob[start.end() :],
        re.I,
    )
    end_pos = start.end() + (end.start() if end else 800)
    chunk = blob[start.start() : end_pos]
    chunk = re.sub(r"\n\s*\n+", "\n", chunk).strip()
    return last_updated, chunk[:2000]


def _parse_dept_table(page_html: str) -> tuple[str, list[dict]]:
    soup = BeautifulSoup(page_html, "lxml")
    main = _main(soup)
    if not main:
        return "", []
    lead = ""
    first_p = main.find("p")
    if first_p:
        lead = clean_text(first_p.get_text(" "))

    rows: list[dict] = []
    # Prefer first HTML table if present
    table = main.find("table")
    if table:
        for tr in table.find_all("tr")[1:]:
            cells = [clean_text(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
            if len(cells) >= 3:
                rows.append({"dept": cells[0], "status": cells[1], "contact": cells[2]})
        return lead, rows

    # Squarespace often uses text blocks rather than a real table; parse status lines
    # Pattern from /info: Department name / Status / phone
    return lead, rows


def _parse_pharmacies(page_html: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "lxml")
    main = _main(soup)
    if not main:
        return []
    pharmacies: list[dict] = []
    # Prefer the actual h1 content block + following list
    heading = None
    for tag in main.find_all(["h1", "h2", "h3"]):
        if clean_text(tag.get_text(" ")).lower() == "pharmacy information and hours":
            heading = tag
            break
    if heading:
        ul = heading.find_next("ul")
        if ul:
            for li in ul.find_all("li"):
                line = clean_text(li.get_text(" "))
                m = re.match(r"^(.+?)\s*[—\-–]\s*(.+)$", line)
                if m:
                    pharmacies.append(
                        {"name": m.group(1).strip(), "phone": m.group(2).strip()}
                    )
                elif line:
                    pharmacies.append({"name": line, "phone": ""})
            return pharmacies[:20]

    blob = main.get_text("\n")
    # Last occurrence is usually the real section (TOC link may appear first)
    matches = list(re.finditer(r"Pharmacy Information and Hours", blob, re.I))
    if not matches:
        return []
    start = matches[-1]
    end = re.search(r"Beach Safety Reminders|Brown Water", blob[start.end() :], re.I)
    end_pos = start.end() + (end.start() if end else 2000)
    chunk = blob[start.start() : end_pos]
    for line in chunk.splitlines():
        line = clean_text(line)
        if not line or "Pharmacy Information" in line or "may change" in line.lower():
            continue
        if "updated as of" in line.lower():
            continue
        m = re.match(r"^(.+?)\s*[—\-–]\s*(.+)$", line)
        if m and re.search(r"\d{3}", m.group(2)):
            pharmacies.append({"name": m.group(1).strip(), "phone": m.group(2).strip()})
        elif re.search(r"808[-\s]?\d{3}", line):
            pharmacies.append({"name": line, "phone": ""})
    return pharmacies[:20]


def scrape() -> dict:
    home = _safe_fetch(BASE_URL)
    if home is None:
        return {
            "id": "kauai_recovers",
            "label": "Recovery (kauairecovers.org)",
            "retrieved_at": now_iso(),
            "source_urls": [BASE_URL],
            "html": "",
            "text": "",
            "error": "Home page unreachable.",
            "stale": True,
            "skip": True,
        }

    debris_html = _safe_fetch(DEBRIS_URL) or ""
    help_html = _safe_fetch(HELP_URL) or ""
    info_html = _safe_fetch(INFO_URL) or ""
    health_html = _safe_fetch(HEALTH_URL) or ""

    sites, debris_notes, updated = _parse_debris(debris_html) if debris_html else ([], [], None)
    if not sites:
        # Site may be retired
        return {
            "id": "kauai_recovers",
            "label": f'Recovery (<a href="{BASE_URL}">kauairecovers.org</a>)',
            "retrieved_at": now_iso(),
            "source_urls": [BASE_URL],
            "html": "",
            "text": "",
            "error": None,
            "stale": False,
            "skip": True,
        }

    last_updated, food = _parse_food_schedule(help_html) if help_html else (None, "")
    lead, depts = _parse_dept_table(info_html) if info_html else ("", [])
    pharmacies = _parse_pharmacies(health_html) if health_html else []

    # Debris table
    def status_class(s: str) -> str:
        if s == "open":
            return "status-green"
        if s == "closed":
            return "status-red"
        return "status-yellow"

    def _short_accepts(items: list[str]) -> str:
        """Keep material types; drop long operational notes mashed into list items."""
        material_re = re.compile(
            r"^(Debris|Green [Ww]aste(?: Only)?|Tires and Motor Oil|"
            r"Scrap metal and appliances(?: from residents)?|"
            r"HOUSEHOLD RECYCLABLES|Metals and appliances)\b",
            re.I,
        )
        short: list[str] = []
        for item in items:
            item = clean_text(item)
            if not item:
                continue
            m = material_re.match(item)
            if m:
                piece = m.group(0)
            else:
                # Take text before an embedded note sentence
                piece = re.split(r"(?<=[a-z])\.\s+[A-Z]", item, maxsplit=1)[0]
                piece = clean_text(piece)
                if len(piece) > 60:
                    piece = re.split(r"[.;]", item, maxsplit=1)[0]
                    piece = clean_text(piece)[:60]
            # Skip pure operational notes (no material label)
            if re.match(
                r"^(Due to|Green waste drop-off|Metals and appliances drop-off|"
                r"No big trucks|Commercial haulers|Crews )",
                piece,
                re.I,
            ):
                continue
            if piece and piece not in short and len(piece) <= 80:
                short.append(piece)
            if len(short) >= 6:
                break
        return ", ".join(short)

    trs = []
    text_lines = ["Debris / green waste sites:"]
    for s in sites:
        accepts = _short_accepts(s["accepts"])
        trs.append(
            "<tr>"
            f'<td class="recovery-site">{html_module.escape(s["name"])}</td>'
            f'<td class="status-cell recovery-status {status_class(s["status"])}">'
            f'{html_module.escape(s["status"])}</td>'
            f'<td class="recovery-hours">{html_module.escape(s["hours"])}</td>'
            f'<td class="recovery-accepts">{html_module.escape(accepts)}</td>'
            "</tr>"
        )
        text_lines.append(
            f"- {s['name']}: {s['status']} | {s['hours']} | {accepts}"
        )

    meta = f'<p class="meta">Updated: {html_module.escape(updated)}</p>' if updated else ""
    notes_html = "".join(f"<p class=\"info\">{html_module.escape(n)}</p>" for n in debris_notes[:4])

    food_block = ""
    if food:
        food_esc = html_module.escape(food).replace("\n", "<br>")
        lu = f" (as of {html_module.escape(last_updated)})" if last_updated else ""
        food_block = (
            f"<details><summary>Food distribution{lu}</summary>"
            f"<div>{food_esc}</div></details>"
        )
        text_lines.append("")
        text_lines.append("Food distribution:")
        text_lines.append(food[:800])

    dept_block = ""
    if depts:
        drows = "".join(
            "<tr>"
            f"<td>{html_module.escape(d['dept'])}</td>"
            f"<td>{html_module.escape(d['status'])}</td>"
            f"<td>{html_module.escape(d['contact'])}</td>"
            "</tr>"
            for d in depts[:20]
        )
        lead_html = f"<p>{html_module.escape(lead)}</p>" if lead else ""
        dept_block = (
            "<details><summary>County department status</summary>"
            f"{lead_html}"
            "<table><thead><tr><th>Department</th><th>Status</th><th>Contact</th></tr></thead>"
            f"<tbody>{drows}</tbody></table></details>"
        )

    pharm_block = ""
    if pharmacies:
        prows = "".join(
            "<tr>"
            f"<td>{html_module.escape(p['name'])}</td>"
            f"<td>{html_module.escape(p['phone'])}</td>"
            "</tr>"
            for p in pharmacies
        )
        pharm_block = (
            "<details><summary>Pharmacies</summary>"
            "<table><thead><tr><th>Pharmacy</th><th>Phone</th></tr></thead>"
            f"<tbody>{prows}</tbody></table></details>"
        )

    css = """
.recovery-table { border-collapse: collapse; width: 100%; table-layout: fixed; }
.recovery-table th, .recovery-table td { padding: 0.35rem 0.5rem; vertical-align: top; }
.recovery-table th:nth-child(1),
.recovery-table td.recovery-site { width: 26%; }
.recovery-table th:nth-child(2),
.recovery-table td.recovery-status { width: 5.5rem; white-space: nowrap; }
.recovery-table th:nth-child(3),
.recovery-table td.recovery-hours { width: 22%; }
.recovery-table th:nth-child(4),
.recovery-table td.recovery-accepts { width: auto; }
.recovery-table tbody tr + tr td { border-top: 1px solid var(--table-row-border, rgba(0,0,0,0.08)); }
"""

    body = (
        "<style>" + css + "</style>"
        + meta
        + '<table class="recovery-table">'
        + "<thead><tr><th>Site</th><th>Status</th><th>Hours</th><th>Accepts</th></tr></thead>"
        + f"<tbody>{''.join(trs)}</tbody></table>"
        + notes_html
        + food_block
        + dept_block
        + pharm_block
    )

    return {
        "id": "kauai_recovers",
        "label": f'Recovery (<a href="{BASE_URL}">kauairecovers.org</a>)',
        "retrieved_at": now_iso(),
        "source_urls": [BASE_URL, DEBRIS_URL, HELP_URL, INFO_URL, HEALTH_URL],
        "html": body,
        "text": "\n".join(text_lines),
        "error": None,
        "stale": False,
        "layout": "full",
    }
