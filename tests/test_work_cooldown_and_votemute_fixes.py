# -*- coding: utf-8 -*-
"""
tests/test_work_cooldown_and_votemute_fixes.py — Regression tests for:
1. Work cooldown atomic reset via Flash Ultra energy drink across RAM and multi-board SQLite rows.
2. Votemute notification text and expiration lifecycle (no resurrected 'бочка с говном' or stale vote_id).
"""

import time
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from common.work_engine import (
    execute_job_action,
    reset_job_timer,
    clear_global_job_timer,
    _GLOBAL_JOB_TIMERS,
    WORK_VACANCIES
)
from common.bot_helpers import merge_user_active_items_rows, _get_user_active_items
import event_push_engine
import votemute_engine


@pytest.mark.asyncio
async def test_flash_ultra_atomic_reset_and_no_resurrection(isolated_test_db):
    """
    Tests that:
    1. Performing work sets cooldown in RAM and active_items.
    2. Drinking Flash Ultra resets cooldown atomically.
    3. Multi-board rows in Users table do not resurrect the cooldown upon reload.
    4. Work can be executed immediately after drinking Flash Ultra.
    """
    user_id = 777123
    board_id = "b"
    job_id = "bottles"
    db = isolated_test_db

    # Clean shared_state and job timers for test isolation
    shared_state.reset_user_work_cooldown(user_id)
    reset_job_timer(user_id)

    # 1. Setup multi-board user rows in DB (boards 'b' and 'po')
    now = int(time.time())
    stale_cooldown = now - 10  # recent work, cooldown is 180s, so ~170s remaining

    items_b = {
        "user_id": user_id,
        "work_shifts": 5,
        "work_cooldowns": {job_id: stale_cooldown}
    }
    items_po = {
        "user_id": user_id,
        "work_shifts": 5,
        "work_cooldowns": {job_id: stale_cooldown}
    }

    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('po', 'Политика')")
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?)",
        (user_id, "b", json.dumps(items_b))
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?)",
        (user_id, "po", json.dumps(items_po))
    )

    # Set RAM state
    shared_state.set_user_work_cooldown(user_id, job_id, stale_cooldown)
    _GLOBAL_JOB_TIMERS[(user_id, job_id)] = stale_cooldown

    # 2. Verify work is currently blocked by cooldown
    ok, reward, msg, drop = execute_job_action(job_id, items_b, user_id=user_id)
    assert ok is False
    assert "Кулдаун" in msg

    # 3. Simulate Flash Ultra consumption ("overtime")
    from economy_extension import cb_work_action
    mock_cb = AsyncMock()
    mock_cb.from_user.id = user_id
    mock_cb.data = "work_overtime"
    mock_cb.answer = AsyncMock()

    with patch("economy_extension.get_pool", return_value=db):
        await cb_work_action(mock_cb, board_id="b")

    # 4. Check that shared_state cooldown is 0
    u_cds = shared_state.get_user_work_cooldowns(user_id)
    assert u_cds.get(job_id, 0) == 0

    # 5. Check that _GLOBAL_JOB_TIMERS was cleared
    assert (user_id, job_id) not in _GLOBAL_JOB_TIMERS

    # 6. Check that BOTH boards in DB have work_cooldowns[job_id] == 0
    async with db.execute("SELECT board_id, active_items FROM Users WHERE user_id = ?", (user_id,)) as cur:
        rows = await cur.fetchall()
    assert len(rows) == 2
    for b_id, a_str in rows:
        d = json.loads(a_str)
        assert d.get("work_cooldowns", {}).get(job_id) == 0, f"Board {b_id} did not reset cooldown!"

    # 7. Reload active items across all boards via _get_user_active_items
    merged = await _get_user_active_items(db, user_id, board_id="b")
    assert merged.get("work_cooldowns", {}).get(job_id) == 0

    # 8. Verify work CAN be performed immediately without cooldown
    ok2, reward2, msg2, drop2 = execute_job_action(job_id, merged, user_id=user_id)
    assert ok2 is True, f"Work failed after Flash Ultra: {msg2}"
    assert reward2 > 0


@pytest.mark.asyncio
async def test_shared_state_set_user_work_cooldown_reset():
    """Verify set_user_work_cooldown(uid, jid, 0) and reset_user_work_cooldown work correctly."""
    uid = 999001
    jid = "courier"

    shared_state.set_user_work_cooldown(uid, jid, 1700000000)
    assert shared_state.get_user_work_cooldowns(uid)[jid] == 1700000000

    # Explicit reset to 0
    shared_state.set_user_work_cooldown(uid, jid, 0)
    assert shared_state.get_user_work_cooldowns(uid)[jid] == 0

    # Set again and test reset_user_work_cooldown
    shared_state.set_user_work_cooldown(uid, jid, 1700000000)
    shared_state.reset_user_work_cooldown(uid, jid)
    assert shared_state.get_user_work_cooldowns(uid)[jid] == 0

    # Test full clear
    shared_state.set_user_work_cooldown(uid, "job1", 100)
    shared_state.set_user_work_cooldown(uid, "job2", 200)
    shared_state.reset_user_work_cooldown(uid)
    assert len(shared_state.get_user_work_cooldowns(uid)) == 0


