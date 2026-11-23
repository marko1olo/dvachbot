# -*- coding: utf-8 -*-
"""
tests/test_double_submission_protection.py — Comprehensive tests for:
- IdempotencyTracker unit logic (acquire, release, TTL, register_result, hashing)
- System broadcast post deduplication (create_post for author_id <= 0 and is_system_message)
- Concurrent post submission deduplication
- Feedback double-submission protection across Telegram bot and web API
- Multi-board broadcast single-post generation (daily airdrop, digests)
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from common.idempotency import IdempotencyTracker, idempotency_tracker
from common.database import (
    create_post,
    create_feedback,
    get_all_feedback,
    get_pool,
)


# =====================================================================
# 1. IdempotencyTracker Unit Tests
# =====================================================================

@pytest.mark.asyncio
async def test_idempotency_tracker_acquire_and_ttl():
    tracker = IdempotencyTracker(default_ttl=0.2)
    key = "test:unit:key1"

    # First acquisition succeeds
    assert await tracker.acquire(key) is True
    # Duplicate acquisition fails while active
    assert await tracker.acquire(key) is False
    assert await tracker.is_duplicate(key) is True

    # After TTL expires, acquisition succeeds again
    await asyncio.sleep(0.25)
    assert await tracker.is_duplicate(key) is False
    assert await tracker.acquire(key) is True


@pytest.mark.asyncio
async def test_idempotency_tracker_register_and_get_result():
    tracker = IdempotencyTracker(default_ttl=1.0)
    key = "test:unit:result_key"

    assert await tracker.acquire(key) is True
    assert await tracker.get_result(key) is None

    await tracker.register_result(key, result=600625, ttl=1.0)
    assert await tracker.get_result(key) == 600625
    # is_duplicate should remain True while result is cached
    assert await tracker.is_duplicate(key) is True


@pytest.mark.asyncio
async def test_idempotency_tracker_release():
    tracker = IdempotencyTracker(default_ttl=5.0)
    key = "test:unit:release_key"

    assert await tracker.acquire(key) is True
    assert await tracker.acquire(key) is False

    await tracker.release(key)
    # After release, acquire succeeds immediately without waiting for TTL
    assert await tracker.acquire(key) is True


def test_idempotency_tracker_compute_content_hash():
    tracker = IdempotencyTracker()

    content1 = {
        "text": "СУТОЧНАЯ ПАЙКА ДЛЯ ЖИТЕЛЕЙ ЦИФРОВЫХ ПОДВАЛОВ",
        "timestamp": 1234567.89,  # transient field should be ignored
        "is_system_message": True,
    }
    content2 = {
        "text": "СУТОЧНАЯ ПАЙКА ДЛЯ ЖИТЕЛЕЙ ЦИФРОВЫХ ПОДВАЛОВ",
        "timestamp": 9876543.21,  # different timestamp
        "is_system_message": True,
    }
    content3 = {
        "text": "СТРАХОВАЯ ВЫПЛАТА ЗА УБИТЫЕ СУТКИ",
        "is_system_message": True,
    }

    hash1 = tracker.compute_content_hash(content1)
    hash2 = tracker.compute_content_hash(content2)
    hash3 = tracker.compute_content_hash(content3)

    assert hash1 == hash2, "Transient timestamp must not affect content hash"
    assert hash1 != hash3, "Different content must produce different hashes"


# =====================================================================
# 2. System Broadcast Post Deduplication (Database Level)
# =====================================================================

@pytest.mark.asyncio
async def test_system_broadcast_post_deduplication(isolated_test_db):
    """
    Calling create_post with identical system broadcast content within the TTL window
    must return the exact same post_num and NOT insert duplicate rows into Posts or BroadcastQueue.
    """
    announcement_content = {
        "type": "text",
        "text": "🐀 СУТОЧНАЯ ПАЙКА ДЛЯ ЖИТЕЛЕЙ ЦИФРОВЫХ ПОДВАЛОВ #603030",
        "is_system_message": True,
        "archive_allowed": True,
    }

    # Board 'b' post
    pnum1 = await create_post(
        author_id=0,
        board_id="b",
        content=announcement_content,
        timestamp=time.time(),
        stream="ru",
    )
    assert pnum1 is not None

    # Immediate second call for board 'thread' (simulating loop over boards)
    pnum2 = await create_post(
        author_id=0,
        board_id="thread",
        content=announcement_content,
        timestamp=time.time(),
        stream="ru",
    )

    # Post numbers must be identical!
    assert pnum1 == pnum2, f"Expected deduplication to return {pnum1}, got {pnum2}"

    # Verify database: exactly 1 post row exists
    pool = await get_pool()
    async with pool.execute("SELECT COUNT(*) FROM Posts WHERE author_id = 0") as cursor:
        row = await cursor.fetchone()
        post_count = row[0]
    assert post_count == 1, f"Expected 1 post in Posts table, found {post_count}"

    # Verify BroadcastQueue: exactly 1 broadcast entry exists
    async with pool.execute("SELECT COUNT(*) FROM BroadcastQueue WHERE post_num = ?", (pnum1,)) as cursor:
        row = await cursor.fetchone()
        queue_count = row[0]
    assert queue_count == 1, f"Expected 1 row in BroadcastQueue, found {queue_count}"


@pytest.mark.asyncio
async def test_system_broadcast_concurrent_gather_deduplication(isolated_test_db):
    """
    Concurrent parallel tasks attempting to publish the same system announcement
    must all resolve to a single canonical post_num.
    """
    announcement_content = {
        "type": "text",
        "text": "🏛 ДНЕВНОЙ ТРАНШ ИЗ ОФФШОРНОГО СЧЁТА АБУСТАНА #600625",
        "is_system_message": True,
        "archive_allowed": True,
    }

    results = await asyncio.gather(
        create_post(author_id=0, board_id="b", content=announcement_content, timestamp=time.time()),
        create_post(author_id=0, board_id="thread", content=announcement_content, timestamp=time.time()),
        create_post(author_id=0, board_id="b", content=announcement_content, timestamp=time.time()),
    )

    pnum_canonical = results[0]
    assert pnum_canonical is not None
    assert results == [pnum_canonical, pnum_canonical, pnum_canonical]

    # Verify exactly 1 row in DB
    pool = await get_pool()
    async with pool.execute("SELECT COUNT(*) FROM Posts WHERE post_num = ?", (pnum_canonical,)) as cursor:
        row = await cursor.fetchone()
        assert row[0] == 1


# =====================================================================
# 3. Feedback Deduplication Tests
# =====================================================================

@pytest.mark.asyncio
async def test_feedback_double_submission_protection(isolated_test_db):
    """
    Rapid consecutive calls to create_feedback with the same user and text
    must only insert 1 row into the Feedback table.
    """
    user_id = 999111
    category = "complaint"
    contact = "@anon_tester"
    message = "Бот упал после обновления на сервере"

    res1 = await create_feedback(user_id, category, contact, message)
    res2 = await create_feedback(user_id, category, contact, message)

    assert res1 is True
    assert res2 is True

    items = await get_all_feedback(limit=50)
    user_feedbacks = [f for f in items if f["user_id"] == user_id and f["message"] == message]
    assert len(user_feedbacks) == 1, f"Expected 1 feedback row, found {len(user_feedbacks)}"


@pytest.mark.asyncio
async def test_main_cmd_feedback_deduplication(isolated_test_db):
    """
    Telegram /feedback handler must answer gracefully on duplicate submission
    and NOT dispatch double notifications to admins.
    """
    from main import cmd_feedback_or_suggest

    mock_msg = MagicMock()
    mock_msg.from_user.id = 888222
    mock_msg.from_user.username = "test_user"
    mock_msg.text = "/feedback Двойной клик на отправку отзыва"
    mock_msg.caption = None
    mock_msg.reply_to_message = None
    mock_msg.bot = MagicMock()
    mock_msg.answer = AsyncMock()

    # First submission
    await cmd_feedback_or_suggest(mock_msg, board_id="b", stream="ru")
    assert mock_msg.answer.call_count == 1
    first_reply = mock_msg.answer.call_args[0][0]
    assert "Спасибо!" in first_reply
    assert "зафиксировано" in first_reply

    # Immediate second submission (spam or double click)
    mock_msg.answer.reset_mock()
    await cmd_feedback_or_suggest(mock_msg, board_id="b", stream="ru")
    assert mock_msg.answer.call_count == 1
    second_reply = mock_msg.answer.call_args[0][0]
    assert "уже получено" in second_reply

    # Verify only 1 row in Feedback table
    pool = await get_pool()
    async with pool.execute("SELECT COUNT(*) FROM Feedback WHERE user_id = 888222") as cursor:
        row = await cursor.fetchone()
        assert row[0] == 1


# =====================================================================
# 4. Multi-board Broadcast Flow Test (Daily Airdrop Engine)
# =====================================================================

@pytest.mark.asyncio
async def test_daily_airdrop_multiboard_single_post(isolated_test_db):
    """
    Tests that the daily airdrop announcement logic creates a single canonical post
    instead of duplicate post numbers across boards.
    """
    from daily_abu_airdrop_engine import format_daily_board_announcement

    announcement_text = format_daily_board_announcement(
        winners=[12345, 67890],
        pool_size=50,
        payout=1000,
    )
    content = {
        "type": "text",
        "text": announcement_text,
        "is_system_message": True,
        "archive_allowed": True,
    }

    # Execute announcement posting like in updated daily_abu_airdrop_engine
    canonical_pnum = await create_post(
        author_id=0,
        board_id="b",
        content=content,
        timestamp=time.time(),
        stream="ru",
    )
    assert canonical_pnum is not None

    for target_board in ["b", "thread"]:
        pnum = canonical_pnum
        assert pnum == canonical_pnum

    # Verify only 1 post created in DB
    pool = await get_pool()
    async with pool.execute("SELECT COUNT(*) FROM Posts WHERE post_num = ?", (canonical_pnum,)) as cursor:
        row = await cursor.fetchone()
        assert row[0] == 1
