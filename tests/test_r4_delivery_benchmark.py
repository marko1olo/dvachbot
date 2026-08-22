import asyncio
import time
import os
import sys
import unittest
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import __main__
import main
__main__.DURABLE_DELIVERY_QUEUE_ENABLED = True
__main__._contains_volatile_delivery_payload = getattr(main, "_contains_volatile_delivery_payload", lambda c: False)

import common.config as config
from shared_state import (
    DELIVERY_INITIAL_CHUNK_SIZE,
    DELIVERY_MAX_CHUNK_SIZE,
    DELIVERY_MIN_CHUNK_SIZE,
    weekly_active_users,
    message_queues,
    board_data,
    current_deliveries,
    messages_storage,
    storage_lock,
    BroadcastConfig,
    BOARD_CONFIG
)
from broadcaster import MessageBroadcaster, DeliveryResults
from delivery_manager import (
    MessageDeliveryTask,
    enqueue_board_message,
    _passive_slice_size_for_content,
    _split_recipients_for_delivery,
    _delete_durable_delivery_item,
    cumulative_post_metrics
)
from common.database import (
    upsert_delivery_queue_item,
    delete_delivery_queue_item,
    get_pending_delivery_queue_items,
    get_post_copies,
    add_post_copies,
    create_post
)
from common.db_pool import create_pool, get_pool, db_lock
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramNetworkError


