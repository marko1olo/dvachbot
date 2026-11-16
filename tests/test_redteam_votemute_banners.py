# -*- coding: utf-8 -*-
"""
tests/test_redteam_votemute_banners.py
======================================
Adversarial redteam verification suite for:
1. votemute_engine.py (concurrency, race conditions, deduplication, privacy, lock safety)
2. banner_manager.py (broken file_id recovery, flood wait backoff with jitter, cache concurrency)
3. delivery_manager.py (priority/passive slicing, anti-starvation preemption, hung recipient timeouts)
"""

import asyncio
import json
import os
import random
import time
from collections import deque
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import banner_manager
import delivery_manager
import votemute_engine
from common.anon_identity import get_anon_id


async def seed_voter(db, voter_id: int, board_id: str = "b"):
    """Seeds voter with 2 recent non-shadow posts so voter is eligible for quorum."""
    now = time.time()
    await db.execute(
        "INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active') ON CONFLICT(user_id, board_id) DO NOTHING",
        (voter_id, board_id),
    )
    await db.execute(
        "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES (?, ?, '{}', ?, 0)",
        (board_id, voter_id, now - 3600),
    )
    await db.execute(
        "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES (?, ?, '{}', ?, 0)",
        (board_id, voter_id, now - 1800),
    )
    await db.commit()


