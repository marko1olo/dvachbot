from site_tgach.importer import ThreadImporter
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



import json
from unittest.mock import AsyncMock

import json
from unittest.mock import AsyncMock, MagicMock, patch

class TestFetchJson(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch("site_tgach.importer.asyncio.sleep", new_callable=AsyncMock)
    async def test_fetch_json_successful_retry(self, mock_sleep):

        import httpx

        importer = ThreadImporter(bot=None, file_storage_channel_id=123)
        importer.client = MagicMock()

        def create_mock_response(status, data=None, exc=None):
            resp = MagicMock()

            async def enter_mock(self_mock):
                if exc:
                    raise exc
                return resp

            async def exit_mock(*args):
                pass

            resp.__aenter__ = enter_mock
            resp.__aexit__ = exit_mock
            resp.status_code = status

            if data:
                async def mock_aiter():
                    yield data
                resp.aiter_bytes.return_value = mock_aiter()

            return resp

        resp1 = create_mock_response(200, exc=httpx.TimeoutException("Timeout 1"))
        resp2 = create_mock_response(200, exc=httpx.TimeoutException("Timeout 2"))
        resp3 = create_mock_response(200, data=b'{"success": true}')

        importer.client.stream.side_effect = [resp1, resp2, resp3, resp3, resp3]

        result = await importer.fetch_json("http://example.com/file.json")
        self.assertEqual(result, {"success": True})
        self.assertEqual(importer.client.stream.call_count, 3)

    @patch("site_tgach.importer.asyncio.sleep", new_callable=AsyncMock)
    async def test_fetch_json_failure_after_retries(self, mock_sleep):

        import httpx

        importer = ThreadImporter(bot=None, file_storage_channel_id=123)
        importer.client = MagicMock()

        def create_mock_response():
            resp = MagicMock()
            async def enter_mock(self_mock):
                raise httpx.TimeoutException("Timeout")
            resp.__aenter__ = enter_mock
            return resp

        importer.client.stream.side_effect = lambda *a, **k: create_mock_response()

        with self.assertRaisesRegex(Exception, "Failed to fetch resource after retries"):
            await importer.fetch_json("http://example.com/file.json")

        self.assertEqual(importer.client.stream.call_count, 5)

    @patch("site_tgach.importer.asyncio.sleep", new_callable=AsyncMock)
    async def test_fetch_json_decode_error(self, mock_sleep):


        importer = ThreadImporter(bot=None, file_storage_channel_id=123)
        importer.client = MagicMock()

        resp = MagicMock()
        async def enter_mock(self_mock):
            return resp
        async def exit_mock(*args):
            pass
        resp.__aenter__ = enter_mock
        resp.__aexit__ = exit_mock
        resp.status_code = 200

        async def mock_aiter():
            yield b'not json'

        resp.aiter_bytes.return_value = mock_aiter()

        importer.client.stream.return_value = resp

        with self.assertRaisesRegex(Exception, "Server returned non-JSON response"):
            await importer.fetch_json("http://example.com/file.json")

        self.assertEqual(importer.client.stream.call_count, 1)

if __name__ == "__main__":
    unittest.main()