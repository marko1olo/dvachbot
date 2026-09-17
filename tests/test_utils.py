import unittest
from utils import split_text

class TestUtils(unittest.TestCase):
    def test_split_text_long_word(self):
        # Edge case: deterministic text input string to test long word truncation
        # The function currently truncates and loses characters when a single word
        # is longer than the limit, because the suffix is appended after the split.
        text = "a" * 100
        limit = 40
        parts = split_text(text, limit)
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "a" * 34 + "\n(1/3)")
        self.assertEqual(parts[1], "a" * 34 + "\n(2/3)")
        self.assertEqual(parts[2], "a" * 20 + "\n(3/3)")

if __name__ == '__main__':
    unittest.main()
