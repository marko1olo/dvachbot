import sys
import os
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

# Need dummy environment variables
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DB_USER"] = "test"
os.environ["DB_PASS"] = "test"
os.environ["DB_HOST"] = "localhost"
os.environ["DB_NAME"] = "test"

# Set up paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

class TestNotifyAdmins(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # We only need to mock bjoern which failed to build
        cls.patcher = patch.dict('sys.modules', {
            'bjoern': MagicMock(),
        })
        cls.patcher.start()

        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Now import the module
        import Dubsite_tgach.main
        cls.main_module = Dubsite_tgach.main

        # We must add the exception types because they are not imported in main.py
        from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError
        cls.main_module.TelegramRetryAfter = TelegramRetryAfter
        cls.main_module.TelegramForbiddenError = TelegramForbiddenError

        # Mock ADMIN_IDS specifically for this test
        cls.original_admin_ids = getattr(Dubsite_tgach.main, 'ADMIN_IDS', [])
        cls.main_module.ADMIN_IDS = [1, 2, 3]

    @classmethod
    def tearDownClass(cls):
        cls.main_module.ADMIN_IDS = cls.original_admin_ids
        cls.patcher.stop()

    async def asyncSetUp(self):
        # Reset ADMIN_IDS before each test to avoid bleed from blocked_admins removal
        self.main_module.ADMIN_IDS = [1, 2, 3]

    async def test_notify_admins_success(self):
        bot = AsyncMock()
        bot.send_message.return_value = True

        with patch.object(self.main_module.asyncio, 'sleep', new_callable=AsyncMock) as mock_sleep:
            await self.main_module.notify_admins(bot, "test message")

        self.assertEqual(bot.send_message.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 3)
        mock_sleep.assert_called_with(0.05)

    async def test_notify_admins_forbidden(self):
        bot = AsyncMock()
        from aiogram.exceptions import TelegramForbiddenError
        bot.send_message.side_effect = [True, TelegramForbiddenError(method='send_message', message='Forbidden'), True]

        with patch.object(self.main_module.asyncio, 'sleep', new_callable=AsyncMock) as mock_sleep:
            await self.main_module.notify_admins(bot, "test message")

        self.assertEqual(bot.send_message.call_count, 3)
        # Sleep is not called for the forbidden error iteration
        self.assertEqual(mock_sleep.call_count, 2)

    async def test_notify_admins_retry_after(self):
        bot = AsyncMock()
        from aiogram.exceptions import TelegramRetryAfter
        # Need to provide enough responses for all tries
        bot.send_message.side_effect = [
            TelegramRetryAfter(method='send_message', message='Retry after', retry_after=5),
            True, # This is the retry for admin 1 (which works)
            True, # Admin 2 (works)
            True  # Admin 3 (works)
        ]

        with patch.object(self.main_module.asyncio, 'sleep', new_callable=AsyncMock) as mock_sleep:
            await self.main_module.notify_admins(bot, "test message")

        # 1st admin gets error, waits, then sent again (2 calls for 1st admin).
        # 2nd and 3rd admin get 1 call each. Total = 4 calls.
        self.assertEqual(bot.send_message.call_count, 4)

        # In main.py:
        # try:
        #    await send_message -> fails
        #    await sleep(0.05) -> skipped
        # except RetryAfter:
        #    await sleep(retry + 1)
        #    try:
        #        await send_message -> succeeds
        #        # NO SLEEP HERE in the code!
        #
        # Admin 2 -> send -> sleep(0.05)
        # Admin 3 -> send -> sleep(0.05)
        #
        # Total sleep count should be 3
        self.assertEqual(mock_sleep.call_count, 3)
        mock_sleep.assert_any_call(6)

    async def test_notify_admins_general_exception(self):
        bot = AsyncMock()
        bot.send_message.side_effect = [Exception("Test error"), True, True]

        with patch.object(self.main_module.asyncio, 'sleep', new_callable=AsyncMock) as mock_sleep:
            await self.main_module.notify_admins(bot, "test message")

        self.assertEqual(bot.send_message.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    async def test_notify_admins_retry_after_second_failure(self):
        bot = AsyncMock()
        from aiogram.exceptions import TelegramRetryAfter
        bot.send_message.side_effect = [
            TelegramRetryAfter(method='send_message', message='Retry after', retry_after=5),
            Exception("Second failure"), # Second try for admin 1
            True, # Admin 2
            True  # Admin 3
        ]

        with patch.object(self.main_module.asyncio, 'sleep', new_callable=AsyncMock) as mock_sleep:
            await self.main_module.notify_admins(bot, "test message")

        self.assertEqual(bot.send_message.call_count, 4)
        # Sleep for retry (6s)
        # Wait for Admin 2 (0.05)
        # Wait for Admin 3 (0.05)
        # Total = 3
        self.assertEqual(mock_sleep.call_count, 3)
        mock_sleep.assert_any_call(6)

if __name__ == '__main__':
    unittest.main()
