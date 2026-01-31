import unittest
from datetime import datetime, timezone

from src.propagation.parse import ReceptionRecord, haversine_km, maidenhead_to_latlon
from src.propagation.score import summarize_indicators


class TestPropagationScoring(unittest.TestCase):
    def _make_record(self, mode: str, band: str, sender: str, receiver: str, snr: int | None):
        sender_lat, sender_lon = maidenhead_to_latlon(sender)
        receiver_lat, receiver_lon = maidenhead_to_latlon(receiver)
        distance = haversine_km(sender_lat, sender_lon, receiver_lat, receiver_lon)
        return ReceptionRecord(
            t_utc="2026-01-31T06:00:00Z",
            mode=mode,
            band=band,
            freq_hz=7_074_000,
            snr_db=snr,
            sender_loc=sender,
            receiver_loc=receiver,
            sender4=sender[:4].upper(),
            receiver4=receiver[:4].upper(),
            sender_lat=sender_lat,
            sender_lon=sender_lon,
            receiver_lat=receiver_lat,
            receiver_lon=receiver_lon,
            distance_km=distance,
        )

    def test_vara_js8_override(self) -> None:
        record = self._make_record("JS8", "40m", "BL11aa", "BL02bb", -8)
        now = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
        nvis_summary, mainland_summary = summarize_indicators(
            [record],
            [],
            prev_state={},
            anchors_reporting=3,
            last_fetch_utc=now,
        )
        self.assertNotEqual(nvis_summary.vara_class, "UNLIKELY")
        self.assertEqual(mainland_summary.status, "UNKNOWN")

    def test_unknown_when_no_records(self) -> None:
        now = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
        nvis_summary, mainland_summary = summarize_indicators(
            [],
            [],
            prev_state={},
            anchors_reporting=0,
            last_fetch_utc=now,
        )
        self.assertEqual(nvis_summary.status, "UNKNOWN")
        self.assertEqual(mainland_summary.status, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
