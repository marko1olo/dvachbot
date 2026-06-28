import sys
with open("tests/test_site_importer.py", "r") as f:
    content = f.read()

new_content = """import unittest
import asyncio
import os
import sys
import importlib

# Add project root to sys.path to allow importing from site_tgach
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock environment variables needed for initialization
os.environ["SECRET_KEY"] = "dummy_secret_key"
os.environ["BOT_TOKEN"] = "dummy_bot_token"
os.environ["OPENAI_API_KEY"] = "dummy_openai_key"

from unittest.mock import MagicMock

# If test_main polluted the sys.modules, we need to clean it up for our test
for mod in list(sys.modules.keys()):
    if mod.startswith('site_tgach.') or mod == 'site_tgach':
        if isinstance(sys.modules[mod], MagicMock) or type(sys.modules[mod]).__name__ == 'MagicMock' or type(sys.modules[mod]).__name__ == 'module':
            del sys.modules[mod]

import site_tgach
# Mock some things that site_tgach.importer imports to avoid dependency errors
sys.modules['warhammer_mode'] = MagicMock()
sys.modules['common.bot_pool'] = MagicMock()
sys.modules['common.async_file_io'] = MagicMock()
sys.modules['site_tgach.image_processing'] = MagicMock()

from site_tgach.importer import ThreadImporter

class TestSiteImporterExtractPostsData(unittest.TestCase):
    def setUp(self):
        # We must make sure ThreadImporter is the ACTUAL class, not a mock.
        if type(ThreadImporter).__name__ == 'MagicMock':
            raise Exception("ThreadImporter is still a mock!")
        # Instantiate importer with dummy values. extract_posts_data is pure sync.
        self.importer = ThreadImporter(bot=None, file_storage_channel_id=123)

    def test_extract_posts_data_dict_with_posts_key(self):
        data = {"posts": [{"id": 1, "text": "hello"}]}
        result = self.importer.extract_posts_data(data)
        self.assertEqual(result, [{"id": 1, "text": "hello"}])

    def test_extract_posts_data_dict_with_threads_key(self):
        data = {
            "threads": [
                {
                    "posts": [{"id": 2, "text": "world"}]
                }
            ]
        }
        result = self.importer.extract_posts_data(data)
        self.assertEqual(result, [{"id": 2, "text": "world"}])

    def test_extract_posts_data_dict_with_threads_missing_posts(self):
        data = {
            "threads": [
                {
                    "other_key": "value"
                }
            ]
        }
        result = self.importer.extract_posts_data(data)
        self.assertEqual(result, [])

    def test_extract_posts_data_dict_with_nested_list_of_dicts_matching_keys(self):
        # test matching 'comment'
        data_comment = {"some_key": [{"comment": "test", "other": 1}]}
        self.assertEqual(self.importer.extract_posts_data(data_comment), [{"comment": "test", "other": 1}])

        # test matching 'no'
        data_no = {"some_key": [{"no": 123, "other": 1}]}
        self.assertEqual(self.importer.extract_posts_data(data_no), [{"no": 123, "other": 1}])

        # test matching 'num'
        data_num = {"some_key": [{"num": 123, "other": 1}]}
        self.assertEqual(self.importer.extract_posts_data(data_num), [{"num": 123, "other": 1}])

        # test matching 'com'
        data_com = {"some_key": [{"com": "hello", "other": 1}]}
        self.assertEqual(self.importer.extract_posts_data(data_com), [{"com": "hello", "other": 1}])

    def test_extract_posts_data_list(self):
        data = [{"id": 1}, {"id": 2}]
        result = self.importer.extract_posts_data(data)
        self.assertEqual(result, [{"id": 1}, {"id": 2}])

    def test_extract_posts_data_value_error_dict_unmatched(self):
        data = {"random": "string", "unrelated": {"dict": 1}}
        with self.assertRaisesRegex(ValueError, "Unknown JSON structure: could not find posts list"):
            self.importer.extract_posts_data(data)

    def test_extract_posts_data_value_error_non_dict_non_list(self):
        data = "just a string"
        with self.assertRaisesRegex(ValueError, "Unknown JSON structure: could not find posts list"):
            self.importer.extract_posts_data(data)

    def test_extract_posts_data_dict_nested_list_unmatched_keys(self):
        # the nested list of dicts does not have 'comment', 'no', 'num', 'com'
        data = {"some_key": [{"id": 123}]}
        with self.assertRaisesRegex(ValueError, "Unknown JSON structure: could not find posts list"):
            self.importer.extract_posts_data(data)

if __name__ == "__main__":
    unittest.main()
"""

with open("tests/test_site_importer.py", "w") as f:
    f.write(new_content)
