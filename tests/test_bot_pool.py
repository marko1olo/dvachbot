import unittest
import os
import sys
import asyncio
import itertools
from pathlib import Path
from unittest.mock import patch, MagicMock

# Mock required environment variables before imports
os.environ['SECRET_KEY'] = 'test_secret_key'
os.environ['BOT_TOKEN'] = 'test_bot_token'
os.environ['OPENAI_API_KEY'] = 'test_openai_api_key'

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Create and set new event loop to avoid Pyrogram/asyncio errors
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from common.bot_pool import MultiStreamBotPool

class TestBotPool(unittest.TestCase):
    def setUp(self):
        # Create a new pool for each test to avoid state leakage
        self.pool = MultiStreamBotPool()

    def test_get_next_bot_fallback(self):
        """Test that requesting an invalid stream falls back to 'ru'."""
        with patch.object(self.pool, 'init_stream') as mock_init_stream:
            # Setup: fake that 'ru' was initialized and has bots
            mock_bot_instance = MagicMock()
            self.pool.iterators['ru'] = itertools.cycle([(123, mock_bot_instance)])

            # Test: Request 'en' stream
            bot_id, bot = self.pool.get_next_bot('en')

            # Verify fallback logic
            self.assertEqual(bot_id, 123)
            self.assertEqual(bot, mock_bot_instance)

            # Since target_stream changes to 'ru' (which is in self.iterators),
            # init_stream('ru') is not explicitly called because of the logic:
            # target_stream = stream if stream in self.iterators else 'ru'
            # if target_stream not in self.iterators:
            #    self.init_stream('ru')
            # So init_stream is only called once for 'en'. Let's verify that.
            self.assertEqual(mock_init_stream.call_count, 1)
            mock_init_stream.assert_called_once_with('en')

    def test_get_next_bot_no_bots_error(self):
        """Test that if neither the requested stream nor fallback has bots, ValueError is raised."""
        with patch.object(self.pool, 'init_stream'):
            # self.iterators is empty

            # Test: Request any stream, even 'ru'
            # It should raise ValueError since no bots are available
            with self.assertRaises(ValueError) as context:
                self.pool.get_next_bot('en')

            self.assertIn("No bots available for stream en or ru!", str(context.exception))

if __name__ == '__main__':
    unittest.main()
