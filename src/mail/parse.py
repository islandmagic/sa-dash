"""Rule-based parsing and synthesis of Kauai county/utility alert emails."""

from __future__ import annotations

import datetime as dt
import html as html_module
import re
from typing import Any

HST = dt.timezone(dt.timedelta(hours=-10))

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "power": ("kiuc", "outage", "restored", "transmission", "power", "electric"),
    "water": ("dow", "boil water", "conservation", "department of water", "water system"),
    "roads": ("closure", "kuhio", "kūhiō", "route", "lane", "bridge", "traffic", "highway"),
    "debris": ("green waste", "transfer station", "landfill", "refuse", "tipping fee", "debris"),
    "shelter": ("refuge area", "shelter", "neighborhood center", "resource center"),
    "food": ("food distribution", "foodbank", "food bank", "meals"),
    "schools": ("school", "elementary", "students"),
    "transit": ("kauaʻi bus", "kauai bus", "paratransit", "bus"),
    "county_services": ("dmv", "civic center", "permits", "building division"),
    "weather": ("tropical storm", "hurricane", "flash flood", "surf", "weather outlook"),
    "safety": ("scam", "911", "driving", "non-emergency"),
}

# ----- family detection -------------------------------------------------


def detect_family(raw_from: str, subject: str, plain: str) -> str:
    from_l = (raw_from or "").lower()
    subject_l = (subject or "").lower()
    body_l = (plain or "").lower()
    first = body_l.strip().splitlines()[0] if body_l.strip() else ""

    # Display-name / subject heuristics (also covers scrubbed fixtures)
    if "kiuc alert" in subject_l or "island utility cooperative" in from_l:
        return "EB-KIUC"
    if "resident alert" in from_l or "countyofkauairesident" in from_l.replace(" ", ""):
        return "EB-AlertKauai"
    if "department of water" in from_l or subject_l.startswith("dow nr"):
        # Could be GD or EB; prefer GD if govdelivery markers present
        if "govdelivery" in body_l or "granicus" in body_l or subject_l.startswith("dow nr"):
            return "GD-DOW"
        return "EB-DOW"
    if "police" in from_l:
        return "GD-KPD"
    if "public information officer" in from_l or "county of kaua" in from_l:
        if "govdelivery" in body_l or "granicus" in body_l or subject_l.startswith("nr "):
            return "GD-PIO"

    # GovDelivery bulletins (including iCloud-relayed local-parts)
    is_govdelivery = (
        "govdelivery" in from_l
        or "govdelivery" in body_l
        or "granicus" in body_l
        or "content.govdelivery.com" in body_l
    )
    if is_govdelivery:
        if (
            "kauaiwater" in from_l
            or subject_l.startswith("dow nr")
            or "department of water, county" in body_l
            or "department of water" in from_l
        ):
            return "GD-DOW"
        if "police" in from_l or "kaua'i police" in body_l or "kauai police" in body_l:
            return "GD-KPD"
        return "GD-PIO"

    is_everbridge = (
        "everbridge" in from_l or "everbridge" in body_l or "mass notification" in body_l
    )
    if (
        is_everbridge
        or subject_l.startswith("kiuc alert")
        or first.startswith("from:")
        or first.startswith("fr:")
    ):
        if "kauai island utility cooperative" in body_l or "kiuc alert" in subject_l:
            return "EB-KIUC"
        if re.search(r"^(from|fr):\s*.*water", first) or (
            first.startswith("from") and "water" in first
        ):
            return "EB-DOW"
        if (
            "through everbridge" in body_l
            or "mass notification" in body_l
            or "everbridge" in from_l
        ):
            return "EB-AlertKauai"
        if subject_l.startswith("kiuc"):
            return "EB-KIUC"

    if "kiuc" in from_l or "kiuc" in subject_l:
        return "EB-KIUC"
    return "other"


# ----- boilerplate stripping --------------------------------------------

_LINK_BRACKET_RE = re.compile(r"\[\s*https?://[^\]]+\]", re.I)
_URL_TRACKING_RE = re.compile(r"https?://\S*(?:utm_|safelinks\.protection)\S*", re.I)
_RULE_RE = re.compile(r"_{10,}")


