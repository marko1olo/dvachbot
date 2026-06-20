import sys
import unittest
import os
from pathlib import Path
import asyncio

# Setup env variables before importing main
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

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
        self.assertEqual(clean_zalgo(""), "")

    def test_normal_string(self):
        self.assertEqual(clean_zalgo("Hello World!"), "Hello World!")

    def test_russian_string(self):
        self.assertEqual(clean_zalgo("Привет мир!"), "Привет мир!")

    def test_no_more_than_four_combining(self):
        # 4 combining characters
        zalgo = "a" + "\u0300" * 4 + "b"
        self.assertEqual(clean_zalgo(zalgo), zalgo)

    def test_more_than_four_combining(self):
        # 5 combining characters - the last one should be removed
        zalgo_input = "a" + "\u0300" * 5 + "b"
        zalgo_expected = "a" + "\u0300" * 4 + "b"
        self.assertEqual(clean_zalgo(zalgo_input), zalgo_expected)

    def test_multiple_zalgo_spots(self):
        # "a" with 10 combining + "b" with 6 combining
        zalgo_input = "a" + "\u0300" * 10 + "b" + "\u0301" * 6 + "c"
        zalgo_expected = "a" + "\u0300" * 4 + "b" + "\u0301" * 4 + "c"
        self.assertEqual(clean_zalgo(zalgo_input), zalgo_expected)

    def test_only_combining_characters(self):
        # Just 10 combining characters
        zalgo_input = "\u0300" * 10
        zalgo_expected = "\u0300" * 4
        self.assertEqual(clean_zalgo(zalgo_input), zalgo_expected)

if __name__ == '__main__':
    unittest.main()
