"""IMAP/SMTP helpers for DreamHost-hosted mailboxes."""

from __future__ import annotations

import datetime as dt
import email
import email.header
import email.utils
import imaplib
import os
import re
from email.message import Message
from typing import Iterable

from bs4 import BeautifulSoup

DEFAULT_IMAP_HOST = "imap.dreamhost.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_SMTP_HOST = "smtp.dreamhost.com"
DEFAULT_SMTP_PORT = 465


def mail_configured() -> bool:
    return bool(os.environ.get("MAIL_USER") and os.environ.get("MAIL_PASSWORD"))


def _imap_host() -> str:
    return os.environ.get("MAIL_IMAP_HOST") or DEFAULT_IMAP_HOST


def _imap_port() -> int:
    try:
        return int(os.environ.get("MAIL_IMAP_PORT") or DEFAULT_IMAP_PORT)
    except ValueError:
        return DEFAULT_IMAP_PORT


def smtp_host() -> str:
    return os.environ.get("MAIL_SMTP_HOST") or DEFAULT_SMTP_HOST


def smtp_port() -> int:
    try:
        return int(os.environ.get("MAIL_SMTP_PORT") or DEFAULT_SMTP_PORT)
    except ValueError:
        return DEFAULT_SMTP_PORT


def mail_user() -> str:
    return (os.environ.get("MAIL_USER") or "").strip()


def mail_password() -> str:
    return os.environ.get("MAIL_PASSWORD") or ""


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    chunks: list[str] = []
    for data, charset in parts:
        if isinstance(data, bytes):
            chunks.append(data.decode(charset or "utf-8", "replace"))
        else:
            chunks.append(data)
    return re.sub(r"\s+", " ", "".join(chunks)).strip()


def extract_body(msg: Message) -> tuple[str, str | None]:
    """Return (plain_text, html_or_none). Prefer text/plain."""
    plain: str | None = None
    html: str | None = None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, "replace")
            if ctype == "text/plain" and plain is None:
                plain = text
            elif ctype == "text/html" and html is None:
                html = text
    else:
        payload = msg.get_payload(decode=True)
        if payload is not None:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, "replace")
            if msg.get_content_type() == "text/html":
                html = text
            else:
                plain = text
    if plain is not None:
        return plain, html
    if html is not None:
        return html_to_text(html), html
    return "", None


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _search_since(days: int) -> str:
    since = dt.date.today() - dt.timedelta(days=days)
    return since.strftime("%d-%b-%Y")


def fetch_since(days: int = 14, folder: str = "INBOX") -> list[dict]:
    """Fetch messages from IMAP newer than `days` days ago.

    Returns list of dicts with keys: message_id, from, subject, date, plain, html, raw_from.
    """
    if not mail_configured():
        return []

    client = imaplib.IMAP4_SSL(_imap_host(), _imap_port())
    try:
        client.login(mail_user(), mail_password())
        typ, _ = client.select(folder, readonly=True)
        if typ != "OK":
            return []
        typ, data = client.search(None, f'(SINCE {_search_since(days)})')
        if typ != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        results: list[dict] = []
        for uid in uids:
            typ, fetched = client.fetch(uid, "(RFC822)")
            if typ != "OK" or not fetched:
                continue
            raw = fetched[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(raw)
            plain, html = extract_body(msg)
            msg_id = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
            date_hdr = msg.get("Date") or ""
            try:
                parsed = email.utils.parsedate_to_datetime(date_hdr)
            except (TypeError, ValueError, IndexError):
                parsed = None
            results.append(
                {
                    "message_id": msg_id or f"uid-{uid.decode() if isinstance(uid, bytes) else uid}",
                    "from": decode_header_value(msg.get("From")),
                    "raw_from": msg.get("From") or "",
                    "subject": decode_header_value(msg.get("Subject")),
                    "date": parsed.isoformat() if parsed else date_hdr,
                    "plain": plain,
                    "html": html,
                }
            )
        return results
    finally:
        try:
            client.logout()
        except Exception:  # noqa: BLE001
            pass


def mark_seen(uids: Iterable[str], folder: str = "INBOX") -> None:
    """Optional: mark messages as Seen. Not required for digest generation."""
    if not mail_configured():
        return
    client = imaplib.IMAP4_SSL(_imap_host(), _imap_port())
    try:
        client.login(mail_user(), mail_password())
        client.select(folder)
        for uid in uids:
            client.store(uid, "+FLAGS", "\\Seen")
    finally:
        try:
            client.logout()
        except Exception:  # noqa: BLE001
            pass
