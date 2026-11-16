# -*- coding: utf-8 -*-
"""
tests/test_inquisitor_votemute_banners.py
=========================================
REDTEAM INQUISITOR #4: The Votemute & Banner Chaos Torture Suite for C:\\dev\\dvachbot.
Adversarial stress-testing of votemute_engine.py and banner_manager.py under extreme concurrency,
hostile edge cases, CDN failures, Windows file lock contention, and expired state bombardment.
"""

import asyncio
import json
import os
import random
import time
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, FSInputFile

import banner_manager
import votemute_engine
from common.anon_identity import get_anon_id


async def seed_eligible_voter(db, voter_id: int, board_id: str = "b"):
    """Seeds voter with 2 recent non-shadow posts so voter is eligible for quorum (>1 post in 48h)."""
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
# SCENARIO 1: Chaos voting under extreme concurrency (50 simultaneous votes + rapid alternations)
# ============================================================================

@pytest.mark.asyncio
async def test_chaos_voting_concurrency_and_alternations(isolated_test_db):
    """
    SCENARIO 1: Chaos voting under extreme concurrency.
    Simulate 50 simultaneous votes for the same post, including rapid alternations of 'yes' and 'no' buttons.
    VERIFY:
    - Atomic tallying (no votes lost or double-counted, exact sync between Votemutes and VotemuteVotes).
    - Exactly 1 execution of the unbribable iron mute if threshold (5) is reached.
    - Zero deadlock under votemute_lock (LazyLock) within bounded time limit.
    """
    db = isolated_test_db
    target_id = 99910
    post_num = 88810
    board_id = "b"

    await db.execute("INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')", (target_id, board_id))
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)",
        (post_num, board_id, target_id, time.time()),
    )
    await db.commit()

    votemute_engine.active_votemutes.clear()

    # Seed 50 distinct voters
    voter_ids = [20000 + i for i in range(50)]
    for v in voter_ids:
        await seed_eligible_voter(db, v, board_id=board_id)

    # Phase 1: Rapid button alternations before quorum is reached
    # 4 voters rapidly switch back and forth: yes -> no -> yes -> no
    alternator_voters = voter_ids[:4]
    async def alternate_voter(vid: int):
        # 4 toggles each: yes -> no -> yes -> no
        for v_type in ["yes", "no", "yes", "no"]:
            await votemute_engine.start_or_add_vote(
                board_id=board_id,
                target_id=target_id,
                post_num=post_num,
                voter_id=vid,
                vote_type=v_type,
            )
            await asyncio.sleep(0.001)

    # Run rapid alternations under concurrency
    await asyncio.wait_for(
        asyncio.gather(*[alternate_voter(v) for v in alternator_voters]),
        timeout=10.0,
    )

    # Verify atomic tallying after alternations:
    # All 4 alternators ended on "no", so yes_votes == 0, no_votes == 4
    vm_key = votemute_engine.generate_votemute_key(target_id, post_num)
    async with db.execute("SELECT yes_votes, no_votes, status FROM Votemutes WHERE vote_id = ?", (vm_key,)) as cur:
        row = await cur.fetchone()
        assert row is not None, "Votemutes row must exist"
        assert row[0] == 0, f"Expected yes_votes=0, got {row[0]}"
        assert row[1] == 4, f"Expected no_votes=4, got {row[1]}"
        assert row[2] == "active", "Session must remain active"

    # Verify VotemuteVotes table consistency: exactly 4 rows, all 'no'
    async with db.execute("SELECT vote_type, COUNT(*) FROM VotemuteVotes WHERE vote_id = ? GROUP BY vote_type", (vm_key,)) as cur:
        rows = await cur.fetchall()
        tally_map = dict(rows)
        assert tally_map.get("no") == 4
        assert tally_map.get("yes") is None

    # Phase 2: Extreme burst: remaining 46 voters + 4 alternators all switch/vote "yes" at the exact same millisecond
    iron_mute_mock = AsyncMock()
    with patch("votemute_engine._apply_unbribable_iron_mute", iron_mute_mock):
        results = await asyncio.wait_for(
            asyncio.gather(*[
                votemute_engine.start_or_add_vote(
                    board_id=board_id,
                    target_id=target_id,
                    post_num=post_num,
                    voter_id=vid,
                    vote_type="yes",
                )
                for vid in voter_ids  # all 50 voters simultaneously!
            ]),
            timeout=10.0,
        )

    # Exactly 1 voter crosses threshold 5 and triggers the verdict!
    executed_results = [r for r in results if r[0] is True and r[3] is True]
    assert len(executed_results) == 1, (
        f"Exactly 1 caller must trigger execution! Found {len(executed_results)}"
    )

    # Exactly 1 call to _apply_unbribable_iron_mute
    assert iron_mute_mock.call_count == 1, (
        f"Iron mute must be applied EXACTLY ONCE! Call count: {iron_mute_mock.call_count}"
    )

    # Verify callers after quorum was reached received clean verdict notification
    late_callers = [r for r in results if r[0] is False and r[3] is True]
    assert len(late_callers) > 0, "Late callers must receive already executed notification"
    for lr in late_callers:
        assert "уже вынесен" in lr[1]

    # Verify DB status is 'executed'
    async with db.execute("SELECT status, yes_votes FROM Votemutes WHERE vote_id = ?", (vm_key,)) as cur:
        final_row = await cur.fetchone()
        assert final_row[0] == "executed"
        assert final_row[1] == 5


