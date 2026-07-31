import unittest
from unittest.mock import MagicMock
import sys

# bjoern fails to build in our environment, so we still mock it.
sys.modules['bjoern'] = MagicMock()

from main import apply_greentext_formatting

class TestApplyGreentextFormatting(unittest.TestCase):
    def test_apply_greentext_formatting(self):
        tests = [
            ("normal text", "normal text"),
            (">greentext", "<code>>greentext</code>"),
            ("&gt;greentext", "<code>&gt;greentext</code>"),
            ("  >spaced greentext", "<code>  >spaced greentext</code>"),
            ("  &gt;spaced greentext", "<code>  &gt;spaced greentext</code>"),
            ("line 1\n>line 2\nline 3", "line 1\n<code>>line 2</code>\nline 3"),
            ("line 1\n&gt;line 2\nline 3", "line 1\n<code>&gt;line 2</code>\nline 3"),
            ("", ""),
            (None, None),
            (">multiple\n>lines\nof text\n&gt;here", "<code>>multiple</code>\n<code>>lines</code>\nof text\n<code>&gt;here</code>"),
        ]

        for text, expected in tests:
            with self.subTest(text=text):
                self.assertEqual(apply_greentext_formatting(text), expected)

if __name__ == '__main__':
    unittest.main()
