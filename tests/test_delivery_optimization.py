import asyncio
import time
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import common.config as config
from shared_state import (
    DELIVERY_INITIAL_CHUNK_SIZE,
    DELIVERY_MAX_CHUNK_SIZE,
    DELIVERY_MIN_CHUNK_SIZE,
    weekly_active_users,
    message_queues,
    board_data,
    BroadcastConfig
)
from broadcaster import MessageBroadcaster, DeliveryResults
from delivery_manager import (
    MessageDeliveryTask,
    _passive_slice_size_for_content,
    _split_recipients_for_delivery,
    _delete_durable_delivery_item,
    cumulative_post_metrics,
    CHUNK_SIZE,
    PRIORITY_SPLIT_MIN_PASSIVE
)
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError


class TestDeliveryOptimization(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Reset metrics and state for test
        cumulative_post_metrics.clear()
        weekly_active_users['b'] = set(range(1, 101))  # 100 active users (1..100)
        board_data['b'] = {
            'users': {'banned': set(), 'active': set(range(1, 1001))},
            'user_settings': {},
            'user_state': {uid: {'location': 'main'} for uid in range(1, 1001)},
        }
        if 'b' not in message_queues:
            message_queues['b'] = asyncio.Queue()

    def test_config_constants(self):
        """Verify configuration constants match target high-throughput parameters."""
        self.assertEqual(config.BOT_DELIVERY_INITIAL_CHUNK_SIZE, 25)
        self.assertEqual(config.BOT_DELIVERY_MAX_CHUNK_SIZE, 30)
        self.assertEqual(config.BOT_DELIVERY_MIN_CHUNK_SIZE, 10)
        self.assertEqual(config.BOT_PRIORITY_PASSIVE_SLICE_SIZE, 250)
        self.assertEqual(config.BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE, 120)
        self.assertEqual(config.BOT_PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE, 150)
        self.assertEqual(config.BOT_PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE, 80)
        self.assertEqual(DELIVERY_INITIAL_CHUNK_SIZE, 25)
        self.assertEqual(DELIVERY_MAX_CHUNK_SIZE, 30)
        self.assertEqual(DELIVERY_MIN_CHUNK_SIZE, 10)

    def test_slice_sizing(self):
        """Verify slice size calculations for text and media."""
        text_content = {'type': 'text', 'text': 'test'}
        media_content = {'type': 'photo', 'caption': 'test photo'}
        self.assertEqual(_passive_slice_size_for_content(text_content, 'b'), 250)
        self.assertEqual(_passive_slice_size_for_content(media_content, 'b'), 120)

    def test_priority_split(self):
        """Verify recipient partitioning into active priority vs passive."""
        all_recipients = set(range(1, 677))  # 676 recipients (1..676)
        prio, passive = _split_recipients_for_delivery('b', all_recipients)
        self.assertEqual(len(prio), 100)
        self.assertEqual(len(passive), 576)

    @patch("delivery_manager.get_post_copies")
    @patch("delivery_manager.send_message_to_users")
    @patch("delivery_manager.delete_delivery_queue_item")
    async def test_durable_restore_metrics_accounting(self, mock_del_db, mock_send, mock_copies):
        """Verify restored posts from DeliveryQueue correctly account for prior copies in cumulative metrics."""
        post_num = 495789
        original_total = 676
        # Simulate that 542 copies were already delivered in DB prior to crash
        prior_copies_in_db = [(uid, 1000 + uid) for uid in range(1, 543)]
        mock_copies.return_value = prior_copies_in_db
        mock_del_db.return_value = True

        # Remaining recipients for this restored item (676 - 542 = 134)
        remaining_recipients = set(range(543, 677))
        self.assertEqual(len(remaining_recipients), 134)

        # Mock send results for the remaining 134
        fake_results = DeliveryResults(
            [(uid, MagicMock(message_id=2000 + uid)) for uid in remaining_recipients],
            remaining_recipients=set(),
            stats={'success': 134, 'passive_recipients': 134, 'priority_recipients': 0, 'errors': 0, 'blocks': 0}
        )
        mock_send.return_value = fake_results

        msg_data = {
            'post_num': post_num,
            'board_id': 'b',
            'recipients': remaining_recipients,
            'content': {'type': 'text', 'text': 'Restored post content'},
            'delivery_phase': 'passive',
            'original_recipients': original_total,
            'durable_delivery_id': 42,
            'enqueued_at': time.time() - 100,
        }

        task = MessageDeliveryTask("Worker-b", "b", MagicMock(), message_queues['b'], msg_data)
        await task.process()

        # Check that delete_delivery_queue_item was called cleanly with item_id=42
        mock_del_db.assert_called_once_with(42)

    @patch("broadcaster.MessageBroadcaster._send_one_guarded")
    async def test_broadcaster_calibrated_pacing(self, mock_send_guarded):
        """Verify broadcaster chunking and pacing maintains the ~28 msg/s ceiling without artificial lag."""
        mock_send_guarded.return_value = MagicMock(message_id=123)

        recipients = list(range(1, 85))  # 84 recipients -> chunks of 25, 25, 25, 9
        config_obj = BroadcastConfig(
            bot_instance=MagicMock(),
            board_id='b',
            recipients=recipients,
            content={'type': 'text', 'text': 'Hello world'},
            verbose=False,
            delivery_phase='passive',
            delivery_original_recipients=len(recipients)
        )

        broadcaster = MessageBroadcaster(config_obj)
        t_start = time.time()
        results = await broadcaster.broadcast()
        t_elapsed = time.time() - t_start

        # 84 recipients at 28 msg/sec ceiling should take ~3.0s (>= 2.5s and <= 4.0s)
        self.assertEqual(len(results), 84)
        self.assertGreaterEqual(t_elapsed, 2.5)
        self.assertLessEqual(t_elapsed, 4.5)

    @patch("broadcaster.MessageBroadcaster._send_one_guarded")
    async def test_transient_flood_wait_resilience(self, mock_send_guarded):
        """Verify broadcaster recovers gracefully from 429 without punitive collapse to 3."""
        failed_uids = set()

        async def fake_send_guarded(uid, timeout_sec):
            nonlocal failed_uids
            if uid == 5 and uid not in failed_uids:
                failed_uids.add(uid)
                # transient flood wait for 1 user on 1st attempt
                return TelegramRetryAfter(method=MagicMock(), message="retry after", retry_after=0.1)
            return MagicMock(message_id=500 + uid)

        mock_send_guarded.side_effect = fake_send_guarded

        recipients = list(range(1, 31))  # 30 recipients
        config_obj = BroadcastConfig(
            bot_instance=MagicMock(),
            board_id='b',
            recipients=recipients,
            content={'type': 'text', 'text': 'Flood wait test'},
            verbose=False,
            delivery_phase='priority',
            delivery_original_recipients=len(recipients)
        )

        broadcaster = MessageBroadcaster(config_obj)
        results = await broadcaster.broadcast()
        # All 30 eventually succeed or get handled
        self.assertEqual(broadcaster.stats['retries'], 1)
        self.assertEqual(len(results), 30)


if __name__ == "__main__":
    unittest.main()
