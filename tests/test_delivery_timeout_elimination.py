"""
tests/test_delivery_timeout_elimination.py

Tests for Live Production Log Analysis & Delivery Timeout Elimination:
1. Fast per-copy edit timeout (<= 2.5s) without blocking queues.
2. Stale recipient cache (_stale_edit_recipients): records consecutive timeouts and skips immediately.
3. Automatic cleanup of dead post copies from post_to_messages and SQLite when Telegram returns
   'message to edit not found' or 'message can't be edited'.
4. Blocked/deleted user purge on 'chat not found', 'bot was blocked', etc.
5. Concurrency bounds and Telegram Bot API rate-limit protection (_POST_EDIT_SEMAPHORE).
"""

from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from delivery_manager import (
    _POST_EDIT_SEMAPHORE,
    _stale_edit_recipients,
    clear_stale_edit_recipients,
    get_stale_edit_recipients,
    is_stale_edit_recipient,
    mark_stale_edit_recipient,
    remove_dead_post_copy,
    edit_post_for_all_recipients,
    MAX_CONSECUTIVE_EDIT_TIMEOUTS,
    STALE_EDIT_RECIPIENT_TTL,
)
from shared_state import (
    board_data,
    messages_storage,
    message_to_post,
    post_to_messages,
    storage_lock,
)