def _strip_urls(text: str) -> str:
    text = _LINK_BRACKET_RE.sub("", text)
    text = _URL_TRACKING_RE.sub("", text)
    return text


def strip_govdelivery(plain: str, subject: str) -> str:
    text = plain or ""
    # Drop everything from ### onward
    cut = re.search(r"^###\s*$", text, re.M)
    if cut:
        text = text[: cut.start()]
    for marker in (
        "Media Contact:",
        "Stay Connected",
        "SUBSCRIBER SERVICES",
        "This email was sent to",
        "Manage Subscriptions",
    ):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]

    # Prefer content after the second horizontal rule (letterhead)
    rules = list(_RULE_RE.finditer(text))
    if len(rules) >= 2:
        text = text[rules[1].end() :]

    # Try to find headline matching subject parenthetical
    paren = re.search(r"\((.+)\)\s*$", subject or "")
    if paren:
        needle = paren.group(1).strip()
        # Search for a shortened version
        for length in (60, 40, 25):
            chunk = needle[:length]
            pos = text.lower().find(chunk.lower())
            if pos != -1:
                # Back up to start of line
                start = text.rfind("\n", 0, pos)
                text = text[start + 1 if start != -1 else pos :]
                break

    text = _strip_urls(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def strip_everbridge(plain: str) -> str:
    text = plain or ""
    drop_patterns = [
        r"^This is an urgent message from the County of Kaua'?i through Everbridge.*$",
        r"^This is an important message from Kauai Island Utility Cooperative.*$",
        r"^Please click here to acknowledge receipt of this message\s*$",
        r"^Message Sender:.*$",
        r"^Notification Status:.*$",
        r"^To stop receiving future email notifications.*$",
        r"^unsubscribe here\s*$",
        r"^This email may contain confidential.*$",
        r"^Access to this e-mail by anyone other than the intended recipient.*$",
        r"^If you are not the intended recipient.*$",
        r"^###\s*$",
    ]
    lines = []
    for line in text.splitlines():
        skip = False
        for pat in drop_patterns:
            if re.match(pat, line.strip(), re.I):
                skip = True
                break
        if not skip:
            lines.append(line)
    text = "\n".join(lines)
    # Truncate at confidentiality paragraph if still present
    for marker in (
        "This email may contain confidential",
        "To stop receiving future email notifications",
    ):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    text = _strip_urls(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def clean_body(family: str, plain: str, subject: str) -> str:
    if family.startswith("GD-"):
        return strip_govdelivery(plain, subject)
    if family.startswith("EB-"):
        return strip_everbridge(plain)
    return _strip_urls(plain or "").strip()


# ----- headline / id ----------------------------------------------------

_NR_RE = re.compile(
    r"(?:Revision:\s*)?(?:(?P<prefix>\d+\s*(?:a\.?m\.?|p\.?m\.?)\s*(?:UPDATE[:,]?|—|-)?\s*)?)?"
    r"(?P<id>(?:DOW\s+)?NR\s+\d{2}-\d{2}(?:-\d{2,4})?)\s*(?:\((?P<title>[^)]+)\))?",
    re.I,
)


def parse_headline(subject: str) -> dict[str, Any]:
    subject = (subject or "").strip()
    revision = bool(
        re.match(r"^(Revision:|\d+\s*(?:a\.?m\.?|p\.?m\.?)\s*(?:UPDATE|UPDATE:))", subject, re.I)
        or "UPDATE:" in subject.upper()
        or subject.upper().startswith("REVISION:")
    )
    match = _NR_RE.search(subject)
    if match:
        return {
            "id": re.sub(r"\s+", " ", match.group("id")).strip().upper(),
            "title": (match.group("title") or subject).strip(),
            "revision": revision or subject.lower().startswith("revision:"),
            "subject": subject,
        }
    return {
        "id": subject[:80],
        "title": subject,
        "revision": revision,
        "subject": subject,
    }


# ----- structure --------------------------------------------------------

_HEADING_RE = re.compile(r"^\*([^*\n]{2,120})\*\s*$")
_BULLET_RE = re.compile(r"^\s*(?:\*|•|-)\s+(.+)$")


def extract_structure(text: str) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    glance: list[str] = []
    current: dict[str, Any] | None = None
    paragraphs: list[str] = []

    def flush() -> None:
        nonlocal current, paragraphs
        if current is not None:
            current["paragraphs"] = paragraphs
            sections.append(current)
        current = None
        paragraphs = []

    for line in (text or "").splitlines():
        stripped = line.strip()
        hm = _HEADING_RE.match(stripped)
        if hm:
            flush()
            heading = hm.group(1).strip(" _")
            current = {"heading": heading, "bullets": [], "paragraphs": []}
            paragraphs = []
            continue
        bm = _BULLET_RE.match(line)
        if bm:
            bullet = bm.group(1).strip()
            if current is not None:
                current.setdefault("bullets", []).append(bullet)
            elif "at a glance" in (sections[-1]["heading"].lower() if sections else ""):
                pass
            paragraphs = []
            continue
        if stripped:
            paragraphs.append(stripped)
            if current is not None and paragraphs:
                # keep accumulating; flush on next heading
                pass

    flush()

    # Capture glance bullets
    for sec in sections:
        if "at a glance" in sec.get("heading", "").lower():
            glance = list(sec.get("bullets") or [])
            break
    # Also look for a heading-less glance block: "*Evening update - at a glance*"
    if not glance:
        for sec in sections:
            if "glance" in sec.get("heading", "").lower():
                glance = list(sec.get("bullets") or [])
                break

    return {"sections": sections, "glance": glance}


# ----- topic tagging ----------------------------------------------------


def tag_topics(*texts: str) -> list[str]:
    blob = " ".join(t or "" for t in texts).lower()
    # Fold common diacritics lightly for matching
    blob_folded = (
        blob.replace("ʻ", "'")
        .replace("ʻ", "'")
        .replace("ā", "a")
        .replace("ē", "e")
        .replace("ī", "i")
        .replace("ō", "o")
        .replace("ū", "u")
    )
    found: list[str] = []
    for topic, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in blob or kw.lower() in blob_folded:
                found.append(topic)
                break
    return found or ["other"]


# ----- fact extraction --------------------------------------------------

_POWER_PCT_RE = re.compile(
    r"[Pp]ower (?:is |has been |now )?restored (?:for |to )(?:about |approximately )?(\d+)\s*%"
)
_CUSTOMERS_OUT_RE = re.compile(
    r"(?:Roughly |About |approximately )?"
    r"([\d,.]+)\s*(K)?\s*(?:members|customers)\s+"
    r"(?:are )?(?:still |remain )?(?:without power|out)",
    re.I,
)
_CUSTOMERS_REMAIN_RE = re.compile(
    r"([\d,.]+)\s*(K)?\s*customers remain without power",
    re.I,
)
_TX_LINES_RE = re.compile(
    r"(\d+)\s+of\s+(\d+)\s+transmission lines",
    re.I,
)
_BOIL_RE = re.compile(
    r"Boil Water Notice\s+(canceled|cancelled|lifted|issued|in effect)"
    r"[^.]*?(?:for\s+(?:the\s+)?)?([A-Za-zĀāĒēĪīŌōŪūʻ''\-\s]+?)(?:\s+Water System|\s+on\s+Sept|\.|,|$)",
    re.I,
)
_CONSERVATION_RE = re.compile(
    r"Water Conservation Notice\s+(lifted|remain(?:s)? in effect|in effect)"
    r"[^.]*?(?:for\s+(?:the\s+)?)?([A-Za-zĀāĒēĪīŌōŪūʻ''\-\s,/]+?)(?:\s+service area|\s+Water System|\s+on\s+|\.|$)",
    re.I,
)
_SITE_SUBJECT_RE = re.compile(
    r"(?P<a>[A-Za-zʻ''\-\s]+?)\s+(?:Temp(?:orary)?\s+)?Green Waste Site\s+"
    r"(?P<a_status>Closed|Open|NOW Open|Closing)"
    r"(?:.*?(?P<b>[A-Za-zʻ''\-\s]+?)\s+(?:Temp(?:orary)?\s+)?(?:Green Waste Site\s+)?"
    r"(?P<b_status>Closed|Open|NOW Open))?",
    re.I,
)
_SITE_SIMPLE_RE = re.compile(
    r"(?P<name>[A-Za-zʻ''\-\s]+?(?:Transfer Station|Landfill|Green Waste Site|Temp(?:orary)? Site))"
    r"\s+(?P<status>is (?:no longer accepting|open|closed)|(?:OPEN|CLOSED|open|closed))",
    re.I,
)


def _parse_count(num: str, k_suffix: str | None) -> int:
    num = num.replace(",", "")
    try:
        value = float(num)
    except ValueError:
        return 0
    if k_suffix:
        value *= 1000
    return int(value)


def extract_facts(subject: str, body: str, when: str | None = None) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    blob = f"{subject}\n{body}"

    m = _POWER_PCT_RE.search(blob)
    if m:
        facts.append(
            {"key": "power_restored_pct", "value": int(m.group(1)), "label": f"{m.group(1)}% restored", "at": when}
        )

    for rx in (_CUSTOMERS_OUT_RE, _CUSTOMERS_REMAIN_RE):
        m = rx.search(blob)
        if m:
            facts.append(
                {
                    "key": "customers_out",
                    "value": _parse_count(m.group(1), m.group(2)),
                    "label": f"{_parse_count(m.group(1), m.group(2))} without power",
                    "at": when,
                }
            )
            break

    m = _TX_LINES_RE.search(blob)
    if m:
        facts.append(
            {
                "key": "transmission_lines",
                "value": f"{m.group(1)} of {m.group(2)}",
                "label": f"{m.group(1)} of {m.group(2)} transmission lines",
                "at": when,
            }
        )

    for m in _BOIL_RE.finditer(blob):
        action = m.group(1).lower()
        system = re.sub(r"\s+", " ", m.group(2)).strip(" ,.")
        status = "canceled" if action in {"canceled", "cancelled", "lifted"} else "issued"
        if system:
            facts.append(
                {
                    "key": f"boil_water:{system.lower()}",
                    "value": status,
                    "label": f"Boil water {system}: {status}",
                    "at": when,
                }
            )

    for m in _CONSERVATION_RE.finditer(blob):
        action = m.group(1).lower()
        area = re.sub(r"\s+", " ", m.group(2)).strip(" ,.")
        status = "lifted" if "lifted" in action else "in_effect"
        if area and len(area) < 80:
            facts.append(
                {
                    "key": f"water_conservation:{area.lower()}",
                    "value": status,
                    "label": f"Conservation {area}: {status}",
                    "at": when,
                }
            )

    # Site status from subject (Alert Kauai style)
    sm = _SITE_SUBJECT_RE.search(subject or "")
    if sm:
        for name_g, status_g in (("a", "a_status"), ("b", "b_status")):
            name = (sm.group(name_g) or "").strip()
            status_raw = (sm.group(status_g) or "").strip().lower()
            if not name or not status_raw:
                continue
            status = "open" if "open" in status_raw else "closed"
            clean_name = re.sub(r"\s+", " ", name).strip()
            facts.append(
                {
                    "key": f"site_status:{clean_name.lower()}",
                    "value": status,
                    "label": f"{clean_name} green waste: {status}",
                    "at": when,
                }
            )

    # Road closures: bullets under Road Closures heading handled by caller via sections
    return facts


def extract_road_closures(sections: list[dict]) -> list[str]:
    closures: list[str] = []
    for sec in sections:
        heading = (sec.get("heading") or "").lower()
        if "road closure" in heading or "partial road" in heading:
            closures.extend(sec.get("bullets") or [])
    return closures


# ----- status board -----------------------------------------------------


def merge_status_board(
    board: dict[str, dict[str, Any]],
    facts: list[dict[str, Any]],
    source: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Keep newest fact per key (by `at` ISO timestamp)."""
    for fact in facts:
        key = fact["key"]
        existing = board.get(key)
        new_at = fact.get("at") or ""
        old_at = (existing or {}).get("at") or ""
        if existing is None or new_at >= old_at:
            entry = dict(fact)
            if source:
                entry["source"] = source
            board[key] = entry
    return board


# ----- top-level parse --------------------------------------------------


def parse_message(msg: dict) -> dict[str, Any]:
    """Parse a raw message dict from mail.client into a structured alert."""
    subject = msg.get("subject") or ""
    plain = msg.get("plain") or ""
    raw_from = msg.get("raw_from") or msg.get("from") or ""
    family = detect_family(raw_from, subject, plain)
    cleaned = clean_body(family, plain, subject)
    headline = parse_headline(subject)
    structure = extract_structure(cleaned)
    topics = tag_topics(subject, cleaned)
    facts = extract_facts(subject, cleaned, when=msg.get("date"))
    roads = extract_road_closures(structure.get("sections") or [])
    if roads:
        facts.append(
            {
                "key": "road_closures",
                "value": roads,
                "label": f"{len(roads)} road closure(s)",
                "at": msg.get("date"),
            }
        )

    # Glance: also detect inline "at a glance" without *heading* markup
    glance = structure.get("glance") or []
    if not glance:
        for m in re.finditer(
            r"at a glance\*?[\s\S]*?(?=\n\*[A-Za-z]|\Z)",
            cleaned,
            re.I,
        ):
            block = m.group(0)
            glance = [
                bm.group(1).strip()
                for bm in _BULLET_RE.finditer(block)
            ]
            if glance:
                break

    return {
        "message_id": msg.get("message_id"),
        "family": family,
        "from": msg.get("from") or "",
        "subject": subject,
        "date": msg.get("date"),
        "headline": headline,
        "body": cleaned[:4000],
        "glance": glance,
        "sections": structure.get("sections") or [],
        "topics": topics,
        "facts": facts,
        "web_url": _govdelivery_url(plain or msg.get("html") or ""),
    }


def _govdelivery_url(text: str) -> str | None:
    m = re.search(
        r"https://content\.govdelivery\.com/accounts/HIKAUAICOUNTY/bulletins/[a-z0-9]+",
        text or "",
        re.I,
    )
    return m.group(0) if m else None


def sender_allowed(raw_from: str, allow_list: list[str]) -> bool:
    """Match allow-list tokens against From, treating '_' as '.' for relay rewrites."""
    blob = (raw_from or "").lower()
    blob_norm = blob.replace("_", ".")
    for token in allow_list:
        if not token:
            continue
        t = token.lower()
        if t in blob or t in blob_norm or t.replace(".", "_") in blob:
            return True
    return False


def is_owner_message(raw_from: str, owner_from: str | None) -> bool:
    if not owner_from:
        return False
    return owner_from.lower() in (raw_from or "").lower()


def render_status_board_html(board: dict[str, dict[str, Any]]) -> str:
    if not board:
        return ""
    # Prefer a stable key order
    priority = [
        "power_restored_pct",
        "customers_out",
        "transmission_lines",
        "road_closures",
    ]
    keys = [k for k in priority if k in board] + sorted(
        k for k in board if k not in priority
    )
    rows = []
    for key in keys:
        entry = board[key]
        label = html_module.escape(str(entry.get("label") or key))
        at = html_module.escape(str(entry.get("at") or "")[:16])
        rows.append(f"<tr><td>{label}</td><td class=\"meta\">{at}</td></tr>")
    return (
        "<h3>Current status (from alerts)</h3>"
        "<table><thead><tr><th>Fact</th><th>As of</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_status_board_text(board: dict[str, dict[str, Any]]) -> str:
    if not board:
        return ""
    lines = ["Current status:"]
    for key in sorted(board):
        entry = board[key]
        lines.append(f"- {entry.get('label') or key}")
    return "\n".join(lines)
