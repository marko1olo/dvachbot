import unittest
import asyncio
from unittest.mock import patch, MagicMock
import os
import sys

# Add project root to sys.path to allow importing from Dubsite_tgach
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock environment variables needed for initialization
os.environ["SECRET_KEY"] = "dummy_secret_key"
os.environ["BOT_TOKEN"] = "dummy_bot_token"
os.environ["OPENAI_API_KEY"] = "dummy_openai_key"


class TestImporter(unittest.TestCase):
    def setUp(self):
        # We need an event loop for Pyrogram to import
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_normalize_html_sync_unescape(self):
        from Dubsite_tgach.importer import ThreadImporter
        importer_instance = ThreadImporter(bot=None, file_storage_channel_id=123)

        # Test basic escaped HTML (User inputted tags should NOT be parsed as HTML tags)
        raw_html = "Hello &lt;br&gt; World"
        normalized = importer_instance._normalize_html_sync(raw_html)

        # Since unescape is removed at start, the tags are treated as text and unescaped later by BeautifulSoup
        self.assertEqual(normalized, "Hello <br> World")

        # Test other escaped entities
        raw_html = "&quot;Hello&quot; &amp; &#39;World&#39;"
        normalized = importer_instance._normalize_html_sync(raw_html)
        self.assertEqual(normalized, "\"Hello\" & 'World'")

        # Test that user inputted unescaped tags are processed correctly as text, not HTML elements to remove
        raw_html = "&lt;script&gt;alert(1)&lt;/script&gt;Hello"
        normalized = importer_instance._normalize_html_sync(raw_html)
        # script should NOT be stripped
        self.assertEqual(normalized, "<script>alert(1)</script>Hello")

        # Test spoiler, if it is actual HTML
        raw_html = 'Text <span class="spoiler">hidden</span>'
        normalized = importer_instance._normalize_html_sync(raw_html)
        self.assertEqual(normalized, "Text ||hidden||")

if __name__ == "__main__":
    unittest.main()
