import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest
import os
import asyncio
from unittest.mock import patch
from common.bot_pool import MultiStreamBotPool

class TestBotPool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pool = MultiStreamBotPool()

    @patch.dict(os.environ, {
        "UPLOAD_BOT_POOL_RU": "111:token1, 222:token2",
        "UPLOAD_BOT_POOL_EN": "333:token3",
        "UPLOAD_BOT_POOL_JP": "111:token1, 444:token4"
    })
    def test_get_bot_by_id_found_in_shared(self):
        self.pool.init_stream('ru')

        # Test finding bot that was loaded in current stream
        bot = self.pool.get_bot_by_id(111)
        self.assertIsNotNone(bot)
        self.assertEqual(bot.id, 111)

    @patch.dict(os.environ, {
        "UPLOAD_BOT_POOL_RU": "111:token1",
        "UPLOAD_BOT_POOL_EN": "333:token3",
        "UPLOAD_BOT_POOL_JP": "444:token4"
    })
    def test_get_bot_by_id_found_lazy_load(self):
        # Only initialize 'ru' at first
        self.pool.init_stream('ru')

        # Test finding bot not in 'ru' but in 'en'
        bot = self.pool.get_bot_by_id(333)

        self.assertIsNotNone(bot)
        self.assertEqual(bot.id, 333)
        self.assertIn('en', self.pool._loaded_streams)

    @patch.dict(os.environ, {
        "UPLOAD_BOT_POOL_RU": "111:token1",
        "UPLOAD_BOT_POOL_EN": "333:token3",
        "UPLOAD_BOT_POOL_JP": "444:token4"
    })
    def test_get_bot_by_id_not_found(self):
        # We try to get a bot id that doesn't exist anywhere
        bot = self.pool.get_bot_by_id(999)
        self.assertIsNone(bot)

        # All streams should have been loaded as it searches through all
        self.assertIn('ru', self.pool._loaded_streams)
        self.assertIn('en', self.pool._loaded_streams)
        self.assertIn('jp', self.pool._loaded_streams)

if __name__ == '__main__':
    unittest.main()
