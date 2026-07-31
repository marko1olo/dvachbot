import unittest
from main import split_text

class TestSplitText(unittest.TestCase):
    def test_short_text(self):
        """Test text smaller than limit."""
        text = "Hello world"
        result = split_text(text, 50)
        self.assertEqual(result, [text])

    def test_exact_limit(self):
        """Test text exactly equal to limit."""
        text = "Hello world"
        result = split_text(text, 11)
        self.assertEqual(result, [text])

    def test_split_by_words(self):
        """Test text with spaces that needs splitting."""
        text = "word1 word2 word3 word4 word5"
        limit = 15
        result = split_text(text, limit)
        for i, part in enumerate(result):
            self.assertTrue(len(part) <= limit, f"Part {i} length {len(part)} > {limit}: {repr(part)}")
        self.assertTrue(len(result) > 1)
        self.assertTrue(all(f"({i+1}/{len(result)})" in part for i, part in enumerate(result)))

    def test_split_long_word(self):
        """Test text without spaces that needs splitting."""
        text = "a" * 25
        limit = 12
        result = split_text(text, limit)
        for i, part in enumerate(result):
            self.assertTrue(len(part) <= limit, f"Part {i} length {len(part)} > {limit}: {repr(part)}")
        self.assertTrue(len(result) > 1)
        self.assertTrue(all(f"({i+1}/{len(result)})" in part for i, part in enumerate(result)))

    def test_newlines(self):
        """Test text with newlines that needs splitting."""
        text = "line1\nline2\nline3\nline4\nline5"
        limit = 14
        result = split_text(text, limit)
        for i, part in enumerate(result):
            self.assertTrue(len(part) <= limit, f"Part {i} length {len(part)} > {limit}: {repr(part)}")
        self.assertTrue(len(result) > 1)
        self.assertTrue(all(f"({i+1}/{len(result)})" in part for i, part in enumerate(result)))

    def test_empty_string(self):
        """Test empty string."""
        self.assertEqual(split_text("", 10), [""])

if __name__ == '__main__':
    unittest.main()
