"""Bounded HTTP failure logging for scrapers and fetchers."""

from __future__ import annotations

import os
import re

_TRUTHY = {"1", "true", "yes", "on"}


def is_debug_enabled(env_var: str) -> bool:
    return os.getenv(env_var, "").lower() in _TRUTHY


def redact_body(text: str, max_len: int = 200) -> str:
    snippet = re.sub(r"\s+", " ", (text or ""))[:max_len].strip()
    snippet = re.sub(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "[redacted]",
        snippet,
    )
    snippet = re.sub(r"\b[A-Za-z0-9_-]{24,}\b", "[redacted]", snippet)
    return snippet


def log_provider_failure(
    provider: str,
    context: str,
    *,
    status_code: int | None = None,
    exc: Exception | None = None,
    response_body: str | None = None,
    debug_env_var: str = "SCRAPER_DEBUG",
) -> None:
    if status_code is not None:
        print(f"{provider} failed: {context} (HTTP {status_code})")
    elif exc is not None:
        print(f"{provider} failed: {context}: {exc}")
    else:
        print(f"{provider} failed: {context}")

    if response_body and is_debug_enabled(debug_env_var):
        print(f"{provider} debug response snippet: {redact_body(response_body)}")
