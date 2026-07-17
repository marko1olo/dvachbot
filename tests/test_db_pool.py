import unittest
from unittest.mock import AsyncMock, patch, MagicMock, call
import asyncio
import aiosqlite

import common.db_pool

class TestDbPool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        common.db_pool._db_connection = None
        # Must reset module level lock because isolated tests create new event loops
        common.db_pool._reconnect_lock = asyncio.Lock()

    async def asyncTearDown(self):
        common.db_pool._db_connection = None

    @patch('common.db_pool.aiosqlite.connect', new_callable=AsyncMock)
    async def test_get_pool_creates_new(self, mock_connect):
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn

        conn = await common.db_pool.get_pool()

        self.assertEqual(conn, mock_conn)
        self.assertEqual(common.db_pool._db_connection, mock_conn)
        mock_connect.assert_called_once_with(common.db_pool.DB_NAME, timeout=60.0, isolation_level=None)
        mock_conn.execute.assert_has_calls([
            call("PRAGMA busy_timeout = 60000;"),
            call("PRAGMA journal_mode=WAL;"),
        ], any_order=False)

    @patch('common.db_pool.aiosqlite.connect', new_callable=AsyncMock)
    async def test_get_pool_returns_cached(self, mock_connect):
        mock_conn = AsyncMock()
        mock_conn._running = True
        mock_conn._conn = True
        common.db_pool._db_connection = mock_conn

        conn = await common.db_pool.get_pool()

        self.assertEqual(conn, mock_conn)
        mock_connect.assert_not_called()

    @patch('common.db_pool.aiosqlite.connect', new_callable=AsyncMock)
    async def test_get_pool_reconnects_if_dead(self, mock_connect):
        dead_conn = AsyncMock()
        dead_conn._running = False
        dead_conn._conn = None
        common.db_pool._db_connection = dead_conn

        new_conn = AsyncMock()
        mock_connect.return_value = new_conn

        conn = await common.db_pool.get_pool()

        self.assertEqual(conn, new_conn)
        dead_conn.close.assert_called_once()
        mock_connect.assert_called_once()

    @patch('common.db_pool.asyncio.sleep', new_callable=AsyncMock)
    @patch('common.db_pool.aiosqlite.connect', new_callable=AsyncMock)
    async def test_get_pool_retries_and_succeeds(self, mock_connect, mock_sleep):
        mock_connect.side_effect = [Exception("Failed 1"), Exception("Failed 2"), AsyncMock()]

        conn = await common.db_pool.get_pool()

        self.assertEqual(mock_connect.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_has_calls([call(2), call(2)])
        self.assertIsNotNone(conn)

    @patch('common.db_pool.asyncio.sleep', new_callable=AsyncMock)
    @patch('common.db_pool.aiosqlite.connect', new_callable=AsyncMock)
    async def test_get_pool_retries_and_fails(self, mock_connect, mock_sleep):
        mock_connect.side_effect = [Exception("Failed 1"), Exception("Failed 2"), Exception("Failed 3")]

        with self.assertRaises(Exception) as context:
            await common.db_pool.get_pool()

        self.assertEqual(str(context.exception), "Failed 3")
        self.assertEqual(mock_connect.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('common.db_pool.get_pool', new_callable=AsyncMock)
    async def test_create_pool_alias(self, mock_get_pool):
        mock_conn = AsyncMock()
        mock_get_pool.return_value = mock_conn

        conn = await common.db_pool.create_pool()

        self.assertEqual(conn, mock_conn)
        mock_get_pool.assert_called_once()

    async def test_close_pool(self):
        mock_conn = AsyncMock()
        common.db_pool._db_connection = mock_conn

        await common.db_pool.close_pool()

        mock_conn.close.assert_called_once()
        self.assertIsNone(common.db_pool._db_connection)

    async def test_close_pool_no_connection(self):
        common.db_pool._db_connection = None
        await common.db_pool.close_pool()
        # Should not raise any exception
        self.assertIsNone(common.db_pool._db_connection)
