import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from Dubsite_tgach.rss import generate_rss
from fastapi import Request, Response
import time

class TestRSS(unittest.IsolatedAsyncioTestCase):
    @patch('Dubsite_tgach.rss.get_pool')
    @patch('Dubsite_tgach.rss.BOARD_CONFIG', {'testboard': {'name': 'Test Board'}})
    async def test_generate_rss(self, mock_get_pool):
        # Mock request
        request = MagicMock(spec=Request)
        request.base_url = 'http://testserver.com/'

        # Mock DB and cursor
        mock_db = AsyncMock()
        mock_get_pool.return_value = mock_db

        # Proper async context manager setup
        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [
            # the query uses json_extract(p.content, '$.text') so it only returns the string directly
            (1, 'Hello <b>world</b>', time.time()),
            (2, None, time.time()), # Test None text_raw
            (3, '', time.time()), # Test empty text string
        ]

        class AsyncContextManagerMock:
            async def __aenter__(self):
                return mock_cursor
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        # Return a standard mock object, but return our custom context manager mock when called
        mock_execute = MagicMock()
        mock_execute.return_value = AsyncContextManagerMock()
        mock_db.execute = mock_execute

        response = await generate_rss('testboard', request)
        self.assertIsInstance(response, Response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "application/xml")

        xml_content = response.body.decode('utf-8')

        self.assertIn('<rss version="2.0">', xml_content)
        self.assertIn('<title>ТГАЧ - Test Board</title>', xml_content)
        self.assertIn('Hello world...', xml_content) # Verify HTML cleaning works on output

    @patch('Dubsite_tgach.rss.BOARD_CONFIG', {})
    async def test_generate_rss_not_found(self):
        request = MagicMock()
        response = await generate_rss('notfound', request)
        self.assertEqual(response.status_code, 404)

if __name__ == '__main__':
    unittest.main()
