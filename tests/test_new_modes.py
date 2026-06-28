import unittest
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from new_modes import _build_pattern

class TestBuildPattern(unittest.TestCase):
    def test_empty_dict_returns_none(self):
        """Test that passing an empty dictionary returns None."""
        self.assertIsNone(_build_pattern({}))

    def test_single_word(self):
        """Test that a single word correctly matches as a boundary word."""
        pattern = _build_pattern({"hello": ["hi"]})
        self.assertIsNotNone(pattern)
        match = pattern.search("Say hello to him")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0).lower(), "hello")

        # Should not match substrings
        self.assertIsNone(pattern.search("Othello"))

    def test_multiple_words_ordered_by_length(self):
        """Test that multiple words match properly and longer strings match first."""
        # 'hello' is longer than 'hi', so it should match the longer prefix when they overlap
        # Wait, hi and hello don't overlap prefixes, let's use overlapping ones
        pattern = _build_pattern({"cater": ["x"], "caterpillar": ["y"]})
        self.assertIsNotNone(pattern)

        match = pattern.search("I found a caterpillar")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0).lower(), "caterpillar")

    def test_special_characters_are_escaped(self):
        """Test that special regex characters in keys are properly escaped."""
        pattern = _build_pattern({"h.ello": ["hi"], "h*i": ["hello"]})
        self.assertIsNotNone(pattern)

        # Should match exact string with special characters
        match1 = pattern.search("Here is h.ello test")
        self.assertIsNotNone(match1)
        self.assertEqual(match1.group(0).lower(), "h.ello")

        match2 = pattern.search("Testing h*i")
        self.assertIsNotNone(match2)
        self.assertEqual(match2.group(0).lower(), "h*i")

        # Should not treat . as wildcard
        self.assertIsNone(pattern.search("Here is hoello"))

    def test_matches_correctly(self):
        """Test that the compiled regex correctly matches words with boundaries and ignores case."""
        pattern = _build_pattern({"cat": ["dog"]})
        self.assertIsNotNone(pattern)

        # Should match 'cat'
        match2 = pattern.search("The cat sat.")
        self.assertIsNotNone(match2)
        self.assertEqual(match2.group(0).lower(), "cat")

        # Should ignore case
        match3 = pattern.search("THE CAT SAT.")
        self.assertIsNotNone(match3)
        self.assertEqual(match3.group(0).lower(), "cat")

        # Should NOT match inside another word (due to word boundaries)
        match4 = pattern.search("The tomcat sat.")
        self.assertIsNone(match4)

        match5 = pattern.search("cattle")
        self.assertIsNone(match5)

if __name__ == '__main__':
    unittest.main()
