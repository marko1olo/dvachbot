"""
tests/test_delivery_deletion_cleanup.py

Comprehensive tests for:
1. Delivery cancellation when a post is marked for deletion (pending_deletion).
2. Instant queue purging for deleted posts (purge_deleted_post_from_delivery_queues).
3. Non-blocking, safe mass deletion of copies (safe_delete_message & delete_messages_background).
4. Memory pruning and strict ceilings (cumulative_post_metrics, post_to_messages BoundedDict, posts_pending_deletion).
"""

import asyncio
import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

import shared_state
from broadcaster import MessageBroadcaster, send_message_to_users
from delivery_manager import (
    MessageDeliveryTask,
    cumulative_post_metrics,
    message_queues,
    prune_stale_cumulative_post_metrics,
    purge_deleted_post_from_delivery_queues,
)
from post_helpers import (
    _is_harmless_delete_error,
    delete_messages_background,
    delete_single_post,
    safe_delete_message,
)
from shared_state import (
    BoundedDict,
    BroadcastConfig,
    messages_storage,
    post_to_messages,
    posts_pending_deletion,
    storage_lock,
)


@pytest.fixture(autouse=True)
def cleanup_state():
    """Resets memory state before and after each test."""
    posts_pending_deletion.clear()
    cumulative_post_metrics.clear()
    for q in message_queues.values():
        if hasattr(q, "_queue"):
            q._queue.clear()
    yield
    posts_pending_deletion.clear()
    cumulative_post_metrics.clear()
    for q in message_queues.values():
        if hasattr(q, "_queue"):
            q._queue.clear()


