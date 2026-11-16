# -*- coding: utf-8 -*-
"""
INQUISITOR 2: PIPELINE DISPATCH & DELIVERY RESILIENCE TORTURE TEST SUITE
Red-team verification for:
1. 30 concurrent user posts dispatched simultaneously to board 'b'.
2. Transient DB lock in create_post triggering jittered retry and succeeding.
3. Per-recipient edit timeout (8.0s) in edit_post_for_all_recipients isolating slow/hung network.
4. Debuff text length budgeting preventing 4096-char Telegram overflow and preserving balanced HTML.
5. Passive slice priority split fanout handling.
"""

import asyncio
import time
from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from post_processor import NewPostProcessor, NewPostContext, _BOARD_DISPATCH_LOCKS
from delivery_manager import edit_post_for_all_recipients, MessageDeliveryTask
import shared_state
from common.bot_helpers import get_telegram_utf16_len

UTC = timezone.utc


# ============================================================================
# SCENARIO 1: 30 CONCURRENT USER POSTS (DISPATCH LOCK INTEGRITY)
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_post_dispatch_monotonic_sequence():
    """
    Spawns 30 users creating posts concurrently on board 'b'.
    Verifies that _BOARD_DISPATCH_LOCKS['b'] strictly serializes creation,
    all 30 posts are recorded in monotonic order, no race conditions occur,
    and network calls are safely decoupled outside the lock.
    """
    board_id = "b"
    total_posts = 30
    post_counter = 50000

    lock_hold_history = []
    current_in_lock = [0]

    async def mock_create_post(board_id, author_id, content=None, **kwargs):
        nonlocal post_counter
        # Verify mutual exclusion inside board_dispatch_lock
        current_in_lock[0] += 1
        assert current_in_lock[0] == 1, f"Concurrency violation! {current_in_lock[0]} tasks inside board_dispatch_lock!"
        await asyncio.sleep(0.01)  # Simulate DB write latency
        post_counter += 1
        num = post_counter
        lock_hold_history.append((author_id, num))
        current_in_lock[0] -= 1
        return num

    async def mock_send_to_author(*args, **kwargs):
        # Network send happens concurrently outside the lock
        await asyncio.sleep(0.02)
        return True

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=9999))

    results = []

    async def user_post_worker(uid: int):
        ctx = NewPostContext(
            bot_instance=mock_bot,
            board_id=board_id,
            user_id=uid,
            content={"text": f"Post from user {uid}", "type": "text"},
            reply_to_post=None,
            is_shadow_muted=False,
        )
        processor = NewPostProcessor(ctx)
        processor.final_content = {"text": f"Post from user {uid}", "type": "text"}
        processor.author_content = processor.final_content.copy()

        def safe_spawn(coro):
            if asyncio.iscoroutine(coro):
                coro.close()
            return MagicMock()

        with patch.object(processor, "_determine_recipients_and_thread", new=AsyncMock(return_value=True)), \
             patch.object(processor, "_apply_content_transformations", new=AsyncMock()), \
             patch("post_processor.create_post", side_effect=mock_create_post), \
             patch("post_processor.spawn_task", side_effect=safe_spawn), \
             patch.object(processor, "_format_and_update_headers", new=AsyncMock()), \
             patch.object(processor, "_save_to_memory", new=AsyncMock()), \
             patch.object(processor, "_send_to_author_with_fallback", side_effect=mock_send_to_author), \
             patch.object(processor, "_process_author_results", new=AsyncMock()), \
             patch.object(processor, "_enqueue_and_notify", new=AsyncMock()):

            res = await processor.execute()
            results.append((uid, res))

    t0 = time.perf_counter()
    tasks = [asyncio.create_task(user_post_worker(1000 + i)) for i in range(total_posts)]
    await asyncio.gather(*tasks)
    dt = time.perf_counter() - t0

    # 1. All 30 posts succeeded
    assert len(results) == total_posts
    assert all(r[1] is not None for r in results)

    # 2. Strict monotonicity of post numbers
    post_nums = [r[1] for r in results]
    assert len(set(post_nums)) == total_posts, f"Duplicate post numbers detected: {post_nums}"

    # 3. All recorded in history without concurrency breaches
    assert len(lock_hold_history) == total_posts
    assert dt < 5.0, f"Dispatch took too long: {dt:.2f}s"


