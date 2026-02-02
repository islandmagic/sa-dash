import base64
import html
import time

import httpx

from src.scrape.base import now_iso

# Example response:
#
'''
{
    "outages": [
        {
            "outageId": "6293639",
            "clusterId": 0,
            "outageType": "UNPLANNED",
            "outageSubType": "NON_OUTAGE_ALARM",
            "outageStatus": "",
            "zipcode": "96722",
            "outageHeader": "Data, voice, text and wireless home internet are limited in this area.",
            "outageContent": "There is a known issue, and we're working on a solution.",
            "reason": "",
            "startDate": "",
            "etrDate": "",
            "startDateNSP": null,
            "ETRH": "",
            "city": "Princeville",
            "state": "HI",
            "county": "Kauai",
            "is_feedback": true,
            "is_troubleshoot": false,
            "is_getdetails": false,
            "priority_rank": 20,
            "is_map": true,
            "is_notification": false,
            "feedback_text": {
                "label": ""
            },
            "link_json": "[{\"text\":\"This type of issue takes us a little longer to fix. Most are resolved within 48 hours. You can check your network status again later for updates.\",\"link\":\"https://www.verizon.com/support/check-network-status/\",\"link_lable\":\"Check network status\",\"newPage\":false},{\"text\":\"Learn how to use Verizon Wi-Fi calling if cellular service isn't available.\",\"link\":\"https://www.verizon.com/support/wifi-calling-faqs/\",\"link_lable\":\"Learn now\",\"newPage\":false}]",
            "restore_description": {
                "label": ""
            },
            "networkType": "MOBILE",
            "networkSubType": "MOBILE",
            "communicationType": "WIRELESS",
            "mdn": null,
            "is_fios_intersect": false
        }
    ]
}
'''

VERIZON_CHECK_URL = "https://www.verizon.com/support/check-network-status/"
VERIZON_URL = "https://api.verizon.com/cnsservice/cns/checkOutages"
TOKEN_URL = "https://api.verizon.com/cnsservice/cns/generate_token"
CLIENT_ID = "TaOzebxgGneCmMhrKQli32gHzD2HXzGa"
CLIENT_SECRET = "kwAqCm8ACwUxwqse"
API_KEY = CLIENT_ID
TOKEN_TTL_SKEW = 60
JOURNEY_ID = 44575938

COUNTY = "Kauai"
STATE = "HI"

TOWNS = [
    {
        "town": "Princeville",
        "address": "5-4280 Kuhio Hwy, Princeville, HI 96722, United States",
        "city": "Princeville",
        "zipcode": "96722",
        "latitude": 22.21315,
        "longitude": -159.47475,
    },
    {
        "town": "Kilauea",
        "address": "4260 Keneke St, Kilauea, HI 96754, United States",
        "city": "Kilauea",
        "zipcode": "96754",
        "latitude": 22.2119526,
        "longitude": -159.4061672,
    },
    {
        "town": "Anahola",
        "address": "4-4350 Kuhio Hwy, Anahola, HI 96703, United States",
        "city": "Anahola",
        "zipcode": "96703",
        "latitude": 22.144722,
        "longitude": -159.314957,
    },
    {
        "town": "Kapaa",
        "address": "4-1105 Kuhio Hwy, Kapaa, HI 96746, United States",
        "city": "Kapaa",
        "zipcode": "96746",
        "latitude": 22.05138,
        "longitude": -159.3338,
    },
    {
        "town": "Lihue",
        "address": "4280 Rice St, Lihue, HI 96766, United States",
        "city": "Lihue",
        "zipcode": "96766",
        "latitude": 21.97285,
        "longitude": -159.36477,
    },
]

_TOKEN_CACHE: dict[str, str | float | None] = {
    "token": None,
    "expires_at": 0.0,
}


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _payload_for_town(town: dict) -> dict:
    return {
        "source": "CNS",
        "longitude": town["longitude"],
        "latitude": town["latitude"],
        "journeyId": JOURNEY_ID,
        "location": _b64(town["address"]),
        "city": _b64(town["city"]),
        "county": _b64(COUNTY),
        "state": STATE,
        "zipcode": town["zipcode"],
        "addressSearchType": "ADDRESS_SELECTION",
        "sourceHost": "gismaps.verizon.com",
        "networkType": "MOBILE",
        "networkSubType": "MOBILE",
        "communicationType": "WIRELESS",
        "mdn": "",
        "isFiosCovered": False,
        "pinSource": "MVO",
        "pinAuthentication": "Unauthenticated",
        "reason": None,
    }


def _fetch_token() -> tuple[str | None, float]:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://gismaps.verizon.com",
        "Referer": "https://gismaps.verizon.com/",
        "apiKey": API_KEY,
        "grant_type": "client_credentials",
    }
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(TOKEN_URL, data=data, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        print(f"Verizon token fetch failed: {exc}")
        return None, 0.0

    token = payload.get("access_token")
    expires_in = payload.get("expires_in")
    try:
        ttl = max(0, int(expires_in) - TOKEN_TTL_SKEW)
    except (TypeError, ValueError):
        ttl = 0
    if not token:
        print("Verizon token missing from response.")
    return token, time.time() + ttl


def _get_token(force_refresh: bool = False) -> str | None:
    if not force_refresh:
        token = _TOKEN_CACHE.get("token")
        expires_at = _TOKEN_CACHE.get("expires_at") or 0.0
        if token and expires_at > time.time():
            return token

    token, expires_at = _fetch_token()
    if token:
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["expires_at"] = expires_at
    return token


def _request_outage(town: dict, token: str) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=20.0) as client:
        return client.post(VERIZON_URL, json=_payload_for_town(town), headers=headers)


def _fetch_outage(town: dict) -> tuple[str, str, str | None]:
    token = _get_token()
    if not token:
        print("Verizon outage check failed: token fetch failed.")
        return "Unknown", "", "Token fetch failed."

    response = None
    try:
        response = _request_outage(town, token)
        if response.status_code in {401, 403}:
            token = _get_token(force_refresh=True)
            if not token:
                print("Verizon outage check failed: token refresh failed.")
                return "Unknown", "", "Token refresh failed."
            response = _request_outage(town, token)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        if response is not None:
            print(
                "Verizon outage check failed for "
                f"{town.get('town', 'unknown')} (HTTP {response.status_code})."
            )
            print(response.text[:500])
        else:
            print(
                f"Verizon outage check failed for {town.get('town', 'unknown')}: {exc}"
            )
        return "Unknown", "", "Fetch failed."

    outages = payload.get("outages", [])
    outage_type = None
    outage_header = None
    outage_subtype = None
    if outages:
        outage_type = outages[0].get("outageType")
        outage_subtype = outages[0].get("outageSubType")
        outage_header = outages[0].get("outageHeader")
    if outage_type == "NONE":
        return "OK", "status-green", None
    if outage_subtype == "NON_OUTAGE_ALARM":
        return "Degraded", "status-yellow", outage_header
    if outage_type:
        return "Outage", "status-red", outage_header
    return "Unknown", "", None


def scrape() -> dict:
    rows = []
    for town in TOWNS:
        status, status_class, detail = _fetch_outage(town)
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
        "id": "verizon_mobile",
        "label": f"Verizon Mobile (<a href=\"{VERIZON_CHECK_URL}\">Verizon</a>)",
        "retrieved_at": now_iso(),
        "source_urls": [VERIZON_URL, TOKEN_URL],
        "html": body,
        "error": None,
        "stale": False,
    }
