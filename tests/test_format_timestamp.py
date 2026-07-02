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
os.environ["ADMIN_CHAT_ID"] = "123456789"
os.environ["API_ID"] = "123"
os.environ["API_HASH"] = "test_hash"
os.environ["BASE_URL"] = "http://test.com"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Dubsite_tgach.main import format_timestamp

class TestFormatTimestamp(unittest.TestCase):
    def test_valid_timestamp(self):
        ts = 1609459200.0 # 2021-01-01 00:00:00 UTC
        result = format_timestamp(ts)
        self.assertEqual(result, "01.01.2021 00:00:00")

    def test_zero_timestamp(self):
        ts = 0.0
        result = format_timestamp(ts)
        self.assertEqual(result, "01.01.1970 00:00:00")

    def test_invalid_timestamp_type(self):
        self.assertEqual(format_timestamp("not a float"), "")
        self.assertEqual(format_timestamp(None), "")
        self.assertEqual(format_timestamp([]), "")

    def test_invalid_timestamp_value(self):
        self.assertEqual(format_timestamp(float('inf')), "")
        self.assertEqual(format_timestamp(float('-inf')), "")
        self.assertEqual(format_timestamp(float('nan')), "")

    def test_negative_timestamp(self):
        try:
            result = format_timestamp(-1000.0)
            self.assertTrue(isinstance(result, str))
            # On some platforms negative timestamps are valid, on others they might raise ValueError/OverflowError
            # The function handles this gracefully by returning empty string on ValueError
        except Exception as e:
            self.fail(f"Negative timestamp should not raise an exception: {e}")

if __name__ == '__main__':
    unittest.main()
