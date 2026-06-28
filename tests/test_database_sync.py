import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio
import sqlite3

from common.database import sync_boards_with_config

class TestSyncBoardsWithConfig(unittest.IsolatedAsyncioTestCase):
    async def test_success(self):
        board_config = {"b": {"name": "Random", "description": "Random board"}}

        mock_db = AsyncMock()

        with patch("common.db_pool.get_pool", new_callable=AsyncMock) as mock_get_pool, \
             patch("common.db_pool.db_lock", new_callable=asyncio.Lock):

            mock_get_pool.return_value = mock_db

            await sync_boards_with_config(board_config)

            mock_get_pool.assert_awaited_once()
            mock_db.execute.assert_any_call("BEGIN IMMEDIATE")
            mock_db.executemany.assert_awaited_once()
            mock_db.execute.assert_any_call("COMMIT")

    async def test_retry_on_locked(self):
        board_config = {"b": {"name": "Random", "description": "Random board"}}

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [
            sqlite3.OperationalError("database is locked"), # Attempt 1 BEGIN
            None,                                           # Attempt 1 ROLLBACK
            sqlite3.OperationalError("database is locked"), # Attempt 2 BEGIN
            None,                                           # Attempt 2 ROLLBACK
            None,                                           # Attempt 3 BEGIN
            None,                                           # Attempt 3 COMMIT
        ]

        with patch("common.db_pool.get_pool", new_callable=AsyncMock) as mock_get_pool, \
             patch("common.db_pool.db_lock", new_callable=asyncio.Lock), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

            mock_get_pool.return_value = mock_db

            await sync_boards_with_config(board_config)

            self.assertEqual(mock_get_pool.await_count, 3)
            self.assertEqual(mock_sleep.await_count, 2)
            mock_sleep.assert_any_await(0.5)
            mock_sleep.assert_any_await(1.0)

    async def test_break_on_other_operational_error(self):
        board_config = {"b": {"name": "Random", "description": "Random board"}}

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [
            sqlite3.OperationalError("syntax error"), # BEGIN IMMEDIATE
            None,                                     # ROLLBACK
        ]

        with patch("common.db_pool.get_pool", new_callable=AsyncMock) as mock_get_pool, \
             patch("common.db_pool.db_lock", new_callable=asyncio.Lock):

            mock_get_pool.return_value = mock_db

            await sync_boards_with_config(board_config)

            # Should only try once and then break
            self.assertEqual(mock_get_pool.await_count, 1)

    async def test_break_on_generic_exception(self):
        board_config = {"b": {"name": "Random", "description": "Random board"}}

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [
            Exception("Some unknown error"), # BEGIN IMMEDIATE
            None,                            # ROLLBACK
        ]

        with patch("common.db_pool.get_pool", new_callable=AsyncMock) as mock_get_pool, \
             patch("common.db_pool.db_lock", new_callable=asyncio.Lock):

            mock_get_pool.return_value = mock_db

            await sync_boards_with_config(board_config)

            # Should only try once and then break
            self.assertEqual(mock_get_pool.await_count, 1)

if __name__ == '__main__':
    unittest.main()
