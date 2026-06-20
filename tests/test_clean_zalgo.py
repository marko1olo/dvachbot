import os
import sys
import unittest
from pathlib import Path
import asyncio

# Setup env variables before importing main
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"
os.environ['ADMIN_CHAT_ID'] = '123456789'
os.environ['API_ID'] = '123'
os.environ['API_HASH'] = 'test_hash'
os.environ['BASE_URL'] = 'http://test.com'

# Setup asyncio loop for Pyrogram imports
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Now import the module
from Dubsite_tgach.main import clean_zalgo

class TestCleanZalgo(unittest.TestCase):
    def test_empty_string(self):
        """Test that an empty string returns an empty string."""
        self.assertEqual(clean_zalgo(""), "")
        self.assertEqual(clean_zalgo(None), "")

    def test_normal_text(self):
        """Test that normal text is returned unchanged."""
        text = "Hello, World!"
        self.assertEqual(clean_zalgo(text), text)

    def test_valid_combining_characters(self):
        """Test that text with valid combining characters (<= 4) is unchanged."""
        # e + 3 combining characters (acute accent)
        text = "e\u0301\u0301\u0301"
        self.assertEqual(clean_zalgo(text), text)

        # e + 4 combining characters
        text = "e\u0301\u0301\u0301\u0301"
        self.assertEqual(clean_zalgo(text), text)

    def test_excess_zalgo_characters(self):
        """Test that text with > 4 consecutive combining characters is truncated."""
        # e + 10 combining characters -> should become e + 4 combining characters
        text = "e" + ("\u0301" * 10)
        expected = "e" + ("\u0301" * 4)
        self.assertEqual(clean_zalgo(text), expected)

    def test_mixed_text(self):
        """Test that mixed text behaves correctly with zalgo and normal chars."""
        # a + 10 comb + b + 2 comb + c + 6 comb
        text = "a" + ("\u0301" * 10) + "b" + ("\u0301" * 2) + "c" + ("\u0301" * 6)
        expected = "a" + ("\u0301" * 4) + "b" + ("\u0301" * 2) + "c" + ("\u0301" * 4)
        self.assertEqual(clean_zalgo(text), expected)

    def test_russian_string(self):
        self.assertEqual(clean_zalgo("Привет мир!"), "Привет мир!")

    def test_only_combining_characters(self):
        # Just 10 combining characters
        zalgo_input = "\u0300" * 10
        zalgo_expected = "\u0300" * 4
        self.assertEqual(clean_zalgo(zalgo_input), zalgo_expected)

if __name__ == '__main__':
    unittest.main()