# ============================================================================
# 1. VOTEMUTE ENGINE REDTEAM AUDIT
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_5th_vote_single_verdict(isolated_test_db):
    """
    REDTEAM 1.1: What happens if 2 users cast the winning 5th vote at the exact same millisecond?
    VERIFY: Verdict is executed EXACTLY ONCE.
    One voter crosses the quorum and executes verdict (is_executed=True).
    The other voter is cleanly informed that verdict was already passed.
    """
    db = isolated_test_db
    target_id = 99901
    post_num = 88801
    board_id = "b"

    await db.execute("INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')", (target_id, board_id))
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)",
                     (post_num, board_id, target_id, time.time()))
    await db.commit()

    votemute_engine.active_votemutes.clear()

    # Pre-seed 6 voters
    voters = [10001, 10002, 10003, 10004, 10005, 10006]
    for v in voters:
        await seed_voter(db, v, board_id=board_id)

    # Cast 4 votes first
    for v in voters[:4]:
        ok, msg, current, executed = await votemute_engine.start_or_add_vote(
            board_id=board_id, target_id=target_id, post_num=post_num, voter_id=v, vote_type="yes"
        )
        assert ok is True
        assert executed is False
    assert current == 4

    # Now voters[4] and voters[5] cast the 5th vote at the exact same millisecond via asyncio.gather
    mute_mock = AsyncMock()
    with patch("votemute_engine._apply_unbribable_iron_mute", mute_mock):
        res1, res2 = await asyncio.gather(
            votemute_engine.start_or_add_vote(board_id=board_id, target_id=target_id, post_num=post_num, voter_id=voters[4], vote_type="yes"),
            votemute_engine.start_or_add_vote(board_id=board_id, target_id=target_id, post_num=post_num, voter_id=voters[5], vote_type="yes"),
        )

    # Exactly one must have triggered the verdict execution
    executed_results = [r for r in (res1, res2) if r[0] is True and r[3] is True]
    rejected_results = [r for r in (res1, res2) if r[0] is False]

    assert len(executed_results) == 1, "Exactly one caller must cross threshold and trigger verdict!"
    assert len(rejected_results) == 1, "Second simultaneous caller must be rejected as verdict already executed!"
    assert "уже вынесен" in rejected_results[0][1]

    # Verify verdict function was called exactly ONCE
    assert mute_mock.call_count == 1, "_apply_unbribable_iron_mute must be called exactly once!"

    # Verify DB status
    async with db.execute("SELECT status, yes_votes FROM Votemutes WHERE target_id = ?", (target_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == "executed"
        assert row[1] == 5


@pytest.mark.asyncio
async def test_double_click_vote_deduplication_and_mutex(isolated_test_db):
    """
    REDTEAM 1.2: Can a user vote twice by double-clicking the inline button?
    VERIFY: Callback query deduplication and mutex locking prevents double-voting.
    """
    db = isolated_test_db
    target_id = 99902
    post_num = 88802
    board_id = "b"
    voter_id = 10007

    await db.execute("INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')", (target_id, board_id))
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)",
                     (post_num, board_id, target_id, time.time()))
    await seed_voter(db, voter_id, board_id=board_id)

    votemute_engine.active_votemutes.clear()
    token = votemute_engine.get_votemute_callback_token(target_id, post_num)

    # Initialize session
    await votemute_engine.start_or_add_vote(board_id, target_id, post_num, 10008, vote_type="yes")

    # Create two simultaneous callback queries from the SAME user
    def make_cb():
        cb = AsyncMock()
        cb.data = f"vm_vote:yes:{token}"
        cb.from_user = MagicMock(id=voter_id)
        cb.message = AsyncMock(caption="Card", photo=[MagicMock()], edit_caption=AsyncMock())
        cb.bot = AsyncMock()
        cb.answer = AsyncMock()
        return cb

    cb1, cb2 = make_cb(), make_cb()

    await asyncio.gather(
        votemute_engine.callback_votemute_vote(cb1, board_id=board_id),
        votemute_engine.callback_votemute_vote(cb2, board_id=board_id),
    )

    answers = [cb1.answer.call_args[0][0], cb2.answer.call_args[0][0]]
    assert any("голос учтен" in a for a in answers), "One click must be recorded"
    assert any("уже отдал свой голос" in a for a in answers), "Second click must be deduplicated"

    # Verify DB: exactly 1 vote row from this voter
    async with db.execute("SELECT COUNT(*) FROM VotemuteVotes WHERE voter_id = ?", (voter_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 1, "Voter must only have exactly 1 recorded vote row"


@pytest.mark.asyncio
async def test_votemute_expired_session_no_deadlock(isolated_test_db):
    """
    REDTEAM 1.3: Deadlock check on expired votemute.
    Previously, an expired session called `async with votemute_lock:` inside an already-acquired
    `votemute_lock`, causing an unrecoverable asyncio.Lock deadlock!
    VERIFY: Clean expiration handling without deadlock, returns in <1 second.
    """
    db = isolated_test_db
    target_id = 99903
    post_num = 88803
    board_id = "b"
    voter_id = 10009

    await db.execute("INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')", (target_id, board_id))
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)",
                     (post_num, board_id, target_id, time.time()))
    await seed_voter(db, voter_id, board_id=board_id)

    # Insert an expired session into DB
    now = time.time()
    vm_key = votemute_engine.generate_votemute_key(target_id, post_num)
    await db.execute(
        """INSERT INTO Votemutes (vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status, yes_votes, no_votes, required_votes)
           VALUES (?, ?, ?, ?, 10001, ?, ?, 'active', 1, 0, 5)""",
        (vm_key, board_id, target_id, post_num, now - 1000, now - 10)  # Expired 10s ago!
    )
    await db.commit()

    votemute_engine.active_votemutes.clear()

    # Must complete cleanly within 2 seconds without deadlocking
    ok, msg, current, executed = await asyncio.wait_for(
        votemute_engine.start_or_add_vote(board_id, target_id, post_num, voter_id, vote_type="yes"),
        timeout=2.0
    )

    assert ok is False
    assert "истек" in msg
    assert executed is False

    # Verify lock is totally free by casting a fresh vote immediately
    voter_fresh = 10010
    await seed_voter(db, voter_fresh, board_id=board_id)
    post_fresh = 999888
    await db.execute("INSERT OR REPLACE INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)",
                     (post_fresh, board_id, target_id, time.time()))
    await db.commit()

    ok_fresh, _, votes_fresh, _ = await asyncio.wait_for(
        votemute_engine.start_or_add_vote(board_id, target_id, post_fresh, voter_fresh, vote_type="yes"),
        timeout=2.0
    )
    assert ok_fresh is True
    assert votes_fresh == 1