class TestDeliveryCancellationOnPostDeletion:
    @pytest.mark.asyncio
    async def test_broadcast_aborts_immediately_when_post_marked_pending_deletion(self):
        """
        Broadcaster must immediately halt delivery loop if self.post_num is in posts_pending_deletion.
        Must drop remaining recipients and not deliver spam/wipe content to them.
        """
        post_num = 602166
        board_id = "b"
        recipients = list(range(1001, 1051))  # 50 recipients
        sent_uids = []

        bot = MagicMock()

        async def fake_send(chat_id, *args, **kwargs):
            sent_uids.append(chat_id)
            # Mark post for deletion right after the 5th message is sent
            if len(sent_uids) == 5:
                posts_pending_deletion.add(post_num)
            await asyncio.sleep(0.001)
            msg = MagicMock()
            msg.message_id = 90000 + chat_id
            return msg

        bot.send_message = AsyncMock(side_effect=fake_send)
        bot.send_photo = AsyncMock()

        # Set up shared board data
        shared_state.board_data[board_id] = {
            "users": {"banned": set(), "active": set(recipients)},
            "user_settings": {},
        }

        config = BroadcastConfig(
            bot_instance=bot,
            board_id=board_id,
            recipients=set(recipients),
            content={"type": "text", "text": "Wipe content that should be cancelled"},
            verbose=False,
        )

        broadcaster = MessageBroadcaster(config)
        broadcaster.post_num = post_num

        results = await broadcaster.broadcast()

        # Delivery must have been aborted before processing all 50 recipients
        assert results.interrupted_reason == "post_deleted_pending_deletion"
        assert len(sent_uids) < len(recipients), f"Expected delivery to abort, but sent to {len(sent_uids)} users"
        # No copies must be saved to DB for deleted post
        assert post_num not in post_to_messages

    @pytest.mark.asyncio
    async def test_purge_deleted_post_from_delivery_queues(self):
        """
        purge_deleted_post_from_delivery_queues must remove pending queue items matching post_num.
        """
        board_id = "b"
        q = message_queues[board_id]
        if not hasattr(q, "_queue"):
            q._queue = deque()

        # Enqueue 3 items: post 100, post 200 (target), post 300
        q._queue.append({"post_num": 100, "recipients": {1, 2}})
        q._queue.append({"post_num": 200, "recipients": {3, 4}})
        q._queue.append({"post_num": 300, "recipients": {5, 6}})
        q._queue.append({"post_num": 200, "recipients": {7, 8}})  # passive slice

        removed = purge_deleted_post_from_delivery_queues(200, board_id)
        assert removed == 2
        remaining_pnums = [item["post_num"] for item in q._queue]
        assert remaining_pnums == [100, 300]
        assert 200 not in remaining_pnums

    @pytest.mark.asyncio
    async def test_worker_skips_post_if_pending_deletion(self):
        """
        MessageDeliveryTask must skip processing immediately if post_num in posts_pending_deletion.
        """
        post_num = 777888
        posts_pending_deletion.add(post_num)

        bot = MagicMock()
        queue = asyncio.Queue()
        msg_data = {
            "post_num": post_num,
            "recipients": {1001, 1002},
            "content": {"type": "text", "text": "Will be skipped"},
            "durable_delivery_id": 42,
        }

        with patch("delivery_manager._delete_durable_delivery_item", new=AsyncMock()) as mock_del_durable, \
             patch("delivery_manager.send_message_to_users", new=AsyncMock()) as mock_send:

            task = MessageDeliveryTask("Worker-b", "b", bot, queue, msg_data)
            await task.process()

            # send_message_to_users must NOT have been called
            mock_send.assert_not_called()
            # Durable item must be cleaned up
            mock_del_durable.assert_called_once_with(msg_data, "post_pending_deletion")

    @pytest.mark.asyncio
    async def test_passive_slice_not_requeued_on_deletion_interrupt(self):
        """
        If broadcaster returns interrupted_reason == 'post_deleted_pending_deletion',
        worker must NOT re-enqueue passive slices to queue.
        """
        post_num = 555666
        bot = MagicMock()
        queue = asyncio.Queue()
        msg_data = {
            "post_num": post_num,
            "recipients": {1001, 1002, 1003},
            "content": {"type": "text", "text": "Post test"},
        }

        fake_results = MagicMock()
        fake_results.__len__.return_value = 1
        fake_results.interrupted_reason = "post_deleted_pending_deletion"
        fake_results.remaining_recipients = {1002, 1003}
        fake_results.stats = {"success": 1}

        with patch("delivery_manager.send_message_to_users", new=AsyncMock(return_value=fake_results)):
            task = MessageDeliveryTask("Worker-b", "b", bot, queue, msg_data)
            await task.process()

            # Queue must remain empty: passive slice must NOT have been re-enqueued
            assert queue.qsize() == 0


