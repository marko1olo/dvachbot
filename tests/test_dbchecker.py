import unittest
from dbchecker import format_size

class TestFormatSize(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(format_size(0), "0.00 B")
        self.assertEqual(format_size(500), "500.00 B")
        self.assertEqual(format_size(1023), "1023.00 B")

    def test_kilobytes(self):
        self.assertEqual(format_size(1024), "1.00 KB")
        self.assertEqual(format_size(1536), "1.50 KB")

    def test_megabytes(self):
        self.assertEqual(format_size(1024 * 1024), "1.00 MB")
        self.assertEqual(format_size(1024 * 1024 * 1.5), "1.50 MB")

    def test_gigabytes(self):
        self.assertEqual(format_size(1024 * 1024 * 1024), "1.00 GB")
        self.assertEqual(format_size(1024 * 1024 * 1024 * 1.5), "1.50 GB")

    def test_terabytes(self):
        self.assertEqual(format_size(1024 * 1024 * 1024 * 1024), "1.00 TB")
        self.assertEqual(format_size(1024 * 1024 * 1024 * 1024 * 2.5), "2.50 TB")

if __name__ == '__main__':
    unittest.main()
