import html

import httpx

from src.scrape.base import now_iso
from src.scrape.verizon_mobile import TOWNS


ATT_CHECK_URL = "https://www.att.com/outages/"
ATT_URL = (
    "https://www.att.com/msapi/outage/v1/workflows/"
    "addressdetails/WIRELESS?executecache=true"
)
ATT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15"
)
ATT_BASE_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": ATT_USER_AGENT,
}


def _payload_for_town(town: dict) -> dict:
    return {
        "addressInfo": {
            "address": town["address"].split(",")[0],
            "agent": "deskTop",
            "city": town["city"],
            "latitude": "",
            "longitude": "",
            "state": "HI",
            "zip": town["zipcode"],
        },
        "serviceType": "wireless",
    }


def _fetch_outage(client: httpx.Client, town: dict) -> tuple[str, str, str | None]:
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.att.com",
        "Referer": ATT_CHECK_URL,
    }
    response = None
    try:
        response = client.post(ATT_URL, json=_payload_for_town(town), headers=headers)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        if response is not None:
            print(
                "AT&T outage check failed for "
                f"{town.get('town', 'unknown')} (HTTP {response.status_code})."
            )
            print(response.text[:500])
        else:
            print(f"AT&T outage check failed for {town.get('town', 'unknown')}: {exc}")
        return "Unknown", "", "Fetch failed."

    notifications = payload.get("data", {}).get("WirelessOutageNotifications")
    if not isinstance(notifications, list) or not notifications:
        return "OK", "status-green", None

    alert_descriptions = []
    alert_codes = set()
    for notification in notifications:
        for alert in notification.get("AlertDescription") or []:
            alert_code = (alert.get("AlertCode") or "").upper()
            content = alert.get("Content") or {}
            additional = alert.get("AdditionalContent") or {}
            description = (
                additional.get("longDescription")
                or content.get("issueDescription")
                or ""
            )
            if description:
                alert_descriptions.append(description)
            if alert_code:
                alert_codes.add(alert_code)

    if not alert_descriptions:
        return "OK", "status-green", None

    detail = alert_descriptions[0]
    if "WLS_NEIGHBOROUTAGE" in alert_codes:
        return "Degraded", "status-yellow", detail
    return "Outage", "status-red", detail


def scrape() -> dict:
    rows = []
    with httpx.Client(timeout=20.0, headers=ATT_BASE_HEADERS) as client:
        try:
            warmup = client.get(ATT_CHECK_URL)
            if warmup.status_code >= 400:
                print(f"AT&T warmup failed (HTTP {warmup.status_code}).")
        except Exception as exc:
            print(f"AT&T warmup failed: {exc}")
        for town in TOWNS:
            status, status_class, detail = _fetch_outage(client, town)
            rows.append(
                {
                    "town": town["town"],
                    "status": status,
                    "status_class": status_class,
                    "detail": detail or "",
                }
            )

    table_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['town'])}</td>"
        f"<td class=\"status-cell {row['status_class']}\">{html.escape(row['status'])}</td>"
        f"<td>{html.escape(row['detail'])}</td>"
        "</tr>"
        for row in rows
    )
    body = (
        "<table>"
        "<thead><tr><th>Town</th><th>Status</th><th>Detail</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
    )

    return {
        "id": "att_mobile",
        "label": f"AT&T Mobile (<a href=\"{ATT_CHECK_URL}\">AT&T</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [ATT_URL, ATT_CHECK_URL],
        "html": body,
        "error": None,
        "stale": False,
    }
