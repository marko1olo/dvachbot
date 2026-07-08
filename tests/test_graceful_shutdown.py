import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from common.shutdown import _graceful_shutdown_impl

class TestGracefulShutdown(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.is_shutting_down_state = False
        def set_shutting_down_cb(val):
            self.is_shutting_down_state = val

        self.set_shutting_down_cb = set_shutting_down_cb
        self.shutdown_event = MagicMock()
        self.dp = MagicMock()
        self.dp.stop_polling = AsyncMock()
        self.runtime_logger = MagicMock()

        self.pending_edit_lock = MagicMock()
        self.pending_edit_lock.__aenter__ = AsyncMock()
        self.pending_edit_lock.__aexit__ = AsyncMock()

        self.pending_edit_tasks = {}
        self.git_executor = MagicMock()
        self.save_executor = MagicMock()

        self.mock_db = AsyncMock()
        self.get_pool = AsyncMock(return_value=self.mock_db)

        self.db_lock = MagicMock()
        self.db_lock.__aenter__ = AsyncMock()
        self.db_lock.__aexit__ = AsyncMock()

        self.close_pool = AsyncMock()

    @patch('asyncio.sleep', new_callable=AsyncMock)
    async def test_graceful_shutdown_success(self, mock_sleep):
        mock_site = AsyncMock()

        await _graceful_shutdown_impl(
            self.is_shutting_down_state,
            self.set_shutting_down_cb,
            self.shutdown_event,
            self.dp,
            self.runtime_logger,
            self.pending_edit_lock,
            self.pending_edit_tasks,
            self.git_executor,
            self.save_executor,
            self.get_pool,
            self.db_lock,
            self.close_pool,
            healthcheck_site=mock_site,
            emergency=False
        )

        self.shutdown_event.set.assert_called_once()
        self.dp.stop_polling.assert_awaited_once()
        self.mock_db.execute.assert_awaited_once_with("PRAGMA wal_checkpoint(TRUNCATE);")
        mock_site.stop.assert_awaited_once()
        self.close_pool.assert_awaited_once()
        self.git_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        self.save_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        self.assertTrue(self.is_shutting_down_state)

    @patch('asyncio.sleep', new_callable=AsyncMock)
    async def test_graceful_shutdown_db_error(self, mock_sleep):
        mock_site = AsyncMock()
        self.mock_db.execute.side_effect = Exception("DB error")

        await _graceful_shutdown_impl(
            self.is_shutting_down_state,
            self.set_shutting_down_cb,
            self.shutdown_event,
            self.dp,
            self.runtime_logger,
            self.pending_edit_lock,
            self.pending_edit_tasks,
            self.git_executor,
            self.save_executor,
            self.get_pool,
            self.db_lock,
            self.close_pool,
            healthcheck_site=mock_site,
            emergency=False
        )

        self.shutdown_event.set.assert_called_once()
        self.dp.stop_polling.assert_awaited_once()
        mock_site.stop.assert_awaited_once()
        self.close_pool.assert_awaited_once()
        self.assertTrue(self.is_shutting_down_state)

    @patch('asyncio.sleep', new_callable=AsyncMock)
    async def test_graceful_shutdown_polling_error(self, mock_sleep):
        self.dp.stop_polling.side_effect = Exception("Polling error")
        mock_site = AsyncMock()

        await _graceful_shutdown_impl(
            self.is_shutting_down_state,
            self.set_shutting_down_cb,
            self.shutdown_event,
            self.dp,
            self.runtime_logger,
            self.pending_edit_lock,
            self.pending_edit_tasks,
            self.git_executor,
            self.save_executor,
            self.get_pool,
            self.db_lock,
            self.close_pool,
            healthcheck_site=mock_site,
            emergency=False
        )

        self.shutdown_event.set.assert_called_once()
        self.mock_db.execute.assert_awaited_once_with("PRAGMA wal_checkpoint(TRUNCATE);")
        mock_site.stop.assert_awaited_once()
        self.close_pool.assert_awaited_once()
        self.assertTrue(self.is_shutting_down_state)

    async def test_graceful_shutdown_already_shutting_down(self):
        self.is_shutting_down_state = True

        await _graceful_shutdown_impl(
            self.is_shutting_down_state,
            self.set_shutting_down_cb,
            self.shutdown_event,
            self.dp,
            self.runtime_logger,
            self.pending_edit_lock,
            self.pending_edit_tasks,
            self.git_executor,
            self.save_executor,
            self.get_pool,
            self.db_lock,
            self.close_pool
        )

        self.shutdown_event.set.assert_not_called()
        self.dp.stop_polling.assert_not_called()

if __name__ == '__main__':
    unittest.main()
