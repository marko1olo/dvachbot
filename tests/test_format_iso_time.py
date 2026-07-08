import os
import sys
import unittest
import time
from datetime import datetime
from unittest.mock import patch

# Mock required environment variables before importing main
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Dubsite_tgach.main import format_iso_time as dubsite_format_iso_time
from site_tgach.main import format_iso_time as site_format_iso_time

class TestFormatIsoTime(unittest.TestCase):
    def setUp(self):
        # Set timezone to UTC for deterministic testing
        os.environ['TZ'] = 'UTC'
        if hasattr(time, 'tzset'):
            time.tzset()

    def test_format_iso_time_implementations(self):
        implementations = [
            ("Dubsite_tgach", dubsite_format_iso_time),
            ("site_tgach", site_format_iso_time)
        ]

        for name, func in implementations:
            with self.subTest(implementation=name):
                # test_valid_timestamp
                ts = 1609459200.0 # 2021-01-01 00:00:00 UTC
                result = func(ts)
                self.assertTrue(result.startswith("2021-01-01T"))

                # test_zero_timestamp
                ts = 0.0
                result = func(ts)
                self.assertTrue(result.startswith("1970-01-01T"))

                # test_invalid_timestamp_type
                self.assertEqual(func("not a float"), "")
                self.assertEqual(func(None), "")
                self.assertEqual(func([]), "")

                # test_invalid_timestamp_value
                self.assertEqual(func(float('inf')), "")
                self.assertEqual(func(float('-inf')), "")
                self.assertEqual(func(float('nan')), "")

                # test_negative_timestamp
                try:
                    result = func(-1000.0)
                    self.assertTrue(isinstance(result, str))
                except Exception as e:
                    self.fail(f"Negative timestamp should not raise an exception: {e}")

if __name__ == '__main__':
    unittest.main()
