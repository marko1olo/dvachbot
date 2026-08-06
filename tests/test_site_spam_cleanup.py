import sys
import time
import asyncio
import unittest
from unittest.mock import patch, MagicMock

class TestSiteSpamCleanup(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict('sys.modules', {'bjoern': MagicMock()}):
            # Import once at class level to avoid ImportError
            import Dubsite_tgach.main as dm
            cls.dm = dm
            cls.site_spam_tracker = dm.site_spam_tracker

    async def test_site_spam_cleanup_task(self):
        self.site_spam_tracker.clear()

        with patch('time.time', return_value=5000.0) as mock_time:
            # Board 1: user1 active, user2 inactive
            self.site_spam_tracker['board1']['user1']['timestamps'] = [4000.0, 4500.0]  # Diff 500 <= 3600
            self.site_spam_tracker['board1']['user2']['timestamps'] = [1000.0, 1200.0]  # Diff 3800 > 3600

            # Board 2: user3 inactive, user4 no timestamps
            self.site_spam_tracker['board2']['user3']['timestamps'] = [1000.0]
            self.site_spam_tracker['board2']['user4']['timestamps'] = []

            # Board 3: explicitly empty
            self.site_spam_tracker['board3']
            self.site_spam_tracker['board3'].clear()

            async def mock_sleep_exception(delay):
                if getattr(mock_sleep_exception, 'called', False):
                    raise asyncio.CancelledError()
                mock_sleep_exception.called = True

            with patch('asyncio.sleep', new=mock_sleep_exception):
                with patch.object(self.dm, 'logger') as mock_logger:
                    try:
                        await self.dm.site_spam_cleanup_task()
                    except asyncio.CancelledError:
                        import traceback; traceback.print_exc()

            self.assertIn('board1', self.site_spam_tracker)
            self.assertIn('user1', self.site_spam_tracker['board1'])
            self.assertNotIn('user2', self.site_spam_tracker['board1'])

            self.assertNotIn('board2', self.site_spam_tracker)
            self.assertNotIn('board3', self.site_spam_tracker)

            mock_logger.info.assert_any_call("🧹 [Site] Cleaning spam tracker memory...")
            mock_logger.info.assert_any_call("✅ [Site] Spam tracker cleaned.")

    async def test_site_spam_cleanup_exception(self):
        self.site_spam_tracker.clear()

        with patch('time.time', side_effect=Exception("Test Error")):
            async def mock_sleep_exception(delay):
                if getattr(mock_sleep_exception, 'called', False):
                    raise asyncio.CancelledError()
                mock_sleep_exception.called = True

            with patch('asyncio.sleep', new=mock_sleep_exception):
                with patch.object(self.dm, 'logger') as mock_logger:
                    try:
                        await self.dm.site_spam_cleanup_task()
                    except asyncio.CancelledError:
                        import traceback; traceback.print_exc()

            mock_logger.error.assert_called_once_with("⚠️ Error cleaning site spam tracker: Test Error")

if __name__ == '__main__':
    unittest.main()
