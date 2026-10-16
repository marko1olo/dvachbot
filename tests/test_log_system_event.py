import unittest
from unittest.mock import patch, MagicMock, ANY
from collections import deque
import datetime
import asyncio

# We installed all dependencies successfully.
import os
os.environ["SECRET_KEY"] = "dummy_secret_key"
os.environ["FILE_UPLOADER_BOT_TOKEN"] = "dummy_bot_token"
os.environ["FILE_STORAGE_CHANNEL_ID"] = "123"

import Dubsite_tgach.main
import site_tgach.main

class TestLogSystemEvent(unittest.TestCase):
    @patch('Dubsite_tgach.main.datetime')
    @patch('Dubsite_tgach.main.spawn_task')
    def test_log_system_event_dubsite(self, mock_spawn_task, mock_datetime):
        mock_now = MagicMock()
        mock_datetime.now.return_value = mock_now
        mock_now.strftime.return_value = "14:30:00"

        # log_global_event is an async function. Let's patch it with a dummy async function
        async def mock_log_event(src, msg):
            return f"mock_{src}_{msg}"

        with patch('Dubsite_tgach.main.log_global_event', side_effect=mock_log_event) as mock_log_global_event:
            with patch('Dubsite_tgach.main.SYSTEM_LOGS', new_callable=lambda: deque(maxlen=100)) as mock_system_logs:
                Dubsite_tgach.main.log_system_event("Test Dubsite Message")

                mock_log_global_event.assert_called_once_with('site', "Test Dubsite Message")

                # We expect spawn_task to be called with a coroutine
                self.assertEqual(mock_spawn_task.call_count, 1)
                coro = mock_spawn_task.call_args[0][0]
                self.assertTrue(asyncio.iscoroutine(coro))

                # Let's cleanly await the coroutine to avoid RuntimeWarning
                result = asyncio.run(coro)
                self.assertEqual(result, "mock_site_Test Dubsite Message")

                self.assertEqual(len(mock_system_logs), 1)
                self.assertEqual(mock_system_logs[0], "[14:30:00] Test Dubsite Message")

    @patch('site_tgach.main.datetime')
    @patch('site_tgach.main.spawn_task')
    def test_log_system_event_site(self, mock_spawn_task, mock_datetime):
        mock_now = MagicMock()
        mock_datetime.now.return_value = mock_now
        mock_now.strftime.return_value = "15:45:00"

        async def mock_log_event(src, msg):
            return f"mock_{src}_{msg}"

        with patch('site_tgach.main.log_global_event', side_effect=mock_log_event) as mock_log_global_event:
            with patch('site_tgach.main.SYSTEM_LOGS', new_callable=lambda: deque(maxlen=100)) as mock_system_logs:
                site_tgach.main.log_system_event("Test Site Message")

                mock_log_global_event.assert_called_once_with('site', "Test Site Message")

                self.assertEqual(mock_spawn_task.call_count, 1)
                coro = mock_spawn_task.call_args[0][0]
                self.assertTrue(asyncio.iscoroutine(coro))

                result = asyncio.run(coro)
                self.assertEqual(result, "mock_site_Test Site Message")

                self.assertEqual(len(mock_system_logs), 1)
                self.assertEqual(mock_system_logs[0], "[15:45:00] Test Site Message")

if __name__ == '__main__':
    unittest.main()
