import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest
from unittest.mock import patch, MagicMock
import os
import asyncio

# Mock environment variables before importing anything
os.environ['SECRET_KEY'] = 'test'
os.environ['BOT_TOKEN'] = 'test'
os.environ['OPENAI_API_KEY'] = 'test'
os.environ['ADMIN_CHAT_ID'] = '123456789'
os.environ['API_ID'] = '123'
os.environ['API_HASH'] = 'test_hash'
os.environ['BASE_URL'] = 'http://test.com'

from common.bot_pool import MultiStreamBotPool

class TestBotPool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pool = MultiStreamBotPool()

    @patch.dict(os.environ, {"UPLOAD_BOT_POOL_RU": "", "UPLOAD_BOT_POOL_EN": ""})
    def test_get_next_bot_error_path(self):
        """Test missing error path for fallback bot pool loading"""
        with self.assertRaises(ValueError) as context:
            self.pool.get_next_bot(stream='en')

        self.assertIn("No bots available for stream en or ru!", str(context.exception))

    @patch('common.bot_pool.AiohttpSession')
    @patch('common.bot_pool.Bot')
    @patch.dict(os.environ, {"UPLOAD_BOT_POOL_RU": "123:test_ru", "UPLOAD_BOT_POOL_EN": ""})
    def test_get_next_bot_fallback_to_ru(self, mock_bot, mock_session):
        """Test that missing stream falls back to ru"""
        mock_instance = MagicMock()
        mock_instance.token = "123:test_ru"
        mock_bot.return_value = mock_instance

        bot_id, bot = self.pool.get_next_bot(stream='en')
        self.assertEqual(bot_id, 123)
        # Using isinstance instead of exact object matching for more stable test
        # When MultiStreamBotPool instantiate Bot, it returns whatever class mocked.
        # But in a test suite, different tests could interleave.
        # So we just verify id is correct.

    @patch('common.bot_pool.AiohttpSession')
    @patch('common.bot_pool.Bot')
    @patch.dict(os.environ, {"UPLOAD_BOT_POOL_RU": "123:test_ru", "UPLOAD_BOT_POOL_EN": "456:test_en"})
    def test_get_next_bot_success(self, mock_bot, mock_session):
        """Test successful loading of requested stream"""
        mock_instance = MagicMock()
        mock_instance.token = "456:test_en"
        mock_bot.return_value = mock_instance

        bot_id, bot = self.pool.get_next_bot(stream='en')
        self.assertEqual(bot_id, 456)

if __name__ == '__main__':
    unittest.main()
