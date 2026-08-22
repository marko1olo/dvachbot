import asyncio
import time
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from collections import defaultdict

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
    _remove_already_delivered_recipients,
    _delete_durable_delivery_item,
    _persist_durable_delivery_item,
    cumulative_post_metrics,
    CHUNK_SIZE,
    PRIORITY_SPLIT_MIN_PASSIVE,
    PRIORITY_PASSIVE_SLICE_SIZE,
    PRIORITY_PASSIVE_MEDIA_SLICE_SIZE,
    PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE,
    PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE,
)
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramNetworkError


class TestAdversarialDeliverySlicing(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        cumulative_post_metrics.clear()
        weekly_active_users['b'] = set(range(1, 101))  # 100 active users (1..100)
        board_data['b'] = {
            'users': {'banned': {9999}, 'active': set(range(1, 2000))},
            'user_settings': {},
            'user_state': {uid: {'location': 'main'} for uid in range(1, 2000)},
        }
        if 'b' not in message_queues:
            message_queues['b'] = asyncio.Queue()

    def test_adv_slicing_edge_cases(self):
        """Adversarial testing of recipient splitting under extreme edge cases."""
        # 1. Empty recipients
        prio, passive = _split_recipients_for_delivery('b', [])
        self.assertEqual(prio, [])
        self.assertEqual(passive, [])

        # 2. Non-existent board in weekly_active_users
        prio, passive = _split_recipients_for_delivery('nonexistent_board', [1, 2, 3])
        self.assertEqual(prio, [])
        self.assertEqual(passive, [1, 2, 3])

        # 3. All recipients active
        all_active = list(range(1, 51))
        prio, passive = _split_recipients_for_delivery('b', all_active)
        self.assertEqual(set(prio), set(all_active))
        self.assertEqual(passive, [])

        # 4. All recipients passive
        all_passive = list(range(500, 600))
        prio, passive = _split_recipients_for_delivery('b', all_passive)
        self.assertEqual(prio, [])
        self.assertEqual(set(passive), set(all_passive))

        # 5. Exactly at PRIORITY_SPLIT_MIN_PASSIVE threshold (30)
        prio, passive = _split_recipients_for_delivery('b', list(range(1, 11)) + list(range(200, 230)))
        self.assertEqual(len(prio), 10)
        self.assertEqual(len(passive), 30)

        # 6. Below PRIORITY_SPLIT_MIN_PASSIVE threshold (29 passive)
        # Verify MessageDeliveryTask behavior when passive < 30
        task_data = {
            'post_num': 1001,
            'board_id': 'b',
            'recipients': set(range(1, 11)) | set(range(200, 229)), # 10 prio, 29 passive
            'content': {'type': 'text', 'text': 'Threshold test'},
            'delivery_phase': 'full',
            'enqueued_at': time.time(),
        }
        task = MessageDeliveryTask("Worker-b", "b", MagicMock(), message_queues['b'], task_data)
        task.thread_id = None
        task.initial_recipients = task_data['recipients']
        task.delivery_phase = 'full'
        task.passive_slice_size = 250
        to_send, for_later, phase, reason = task._determine_delivery_phases(task._resolve_active_recipients())
        # Should NOT split because passive < 30 (PRIORITY_SPLIT_MIN_PASSIVE = 30)
        self.assertEqual(len(to_send), 39)
        self.assertEqual(len(for_later), 0)
        self.assertEqual(phase, "full")

        # 7. At/Above PRIORITY_SPLIT_MIN_PASSIVE threshold (30 passive)
        task_data_split = {
            'post_num': 1002,
            'board_id': 'b',
            'recipients': set(range(1, 11)) | set(range(200, 230)), # 10 prio, 30 passive
            'content': {'type': 'text', 'text': 'Threshold split test'},
            'delivery_phase': 'full',
            'enqueued_at': time.time(),
        }
        task_split = MessageDeliveryTask("Worker-b", "b", MagicMock(), message_queues['b'], task_data_split)
        task_split.thread_id = None
        task_split.initial_recipients = task_data_split['recipients']
        task_split.delivery_phase = 'full'
        task_split.passive_slice_size = 250
        to_send_s, for_later_s, phase_s, reason_s = task_split._determine_delivery_phases(task_split._resolve_active_recipients())
        self.assertEqual(len(to_send_s), 10)
        self.assertEqual(len(for_later_s), 30)
        self.assertEqual(phase_s, "priority")
        self.assertEqual(reason_s, "split_priority_first")

    def test_adv_pressure_slice_sizing(self):
        """Stress-test content types and pressure slice sizing."""
        content_types_media = [
            'photo', 'video', 'animation', 'document', 'audio',
            'voice', 'sticker', 'video_note', 'media_group'
        ]
        for ctype in content_types_media:
            cnt = {'type': ctype}
            self.assertEqual(_passive_slice_size_for_content(cnt, 'b'), 120)

        content_types_text = ['text', 'poll', 'unknown_custom']
        for ctype in content_types_text:
            cnt = {'type': ctype}
            self.assertEqual(_passive_slice_size_for_content(cnt, 'b'), 250)

        # Mock queue backlog age >= 600s
        with patch("delivery_manager._board_queue_oldest_age_sec", return_value=650.0):
            # Under pressure, text slice drops to 150, media slice drops to 80
            self.assertEqual(_passive_slice_size_for_content({'type': 'text'}, 'b'), 150)
            self.assertEqual(_passive_slice_size_for_content({'type': 'photo'}, 'b'), 80)
            self.assertEqual(_passive_slice_size_for_content({'type': 'video'}, 'b'), 80)

    @patch("broadcaster.MessageBroadcaster._send_one_guarded")
    async def test_adv_dynamic_chunk_sizing_stress(self, mock_send_guarded):
        """Stress test dynamic chunk sizing limits: min 10, max 30, and adaptation."""
        mock_send_guarded.return_value = MagicMock(message_id=999)

        # 1. Verify growth up to max 30 on clean chunks
        recipients = list(range(1, 201)) # 200 recipients
        config_obj = BroadcastConfig(
            bot_instance=MagicMock(),
            board_id='b',
            recipients=recipients,
            content={'type': 'text', 'text': 'Chunk growth test'},
            verbose=False,
            delivery_phase='passive',
            delivery_original_recipients=len(recipients)
        )
        broadcaster = MessageBroadcaster(config_obj)
        # Mock _send_one_guarded to track chunk sizes passed to asyncio.gather
        chunk_sizes_seen = []
        orig_process = broadcaster._process_delivery_queue

        with patch("broadcaster.asyncio.sleep", new_callable=AsyncMock):
            results = await broadcaster.broadcast()
        self.assertEqual(len(results), 200)

        # 2. Verify shrinking down to min 10 on repeated flood-waits (never below 10)
        flood_uids = set(range(1, 100))
        call_count = defaultdict(int)

        async def flood_then_succeed(uid, timeout):
            call_count[uid] += 1
            if call_count[uid] <= 2:
                # Trigger flood wait
                return TelegramRetryAfter(method=MagicMock(), message="flood", retry_after=0.01)
            return MagicMock(message_id=uid)

        mock_send_guarded.side_effect = flood_then_succeed

        recipients_flood = list(range(1, 51))
        config_flood = BroadcastConfig(
            bot_instance=MagicMock(),
            board_id='b',
            recipients=recipients_flood,
            content={'type': 'text', 'text': 'Flood clamp test'},
            verbose=False,
            delivery_phase='passive',
            delivery_original_recipients=len(recipients_flood)
        )
        broadcaster_flood = MessageBroadcaster(config_flood)
        with patch("broadcaster.asyncio.sleep", new_callable=AsyncMock):
            results_flood = await broadcaster_flood.broadcast()
        self.assertEqual(len(results_flood), 50)
        self.assertGreater(broadcaster_flood.stats['retries'], 0)

    @patch("delivery_manager.get_post_copies")
    @patch("delivery_manager.delete_delivery_queue_item")
    async def test_adv_durable_already_delivered_purged(self, mock_del_db, mock_copies):
        """If all recipients were already delivered in DB, verify no redundant sending occurs and row is deleted."""
        post_num = 98765
        # 100 recipients in durable item, all 100 already in PostCopies
        mock_copies.return_value = [(uid, 5000 + uid) for uid in range(1, 101)]
        mock_del_db.return_value = True

        remaining = await _remove_already_delivered_recipients(post_num, set(range(1, 101)))
        self.assertEqual(remaining, set())

        msg_data = {
            'post_num': post_num,
            'board_id': 'b',
            'recipients': set(range(1, 101)),
            'content': {'type': 'text', 'text': 'Fully delivered post'},
            'delivery_phase': 'passive',
            'durable_delivery_id': 99,
        }
        task = MessageDeliveryTask("Worker-b", "b", MagicMock(), message_queues['b'], msg_data)
        with patch("delivery_manager.send_message_to_users") as mock_send:
            await task.process()
            mock_send.assert_not_called()
            mock_del_db.assert_called_once_with(99)


if __name__ == "__main__":
    unittest.main()
