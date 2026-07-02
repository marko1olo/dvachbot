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

        # Test basic escaped HTML
        raw_html = "Hello &lt;br&gt; World"
        normalized = importer_instance._normalize_html_sync(raw_html)

        # In the original method, <br> is replaced with \n and extra spaces might be present
        self.assertEqual(normalized, "Hello \n World")

        # Test other escaped entities
        raw_html = "&quot;Hello&quot; &amp; &#39;World&#39;"
        normalized = importer_instance._normalize_html_sync(raw_html)
        self.assertEqual(normalized, "\"Hello\" & 'World'")

        # Test that unescaped tags are processed correctly
        # (BeautifulSoup strips scripts and some tags, unwraps others)
        raw_html = "&lt;script&gt;alert(1)&lt;/script&gt;Hello"
        normalized = importer_instance._normalize_html_sync(raw_html)
        # script should be stripped
        self.assertEqual(normalized, "Hello")

        # Test spoiler
        raw_html = "Text &lt;span class=&quot;spoiler&quot;&gt;hidden&lt;/span&gt;"
        normalized = importer_instance._normalize_html_sync(raw_html)
        self.assertEqual(normalized, "Text ||hidden||")


    def test_normalize_html_sync_ast_unescape(self):
        import inspect
        import ast
        import textwrap
        from Dubsite_tgach.importer import ThreadImporter

        source = inspect.getsource(ThreadImporter._normalize_html_sync)
        source = textwrap.dedent(source)
        tree = ast.parse(source)

        unescape_found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'unescape':
                        unescape_found = True
                        break

        self.assertTrue(unescape_found, "unescape must be called in _normalize_html_sync to allow BeautifulSoup to parse tags properly")

if __name__ == "__main__":
    unittest.main()
