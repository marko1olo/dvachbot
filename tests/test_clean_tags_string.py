import os
import sys
import unittest
from pathlib import Path
import asyncio

# Setup env variables before importing main to prevent ValueErrors
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"
os.environ['ADMIN_CHAT_ID'] = '123456789'
os.environ['API_ID'] = '123'
os.environ['API_HASH'] = 'test_hash'
os.environ['BASE_URL'] = 'http://test.com'

# Setup asyncio loop for Pyrogram imports, if necessary
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Now import the module
from Dubsite_tgach.image_processing import clean_tags_string

class TestCleanTagsString(unittest.TestCase):
    def test_empty_and_none(self):
        """Test with None and empty strings."""
        self.assertIsNone(clean_tags_string(None))
        self.assertIsNone(clean_tags_string(""))

    def test_whitespace_only(self):
        """Test with strings containing only whitespace."""
        self.assertEqual(clean_tags_string("   "), "")
        self.assertEqual(clean_tags_string("\n\t  "), "")

    def test_extra_spaces(self):
        """Test removing extra spaces between words."""
        self.assertEqual(clean_tags_string("tag1   tag2 \t tag3"), "tag1 tag2 tag3")
        self.assertEqual(clean_tags_string("  tag1  \n tag2  "), "tag1 tag2")

    def test_comma_replacements(self):
        """Test that excessive commas and commas with spaces are reduced."""
        self.assertEqual(clean_tags_string("tag1,,tag2"), "tag1,tag2")
        self.assertEqual(clean_tags_string("tag1, ,tag2"), "tag1,tag2")

        # Test consecutive replacements
        self.assertEqual(clean_tags_string("tag1,,,tag2"), "tag1,,tag2")

    def test_complex_cases(self):
        """Test combination of spaces, tabs, and commas."""
        self.assertEqual(clean_tags_string("tag1 , , tag2"), "tag1 , tag2")
        self.assertEqual(clean_tags_string("  tag1 , , tag2 \t\t,, tag3, ,tag4  "), "tag1 , tag2 , tag3,tag4")

if __name__ == '__main__':
    unittest.main()