@pytest.mark.asyncio
async def test_votemute_push_notification_headline_and_text():
    """Verify event_push_engine.push_votemute_open sends new headline and no 'бочка с говном' text."""
    mock_bot = AsyncMock()

    with patch("event_push_engine.push_event_to_board", new_callable=AsyncMock) as mock_push:
        await event_push_engine.push_votemute_open(
            bot=mock_bot,
            board_id="b",
            post_num=123456,
            target_anon_id="A1B2C3",
            votes_count=1,
            votes_req=5,
            exclude_uid=101
        )

        assert mock_push.called
        call_kwargs = mock_push.call_args.kwargs
        assert call_kwargs["headline"] == "⚖️ ОТКРЫТО НАРОДНОЕ ГОЛОСОВАНИЕ!"
        assert "БОЧКА С ГОВНОМ" not in call_kwargs["headline"]

        full_body = " ".join(call_kwargs["body_lines"])
        assert "бочка" not in full_body.lower()
        assert "говн" not in full_body.lower()
        assert "123456" in full_body


@pytest.mark.asyncio
async def test_votemute_expired_session_lifecycle(isolated_test_db):
    """
    Verify that an expired votemute session:
    1. Is marked 'expired' upon expiration check.
    2. Starting a new vote on a new post creates a fresh vote_id and does not resurrect the old post or card.
    """
    db = isolated_test_db
    await votemute_engine.ensure_votemute_tables(db)

    target_id = 444001
    old_post = 1001
    new_post = 2002
    voter_id = 555001
    now = time.time()

    # 1. Insert an expired votemute session
    old_key = votemute_engine.generate_votemute_key(target_id, old_post)
    await db.execute(
        """INSERT INTO Votemutes (vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status, yes_votes, no_votes, required_votes, broadcast_msgs)
           VALUES (?, 'b', ?, ?, ?, ?, ?, 'active', 2, 0, 5, '[]')""",
        (old_key, target_id, old_post, 888, now - 1000, now - 400)
    )

    # 2. Starting or adding a vote on new_post for the same target
    ok, msg, current_votes, is_executed = await votemute_engine.start_or_add_vote(
        board_id="b",
        target_id=target_id,
        post_num=new_post,
        voter_id=voter_id,
        vote_type="yes",
        check_eligibility=False
    )

    assert ok is True
    assert current_votes == 1

    # 3. Verify old session is marked 'expired'
    async with db.execute("SELECT status FROM Votemutes WHERE vote_id = ?", (old_key,)) as cur:
        old_row = await cur.fetchone()
    assert old_row is not None
    assert old_row[0] == "expired"

    # 4. Verify new session has fresh vote_id for new_post
    new_key = votemute_engine.generate_votemute_key(target_id, new_post)
    async with db.execute("SELECT status, post_num, yes_votes FROM Votemutes WHERE vote_id = ?", (new_key,)) as cur:
        new_row = await cur.fetchone()
    assert new_row is not None
    assert new_row[0] == "active"
    assert new_row[1] == new_post
    assert new_row[2] == 1


@pytest.mark.asyncio
async def test_flash_ultra_picks_highest_cooldown_job(isolated_test_db):
    """Verify Flash Ultra selects the job with the longest remaining cooldown and resets it."""
    db = isolated_test_db
    user_id = 888222
    board_id = "b"

    shared_state.reset_user_work_cooldown(user_id)
    reset_job_timer(user_id)

    now = int(time.time())
    # bottles cd is 180s, courier cd is 600s
    # bottles done at now - 10 (rem: 170s)
    # courier done at now - 10 (rem: 590s)
    items = {
        "user_id": user_id,
        "work_shifts": 20,
        "work_cooldowns": {
            "bottles": now - 10,
            "courier": now - 10
        }
    }

    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?)",
        (user_id, board_id, json.dumps(items))
    )
    shared_state.set_user_work_cooldown(user_id, "bottles", now - 10)
    shared_state.set_user_work_cooldown(user_id, "courier", now - 10)
    _GLOBAL_JOB_TIMERS[(user_id, "bottles")] = now - 10
    _GLOBAL_JOB_TIMERS[(user_id, "courier")] = now - 10

    from economy_extension import cb_work_action
    mock_cb = AsyncMock()
    mock_cb.from_user.id = user_id
    mock_cb.data = "work_overtime"
    mock_cb.answer = AsyncMock()

    with patch("economy_extension.get_pool", return_value=db):
        await cb_work_action(mock_cb, board_id=board_id)

    # courier had 590s left vs 170s, so courier must be reset to 0, bottles unchanged
    u_cds = shared_state.get_user_work_cooldowns(user_id)
    assert u_cds.get("courier", 0) == 0
    assert (user_id, "courier") not in _GLOBAL_JOB_TIMERS

    # verify toast mentioned courier
    assert mock_cb.answer.called
    toast = mock_cb.answer.call_args[0][0]
    assert "Курьер" in toast or "courier" in toast.lower()


@pytest.mark.asyncio
async def test_flash_ultra_no_active_cooldowns_no_waste(isolated_test_db):
    """Verify Flash Ultra does not waste a can when all jobs are ready/free."""
    db = isolated_test_db
    user_id = 888333
    board_id = "b"

    shared_state.reset_user_work_cooldown(user_id)
    reset_job_timer(user_id)

    items = {
        "user_id": user_id,
        "work_shifts": 10,
        "work_cooldowns": {}
    }
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?)",
        (user_id, board_id, json.dumps(items))
    )

    from economy_extension import cb_work_action
    mock_cb = AsyncMock()
    mock_cb.from_user.id = user_id
    mock_cb.data = "work_overtime"
    mock_cb.answer = AsyncMock()

    with patch("economy_extension.get_pool", return_value=db):
        await cb_work_action(mock_cb, board_id=board_id)

    toast = mock_cb.answer.call_args[0][0]
    assert "нет карьерных смен на кулдауне" in toast

    # Check that overtime_uses_today was NOT incremented
    loaded = await _get_user_active_items(db, user_id, board_id)
    assert loaded.get("overtime_uses_today", 0) == 0
