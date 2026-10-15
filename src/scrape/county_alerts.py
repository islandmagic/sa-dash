"""Ingest and synthesize county/utility alert emails from DreamHost mailbox."""

from __future__ import annotations

import html as html_module
import os
from pathlib import Path

from src.mail.client import fetch_since, mail_configured
from src.mail.parse import (
    is_owner_message,
    merge_status_board,
    parse_message,
    render_status_board_html,
    render_status_board_text,
    sender_allowed,
)
from src.scrape.base import now_iso
from src.scrape.cache import load_cache, save_cache

DEFAULT_SENDERS = (
    "govdelivery.com",
    "everbridge.net",
    "kauai.gov",
    "kauaiwater.org",
    "kiuc.coop",
)
MAX_ITEMS = 40
BODY_CAP = 2500
_REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = _REPO_ROOT / "data" / "cache"


def _allow_list() -> list[str]:
    raw = os.environ.get("ALERT_SENDERS") or ""
    if raw.strip():
        return [t.strip() for t in raw.split(",") if t.strip()]
    return list(DEFAULT_SENDERS)


def _owner_from() -> str | None:
    return (os.environ.get("MAIL_OWNER_FROM") or "").strip() or None


def _dedupe_merge(existing: list[dict], new_items: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for item in existing + new_items:
        mid = item.get("message_id") or ""
        if not mid:
            continue
        # Prefer revision / newer
        prev = by_id.get(mid)
        if prev is None:
            by_id[mid] = item
            continue
        # Same message id — keep whichever has later date
        if (item.get("date") or "") >= (prev.get("date") or ""):
            by_id[mid] = item

    # Also collapse revisions of same NR id: keep newest
    by_nr: dict[str, dict] = {}
    leftovers: list[dict] = []
    for item in by_id.values():
        nr_id = (item.get("headline") or {}).get("id") or ""
        if nr_id.upper().startswith("NR") or nr_id.upper().startswith("DOW NR"):
            prev = by_nr.get(nr_id.upper())
            if prev is None or (item.get("date") or "") >= (prev.get("date") or ""):
                by_nr[nr_id.upper()] = item
        else:
            leftovers.append(item)

    merged = list(by_nr.values()) + leftovers
    merged.sort(key=lambda x: x.get("date") or "", reverse=True)
    return merged[:MAX_ITEMS]


def _render_alert_details(items: list[dict]) -> str:
    blocks: list[str] = []
    for item in items:
        family = html_module.escape(item.get("family") or "")
        subject = html_module.escape(item.get("subject") or "Alert")
        date = html_module.escape(str(item.get("date") or "")[:19])
        topics = ", ".join(item.get("topics") or [])
        topics_html = (
            f' <span class="meta">[{html_module.escape(topics)}]</span>' if topics else ""
        )
        body = html_module.escape((item.get("body") or "")[:BODY_CAP]).replace("\n", "<br>")
        web = item.get("web_url")
        link = (
            f' <a href="{html_module.escape(web)}">View as web page</a>' if web else ""
        )
        glance = item.get("glance") or []
        glance_html = ""
        if glance:
            lis = "".join(f"<li>{html_module.escape(g)}</li>" for g in glance)
            glance_html = f"<p><strong>At a glance</strong></p><ul>{lis}</ul>"
        blocks.append(
            "<details>"
            f"<summary><span class=\"meta\">{family}</span> {subject}"
            f"<br/><span class=\"meta\">{date}</span>{topics_html}</summary>"
            f"<div>{glance_html}{body}{link}</div>"
            "</details>"
        )
    return "".join(blocks) if blocks else "<p>No recent county alerts.</p>"


def _digest_text(board: dict, items: list[dict], notes: list[dict]) -> str:
    lines: list[str] = []
    board_txt = render_status_board_text(board)
    if board_txt:
        lines.append(board_txt)
        lines.append("")

    # Newest PIO glance
    for item in items:
        if item.get("family") == "GD-PIO" and item.get("glance"):
            lines.append("At a glance:")
            for g in item["glance"]:
                lines.append(f"- {g}")
            lines.append("")
            break

    lines.append("Recent alerts (24h headlines):")
    # Filter roughly last day by string compare on ISO dates is fine-ish; show top 12
    for item in items[:12]:
        lines.append(
            f"- [{item.get('family')}] {item.get('subject')} ({str(item.get('date') or '')[:16]})"
        )
    if notes:
        lines.append("")
        lines.append("Community notes:")
        for n in notes[:5]:
            lines.append(f"- {n.get('subject')}")
    return "\n".join(lines)


def scrape() -> dict:
    if not mail_configured():
        return {
            "id": "county_alerts",
            "label": "County Alerts (email)",
            "retrieved_at": now_iso(),
            "source_urls": [],
            "html": "",
            "text": "",
            "error": None,
            "stale": False,
            "skip": True,
        }

    cached = load_cache(CACHE_DIR, "county_alerts") or {}
    existing_items = list(cached.get("items") or [])
    existing_notes = list(cached.get("notes") or [])
    board = dict(cached.get("status_board") or {})

    allow = _allow_list()
    owner = _owner_from()
    raw_messages = fetch_since(days=14)

    new_alerts: list[dict] = []
    new_notes: list[dict] = []
    for raw in raw_messages:
        raw_from = raw.get("raw_from") or raw.get("from") or ""
        if is_owner_message(raw_from, owner):
            parsed = parse_message(raw)
            new_notes.append(parsed)
            continue
        if not sender_allowed(raw_from, allow):
            continue
        parsed = parse_message(raw)
        if parsed.get("family") == "other":
            continue
        new_alerts.append(parsed)
        board = merge_status_board(board, parsed.get("facts") or [], source=parsed.get("subject"))

    items = _dedupe_merge(existing_items, new_alerts)
    notes = _dedupe_merge(existing_notes, new_notes)[:20]

    # Rebuild board from all kept items for consistency
    board = {}
    for item in sorted(items, key=lambda x: x.get("date") or ""):
        board = merge_status_board(board, item.get("facts") or [], source=item.get("subject"))

    board_html = render_status_board_html(board)
    alerts_html = _render_alert_details(items)
    notes_html = ""
    if notes:
        notes_html = "<h3>Community Notes</h3>" + _render_alert_details(notes)

    body = board_html + alerts_html + notes_html
    text = _digest_text(board, items, notes)

    result = {
        "id": "county_alerts",
        "label": "County Alerts (email)",
        "retrieved_at": now_iso(),
        "source_urls": [],
        "html": body,
        "text": text,
        "error": None,
        "stale": False,
        "layout": "full",
        "items": items,
        "notes": notes,
        "status_board": board,
    }
    # Persist committed cache contents for next run
    save_cache(CACHE_DIR, "county_alerts", result)
    return result
