import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from witching_hour import apply_zalgo

class TestWitchingHour(unittest.TestCase):
    def test_apply_zalgo_empty_string(self):
        """Test that apply_zalgo returns empty string when given an empty string."""
        self.assertEqual(apply_zalgo(""), "")

    def test_apply_zalgo_none(self):
        """Test that apply_zalgo returns None when given None."""
        self.assertEqual(apply_zalgo(None), None)

    def test_apply_zalgo_normal_string(self):
        """Test that apply_zalgo modifies a normal string."""
        original = "Hello World"
        result = apply_zalgo(original)
        self.assertNotEqual(original, result)
        self.assertTrue(len(result) >= len(original))

if __name__ == '__main__':
    unittest.main()