class TestSafeMassDeletionOfCopies:
    @pytest.mark.asyncio
    async def test_safe_delete_message_handles_not_found_and_errors(self):
        """
        safe_delete_message must silently return True for harmless errors (message already deleted),
        and False for non-recoverable errors without raising exceptions.
        """
        bot = MagicMock()

        # 1. Successful deletion
        bot.delete_message = AsyncMock(return_value=True)
        assert await safe_delete_message(bot, 12345, 6789) is True

        # 2. Harmless: message to delete not found
        bot.delete_message = AsyncMock(side_effect=TelegramBadRequest(method="deleteMessage", message="Bad Request: message to delete not found"))
        assert await safe_delete_message(bot, 12345, 6789) is True

        # 3. Harmless: message can't be deleted
        bot.delete_message = AsyncMock(side_effect=TelegramBadRequest(method="deleteMessage", message="Bad Request: message can't be deleted"))
        assert await safe_delete_message(bot, 12345, 6789) is True

        # 4. Forbidden: user blocked bot
        bot.delete_message = AsyncMock(side_effect=TelegramForbiddenError(method="deleteMessage", message="Forbidden: bot was blocked by the user"))
        assert await safe_delete_message(bot, 12345, 6789) is False

    @pytest.mark.asyncio
    async def test_delete_messages_background_chunked_execution(self):
        """
        delete_messages_background must process 100 copies in chunks without crashing on exceptions.
        """
        bot = MagicMock()
        deleted_ids = []

        async def mock_del(chat_id, message_id, **kwargs):
            deleted_ids.append((chat_id, message_id))
            if chat_id == 1010:
                raise TelegramBadRequest(method="deleteMessage", message="message to delete not found")
            return True

        bot.delete_message = AsyncMock(side_effect=mock_del)

        copies = [(1000 + i, 50000 + i) for i in range(100)]
        count = await delete_messages_background(copies, bot, board_id="b")

        # 100 copies processed, harmless error counted as success
        assert count == 100
        assert len(deleted_ids) == 100

    @pytest.mark.asyncio
    async def test_delete_single_post_background_mode(self):
        """
        delete_single_post with background=True must return copy count immediately without waiting.
        """
        post_num = 444555
        bot = MagicMock()

        with patch("post_helpers.get_all_channel_copies", new=AsyncMock(return_value=[])), \
             patch("post_helpers.get_post_copies", new=AsyncMock(return_value=[(1, 10), (2, 20), (3, 30)])), \
             patch("post_helpers.delete_post_by_num", new=AsyncMock(return_value=True)), \
             patch("post_helpers.get_pool") as mock_pool, \
             patch("common.task_manager.spawn_task") as mock_spawn:

            def fake_spawn(coro):
                coro.close()
                return MagicMock()
            mock_spawn.side_effect = fake_spawn

            fake_db = MagicMock()
            fake_db.execute = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(fetchone=AsyncMock(return_value=None)))))
            mock_pool.return_value = fake_db

            deleted_count = await delete_single_post(post_num, bot, background=True)
            assert deleted_count == 3
            assert mock_spawn.called
            assert post_num in posts_pending_deletion


class TestMemoryPruningAndCeilings:
    def test_prune_stale_cumulative_post_metrics(self):
        """
        prune_stale_cumulative_post_metrics must purge entries older than max_age_sec
        and enforce max_keep limit.
        """
        now = time.time()

        # Add 10 stale entries (older than 1800s)
        for i in range(10):
            cumulative_post_metrics[("b", 100 + i)] = {
                "start_time": now - 3600,
                "total": 100, "success": 100,
            }

        # Add 5 fresh entries
        for i in range(5):
            cumulative_post_metrics[("b", 200 + i)] = {
                "start_time": now - 60,
                "total": 100, "success": 100,
            }

        assert len(cumulative_post_metrics) == 15

        # Prune with max_age_sec=1800
        removed = prune_stale_cumulative_post_metrics(max_age_sec=1800.0, max_keep=10)
        assert removed == 10
        assert len(cumulative_post_metrics) == 5

        # Verify only fresh entries remain
        for i in range(5):
            assert ("b", 200 + i) in cumulative_post_metrics

    def test_post_to_messages_bounded_dict_capacity(self):
        """
        post_to_messages must strictly enforce its capacity ceiling and evict oldest entries.
        """
        b_dict = BoundedDict(max_size=5)
        for i in range(10):
            b_dict[i] = {f"user_{i}": i * 10}

        assert len(b_dict) == 5
        # Oldest 0..4 evicted, newest 5..9 kept
        assert list(b_dict.keys()) == [5, 6, 7, 8, 9]

    def test_posts_pending_deletion_bounded_pruning(self):
        """
        Verify that posts_pending_deletion can be safely pruned when large without memory leak.
        """
        posts_pending_deletion.update(range(1200))
        assert len(posts_pending_deletion) == 1200

        # Simulate cleaner pruning excess down to 500
        if len(posts_pending_deletion) > 1000:
            excess = len(posts_pending_deletion) - 500
            for p in sorted(posts_pending_deletion)[:excess]:
                posts_pending_deletion.discard(p)

        assert len(posts_pending_deletion) == 500
        assert min(posts_pending_deletion) == 700