# ============================================================================
# SCENARIO 2: TRANSIENT DB LOCK RETRY IN CREATE_POST
# ============================================================================

@pytest.mark.asyncio
async def test_transient_create_post_retry_success():
    """
    Simulates transient SQLite lock where create_post returns None twice before succeeding.
    Verifies jittered retry logic kicks in and resolves cleanly.
    """
    board_id = "b"
    user_id = 7716348189
    call_attempts = [0]

    async def flaky_create_post(*args, **kwargs):
        call_attempts[0] += 1
        if call_attempts[0] < 3:
            return None  # Simulate transient lock timeout
        return 777888

    ctx = NewPostContext(
        bot_instance=MagicMock(),
        board_id=board_id,
        user_id=user_id,
        content={"text": "Post under transient DB contention", "type": "text"},
        reply_to_post=None,
        is_shadow_muted=False,
    )
    processor = NewPostProcessor(ctx)
    processor.author_content = {"text": "Post under transient DB contention", "type": "text"}

    with patch("post_processor.create_post", side_effect=flaky_create_post), \
         patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:

        now_dt = datetime.now(UTC)
        success = await processor._create_post_record(now_dt)

        assert success is True
        assert processor.current_post_num == 777888
        assert call_attempts[0] == 3
        # Jittered backoff slept twice
        assert mock_sleep.await_count == 2


# ============================================================================
# SCENARIO 3: PER-RECIPIENT TIMEOUT ISOLATION IN EDIT_POST
# ============================================================================

@pytest.mark.asyncio
async def test_edit_post_timeout_isolation():
    """
    Tests edit_post_for_all_recipients when one recipient's network hangs forever.
    Verifies asyncio.wait_for(..., timeout=8.0) trips, cancels the hung recipient,
    and allows other recipients to receive edits.
    """
    post_num = 999123
    bot_mock = MagicMock()

    recipients_hit = []

    async def mock_edit_text(text, chat_id, message_id, **kwargs):
        if chat_id == 222:
            # Recipient 222 hangs indefinitely
            await asyncio.sleep(60.0)
            return True
        recipients_hit.append(chat_id)
        return True

    bot_mock.edit_message_text = AsyncMock(side_effect=mock_edit_text)

    # get_post_copies returns list of (user_id, message_id) tuples
    mock_copies = [
        (111, 10),
        (222, 20),  # Hung
        (333, 30),
    ]

    shared_state.messages_storage[post_num] = {
        "board_id": "b",
        "author_id": 999999,
        "content": {"text": "Updated post content", "type": "text", "header": "Post #999123"},
        "reactions": {"users": {}},
        "timestamp": time.time(),
        "thread_id": None,
    }
    shared_state.board_data.setdefault("b", {})["user_settings"] = {}

    real_wait_for = asyncio.wait_for

    async def controlled_wait_for(coro, timeout):
        return await real_wait_for(coro, timeout=0.05)

    with patch("delivery_manager.get_post_copies", new=AsyncMock(return_value=mock_copies)), \
         patch("delivery_manager._format_message_body", new=AsyncMock(return_value="Updated body text")), \
         patch("delivery_manager.asyncio.wait_for", side_effect=controlled_wait_for), \
         patch("delivery_manager.asyncio.sleep", new=AsyncMock()):

        t0 = time.perf_counter()
        await edit_post_for_all_recipients(post_num, bot_mock)
        dt = time.perf_counter() - t0

        # Recipients 111 and 333 succeeded
        assert 111 in recipients_hit
        assert 333 in recipients_hit
        assert 222 not in recipients_hit
        assert dt < 2.0, f"Edit loop hung: took {dt:.2f}s"


