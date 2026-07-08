import sys
import os
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

# Setup required env vars
os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "123:test"

# No need to mock everything globally here, main.py behaves normally
# when imported directly in a single test file without Dispatcher mock conflicts,
# as long as we only run the single test, or we ensure the test executes successfully.
import main

class TestDeleteUserPosts(unittest.IsolatedAsyncioTestCase):
    @patch("main._delete_user_posts_from_db", new_callable=AsyncMock)
    @patch("main._clean_posts_from_ram", new_callable=AsyncMock)
    @patch("main._clean_posts_from_caches", new_callable=MagicMock)
    @patch("main._delete_posts_from_channels", new_callable=AsyncMock)
    @patch("main._delete_posts_from_pm_api", new_callable=AsyncMock)
    async def test_delete_user_posts_happy_path(
        self,
        mock_delete_pm,
        mock_delete_channels,
        mock_clean_caches,
        mock_clean_ram,
        mock_delete_db,
    ):
        mock_bot = MagicMock()
        # Mock DB returning lists of posts, PM messages, and channel messages
        mock_delete_db.return_value = ([1, 2, 3], ['msg1', 'msg2'], ['chan1', 'chan2'])
        # Mock total deleted returned from PM api
        mock_delete_pm.return_value = 5

        res = await main.delete_user_posts(mock_bot, 12345, 60, "b")

        self.assertEqual(res, 5)
        mock_delete_db.assert_called_once()
        mock_clean_ram.assert_called_once_with([1, 2, 3], "b")
        mock_clean_caches.assert_called_once_with([1, 2, 3])
        mock_delete_channels.assert_called_once_with(['chan1', 'chan2'], mock_bot)
        mock_delete_pm.assert_called_once_with(['msg1', 'msg2'], mock_bot)

    @patch("main._delete_user_posts_from_db", new_callable=AsyncMock)
    @patch("main._clean_posts_from_ram", new_callable=AsyncMock)
    @patch("main._clean_posts_from_caches", new_callable=MagicMock)
    @patch("main._delete_posts_from_channels", new_callable=AsyncMock)
    @patch("main._delete_posts_from_pm_api", new_callable=AsyncMock)
    async def test_delete_user_posts_no_posts(
        self,
        mock_delete_pm,
        mock_delete_channels,
        mock_clean_caches,
        mock_clean_ram,
        mock_delete_db,
    ):
        mock_bot = MagicMock()
        # Mock DB returning empty lists
        mock_delete_db.return_value = ([], [], [])

        res = await main.delete_user_posts(mock_bot, 12345, 60, "b")

        # When no posts, returns 0 directly
        self.assertEqual(res, 0)
        mock_delete_db.assert_called_once()
        mock_clean_ram.assert_not_called()
        mock_clean_caches.assert_not_called()
        mock_delete_channels.assert_not_called()
        mock_delete_pm.assert_not_called()

    @patch("main._delete_user_posts_from_db", new_callable=AsyncMock)
    async def test_delete_user_posts_exception(self, mock_delete_db):
        mock_bot = MagicMock()
        # Simulating DB failure
        mock_delete_db.side_effect = Exception("DB error")

        # We also mock print to prevent the traceback from dirtying the console output during tests
        with patch('builtins.print'):
            res = await main.delete_user_posts(mock_bot, 12345, 60, "b")

        self.assertEqual(res, 0)
        mock_delete_db.assert_called_once()

if __name__ == "__main__":
    unittest.main()