# ============================================================================
# SCENARIO 2: Expired votemute bombardment (20 concurrent button clicks)
# ============================================================================

@pytest.mark.asyncio
async def test_expired_votemute_bombardment(isolated_test_db):
    """
    SCENARIO 2: Expired votemute bombardment.
    Simulate 20 users clicking inline buttons on a votemute card that expired 1 second ago.
    VERIFY:
    - All callers receive the clean alert without any unhandled exceptions or hung tasks.
    - Zero deadlocks under votemute_lock (LazyLock).
    - Status in DB is updated to 'expired'.
    """
    db = isolated_test_db
    target_id = 99920
    post_num = 88820
    board_id = "b"

    await db.execute("INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')", (target_id, board_id))
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)",
        (post_num, board_id, target_id, time.time() - 700),
    )

    # Seed 20 voters
    voter_ids = [21000 + i for i in range(20)]
    for v in voter_ids:
        await seed_eligible_voter(db, v, board_id=board_id)

    # Insert a session that expired 1 second ago (created 601s ago, window is 600s)
    now = time.time()
    vm_key = votemute_engine.generate_votemute_key(target_id, post_num)
    await db.execute(
        """INSERT INTO Votemutes (vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status, yes_votes, no_votes, required_votes, broadcast_msgs)
           VALUES (?, ?, ?, ?, 21000, ?, ?, 'active', 2, 0, 5, '[]')""",
        (vm_key, board_id, target_id, post_num, now - 601, now - 1),
    )
    await db.commit()

    votemute_engine.active_votemutes.clear()
    token = votemute_engine.get_votemute_callback_token(target_id, post_num)

    # Build 20 callback queries
    callbacks = []
    for vid in voter_ids:
        cb = AsyncMock()
        cb.data = f"vm_vote:yes:{token}"
        cb.from_user = MagicMock(id=vid)
        mock_msg = AsyncMock()
        mock_msg.chat = MagicMock(id=vid)
        mock_msg.message_id = 1000 + vid
        mock_msg.caption = "Old Card"
        mock_msg.photo = [MagicMock()]
        mock_msg.edit_caption = AsyncMock()
        mock_msg.edit_text = AsyncMock()
        mock_msg.edit_reply_markup = AsyncMock()
        cb.message = mock_msg
        cb.bot = AsyncMock()
        cb.answer = AsyncMock()
        callbacks.append(cb)

    # Bombard with 20 simultaneous clicks
    await asyncio.wait_for(
        asyncio.gather(*[
            votemute_engine.callback_votemute_vote(cb, board_id=board_id)
            for cb in callbacks
        ]),
        timeout=5.0,
    )

    # Verify all 20 callers received clean answers containing 'истек'
    for i, cb in enumerate(callbacks):
        assert cb.answer.called, f"Callback {i} was never answered!"
        answer_text = str(cb.answer.call_args[0][0]).lower()
        assert "истек" in answer_text, f"Expected 'истек' in alert, got: {answer_text}"

    # Verify DB status is 'expired'
    async with db.execute("SELECT status FROM Votemutes WHERE vote_id = ?", (vm_key,)) as cur:
        row = await cur.fetchone()
        assert row[0] == "expired"


