import unittest
from datetime import datetime, timezone
from main import _fast_storage_ts


class TestFastStorageTs(unittest.TestCase):
    def test_datetime_utc(self):
        dt = datetime(2023, 5, 10, 14, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(_fast_storage_ts(dt), dt.timestamp())

    def test_datetime_naive(self):
        dt = datetime(2023, 5, 10, 14, 30, 0)
        self.assertEqual(_fast_storage_ts(dt), dt.timestamp())

    def test_none_value(self):
        self.assertEqual(_fast_storage_ts(None), 0.0)

    def test_integer_timestamp(self):
        result = _fast_storage_ts(1683729000)
        self.assertEqual(result, 1683729000.0)
        self.assertIsInstance(result, float)

    def test_float_timestamp(self):
        result = _fast_storage_ts(1683729000.5)
        self.assertEqual(result, 1683729000.5)
        self.assertIsInstance(result, float)


if __name__ == '__main__':
    unittest.main()
