import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import json
import sys
from contextlib import asynccontextmanager

# In some test suite runs, test_main.py heavily pollutes sys.modules by mocking all site_tgach.* modules
# and attaching __getattr__ = lambda: MagicMock() to them. The hasattr(__file__) check is unreliable
# because __getattr__ returns MagicMock for any attribute including __file__.
# Unconditionally evict all site_tgach.* mocks so we get the real module.
import types
for _key in [k for k in sys.modules if k.startswith('site_tgach')]:
    _mod = sys.modules[_key]
    # It's a mock if it has no real __spec__ or is a bare ModuleType without a file
    if isinstance(_mod, types.ModuleType) and getattr(_mod, '__spec__', None) is None:
        del sys.modules[_key]

from site_tgach.rss import generate_rss

class MockCursor:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return self.rows.pop(0)
        except IndexError:
            raise StopAsyncIteration

class TestRSS(unittest.IsolatedAsyncioTestCase):
    @patch("site_tgach.rss.BOARD_CONFIG", {})
    async def test_404_response(self):
        request = MagicMock()
        request.base_url = "http://testserver/"
        response = await generate_rss("unknown_board", request)
        self.assertEqual(response.status_code, 404)

    @patch("site_tgach.rss.BOARD_CONFIG", {"b": {"name": "Бред"}})
    @patch("site_tgach.rss.get_pool", new_callable=AsyncMock)
    async def test_success_path(self, mock_get_pool):
        mock_db = MagicMock()

        @asynccontextmanager
        async def mock_execute(query, args):
            yield MockCursor([
                (1, json.dumps({"text": "Hello world"}), 1620000000.0),
                (2, json.dumps({"text": "<b>Test HTML</b>"}), 1620000010.0),
            ])

        mock_db.execute = mock_execute
        mock_get_pool.return_value = mock_db

        request = MagicMock()
        request.base_url = "http://testserver/"

        response = await generate_rss("b", request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "application/xml")

        content = response.body.decode()
        self.assertIn("<title>ТГАЧ - Бред</title>", content)
        self.assertIn("<link>http://testserver/b/</link>", content)

        # Check items
        self.assertIn("<title>#1 Hello world...</title>", content)
        self.assertIn("<title>#2 Test HTML...</title>", content) # HTML stripped
        self.assertIn("<![CDATA[<b>Test HTML</b>]]>", content) # Raw HTML in description

    @patch("site_tgach.rss.BOARD_CONFIG", {"b": {"name": "Бред"}})
    @patch("site_tgach.rss.get_pool", new_callable=AsyncMock)
    async def test_db_error_path(self, mock_get_pool):
        mock_db = MagicMock()

        @asynccontextmanager
        async def mock_execute_error(query, args):
            raise Exception("Test Database Error")
            yield MockCursor([]) # unreachable

        mock_db.execute = mock_execute_error
        mock_get_pool.return_value = mock_db

        request = MagicMock()
        request.base_url = "http://testserver/"

        response = await generate_rss("b", request)
        self.assertEqual(response.status_code, 200)

        content = response.body.decode()
        self.assertIn("<title>ТГАЧ - Бред</title>", content)
        self.assertNotIn("<item>", content) # No items due to error

    @patch("site_tgach.rss.BOARD_CONFIG", {"b": {"name": "Бред"}})
    @patch("site_tgach.rss.get_pool", new_callable=AsyncMock)
    async def test_content_parsing_error(self, mock_get_pool):
        mock_db = MagicMock()

        @asynccontextmanager
        async def mock_execute(query, args):
            yield MockCursor([
                (1, json.dumps({"text": "First"}), 1620000000.0),
                (2, "invalid json", 1620000010.0),
                (3, json.dumps({"text": "Third"}), 1620000020.0),
            ])

        mock_db.execute = mock_execute
        mock_get_pool.return_value = mock_db

        request = MagicMock()
        request.base_url = "http://testserver/"

        response = await generate_rss("b", request)
        self.assertEqual(response.status_code, 200)

        content = response.body.decode()
        self.assertIn("<title>#1 First...</title>", content)
        self.assertNotIn("#2", content)
        self.assertIn("<title>#3 Third...</title>", content)