# ============================================================================
# SCENARIO 3: Banner cache corruption & concurrent disk write (30 calls)
# ============================================================================

def test_banner_cache_concurrent_disk_write_no_corruption(tmp_path):
    """
    SCENARIO 3: Banner cache corruption & concurrent disk write.
    Simulate 30 concurrent calls to save_cache(force=True) across multiple threads/tasks.
    VERIFY:
    - Windows file locking ([WinError 32] / [WinError 5]) NEVER occurs.
    - banners_cache.json remains 100% valid JSON with zero corruption.
    - Bounded execution under thread contention.
    """
    test_cache_file = tmp_path / "test_banners_cache.json"

    with patch.object(banner_manager, "CACHE_FILE", test_cache_file):
        # Seed cache with 150 items
        for i in range(150):
            banner_manager._BANNER_CACHE[f"bot_{i % 3}:banner_{i}.jpg"] = f"AgACAgIAAxkBAAI{i}test"

        errors = []
        successes = []

        def worker(worker_id: int):
            try:
                # Concurrent mutations while saving
                banner_manager._BANNER_CACHE[f"bot_worker:worker_{worker_id}.jpg"] = f"fid_worker_{worker_id}"
                ok = banner_manager.save_cache(force=True)
                if ok:
                    successes.append(worker_id)
                else:
                    errors.append(f"Worker {worker_id}: save_cache returned False")
            except Exception as e:
                errors.append(f"Worker {worker_id}: {type(e).__name__}: {e}")

        # Launch 30 concurrent threads
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Zero errors allowed!
        assert len(errors) == 0, f"Encountered file lock errors during concurrent writes: {errors}"
        assert len(successes) == 30, f"Expected 30 successes, got {len(successes)}"

        # Validate file integrity: must be valid JSON
        assert test_cache_file.exists(), "Cache file must exist on disk"
        with open(test_cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert isinstance(data, dict), "Cache data must be a JSON object"
        assert len(data) >= 150, f"Expected at least 150 entries, got {len(data)}"
        for w in range(30):
            assert f"bot_worker:worker_{w}.jpg" in data, f"Worker {w} key missing from disk cache!"


# ============================================================================
# SCENARIO 4: Telegram CDN failure cascade
# ============================================================================

@pytest.mark.asyncio
async def test_telegram_cdn_failure_cascade_recovery_and_fallback(tmp_path):
    """
    SCENARIO 4: Telegram CDN failure cascade.
    Simulate Telegram systematically rejecting cached file_ids with BadRequest("wrong file identifier").
    VERIFY:
    Part A: Cached bad file_id is evicted, local file is re-read and re-uploaded cleanly.
    Part B: When local file is missing, fallback text is delivered without crashing.
    Part C: broadcast_banner_to_users delivers fallback to all recipients without dropping anyone.
    """
    test_banners_dir = tmp_path / "banners"
    test_banners_dir.mkdir(parents=True, exist_ok=True)
    test_cache_file = tmp_path / "banners_cache.json"

    # Create dummy local banner file
    local_banner = test_banners_dir / "sample_test_banner.jpg"
    local_banner.write_bytes(b"DUMMY_JPEG_HEADER_FOR_TESTING_1234567890")

    with patch.object(banner_manager, "BANNERS_DIR", test_banners_dir), \
         patch.object(banner_manager, "CACHE_FILE", test_cache_file):

        banner_manager._BANNER_CACHE.clear()
        banner_manager._CACHE_BY_FILENAME.clear()

        # PART A: Bad cached file_id, local file EXISTS
        bad_fid = "bad_cached_remote_id_invalid"
        bot_id = 998877
        banner_fname = "sample_test_banner.jpg"

        banner_manager._BANNER_CACHE[f"{bot_id}:{banner_fname}"] = bad_fid
        banner_manager._CACHE_BY_FILENAME[banner_fname] = bad_fid

        mock_bot = AsyncMock()
        mock_bot.id = bot_id

        # First send_photo call raises BadRequest("wrong file identifier")
        # Second send_photo call (local FSInputFile) succeeds
        good_sent_msg = AsyncMock(spec=Message)
        good_photo_obj = MagicMock(file_id="fresh_uploaded_cdn_id_999")
        good_sent_msg.photo = [good_photo_obj]
        good_sent_msg.video = None
        good_sent_msg.animation = None
        good_sent_msg.message_id = 55501

        call_count = 0
        async def fake_send_photo(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Reject bad cached ID
                raise TelegramBadRequest(method=None, message="Bad Request: wrong remote file identifier specified")
            return good_sent_msg

        mock_bot.send_photo = fake_send_photo

        result_msg = await banner_manager.send_banner_message(
            bot=mock_bot,
            chat_id=12345,
            caption="Test Banner Caption",
            banner_name=banner_fname,
        )

        assert result_msg is good_sent_msg
        assert call_count == 2, "Must retry with local file upload"
        # Verify bad ID was evicted and fresh ID was saved
        assert banner_manager._BANNER_CACHE.get(f"{bot_id}:{banner_fname}") == "fresh_uploaded_cdn_id_999"

        # PART B: Bad cached file_id, local file is MISSING (Total CDN + Disk Failure)
        banner_manager._BANNER_CACHE.clear()
        missing_fname = "nonexistent_banner_404.jpg"
        banner_manager._BANNER_CACHE[f"{bot_id}:{missing_fname}"] = "stale_broken_id"

        mock_bot_b = AsyncMock()
        mock_bot_b.id = bot_id
        mock_bot_b.send_photo.side_effect = TelegramBadRequest(method=None, message="Bad Request: wrong file identifier")

        text_fallback_msg = AsyncMock(spec=Message)
        text_fallback_msg.message_id = 55502
        mock_bot_b.send_message.return_value = text_fallback_msg

        result_b = await banner_manager.send_banner_message(
            bot=mock_bot_b,
            chat_id=12346,
            caption="Fallback Caption",
            banner_name=missing_fname,
        )

        assert result_b is text_fallback_msg, "Must cleanly deliver fallback text message"
        assert f"{bot_id}:{missing_fname}" not in banner_manager._BANNER_CACHE, "Bad ID must be evicted from cache"

        # PART C: High-concurrency broadcast under full CDN rejection
        recipients = [30001, 30002, 30003, 30004, 30005, 30006, 30007, 30008, 30009, 30010]
        banner_manager._BANNER_CACHE[f"{bot_id}:{missing_fname}"] = "stale_broken_broadcast_id"

        mock_bot_c = AsyncMock()
        mock_bot_c.id = bot_id
        mock_bot_c.send_photo.side_effect = TelegramBadRequest(method=None, message="Bad Request: wrong file identifier")

        sent_mids = []
        async def fake_send_msg(chat_id, text, **kwargs):
            m = AsyncMock(spec=Message)
            m.message_id = 60000 + chat_id
            sent_mids.append((chat_id, m.message_id))
            return m

        mock_bot_c.send_message = fake_send_msg

        delivered = await banner_manager.broadcast_banner_to_users(
            bot=mock_bot_c,
            user_ids=recipients,
            exclude_uid=0,
            caption="Mass Broadcast Fallback",
            banner_name=missing_fname,
        )

        # All 10 recipients must receive the fallback message without any drops
        assert len(delivered) == 10, f"Expected 10 delivered messages, got {len(delivered)}"
        delivered_uids = {uid for uid, mid in delivered}
        assert delivered_uids == set(recipients), "Zero recipients must be dropped during CDN cascade failure!"
