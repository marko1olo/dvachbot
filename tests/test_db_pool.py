import asyncio
from unittest.mock import patch, AsyncMock
import unittest
from common import db_pool

class TestDbPoolRetry(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        db_pool._db_connection = None
        # Reset the lock for each test to ensure a clean state
        db_pool._reconnect_lock = asyncio.Lock()

    @patch("common.db_pool.asyncio.sleep", new_callable=AsyncMock)
    @patch("common.db_pool.aiosqlite.connect", new_callable=AsyncMock)
    async def test_get_pool_retries_and_raises(self, mock_connect, mock_sleep):
        """
        Test that get_pool retries 3 times when aiosqlite.connect fails,
        sleeps for 2 seconds between retries, and ultimately raises the exception.
        """
        test_exception = Exception("Test connection failure")
        mock_connect.side_effect = test_exception

        with self.assertRaises(Exception) as context:
            await db_pool.get_pool()

        self.assertEqual(str(context.exception), "Test connection failure")

        # Verify it retried 3 times (the loop runs 3 times)
        self.assertEqual(mock_connect.call_count, 3)

        # Verify it slept 2 times (only for the first two failures)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_any_call(2)

if __name__ == "__main__":
    unittest.main()