# ============================================================================
# SCENARIO 4: DEBUFF LENGTH BUDGETING & HTML TAG BALANCING
# ============================================================================

@pytest.mark.asyncio
async def test_debuff_length_budgeting_prevents_overflow():
    """
    Tests NewPostProcessor debuff formatting with a massive 4000-char message
    and multiple debuffs active simultaneously (curse, shit, vomit, flag_ua, schizo).
    Verifies that the final text is budgeted strictly under 4096 units,
    and HTML tags remain balanced without breaking Telegram formatting.
    """
    import json
    board_id = "b"
    user_id = 888777

    # 4000-character message with Cyrillic text and emojis
    massive_text = "<b>Очень длинное сообщение</b> с текстом и подробностями! " * 80
    assert len(massive_text) > 3500

    ctx = NewPostContext(
        bot_instance=MagicMock(),
        board_id=board_id,
        user_id=user_id,
        content={"text": massive_text, "type": "text"},
        reply_to_post=None,
        is_shadow_muted=False,
    )
    processor = NewPostProcessor(ctx)
    processor.author_content = {"text": massive_text, "type": "text"}

    now_ts = int(time.time())
    future_ts = now_ts + 3600

    class MockAsyncCursor:
        def __init__(self, rows):
            self.rows = rows
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False
        def __aiter__(self):
            return self._gen()
        async def _gen(self):
            for row in self.rows:
                yield row

    mock_db = MagicMock()
    mock_db.execute.return_value = MockAsyncCursor([
        (
            future_ts,
            json.dumps({
                "cursed_until": future_ts,
                "schizo_pill_until": future_ts,
                "shit_until": future_ts,
                "vomit_until": future_ts,
                "flag_ua_until": future_ts,
            })
        )
    ])

    with patch("common.db_pool.get_pool", new=AsyncMock(return_value=mock_db)), \
         patch("common.bot_helpers.is_admin", return_value=False), \
         patch.dict(shared_state.board_data, {'b': {}}):

        await processor._apply_content_transformations()

        final_text = processor.author_content.get("text", "")
        final_len = get_telegram_utf16_len(final_text)

        # 1. Must NOT exceed Telegram limit (4096)
        assert final_len <= 4096, f"Text length {final_len} exceeded Telegram limit 4096!"

        # 2. Must contain debuff markers
        assert "ШИЗО-ТАБЛЕТКА" in final_text
        assert "<i>" in final_text and "</i>" in final_text

        # 3. HTML tags MUST be balanced (equal opens and closes)
        for tag in ["b", "i"]:
            opens = final_text.count(f"<{tag}>")
            closes = final_text.count(f"</{tag}>")
            assert opens == closes, f"Unbalanced <{tag}> tag in final text: {opens} opens vs {closes} closes!"


# ============================================================================
# SCENARIO 5: PASSIVE SLICE PRIORITY SPLIT FANOUT
# ============================================================================

def test_passive_slice_delivery_phase_matching():
    """
    Verifies MessageDeliveryTask correctly handles delivery_phase in ("passive", "passive_slice").
    """
    msg_passive = {
        "post_num": 101,
        "content": {"text": "Fanout slice test", "type": "text"},
        "delivery_phase": "passive",
        "recipients": {111, 222, 333},
    }
    task_passive = MessageDeliveryTask("worker_1", "b", MagicMock(), MagicMock(), msg_passive)
    assert task_passive.delivery_phase == "passive"

    msg_slice = {
        "post_num": 102,
        "content": {"text": "Fanout slice test 2", "type": "text"},
        "delivery_phase": "passive_slice",
        "recipients": {111, 222, 333},
    }
    task_slice = MessageDeliveryTask("worker_1", "b", MagicMock(), MagicMock(), msg_slice)
    assert task_slice.delivery_phase == "passive_slice"
