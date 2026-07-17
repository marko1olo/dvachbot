import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from common.db_pool import get_pool, create_pool, close_pool
import common.db_pool as db_pool_module

class TestDbPool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Reset globals for clean state
        db_pool_module._db_connection = None
        db_pool_module._reconnect_lock = asyncio.Lock()
        db_pool_module.db_lock = asyncio.Lock()

    @patch('common.db_pool.aiosqlite.connect', new_callable=AsyncMock)
    @patch('common.db_pool.asyncio.sleep', new_callable=AsyncMock)
    async def test_get_pool_retry_failure(self, mock_sleep, mock_connect):
        # Setup mock to always raise an exception
        mock_connect.side_effect = Exception("Mocked connection failure")

        # Call the function and expect the exception to be re-raised
        with self.assertRaises(Exception) as context:
            await get_pool()

        self.assertEqual(str(context.exception), "Mocked connection failure")

        # Verify connect was called exactly 3 times
        self.assertEqual(mock_connect.call_count, 3)

        # Verify sleep was called exactly 2 times with 2 seconds
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(2)

    @patch('common.db_pool.aiosqlite.connect', new_callable=AsyncMock)
    @patch('common.db_pool.asyncio.sleep', new_callable=AsyncMock)
    async def test_get_pool_success_after_retries(self, mock_sleep, mock_connect):
        # Setup mock to fail twice, then succeed
        mock_conn = AsyncMock() # We need an AsyncMock for the conn object because it will be awaited in conn.execute
        mock_connect.side_effect = [Exception("Fail 1"), Exception("Fail 2"), mock_conn]

        pool = await get_pool()

        self.assertEqual(pool, mock_conn)
        self.assertEqual(mock_connect.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(2)

if __name__ == '__main__':
    unittest.main()
