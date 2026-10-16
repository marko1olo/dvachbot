import unittest
from utils import split_text

class TestSplitText(unittest.TestCase):
    def test_split_text_under_limit(self):
        text = "Hello, World!"
        result = split_text(text, 50)
        self.assertEqual(result, [text])

    def test_split_text_exact_limit(self):
        text = "Hello, World!"
        result = split_text(text, len(text))
        self.assertEqual(result, [text])

    def test_split_text_by_words(self):
        text = "This is a slightly longer text that needs to be split."
        limit = 20
        result = split_text(text, limit)
        for part in result:
            self.assertLessEqual(len(part), limit)
        self.assertTrue(result[0].endswith(f"(1/{len(result)})"))
        self.assertTrue(result[-1].endswith(f"({len(result)}/{len(result)})"))

    def test_split_text_no_spaces(self):
        text = "A" * 50
        limit = 20
        result = split_text(text, limit)
        for part in result:
            self.assertLessEqual(len(part), limit)
        self.assertGreater(len(result), 1)
        self.assertTrue(result[0].endswith(f"(1/{len(result)})"))

    def test_split_text_with_newlines(self):
        text = "Line 1\nLine 2\nLine 3\nLine 4"
        limit = 15
        result = split_text(text, limit)
        for part in result:
            self.assertLessEqual(len(part), limit)
        self.assertGreater(len(result), 1)

if __name__ == '__main__':
    unittest.main()
