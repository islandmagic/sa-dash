import unittest
from datetime import datetime, timezone

from src.propagation.parse import dedupe_records, parse_reports


class TestPropagationParse(unittest.TestCase):
    def test_parse_and_dedupe(self) -> None:
        xml = """
        <receptionReports>
          <receptionReport senderLocator="BL11aa" receiverLocator="BL02bb" frequency="7074000" sNR="-10" mode="FT8" />
          <receptionReport senderLocator="BL11aa" receiverLocator="BL02bb" frequency="7074000" sNR="-5" mode="FT8" />
        </receptionReports>
        """
        now = datetime(2026, 1, 31, tzinfo=timezone.utc)
        records = parse_reports(xml, now)
        self.assertEqual(len(records), 2)

        deduped = dedupe_records(records)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].snr_db, -5)


if __name__ == "__main__":
    unittest.main()