@pytest.mark.asyncio
async def test_concurrent_cmd_votemute_single_card_and_broadcast(isolated_test_db):
    """
    REDTEAM 1.4: Verify that only exactly 1 card is broadcast even if 2 users run /votemute concurrently.
    """
    db = isolated_test_db
    target_id = 99904
    post_num = 88805
    board_id = "b"
    voter_1 = 10011
    voter_2 = 10012

    await db.execute("INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')", (target_id, board_id))
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)",
                     (post_num, board_id, target_id, time.time()))
    await seed_voter(db, voter_1, board_id=board_id)
    await seed_voter(db, voter_2, board_id=board_id)

    votemute_engine.active_votemutes.clear()

    def make_msg(v_id):
        m = AsyncMock()
        m.from_user = MagicMock(id=v_id)
        m.chat = MagicMock(id=v_id)
        m.text = f"/votemute {post_num}"
        m.reply_to_message = None
        m.answer = AsyncMock()
        m.answer_photo = AsyncMock()
        m.bot = AsyncMock()
        m.bot.id = 99999999
        return m

    m1, m2 = make_msg(voter_1), make_msg(voter_2)

    bcast_mock = AsyncMock()
    with patch("banner_manager.broadcast_banner_to_users", bcast_mock), \
         patch("votemute_engine._resolve_target_from_message", return_value=(post_num, target_id)):
        await asyncio.gather(
            votemute_engine.cmd_votemute(m1, board_id=board_id),
            votemute_engine.cmd_votemute(m2, board_id=board_id),
        )

    # Exactly 1 broadcast must be launched
    assert bcast_mock.call_count == 1, f"broadcast_banner_to_users must be called exactly ONCE, got {bcast_mock.call_count}!"

    # One user got the initial card, the second user got the link/info reply
    all_replies = [
        m1.answer.call_args[0][0] if m1.answer.called else (m1.answer_photo.call_args[1].get("caption") if m1.answer_photo.called else ""),
        m2.answer.call_args[0][0] if m2.answer.called else (m2.answer_photo.call_args[1].get("caption") if m2.answer_photo.called else ""),
    ]
    assert any("уже активно" in r for r in all_replies), "Second concurrent caller must be linked to active voting without duplicate card!"


def test_votemute_strict_privacy_no_personal_data_leak():
    """
    REDTEAM 1.5: Verify that NO user personal data (username, telegram ID, first name)
    is leaked anywhere in votemute cards, callbacks, or broadcast captions.
    """
    target_id = 987654321
    post_num = 45678

    # 1. Callback token: must only use hash (anon_id), never raw target_id
    token = votemute_engine.get_votemute_callback_token(target_id, post_num)
    assert str(target_id) not in token, "Raw telegram ID must never be exposed in callback token!"
    assert str(post_num) in token

    # 2. Card text: references post number only (#45678)
    card_text = votemute_engine.get_votemute_card_text(
        post_num=post_num, target_id=target_id, votes_count=2, created_ts=time.time(), no_votes=1
    )
    assert str(target_id) not in card_text
    assert f"#{post_num}" in card_text
    assert "@" not in card_text

    # 3. All 40 public verdict announcements: verify NO target_id or username placeholder
    for ann in votemute_engine.VOTEMUTE_ANNOUNCEMENTS:
        formatted = ann.format(post_num=post_num, target_anon=f"#{post_num}")
        assert str(target_id) not in formatted
        assert "@" not in formatted
        assert f"#{post_num}" in formatted


# ============================================================================
# 2. BANNER MANAGER REDTEAM AUDIT
# ============================================================================

