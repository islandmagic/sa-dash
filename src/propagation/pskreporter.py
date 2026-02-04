from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import re
from urllib.parse import urlencode, urljoin

import httpx

from src.propagation.config import (
    DEFAULT_APP_CONTACT,
    MIN_SECONDS_BETWEEN_IDENTICAL_URL,
    WINDOW_MIN,
)

PSKREPORTER_BASE = "https://retrieve.pskreporter.info/query"
PSKREPORTER_WARMUP_URL = "https://pskreporter.info/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15"
    ),
    "Accept": "application/xml, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://pskreporter.info/",
}


@dataclass
class FetchResult:
    text: str | None
    from_cache: bool
    fetched: bool
    error: str | None = None


def _extract_cf_challenge_url(base_url: str, html: str) -> str | None:
    if not html:
        return None
    match = re.search(r'cUPMDTk:"([^"]+)"', html)
    if not match:
        match = re.search(r'fa:"([^"]+)"', html)
    if not match:
        match = re.search(r'replaceState\([^,]+,[^,]+,"([^"]+)"\)', html)
    if not match:
        return None
    raw_path = match.group(1).replace("\\/", "/")
    return urljoin(base_url, raw_path)


def _redact_cf_url(url: str) -> str:
    if "__cf_chl_" not in url:
        return url
    return re.sub(r"(__cf_chl_[^=]+=)[^&]+", r"\1REDACTED", url)


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"requests": [], "responses": {}, "last_fetch_utc": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"requests": [], "responses": {}, "last_fetch_utc": None}


def _save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    json_payload = json.dumps(payload, indent=2, ensure_ascii=True)
    path.write_text(json_payload, encoding="utf-8")
    print(json_payload)


def build_query_url(
    anchor: str,
    window_min: int = WINDOW_MIN,
    app_contact: str | None = DEFAULT_APP_CONTACT,
) -> str:
    params = {
        "callsign": anchor,
        "modify": "grid",
        "flowStartSeconds": -(window_min * 60),
        "rronly": 1,
        "rptlimit": 2000,
    }
    if app_contact:
        params["appcontact"] = app_contact
    return f"{PSKREPORTER_BASE}?{urlencode(params)}"


def _prune_requests(requests: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    cutoff = now - timedelta(hours=1)
    pruned = []
    for entry in requests:
        ts = entry.get("ts_utc")
        if not ts:
            continue
        try:
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts_dt >= cutoff:
            pruned.append({"ts_utc": ts_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")})
    return pruned


def _cached_response(
    responses: dict[str, Any], url: str, now: datetime
) -> str | None:
    entry = responses.get(url)
    if not entry:
        return None
    fetched_at = entry.get("fetched_utc")
    if not fetched_at:
        return None
    try:
        fetched_dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    age = (now - fetched_dt).total_seconds()
    if age <= MIN_SECONDS_BETWEEN_IDENTICAL_URL:
        return entry.get("content")
    return None


def fetch_reports(
    url: str,
    cache_path: Path,
    now: datetime,
    timeout: float = 120.0,
) -> FetchResult:
    cache = _load_cache(cache_path)
    requests = _prune_requests(cache.get("requests", []), now)
    responses = cache.get("responses", {})

    cached = _cached_response(responses, url, now)
    if cached is not None:
        cache["requests"] = requests
        _save_cache(cache_path, cache)
        return FetchResult(text=cached, from_cache=True, fetched=False)

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=DEFAULT_HEADERS) as client:
            warmup = client.get(PSKREPORTER_WARMUP_URL)
            if warmup.status_code >= 400:
                print(f"PSKReporter warmup failed (HTTP {warmup.status_code}).")
            response = client.get(url)
            if response.status_code != 200:
                if response.status_code == 403:
                    challenge_url = _extract_cf_challenge_url(url, response.text)
                    if challenge_url:
                        print("PSKReporter Cloudflare challenge detected (403).")
                        print(f"Retrying with challenge URL: {_redact_cf_url(challenge_url)}")
                        retry = client.get(challenge_url)
                        if retry.status_code == 200:
                            response = retry
                        else:
                            print(
                                "PSKReporter challenge retry failed "
                                f"(HTTP {retry.status_code})."
                            )
                            print(retry.text[:500])
                    else:
                        print("PSKReporter Cloudflare challenge detected, no retry URL found.")
                if response.status_code != 200:
                    print(f"PSKReporter HTTP {response.status_code} for {url}")
                    print(response.text[:500])
                    response.raise_for_status()
            text = response.text
    except Exception as exc:  # noqa: BLE001 - keep generator resilient
        cached_fallback = responses.get(url, {}).get("content")
        cache["requests"] = requests
        _save_cache(cache_path, cache)
        if cached_fallback:
            return FetchResult(text=cached_fallback, from_cache=True, fetched=False, error=str(exc))
        return FetchResult(text=None, from_cache=False, fetched=False, error=str(exc))

    fetched_at = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    responses[url] = {"fetched_utc": fetched_at, "content": text}
    requests.append({"ts_utc": fetched_at})
    cache["responses"] = responses
    cache["requests"] = requests
    cache["last_fetch_utc"] = fetched_at
    _save_cache(cache_path, cache)
    return FetchResult(text=text, from_cache=False, fetched=True)


def request_count_last_hour(cache_path: Path, now: datetime) -> int:
    cache = _load_cache(cache_path)
    requests = _prune_requests(cache.get("requests", []), now)
    cache["requests"] = requests
    _save_cache(cache_path, cache)
    return len(requests)


def last_fetch_utc(cache_path: Path) -> str | None:
    cache = _load_cache(cache_path)
    value = cache.get("last_fetch_utc")
    return value if isinstance(value, str) else None
