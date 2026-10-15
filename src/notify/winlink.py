"""Send plain-text digest to a Winlink address via DreamHost SMTP."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from src.mail.client import mail_password, mail_user, smtp_host, smtp_port
from src.render.text import ascii_fold

HARD_LIMIT = 15_000


def send_digest(text: str, to: str, subject: str | None = None) -> None:
    """Send ASCII plain-text digest. Raises on SMTP failure."""
    user = mail_user()
    password = mail_password()
    if not user or not password:
        raise RuntimeError("MAIL_USER / MAIL_PASSWORD not configured.")
    if not to:
        raise RuntimeError("WINLINK_TO not configured.")

    body = ascii_fold(text or "")
    if len(body) > HARD_LIMIT:
        body = body[: HARD_LIMIT - 20].rstrip() + "\n...(truncated)\n"

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject or "Kauai digest"
    msg.set_content(body, charset="us-ascii", cte="7bit")

    host = smtp_host()
    port = smtp_port()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(msg)