class TestR4DeliveryBenchmark(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Reset state
        cumulative_post_metrics.clear()
        current_deliveries.clear()
        
        # Ensure DB pool is initialized
        try:
            await create_pool()
        except Exception:
            pass

        # Set up test boards and active user sets
        for b in list(BOARD_CONFIG.keys())[:13]:
            weekly_active_users[b] = set(range(1, 61))  # 60 active users per board (typical active set)
            board_data[b] = {
                'users': {'banned': set(), 'active': set(range(1, 1501))},
                'user_settings': {},
                'user_state': {uid: {'location': 'main'} for uid in range(1, 1501)},
            }
            if b not in message_queues:
                message_queues[b] = asyncio.Queue()
            else:
                while not message_queues[b].empty():
                    message_queues[b].get_nowait()

    async def test_01_active_user_priority_latency(self):
        """Benchmark 1: Active user priority delivery <= 2.5s (target < 2.0s for typical 50-60 active users)."""
        board_id = 'b'
        active_count = 55  # Typical active user set
        total_recipients = 676

        all_recipients = set(range(1, total_recipients + 1))
        weekly_active_users[board_id] = set(range(1, active_count + 1))

        prio_recipients, passive_recipients = _split_recipients_for_delivery(board_id, all_recipients)
        self.assertEqual(len(prio_recipients), active_count)
        self.assertEqual(len(passive_recipients), total_recipients - active_count)

        delivered_ids = []
        async def mock_send(uid, timeout_sec):
            delivered_ids.append(uid)
            return MagicMock(message_id=10000 + uid)

        config_obj = BroadcastConfig(
            bot_instance=MagicMock(),
            board_id=board_id,
            recipients=list(prio_recipients),
            content={'type': 'text', 'text': 'Priority post content'},
            verbose=False,
            delivery_phase='priority',
            delivery_original_recipients=total_recipients
        )

        simulated_sleep_t1 = 0.0
        async def fake_sleep_t1(sec):
            nonlocal simulated_sleep_t1
            simulated_sleep_t1 += sec

        broadcaster = MessageBroadcaster(config_obj)
        broadcaster._send_one_guarded = mock_send

        with patch("broadcaster.asyncio.sleep", side_effect=fake_sleep_t1):
            t_start = time.perf_counter()
            results = await broadcaster.broadcast()
            t_elapsed = (time.perf_counter() - t_start) + simulated_sleep_t1

        throughput = len(results) / t_elapsed
        print(f"\n[BENCHMARK 1] Priority delivery for {len(results)} active users: {t_elapsed:.3f}s (Throughput: {throughput:.1f} msg/s)")
        self.assertEqual(len(results), active_count)
        # Verification: Active user priority delivery <= 2.5s (target < 2.0s)
        self.assertLessEqual(t_elapsed, 2.5)

    async def test_02_passive_broadcast_676_recipients_under_30s(self):
        """Benchmark 2: Full passive broadcast of 676 recipients completes in <= 30s across dedicated bot token."""
        board_id = 'b'
        total_recipients = 676
        recipients = set(range(1, total_recipients + 1))

        # Create valid post in DB first
        post_num = await create_post(author_id=1, board_id=board_id, content={'type': 'text', 'text': 'Bench post 2'}, timestamp=time.time())

        # Enqueue post for delivery manager slicing pipeline
        msg_data = {
            'post_num': post_num,
            'board_id': board_id,
            'recipients': recipients,
            'content': {'type': 'text', 'text': 'Passive broadcast test post'},
            'delivery_phase': 'full',
            'original_recipients': total_recipients,
            'enqueued_at': time.time()
        }
        await message_queues[board_id].put(msg_data)

        delivered_uids = []
        # Mock low-level broadcaster send guarded to simulate network sending
        async def mock_send(uid, timeout_sec):
            delivered_uids.append(uid)
            return MagicMock(message_id=20000 + uid)

        simulated_sleep_t2 = 0.0
        async def fake_sleep_t2(sec):
            nonlocal simulated_sleep_t2
            simulated_sleep_t2 += sec

        with patch("broadcaster.MessageBroadcaster._send_one_guarded", side_effect=mock_send), \
             patch("broadcaster.asyncio.sleep", side_effect=fake_sleep_t2):
            t_start = time.perf_counter()
            # Process delivery queue until all slices complete
            while not message_queues[board_id].empty():
                item = await message_queues[board_id].get()
                task = MessageDeliveryTask("Worker-b", board_id, MagicMock(), message_queues[board_id], item)
                await task.process()
            t_elapsed = (time.perf_counter() - t_start) + simulated_sleep_t2

        throughput = len(delivered_uids) / t_elapsed
        print(f"\n[BENCHMARK 2] Full delivery for {len(delivered_uids)} recipients: {t_elapsed:.3f}s (Throughput: {throughput:.1f} msg/s)")
        self.assertEqual(len(delivered_uids), total_recipients)
        # Requirement: Passive broadcast of 676 recipients completes in <= 30.0s
        self.assertLessEqual(t_elapsed, 30.0)
        self.assertGreaterEqual(throughput, 22.0)  # Pacing calibrated at ~28 msg/s

    async def test_03_inter_slice_priority_preemption(self):
        """Benchmark 3: Active user priority delivery preempts background passive slicing in < 2.5s."""
        board_id = 'b'
        post_passive = 880003
        post_active = 880004

        # 1. Enqueue large passive slicing post (800 passive recipients)
        passive_msg = {
            'post_num': post_passive,
            'board_id': board_id,
            'recipients': set(range(101, 901)), # 800 passive users
            'content': {'type': 'text', 'text': 'Background passive post'},
            'delivery_phase': 'passive',
            'original_recipients': 900,
            'enqueued_at': time.time()
        }
        await message_queues[board_id].put(passive_msg)

        # 2. Enqueue urgent active post (50 active users)
        active_msg = {
            'post_num': post_active,
            'board_id': board_id,
            'recipients': set(range(1, 51)), # 50 active users
            'content': {'type': 'text', 'text': 'Urgent active post'},
            'delivery_phase': 'priority',
            'original_recipients': 50,
            'enqueued_at': time.time()
        }
        await message_queues[board_id].put(active_msg)

        # Track execution order and timing
        processed_phases = []
        async def fake_send_to_users(config):
            processed_phases.append((config.delivery_phase, len(config.recipients), config.delivery_original_recipients))
            return DeliveryResults(
                [(uid, MagicMock(message_id=uid)) for uid in config.recipients],
                remaining_recipients=set(),
                stats={'success': len(config.recipients), 'priority_recipients': len(config.recipients) if config.delivery_phase == 'priority' else 0, 'passive_recipients': len(config.recipients) if config.delivery_phase != 'priority' else 0}
            )

        with patch("delivery_manager.send_message_to_users", side_effect=fake_send_to_users), \
             patch("delivery_manager._persist_durable_delivery_item", return_value=1), \
             patch("delivery_manager._delete_durable_delivery_item", return_value=True):
            
            # Step 1: Process passive task slice (slice size = 250)
            item1 = await message_queues[board_id].get()
            t1 = MessageDeliveryTask("Worker-b", board_id, MagicMock(), message_queues[board_id], item1)
            await t1.process()

            # Passive slice deferred remaining (800 - 250 = 550) to back of queue.
            # Active task is now at front of queue!
            self.assertEqual(message_queues[board_id].qsize(), 2)

            # Step 2: Process urgent active task next
            t_active_start = time.perf_counter()
            item2 = await message_queues[board_id].get()
            self.assertEqual(item2['post_num'], post_active)
            self.assertEqual(item2['delivery_phase'], 'priority')

            t2 = MessageDeliveryTask("Worker-b", board_id, MagicMock(), message_queues[board_id], item2)
            await t2.process()
            t_active_elapsed = time.perf_counter() - t_active_start

            print(f"\n[BENCHMARK 3] Preempted active post processed in {t_active_elapsed*1000:.2f}ms without waiting for 550 passive users")
            self.assertLessEqual(t_active_elapsed, 2.5)

    async def test_04_durable_delivery_recovery_and_zero_drop(self):
        """Benchmark 4: Durable delivery restore recovers exact pending slices without dropping or repeating."""
        board_id = 'b'
        total_recipients = 1000

        # Create real post in DB
        post_num = await create_post(author_id=1, board_id=board_id, content={'type': 'text', 'text': 'Durable recovery post'}, timestamp=time.time())

        # Scenario: 100 priority + 250 passive delivered before crash = 350 delivered.
        # 650 passive recipients were pending in DB when process died.
        delivered_before_crash = set(range(1, 351))
        pending_in_db = set(range(351, total_recipients + 1))
        self.assertEqual(len(pending_in_db), 650)

        # 1. Populate DB with PostCopies for delivered_before_crash
        copies_data = [(uid, post_num * 10000 + uid) for uid in delivered_before_crash]
        await add_post_copies(post_num, copies_data)

        # 2. Insert durable item in DeliveryQueue
        item_id = await upsert_delivery_queue_item(
            board_id=board_id,
            post_num=post_num,
            recipients=list(pending_in_db),
            content={'type': 'text', 'text': 'Durable recovery post'},
            delivery_phase="passive",
            original_recipients=total_recipients
        )
        self.assertIsNotNone(item_id)

        # 3. Execute recovery logic
        delivered_after_recovery = []
        async def fake_send_to_users(config):
            delivered_after_recovery.extend(config.recipients)
            # Add copies to DB as delivery_manager does
            await add_post_copies(post_num, [(uid, post_num * 10000 + 5000 + uid) for uid in config.recipients])
            return DeliveryResults(
                [(uid, MagicMock(message_id=uid)) for uid in config.recipients],
                remaining_recipients=set(),
                stats={'success': len(config.recipients), 'priority_recipients': 0, 'passive_recipients': len(config.recipients)}
            )

        with patch("delivery_manager.send_message_to_users", side_effect=fake_send_to_users):
            restored_msg_data = {
                "recipients": list(pending_in_db),
                "content": {'type': 'text', 'text': 'Durable recovery post'},
                "post_num": post_num,
                "board_id": board_id,
                "delivery_phase": "passive",
                "original_recipients": total_recipients,
                "durable_delivery_id": item_id,
                "enqueued_at": time.time(),
            }

            # Process slices until complete (650 users -> 250 + 250 + 150 = 3 slices)
            queue = asyncio.Queue()
            await queue.put(restored_msg_data)

            slice_count = 0
            while not queue.empty():
                slice_item = await queue.get()
                task = MessageDeliveryTask("Worker-b", board_id, MagicMock(), queue, slice_item)
                await task.process()
                slice_count += 1

            self.assertEqual(slice_count, 3)
            self.assertEqual(len(delivered_after_recovery), 650)

            # Verify PostCopies has all 1000 unique recipients (350 before + 650 after)
            all_copies = await get_post_copies(post_num)
            all_copy_uids = {r[0] for r in all_copies}
            self.assertEqual(len(all_copy_uids), 1000)
            self.assertEqual(all_copy_uids, set(range(1, 1001)))

            # Verify item was removed from DB (status deleted or row gone)
            db_conn = await get_pool()
            async with db_conn.execute("SELECT id FROM DeliveryQueue WHERE id = ?", (item_id,)) as cur:
                row = await cur.fetchone()
                self.assertIsNone(row)

            print(f"\n[BENCHMARK 4] Durable recovery verified: 1000/1000 recipients delivered (0 dropped, 0 duplicate, DB cleaned)")

    async def test_05_multi_board_13_bot_swarm_concurrency_and_zero_deadlocks(self):
        """Benchmark 5: Multi-board concurrent delivery across 13 bot swarm with zero deadlocks."""
        boards = list(BOARD_CONFIG.keys())[:13]
        recipients_per_board = 200  # 50 active + 150 passive per board -> 2,600 total

        simulated_sleep_t5 = 0.0
        async def fake_sleep_t5(sec):
            nonlocal simulated_sleep_t5
            simulated_sleep_t5 += sec

        async def run_board_delivery(board_idx, board_id):
            recipients = list(range(1, recipients_per_board + 1))
            delivered = []
            
            async def mock_send(uid, timeout_sec):
                delivered.append(uid)
                return MagicMock(message_id=30000 + uid)

            config_obj = BroadcastConfig(
                bot_instance=MagicMock(),
                board_id=board_id,
                recipients=recipients,
                content={'type': 'text', 'text': f'Swarm broadcast on /{board_id}/'},
                verbose=False,
                delivery_phase='full',
                delivery_original_recipients=recipients_per_board
            )

            broadcaster = MessageBroadcaster(config_obj)
            broadcaster._send_one_guarded = mock_send

            # Concurrently perform DB operations
            post_num = await create_post(
                author_id=100,
                board_id=board_id,
                content={'type': 'text', 'text': f'Swarm post on /{board_id}/'},
                timestamp=time.time()
            )
            await add_post_copies(post_num, [(1, 101), (2, 102), (3, 103)])
            await get_post_copies(post_num)

            t0 = time.perf_counter()
            results = await broadcaster.broadcast()
            t_elapsed = time.perf_counter() - t0
            return board_id, len(results), t_elapsed

        with patch("broadcaster.asyncio.sleep", side_effect=fake_sleep_t5):
            t_swarm_start = time.perf_counter()
            tasks = [run_board_delivery(i, b) for i, b in enumerate(boards)]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            t_swarm_total = (time.perf_counter() - t_swarm_start) + (simulated_sleep_t5 / 13.0)

        total_msgs = sum(r[1] for r in results)
        aggregate_throughput = total_msgs / t_swarm_total
        print(f"\n[BENCHMARK 5] 13-board swarm concurrency completed: {total_msgs} messages in {t_swarm_total:.3f}s (Swarm Throughput: {aggregate_throughput:.1f} msg/s across 13 bots)")

        self.assertEqual(len(results), 13)
        self.assertEqual(total_msgs, 13 * recipients_per_board)
        # All 13 boards ran concurrently, each taking ~7-10s (200 msgs / 28 msg/s) in parallel
        self.assertLessEqual(t_swarm_total, 16.0)
        self.assertGreaterEqual(aggregate_throughput, 180.0)  # Total swarm throughput > 180 msg/s


if __name__ == "__main__":
    unittest.main()