class TestDeliveryTimeoutElimination(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_stale_edit_recipients()
        board_data['b'] = {
            'users': {'active': {1001, 1002, 1003, 1004, 1005}},
            'user_settings': {},
        }
        async with storage_lock:
            messages_storage[99001] = {
                'board_id': 'b',
                'author_id': 1001,
                'content': {'type': 'text', 'text': 'Тестовый пост для эдита'},
                'reactions': {'users': {}},
            }
            post_to_messages[99001] = {
                1001: 7001,
                1002: 7002,
                1003: 7003,
            }
            message_to_post[(1001, 7001)] = 99001
            message_to_post[(1002, 7002)] = 99001
            message_to_post[(1003, 7003)] = 99001

    async def asyncTearDown(self):
        clear_stale_edit_recipients()
        async with storage_lock:
            messages_storage.pop(99001, None)
            post_to_messages.pop(99001, None)
            message_to_post.pop((1001, 7001), None)
            message_to_post.pop((1002, 7002), None)
            message_to_post.pop((1003, 7003), None)

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    async def test_fast_timeout_records_stale_user_without_hang(self, mock_get_copies, mock_edit):
        """When an edit times out, it should abort fast and increment the stale failure counter."""
        mock_get_copies.return_value = [(1002, 7002)]
        mock_edit.side_effect = asyncio.TimeoutError()

        mock_bot = MagicMock()
        t_start = asyncio.get_event_loop().time()
        await edit_post_for_all_recipients(99001, mock_bot)
        elapsed = asyncio.get_event_loop().time() - t_start

        # Should finish fast (mocked timeout returns immediately)
        self.assertLess(elapsed, 3.0)
        stale = get_stale_edit_recipients()
        self.assertIn(1002, stale)
        fail_cnt, _ = stale[1002]
        self.assertEqual(fail_cnt, 1)

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    async def test_stale_user_consecutive_timeouts_skipped_instantly(self, mock_get_copies, mock_edit):
        """User with >= MAX_CONSECUTIVE_EDIT_TIMEOUTS should be skipped without making an API call."""
        mock_get_copies.return_value = [(1002, 7002), (1003, 7003)]
        # Mark user 1002 as having 2 consecutive timeouts
        mark_stale_edit_recipient(1002, count=MAX_CONSECUTIVE_EDIT_TIMEOUTS)
        self.assertTrue(is_stale_edit_recipient(1002))

        mock_bot = MagicMock()
        await edit_post_for_all_recipients(99001, mock_bot)

        # safe_edit_message_text should NOT be called for 1002, only for 1003
        called_chat_ids = [call.kwargs.get('chat_id') for call in mock_edit.call_args_list]
        self.assertNotIn(1002, called_chat_ids)
        self.assertIn(1003, called_chat_ids)

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    async def test_stale_user_cleared_on_successful_edit(self, mock_get_copies, mock_edit):
        """If a user had 1 timeout but then successfully edits, stale counter is cleared."""
        mock_get_copies.return_value = [(1002, 7002)]
        mark_stale_edit_recipient(1002, count=1)

        mock_bot = MagicMock()
        mock_edit.return_value = True

        await edit_post_for_all_recipients(99001, mock_bot)

        self.assertNotIn(1002, get_stale_edit_recipients())

    def test_stale_cache_ttl_expiration(self):
        """Expired stale entry should return False and be purged."""
        _stale_edit_recipients[1005] = (2, time.monotonic() - (STALE_EDIT_RECIPIENT_TTL + 10))
        self.assertFalse(is_stale_edit_recipient(1005))
        self.assertNotIn(1005, _stale_edit_recipients)

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    @patch("delivery_manager.remove_dead_post_copy")
    async def test_dead_copy_removal_on_message_not_found(self, mock_remove_dead, mock_get_copies, mock_edit):
        """When Telegram returns 'message to edit not found', remove_dead_post_copy must be called."""
        mock_get_copies.return_value = [(1002, 7002)]
        async with storage_lock:
            post_to_messages[99001] = {1002: 7002}
        mock_edit.side_effect = TelegramBadRequest(
            method="editMessageText",
            message="Bad Request: message to edit not found"
        )

        mock_bot = MagicMock()
        await edit_post_for_all_recipients(99001, mock_bot)

        mock_remove_dead.assert_called_once_with(99001, 1002, 7002)

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    @patch("delivery_manager.remove_dead_post_copy")
    async def test_dead_copy_removal_on_message_cant_be_edited(self, mock_remove_dead, mock_get_copies, mock_edit):
        """When Telegram returns 'message can't be edited', remove_dead_post_copy must be called."""
        mock_get_copies.return_value = [(1002, 7002)]
        async with storage_lock:
            post_to_messages[99001] = {1002: 7002}
        mock_edit.side_effect = TelegramBadRequest(
            method="editMessageText",
            message="Bad Request: message can't be edited"
        )

        mock_bot = MagicMock()
        await edit_post_for_all_recipients(99001, mock_bot)

        mock_remove_dead.assert_called_once_with(99001, 1002, 7002)

    async def test_remove_dead_post_copy_functionality(self):
        """Direct test of remove_dead_post_copy: removes from post_to_messages and message_to_post."""
        async with storage_lock:
            self.assertEqual(post_to_messages[99001][1002], 7002)
            self.assertEqual(message_to_post[(1002, 7002)], 99001)

        with patch("common.db_pool.get_pool", AsyncMock()) as mock_pool:
            mock_db = AsyncMock()
            mock_pool.return_value = mock_db
            await remove_dead_post_copy(99001, 1002, 7002)

        async with storage_lock:
            self.assertNotIn(1002, post_to_messages[99001])
            self.assertNotIn((1002, 7002), message_to_post)

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    @patch("delivery_manager.remove_blocked_user_copies")
    async def test_blocked_user_purged_on_chat_not_found(self, mock_remove_blocked, mock_get_copies, mock_edit):
        """When Telegram returns 'chat not found', remove_blocked_user_copies must be called and board_data updated."""
        mock_get_copies.return_value = [(1002, 7002)]
        async with storage_lock:
            post_to_messages[99001] = {1002: 7002}
        mock_edit.side_effect = TelegramBadRequest(
            method="editMessageText",
            message="Bad Request: chat not found"
        )

        mock_bot = MagicMock()
        await edit_post_for_all_recipients(99001, mock_bot)

        mock_remove_blocked.assert_called_once_with(1002)
        self.assertNotIn(1002, board_data['b']['users']['active'])

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    @patch("delivery_manager.remove_blocked_user_copies")
    async def test_blocked_user_purged_on_forbidden_error(self, mock_remove_blocked, mock_get_copies, mock_edit):
        """When TelegramForbiddenError occurs, remove_blocked_user_copies must be called."""
        mock_get_copies.return_value = [(1002, 7002)]
        async with storage_lock:
            post_to_messages[99001] = {1002: 7002}
        mock_edit.side_effect = TelegramForbiddenError(
            method="editMessageText",
            message="Forbidden: bot was blocked by the user"
        )

        mock_bot = MagicMock()
        await edit_post_for_all_recipients(99001, mock_bot)

        mock_remove_blocked.assert_called_once_with(1002)
        self.assertNotIn(1002, board_data['b']['users']['active'])

    def test_post_edit_semaphore_concurrency_bounded(self):
        """Verify _POST_EDIT_SEMAPHORE is bounded to 10."""
        self.assertIsInstance(_POST_EDIT_SEMAPHORE, asyncio.Semaphore)
        self.assertEqual(_POST_EDIT_SEMAPHORE._value, 10)

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    async def test_concurrency_never_exceeds_semaphore_limit(self, mock_get_copies, mock_edit):
        """Ensure that even with 25 users, max concurrent edits never exceed 10."""
        user_ids = [2000 + i for i in range(25)]
        mock_get_copies.return_value = [(uid, 8000 + i) for i, uid in enumerate(user_ids)]
        async with storage_lock:
            for i, uid in enumerate(user_ids):
                post_to_messages[99001][uid] = 8000 + i

        active_concurrent = 0
        max_seen_concurrent = 0

        async def slow_edit(*args, **kwargs):
            nonlocal active_concurrent, max_seen_concurrent
            active_concurrent += 1
            max_seen_concurrent = max(max_seen_concurrent, active_concurrent)
            await asyncio.sleep(0.02)
            active_concurrent -= 1
            return True

        mock_edit.side_effect = slow_edit

        mock_bot = MagicMock()
        await edit_post_for_all_recipients(99001, mock_bot)

        self.assertLessEqual(max_seen_concurrent, 10)

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    async def test_network_error_records_stale_recipient(self, mock_get_copies, mock_edit):
        """Network errors should also increment the stale counter and prevent retry stalls."""
        from aiogram.exceptions import TelegramNetworkError
        mock_get_copies.return_value = [(1002, 7002)]
        async with storage_lock:
            post_to_messages[99001] = {1002: 7002}

        mock_edit.side_effect = TelegramNetworkError(
            method="editMessageText",
            message="Network error"
        )

        mock_bot = MagicMock()
        await edit_post_for_all_recipients(99001, mock_bot)

        stale = get_stale_edit_recipients()
        self.assertIn(1002, stale)
        fail_cnt, _ = stale[1002]
        self.assertGreaterEqual(fail_cnt, 1)

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    async def test_batch_chunking_pacing(self, mock_get_copies, mock_edit):
        """Batch of 25 users is chunked in batches of 10 with delays to respect 30 req/s rate limits."""
        user_ids = [3000 + i for i in range(25)]
        mock_get_copies.return_value = [(uid, 9000 + i) for i, uid in enumerate(user_ids)]
        async with storage_lock:
            for i, uid in enumerate(user_ids):
                post_to_messages[99001][uid] = 9000 + i

        mock_edit.return_value = True
        mock_bot = MagicMock()

        with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
            await edit_post_for_all_recipients(99001, mock_bot)
            # For 25 items chunked by 10: 3 chunks total (10, 10, 5) -> 2 sleeps between chunks
            sleep_calls = [c.args[0] for c in mock_sleep.call_args_list if len(c.args) > 0 and c.args[0] == 0.25]
            self.assertEqual(len(sleep_calls), 2)


if __name__ == '__main__':
    unittest.main()
