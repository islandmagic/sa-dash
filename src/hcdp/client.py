"""HTTP client for HCDP Mesonet `/mesonet/db/measurements`."""

from __future__ import annotations

import os
from typing import Any, Sequence
from urllib.parse import urlencode

import httpx

from src.scrape.base import DEFAULT_HEADERS

HCDP_BASE_URL = "https://api.hcdp.ikewai.org"
MEASUREMENTS_PATH = "/mesonet/db/measurements"


def _csv_ids(ids: str | Sequence[str]) -> str:
    if isinstance(ids, str):
        return ids
    return ",".join(ids)


class MesonetClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = HCDP_BASE_URL,
        timeout: float = 45.0,
    ) -> None:
        key = api_key if api_key is not None else os.getenv("HCDP_API_KEY", "")
        self._api_key = (key or "").strip()
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key)

    def get_measurements(
        self,
        *,
        station_ids: str | Sequence[str],
        var_ids: str | Sequence[str],
        location: str = "hawaii",
        start_date: str | None = None,
        end_date: str | None = None,
        join_metadata: bool = True,
        row_mode: str | None = None,
        local_tz: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        reverse: str | None = None,
        intervals: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._api_key:
            raise RuntimeError("HCDP_API_KEY is not set.")

        params: dict[str, str] = {
            "station_ids": _csv_ids(station_ids),
            "var_ids": _csv_ids(var_ids),
            "location": location,
        }
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date
        if join_metadata:
            params["join_metadata"] = "true"
        if row_mode is not None:
            params["row_mode"] = row_mode
        if local_tz is not None:
            params["local_tz"] = local_tz
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)
        if reverse is not None:
            params["reverse"] = reverse
        if intervals is not None:
            params["intervals"] = intervals

        url = f"{self._base}{MEASUREMENTS_PATH}?{urlencode(params)}"
        headers = {
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        with httpx.Client(follow_redirects=True, timeout=self._timeout, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()

        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and "data" in payload and "index" in payload:
            idx = payload["index"]
            rows = payload["data"]
            return [dict(zip(idx, row)) for row in rows]
        if isinstance(payload, dict):
            return [payload]
        return []

