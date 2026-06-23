import unittest
import sys
import os
import asyncio
from pathlib import Path

# Setup env variables before importing main to prevent errors
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"
os.environ['ADMIN_CHAT_ID'] = '123456789'
os.environ['API_ID'] = '123'
os.environ['API_HASH'] = 'test_hash'
os.environ['BASE_URL'] = 'http://test.com'

try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Let's import from Dubsite_tgach
from Dubsite_tgach.image_processing import clean_tags_string as clean_tags_string_dubsite
from site_tgach.image_processing import clean_tags_string as clean_tags_string_site

class TestCleanTagsString(unittest.TestCase):
    def test_none_input(self):
        self.assertIsNone(clean_tags_string_dubsite(None))
        self.assertIsNone(clean_tags_string_site(None))

    def test_empty_string(self):
        self.assertIsNone(clean_tags_string_dubsite(""))
        self.assertIsNone(clean_tags_string_site(""))

        # Test string with just spaces
        self.assertEqual(clean_tags_string_dubsite("   "), "")
        self.assertEqual(clean_tags_string_site("   "), "")

    def test_normal_tags(self):
        self.assertEqual(clean_tags_string_dubsite("tag1, tag2, tag3"), "tag1, tag2, tag3")
        self.assertEqual(clean_tags_string_site("tag1, tag2, tag3"), "tag1, tag2, tag3")

    def test_extra_spaces(self):
        self.assertEqual(clean_tags_string_dubsite("  tag1,   tag2  "), "tag1, tag2")
        self.assertEqual(clean_tags_string_site("  tag1,   tag2  "), "tag1, tag2")

    def test_multiple_commas(self):
        self.assertEqual(clean_tags_string_dubsite("tag1,,tag2"), "tag1,tag2")
        self.assertEqual(clean_tags_string_site("tag1,,tag2"), "tag1,tag2")

        self.assertEqual(clean_tags_string_dubsite("tag1,,,tag2"), "tag1,,tag2")
        self.assertEqual(clean_tags_string_site("tag1,,,tag2"), "tag1,,tag2")

    def test_comma_with_spaces(self):
        self.assertEqual(clean_tags_string_dubsite("tag1, ,tag2"), "tag1,tag2")
        self.assertEqual(clean_tags_string_site("tag1, ,tag2"), "tag1,tag2")

        self.assertEqual(clean_tags_string_dubsite("tag1,  ,tag2"), "tag1,tag2")
        self.assertEqual(clean_tags_string_site("tag1,  ,tag2"), "tag1,tag2")

    def test_complex_combinations(self):
        complex_input = "  tag1,, , tag2 ,,, tag3,  , tag4  "
        expected_dubsite = clean_tags_string_dubsite(complex_input)
        self.assertEqual(expected_dubsite, "tag1, tag2 ,, tag3, tag4")
        expected_site = clean_tags_string_site(complex_input)
        self.assertEqual(expected_site, "tag1, tag2 ,, tag3, tag4")

if __name__ == '__main__':
    unittest.main()
