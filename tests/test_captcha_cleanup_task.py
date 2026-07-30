import unittest
from unittest.mock import patch, MagicMock
import asyncio
import time
import sys
import os

sys.modules['bjoern'] = MagicMock()

os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"
os.environ["DB_USER"] = "test"
os.environ["DB_PASS"] = "test"
os.environ["DB_HOST"] = "test"
os.environ["DB_NAME"] = "test"

import Dubsite_tgach.main as main

class TestCaptchaCleanupTask(unittest.IsolatedAsyncioTestCase):
    async def test_captcha_cleanup_task(self):
        main.CAPTCHA_SESSIONS.clear()
        now = time.time()

        main.CAPTCHA_SESSIONS['test1'] = {'expires': now - 100} # expired
        main.CAPTCHA_SESSIONS['test2'] = {'expires': now + 100} # valid

        with patch('asyncio.sleep') as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            try:
                await main.captcha_cleanup_task()
            except asyncio.CancelledError:
                pass

        self.assertNotIn('test1', main.CAPTCHA_SESSIONS)
        self.assertIn('test2', main.CAPTCHA_SESSIONS)

    async def test_captcha_cleanup_task_exception(self):
        main.CAPTCHA_SESSIONS.clear()

        with patch('asyncio.sleep') as mock_sleep, patch('time.time') as mock_time, patch('Dubsite_tgach.main.logger.error') as mock_log_error:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            mock_time.side_effect = Exception("Test Error")

            try:
                await main.captcha_cleanup_task()
            except asyncio.CancelledError:
                pass

            mock_log_error.assert_called_once()
            self.assertIn("Test Error", mock_log_error.call_args[0][0])