@pytest.mark.asyncio
async def test_banner_broken_file_id_eviction_and_recovery(tmp_path):
    """
    REDTEAM 2.1: What happens if cached file_id is invalid or expired?
    VERIFY:
    - Evicted from BOTH _BANNER_CACHE and _CACHE_BY_FILENAME.
    - Re-uploads local file, extracts new file_id, updates both caches.
    - Subsequent calls return the new file_id, not the broken one!
    """
    fake_banner = "test_adversarial_banner.jpg"
    broken_fid = "AgACAgIAAxkBAAI_BROKEN_OLD_FILE_ID"
    new_valid_fid = "AgACAgIAAxkBAAI_FRESH_VALID_FILE_ID"
    bot_id = 12345678

    orig_cache = dict(banner_manager._BANNER_CACHE)
    orig_cbf = dict(banner_manager._CACHE_BY_FILENAME)

    # Seed broken ID into both caches
    banner_manager._BANNER_CACHE[f"{bot_id}:{fake_banner}"] = broken_fid
    banner_manager._BANNER_CACHE[fake_banner] = broken_fid
    banner_manager._CACHE_BY_FILENAME[fake_banner] = broken_fid

    # Create dummy local banner file
    local_banner_path = banner_manager.BANNERS_DIR / fake_banner
    banner_manager.BANNERS_DIR.mkdir(parents=True, exist_ok=True)
    local_banner_path.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 100)

    try:
        mock_bot = AsyncMock()
        mock_bot.id = bot_id

        # First call with broken file_id raises TelegramBadRequest
        # Second call with local FSInputFile succeeds and returns message with new_valid_fid
        success_msg = MagicMock()
        photo_size = MagicMock(file_id=new_valid_fid)
        success_msg.photo = [photo_size]
        success_msg.video = None
        success_msg.animation = None

        call_count = 0
        async def fake_send_photo(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Broken file_id rejected by Telegram
                raise TelegramBadRequest(method=None, message="Bad Request: wrong remote file identifier and/or state")
            return success_msg

        mock_bot.send_photo = AsyncMock(side_effect=fake_send_photo)

        sent = await banner_manager.send_banner_message(
            bot=mock_bot,
            chat_id=111,
            caption="Test banner",
            banner_name=fake_banner
        )

        assert sent is success_msg
        assert call_count == 2, "Must retry once with local file"

        # VERIFY CACHES: broken_fid must be gone, new_valid_fid must be present in BOTH
        assert banner_manager._BANNER_CACHE.get(f"{bot_id}:{fake_banner}") == new_valid_fid
        assert banner_manager._CACHE_BY_FILENAME.get(fake_banner) == new_valid_fid
        assert broken_fid not in banner_manager._BANNER_CACHE.values()
        assert broken_fid not in banner_manager._CACHE_BY_FILENAME.values()

        # Subsequent call to get_banner_file must immediately return new_valid_fid!
        chosen, payload = banner_manager.get_banner_file(banner_name=fake_banner, bot_id=bot_id)
        assert payload == new_valid_fid
    finally:
        if local_banner_path.exists():
            local_banner_path.unlink()
        banner_manager._BANNER_CACHE.clear()
        banner_manager._BANNER_CACHE.update(orig_cache)
        banner_manager._CACHE_BY_FILENAME.clear()
        banner_manager._CACHE_BY_FILENAME.update(orig_cbf)


@pytest.mark.asyncio
async def test_banner_broadcast_flood_wait_jitter_and_recovery():
    """
    REDTEAM 2.2: What happens in broadcast_banner_to_users on TelegramRetryAfter?
    VERIFY: Handled with jittered backoff, does not crash, delivers to all recipients.
    """
    mock_bot = AsyncMock()
    mock_bot.id = 7777777

    # User 1 hits flood wait first, user 2 succeeds immediately
    user1_attempts = 0
    async def fake_send(bot, chat_id, *args, **kwargs):
        nonlocal user1_attempts
        if chat_id == 101:
            user1_attempts += 1
            if user1_attempts == 1:
                raise TelegramRetryAfter(method=None, message="Flood", retry_after=0.05)
        m = MagicMock()
        m.message_id = chat_id + 5000
        return m

    with patch("banner_manager.send_banner_message", side_effect=fake_send):
        results = await banner_manager.broadcast_banner_to_users(
            bot=mock_bot,
            user_ids=[101, 102],
            exclude_uid=0,
            caption="Flood test",
        )

    assert len(results) == 2, "Both recipients must receive message despite flood wait!"
    assert user1_attempts == 2, "User 1 must have retried after flood backoff"


@pytest.mark.asyncio
async def test_banners_cache_atomic_write_concurrency():
    """
    REDTEAM 2.3: Is banners_cache.json write-safe under concurrent access on Windows?
    VERIFY: 20 concurrent tasks calling save_cache() succeed with 0 PermissionErrors.
    """
    orig_cache = dict(banner_manager._BANNER_CACHE)
    try:
        # Seed various cache keys
        for i in range(50):
            banner_manager._BANNER_CACHE[f"bot_{i}:banner_{i}.jpg"] = f"fid_{i}"

        # Run 20 concurrent saves
        tasks = [asyncio.to_thread(banner_manager.save_cache, force=True) for _ in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Concurrent save_cache failed with: {errors}"

        # Verify JSON file on disk is valid
        assert banner_manager.CACHE_FILE.exists()
        content = json.loads(banner_manager.CACHE_FILE.read_text(encoding="utf-8"))
        assert isinstance(content, dict)
        assert len(content) >= 50
    finally:
        banner_manager._BANNER_CACHE.clear()
        banner_manager._BANNER_CACHE.update(orig_cache)
        banner_manager.save_cache(force=True)


def test_user_recent_banners_memory_bound():
    """
    REDTEAM 2.4: Ensure _USER_RECENT_BANNERS stays bounded and does not leak RAM on 1GB VPS.
    """
    orig_start = list(banner_manager._CATEGORIZED_BANNERS.get("start", []))
    orig_users = dict(banner_manager._USER_RECENT_BANNERS)
    try:
        banner_manager._USER_RECENT_BANNERS.clear()
        banner_manager._CATEGORIZED_BANNERS["start"] = ["b1.jpg", "b2.jpg", "b3.jpg"]

        # Simulate 6000 unique users
        for uid in range(1, 6001):
            banner_manager.get_banner_file(category="start", user_id=uid)

        assert len(banner_manager._USER_RECENT_BANNERS) <= 5000, \
            f"_USER_RECENT_BANNERS must be capped at 5000, got {len(banner_manager._USER_RECENT_BANNERS)}"
    finally:
        banner_manager._CATEGORIZED_BANNERS["start"] = orig_start
        banner_manager._USER_RECENT_BANNERS.clear()
        banner_manager._USER_RECENT_BANNERS.update(orig_users)


# ============================================================================
# 3. DELIVERY MANAGER REDTEAM AUDIT
# ============================================================================

def test_delivery_passive_slicing_and_no_starvation():
    """
    REDTEAM 3.1: Are passive slices correctly prioritized without starving passive recipients?
    VERIFY:
    - Bounded preemption (PASSIVE_MAX_PREEMPTIONS): yields 3 times, then enforces delivery on 4th.
    - Slicing correctly applies to both 'passive' and 'passive_slice' phases.
    """
    # 1. Anti-starvation preemption check
    queue = asyncio.Queue()
    queue.put_nowait({"delivery_phase": "full", "post_num": 1, "recipients": [101], "content": {}})

    msg_data = {
        "delivery_phase": "passive",
        "post_num": 99,
        "recipients": [201, 202],
        "content": {},
        "passive_preemptions": 0
    }
    task = delivery_manager.MessageDeliveryTask(
        worker_name="Worker-b", board_id="b", bot_instance=MagicMock(),
        queue=queue, msg_data=msg_data
    )

    # First 3 preemptions yield (return True)
    loop = asyncio.new_event_loop()
    try:
        assert loop.run_until_complete(task._handle_preemption()) is True
        assert msg_data["passive_preemptions"] == 1

        assert loop.run_until_complete(task._handle_preemption()) is True
        assert msg_data["passive_preemptions"] == 2

        assert loop.run_until_complete(task._handle_preemption()) is True
        assert msg_data["passive_preemptions"] == 3

        # 4th check: preemptions (3) >= PASSIVE_MAX_PREEMPTIONS (3) -> returns False (NO STARVATION!)
        assert loop.run_until_complete(task._handle_preemption()) is False
    finally:
        loop.close()

    # 2. Phase determination check for restored 'passive_slice'
    task.delivery_phase = "passive_slice"
    task.passive_slice_size = 10
    active_recipients = set(range(1, 26))  # 25 recipients

    to_send, for_later, phase, reason = task._determine_delivery_phases(active_recipients)
    assert len(to_send) == 10
    assert len(for_later) == 15
    assert phase == "passive_slice"


@pytest.mark.asyncio
async def test_delivery_edit_slow_recipient_timeout():
    """
    REDTEAM 3.2: Does edit_post_for_all_recipients handle slow / hung recipients gracefully?
    VERIFY: A hung recipient (sleeping 30s) hits the 8.0s timeout and is cancelled,
    allowing other recipients in the chunk to complete without deadlocking the delivery worker.
    """
    mock_bot = AsyncMock()

    # User 1 hangs indefinitely, User 2 finishes immediately
    async def fake_edit_text(*args, **kwargs):
        chat_id = kwargs.get("chat_id")
        if chat_id == 501:
            await asyncio.sleep(25.0)  # Hung connection!
        return MagicMock()

    mock_bot.edit_message_text = AsyncMock(side_effect=fake_edit_text)

    # Mock DB copies
    with patch("delivery_manager.get_post_copies", return_value=[(501, 1001), (502, 1002)]), \
         patch("delivery_manager.messages_storage", {77: {"content": {"type": "text", "text": "Hello"}, "board_id": "b"}}), \
         patch("delivery_manager.board_data", {"b": {"user_settings": {}}}):

        start = time.time()
        # Must complete within 12 seconds (timeout is 8.0s), NOT 25 seconds!
        await asyncio.wait_for(
            delivery_manager.edit_post_for_all_recipients(post_num=77, bot_instance=mock_bot),
            timeout=12.0
        )
        elapsed = time.time() - start
        assert elapsed < 12.0, f"Edit batch must complete within timeout, took {elapsed:.1f}s!"
