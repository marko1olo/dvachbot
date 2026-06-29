import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dbchecker import format_size

class TestFormatSize(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(format_size(0), "0.00 B")
        self.assertEqual(format_size(500), "500.00 B")
        self.assertEqual(format_size(1023), "1023.00 B")

    def test_kilobytes(self):
        self.assertEqual(format_size(1024), "1.00 KB")
        self.assertEqual(format_size(1536), "1.50 KB")
        self.assertEqual(format_size(1024 * 1024 - 1), "1024.00 KB")

    def test_megabytes(self):
        self.assertEqual(format_size(1024 * 1024), "1.00 MB")
        self.assertEqual(format_size(1024 * 1024 * 2.5), "2.50 MB")
        self.assertEqual(format_size(1024 * 1024 * 1024 - 1), "1024.00 MB")

    def test_gigabytes(self):
        self.assertEqual(format_size(1024 * 1024 * 1024), "1.00 GB")
        self.assertEqual(format_size(1024 * 1024 * 1024 * 3.75), "3.75 GB")

    def test_terabytes(self):
        self.assertEqual(format_size(1024 * 1024 * 1024 * 1024), "1.00 TB")
        self.assertEqual(format_size(1024 * 1024 * 1024 * 1024 * 5.2), "5.20 TB")

    def test_negative(self):
        # Even though size_bytes shouldn't normally be negative, it handles it gracefully
        self.assertEqual(format_size(-100), "-100.00 B")

if __name__ == '__main__':
    unittest.main()
