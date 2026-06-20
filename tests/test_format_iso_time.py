import os
import sys
import unittest
import time
from datetime import datetime

# Set timezone to UTC for deterministic testing
os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()

# Mock required environment variables before importing main
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Dubsite_tgach.main import format_iso_time

class TestFormatIsoTime(unittest.TestCase):
    def test_valid_timestamp(self):
        ts = 1609459200.0 # 2021-01-01 00:00:00 UTC
        result = format_iso_time(ts)
        self.assertTrue(result.startswith("2021-01-01T"))

    def test_zero_timestamp(self):
        ts = 0.0
        result = format_iso_time(ts)
        self.assertTrue(result.startswith("1970-01-01T"))

    def test_invalid_timestamp_type(self):
        self.assertEqual(format_iso_time("not a float"), "")
        self.assertEqual(format_iso_time(None), "")
        self.assertEqual(format_iso_time([]), "")

    def test_invalid_timestamp_value(self):
        self.assertEqual(format_iso_time(float('inf')), "")
        self.assertEqual(format_iso_time(float('-inf')), "")
        self.assertEqual(format_iso_time(float('nan')), "")

    def test_negative_timestamp(self):
        try:
            result = format_iso_time(-1000.0)
            self.assertTrue(isinstance(result, str))
        except Exception:
            self.fail("Negative timestamp should not raise an exception")

if __name__ == '__main__':
    unittest.main()
