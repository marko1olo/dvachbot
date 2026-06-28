import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from new_modes import _key


class TestNewModesKey(unittest.TestCase):
    def test_key_lowercase(self):
        self.assertEqual(_key("test"), "test")

    def test_key_uppercase(self):
        self.assertEqual(_key("TEST"), "test")

    def test_key_mixed_case(self):
        self.assertEqual(_key("tEsT"), "test")

    def test_key_empty(self):
        self.assertEqual(_key(""), "")

    def test_key_non_ascii(self):
        # Python's casefold() converts 'ß' to 'ss'
        self.assertEqual(_key("groß"), "gross")
        # Cyrillic casefold
        self.assertEqual(_key("ТЕСТ"), "тест")


if __name__ == "__main__":
    unittest.main()
