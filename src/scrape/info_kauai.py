import html

from src.scrape.base import now_iso


def _tel(phone_display: str) -> str:
    digits = "".join(ch for ch in phone_display if ch.isdigit())
    if len(digits) == 10:
        tel_href = f"+1{digits}"
    else:
        tel_href = digits
    return f'<a href="tel:{html.escape(tel_href)}">{html.escape(phone_display)}</a>'


def scrape() -> dict:
    contacts = [
        ("KPD Dispatch (non-emergency)", "808-241-1711", "Report non-emergency road hazards. Do not call 9-1-1 unless emergency."),
        ("Kauai Fire Dept", "808-241-4980", '<a href="mailto:kfd@kauai.gov">kfd@kauai.gov</a>'),
        ("Kaua‘i Emergency Mgmt Agency (KEMA)", "808-241-1800", '<a href="https://www.kauai.gov/kema">kauai.gov/kema</a> • <a href="mailto:kema@kauai.gov">kema@kauai.gov</a>'),
        ("Hawaii Emergency Mgmt Agency", "808-733-4300", '<a href="mailto:HawaiiEMA@hawaii.gov">HawaiiEMA@hawaii.gov</a>'),
        ("National Weather Service (HFO)", "808-245-6001", '<a href="https://weather.gov/hfo">weather.gov/hfo</a> • automated weather line'),
        ("NOAA Weather Kauai", "808-245-3564", ""),
        ("Kauai County", "808-241-6699", ""),
        ("Report a problem (County)", "808-241-3000", ""),
        ("Road & closure conditions", "808-241-1725", ""),
        ("Kauai Dept of Public Works", "808-241-4992", '<a href="mailto:publicworks@kauai.gov">publicworks@kauai.gov</a>'),
        ("KIUC (power emergencies)", "808-246-4300", '<a href="mailto:info@kiuc.coop">info@kiuc.coop</a>'),
        ("Water Service Emergency", "808-245-5400", "Business hours option 1. After-hours via KPD Dispatch."),
        ("Hawaiian Tel", "808-643-6111", ""),
        ("Wilcox Medical Center", "808-245-1100", ""),
        ("Makana North Shore Urgent Care", "808-320-7300", ""),
    ]

    contact_rows = "".join(
        "<tr>"
        f"<td>{html.escape(name)}</td>"
        f"<td class=\"info-td-phone\">{_tel(phone)}</td>"
        f"<td class=\"info-td-notes\">{notes}</td>"
        "</tr>"
        for name, phone, notes in contacts
    )
    contacts_table = (
        "<table class=\"info-table\">"
        "<thead><tr><th>Contact</th><th>Phone</th><th>Notes</th></tr></thead>"
        f"<tbody>{contact_rows}</tbody>"
        "</table>"
    )

    stations = [
        ("HPR1", "89.9", "FM", "Kauai"),
        ("KKCR", "91.9", "FM", "Kauai"),
        ("KONG", "93.5", "FM", "Kauai"),
        ("HI95", "95.9", "FM", "Kauai"),
        ("HPR2", "101.7", "FM", "Kauai"),
        ("KHNR", "690", "AM", "Honolulu"),
        ("KGU", "760", "AM", "Honolulu"),
        ("KHVH", "830", "AM", "Honolulu"),
        ("KIKI", "990", "AM", "Honolulu"),
        ("KKEA", "1420", "AM", "Honolulu"),
        ("KHKA", "1500", "AM", "Honolulu"),
    ]
    station_rows = "".join(
        "<tr>"
        f"<td>{html.escape(call)}</td>"
        f"<td class=\"info-td-num\">{html.escape(freq)}</td>"
        f"<td>{html.escape(band)}</td>"
        f"<td>{html.escape(area)}</td>"
        "</tr>"
        for call, freq, band, area in stations
    )
    broadcast_table = (
        "<table class=\"info-table info-table--radio\">"
        "<thead><tr><th>Station</th><th class=\"info-td-num\">Freq</th><th>Band</th><th>Area</th></tr></thead>"
        f"<tbody>{station_rows}</tbody>"
        "</table>"
    )

    broadcast_radio_block = (
        "<details class=\"info-details-broadcast\">"
        "<summary>Broadcast radio</summary>"
        "<div class=\"info-details-body\">"
        f"{broadcast_table}"
        "</div>"
        "</details>"
    )

    repeaters = [
        ("KH6E", "146.700", "-", "PL100", "Crater Hill, Kilauea"),
        ("KH6E", "147.280", "+", "PL100", "Kalepa Ridge, Lihue"),
        ("KH6E", "147.080", "+", "PL100", "Kukuiolono Park, Kalaheo"),
        ("KH6E", "147.100", "+", "PL100", "Kukui, Waimea Canyon"),
        ("KH6E", "147.160", "+", "PL100", "Wilcox Hospital, Lihue"),
        ("KH6S", "147.000", "+", "PL100", "Princeville"),
        ("KH6NS", "146.740", "-", "PL100", "Kilauea"),
        ("KH6S", "442.500", "+", "PL100", "Kapaa"),
        ("KH6S", "442.250", "+", "PL100", "Lihue"),
        ("KH6S", "444.975", "+", "PL100", "Kalaheo"),
    ]
    rep_rows = "".join(
        "<tr>"
        f"<td>{html.escape(call)}</td>"
        f"<td class=\"info-td-num\">{html.escape(freq)}</td>"
        f"<td>{html.escape(offset)}</td>"
        f"<td>{html.escape(pl)}</td>"
        f"<td>{html.escape(site)}</td>"
        "</tr>"
        for call, freq, offset, pl, site in repeaters
    )
    repeater_table = (
        "<p class=\"info-kicker\">National calling: 146.520 MHz<br/>GMRS calling: 462.675 MHz (CH 20)</p>"
        "<table class=\"info-table info-table--radio\">"
        "<thead><tr><th>Call</th><th class=\"info-td-num\">Freq</th><th>Offset</th><th>PL</th><th>Site</th></tr></thead>"
        f"<tbody>{rep_rows}</tbody>"
        "</table>"
    )

    amateur_radio_block = (
        "<details class=\"info-details-amradio\">"
        "<summary>Amateur radio</summary>"
        "<div class=\"info-details-body\">"
        f"{repeater_table}"
        "</div>"
        "</details>"
    )

    css = """
.info-module .info-contacts { margin-bottom: 0.35rem; }
.info-module .info-table { border-collapse: collapse; }
.info-module .info-td-phone { white-space: nowrap; }
.info-module .info-td-notes { color: #555; font-size: 0.85em; }
.info-module .info-kicker { margin-top: 0; color: #555; font-size: 0.9em; }
.info-module .info-subhead { margin: 0.75rem 0 0.35rem; font-size: 1rem; }
.info-module .info-compact-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.25rem 1rem; }
.info-module .info-details-broadcast,
.info-module .info-details-amradio { margin-top: 0.5rem; }
.info-module .info-details-body { margin-top: 0.5rem; }
.info-module .info-table--radio .info-td-num { text-align: right; }
"""

    body = (
        "<style>" + css + "</style>"
        "<div class=\"info-module\">"
        "<div class=\"info-contacts\">"
        f"{contacts_table}"
        "</div>"
        f"{broadcast_radio_block}"
        f"{amateur_radio_block}"
        "</div>"
    )

    return {
        "id": "info_kauai",
        "label": "Info (Contacts & Radio)",
        "retrieved_at": now_iso(),
        "source_urls": [],
        "html": body,
        "error": None,
        "stale": False,
        "layout": "full",
    }

