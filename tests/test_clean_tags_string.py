import os
import sys
import unittest
from pathlib import Path
import asyncio

# Setup env variables before importing main modules if needed
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

# Setup asyncio loop for Pyrogram imports if they happen
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Dubsite_tgach.image_processing import clean_tags_string

class TestCleanTagsString(unittest.TestCase):
    def test_none_or_empty(self):
        """Test that None and empty string return None."""
        self.assertIsNone(clean_tags_string(None))
        self.assertIsNone(clean_tags_string(""))

    def test_normal_tags(self):
        """Test that normal tags are returned as is."""
        self.assertEqual(clean_tags_string("tag1, tag2, tag3"), "tag1, tag2, tag3")
        self.assertEqual(clean_tags_string("anime, girl"), "anime, girl")

    def test_whitespace_removal(self):
        """Test that extra whitespace is compressed into a single space."""
        self.assertEqual(clean_tags_string("  tag1   tag2  "), "tag1 tag2")
        self.assertEqual(clean_tags_string("tag1\n\ttag2"), "tag1 tag2")

    def test_consecutive_commas(self):
        """Test that consecutive commas are reduced."""
        self.assertEqual(clean_tags_string("tag1,,tag2"), "tag1,tag2")
        self.assertEqual(clean_tags_string("tag1,,,tag2"), "tag1,,tag2")

    def test_spaced_commas(self):
        """Test that spaced commas are properly cleaned."""
        # split: ["tag1,", ",tag2"] -> join: "tag1, ,tag2" -> replace(", ,", ",") -> "tag1,,tag2" -> replace(",,", ",") -> "tag1,tag2"
        self.assertEqual(clean_tags_string("tag1, ,tag2"), "tag1,tag2")

        # split: ["tag1", ",", ",", "tag2"] -> join: "tag1 , , tag2" -> replace ", ," -> "tag1 ,, tag2" -> replace ",," -> "tag1 , tag2"
        self.assertEqual(clean_tags_string("tag1 , , tag2"), "tag1 , tag2")

if __name__ == '__main__':
    unittest.main()
