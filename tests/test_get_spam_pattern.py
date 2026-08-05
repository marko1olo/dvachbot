import re
import unittest

from Dubsite_tgach.main import _get_spam_pattern

class TestGetSpamPattern(unittest.TestCase):
    def test_empty_frozenset(self):
        """Test that an empty frozenset or None returns None."""
        self.assertIsNone(_get_spam_pattern(frozenset()))
        self.assertIsNone(_get_spam_pattern(None))

    def test_single_word(self):
        """Test that a single word creates a regex pattern matching that word."""
        pattern = _get_spam_pattern(frozenset(["spam"]))
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.pattern, r"\b(?:spam)\b")

    def test_multiple_words(self):
        """Test that multiple words are present in the pattern."""
        words = frozenset(["spam", "spammy", "sp"])
        pattern = _get_spam_pattern(words)
        self.assertIsNotNone(pattern)
        self.assertTrue(pattern.pattern.startswith(r"\b(?:"))
        self.assertTrue(pattern.pattern.endswith(r")\b"))
        inner_pattern = pattern.pattern[5:-3]
        self.assertEqual(set(inner_pattern.split("|")), {"spam", "spammy", "sp"})

    def test_regex_escaping(self):
        """Test that regex special characters in stop words are properly escaped."""
        words = frozenset(["spam.com", "buy(now)"])
        pattern = _get_spam_pattern(words)
        self.assertIsNotNone(pattern)
        # We can't guarantee order if lengths are same, but here buy(now) and spam.com are same length (8)
        # So we should just check if both escaped parts are present
        self.assertIn("spam\\.com", pattern.pattern)
        self.assertIn("buy\\(now\\)", pattern.pattern)

if __name__ == '__main__':
    unittest.main()
