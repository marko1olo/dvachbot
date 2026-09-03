# -*- coding: utf-8 -*-
"""
test_classic_duel_adversarial.py — Empirical Adversarial Concurrency & Stress Suite for Classic Duels
===================================================================================================
Covers:
1. Concurrency races: Simultaneous accept vs cancel/decline races on _active_duels.
2. Rapid double-clicks / spam: Concurrent cb_duel_accept and cb_duel_decline invocations.
3. 100-user concurrency: 100 distinct candidate users competing to accept a single classic duel.
4. Watchdog timeout recovery: Expired duels cleaned up with zero financial leakage.
5. Escrow and balance safety: Insufficient balance on challenger/opponent, expired duel acceptance.
"""

import sys
import time
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shared_state
from shared_state import (
    _active_duels,
    _duel_cooldowns,
    _DUEL_TIMEOUT,
    make_duel_token,
    resolve_duel_token,
)
from common.bot_helpers import accept_duel_logic, decline_duel_logic, classic_duel_lock
import main
from main import (
    cb_duel_accept,
    cb_duel_decline,
    classic_duel_watchdog_step,
)
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    get_abu_fund_total,
)


from common.anon_identity import get_anon_id
import common.bot_helpers
common.bot_helpers.get_anon_id = get_anon_id


@pytest.fixture(autouse=True)
def clean_classic_duel_state():
    _active_duels.clear()
    _duel_cooldowns.clear()
    common.bot_helpers.get_anon_id = get_anon_id
    yield
    _active_duels.clear()
    _duel_cooldowns.clear()


def make_mock_message(user_id: int, chat_id: int = 100, msg_id: int = 200):
    msg = MagicMock()
    msg.from_user = MagicMock(id=user_id)
    msg.chat = MagicMock(id=chat_id)
    msg.message_id = msg_id
    msg.answer = AsyncMock()
    msg.answer_photo = AsyncMock()
    msg.bot = AsyncMock()
    msg.bot.send_message = AsyncMock()
    msg.bot.edit_message_text = AsyncMock()
    return msg


def make_mock_callback(user_id: int, data: str, chat_id: int = 100, msg_id: int = 200):
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.message = make_mock_message(user_id, chat_id, msg_id)
    cb.answer = AsyncMock()
    cb.bot = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_100_concurrent_accepts_distinct_users(isolated_test_db):
    """
    100 distinct users concurrently race to accept a single classic duel.
    Invariant: Exactly 1 duel is executed, 99 rejected; exact escrow debited.
    """
    db = isolated_test_db
    board_id = "b"
    challenger_id = 101
    stake = 1000

    # Fund challenger
    await add_user_global_balance(db, challenger_id, board_id, 100_000)

    # Fund 100 candidates
    candidate_ids = list(range(201, 301))
    for cid in candidate_ids:
        await add_user_global_balance(db, cid, board_id, 50_000)

    fund_before = await get_abu_fund_total(db)

    # Register open duel in _active_duels
    async with classic_duel_lock:
        _active_duels[challenger_id] = {
            "board_id": board_id,
            "amount": stake,
            "ts": time.time(),
            "msg_id": 555,
            "chat_id": 100,
            "broadcast_msgs": [],
        }

    # 100 concurrent accepts
    messages = [make_mock_message(cid) for cid in candidate_ids]
    tasks = [
        accept_duel_logic(messages[i], challenger_id, board_id, user_id=candidate_ids[i])
        for i in range(100)
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    # _active_duels must be popped
    async with classic_duel_lock:
        assert challenger_id not in _active_duels

    # Exactly 1 message received a duel outcome (photo or answer with victory)
    played_candidates = []
    rejected_candidates = []

    for i, cid in enumerate(candidate_ids):
        msg = messages[i]
        # Check if photo (duel poster) or text answered
        has_poster = msg.answer_photo.called
        answered_text = msg.answer.call_args[0][0] if msg.answer.called else ""
        if has_poster or "ДУЭЛЬ ЗАВЕРШЕНА" in answered_text:
            played_candidates.append(cid)
        else:
            rejected_candidates.append(cid)

    assert len(played_candidates) == 1, f"Expected 1 played, got {len(played_candidates)}"
    assert len(rejected_candidates) == 99

    accepted_user = played_candidates[0]

    # Verify balances
    rake = max(1, int(stake * 0.05))
    net_win = stake - rake

    ch_bal = await get_user_global_balance(db, challenger_id)
    op_bal = await get_user_global_balance(db, accepted_user)
    fund_after = await get_abu_fund_total(db)

    # Either challenger won or accepted_user won (accounting for 200 shekel first duel win achievement)
    ach_bonus = 200
    if ch_bal in (100_000 + net_win, 100_000 + net_win + ach_bonus):
        assert op_bal == 50_000 - stake
    elif op_bal in (50_000 + net_win, 50_000 + net_win + ach_bonus):
        assert ch_bal == 100_000 - stake
    else:
        pytest.fail(f"Unexpected balance distribution: ch={ch_bal}, op={op_bal}")

    assert fund_after == fund_before + rake

    # Non-participating candidates balances untouched
    for cid in candidate_ids:
        if cid != accepted_user:
            bal = await get_user_global_balance(db, cid)
            assert bal == 50_000


@pytest.mark.asyncio
async def test_concurrent_accept_vs_cancel_race(isolated_test_db):
    """
    Race condition test: Acceptor tries to accept at the EXACT same instant challenger cancels.
    Strict Invariant: Exactly one action succeeds (either duel completes OR is cancelled).
    Never an inconsistent state or dangling lock.
    """
    db = isolated_test_db
    board_id = "b"
    challenger_id = 401
    acceptor_id = 402
    stake = 2000

    await add_user_global_balance(db, challenger_id, board_id, 20_000)
    await add_user_global_balance(db, acceptor_id, board_id, 20_000)

    # Repeat race 10 times to stress concurrency windows
    for iteration in range(10):
        async with classic_duel_lock:
            _active_duels[challenger_id] = {
                "board_id": board_id,
                "amount": stake,
                "ts": time.time(),
                "msg_id": 700 + iteration,
                "chat_id": 100,
                "broadcast_msgs": [],
            }

        msg_accept = make_mock_message(acceptor_id)
        msg_cancel = make_mock_message(challenger_id)

        task_accept = asyncio.create_task(
            accept_duel_logic(msg_accept, challenger_id, board_id, user_id=acceptor_id)
        )
        task_cancel = asyncio.create_task(
            decline_duel_logic(msg_cancel, challenger_id, user_id=challenger_id)
        )

        await asyncio.gather(task_accept, task_cancel, return_exceptions=True)

        async with classic_duel_lock:
            assert challenger_id not in _active_duels

        # Verify exactly one outcome occurred
        accept_played = (
            msg_accept.answer_photo.called
            or (msg_accept.answer.called and "ДУЭЛЬ ЗАВЕРШЕНА" in msg_accept.answer.call_args[0][0])
        )
        cancel_succeeded = (
            msg_cancel.answer.called
            and "отменен создателем" in msg_cancel.answer.call_args[0][0]
        )

        assert accept_played ^ cancel_succeeded, "Either accept or cancel must succeed, never both or neither!"


@pytest.mark.asyncio
async def test_rapid_double_clicks_on_accept(isolated_test_db):
    """
    Spamming accept button concurrently (50 rapid calls via cb_duel_accept).
    Strict Invariant: Exactly 1 invocation proceeds, 49 rejected.
    """
    db = isolated_test_db
    board_id = "b"
    challenger_id = 501
    acceptor_id = 502
    stake = 1500

    await add_user_global_balance(db, challenger_id, board_id, 10_000)
    await add_user_global_balance(db, acceptor_id, board_id, 10_000)

    token = make_duel_token(challenger_id)
    async with classic_duel_lock:
        _active_duels[challenger_id] = {
            "board_id": board_id,
            "amount": stake,
            "ts": time.time(),
            "msg_id": 888,
            "chat_id": 100,
            "broadcast_msgs": [],
        }

    callbacks = [
        make_mock_callback(acceptor_id, f"duel_accept:{token}")
        for _ in range(50)
    ]
    tasks = [cb_duel_accept(cb, board_id) for cb in callbacks]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Duel must be resolved
    async with classic_duel_lock:
        assert challenger_id not in _active_duels

    # Total balance changes must reflect exactly 1 duel (not 50)
    rake = max(1, int(stake * 0.05))
    net_win = stake - rake

    ch_bal = await get_user_global_balance(db, challenger_id)
    op_bal = await get_user_global_balance(db, acceptor_id)

    total_wealth = ch_bal + op_bal
    # Initially 20,000. Exactly rake (75) is removed, plus optional 200 first win achievement
    assert total_wealth in (20_000 - rake, 20_000 - rake + 200)


@pytest.mark.asyncio
async def test_rapid_double_clicks_on_decline(isolated_test_db):
    """
    Spamming decline/cancel button concurrently (50 rapid calls via cb_duel_decline).
    Strict Invariant: Exactly 1 succeeds, 49 receive expired/already cancelled alert.
    """
    board_id = "b"
    challenger_id = 601
    token = make_duel_token(challenger_id)

    async with classic_duel_lock:
        _active_duels[challenger_id] = {
            "board_id": board_id,
            "amount": 1000,
            "ts": time.time(),
            "msg_id": 999,
            "chat_id": 100,
            "broadcast_msgs": [],
        }

    callbacks = [
        make_mock_callback(challenger_id, f"duel_cancel:{token}")
        for _ in range(50)
    ]
    tasks = [cb_duel_decline(cb, board_id) for cb in callbacks]
    await asyncio.gather(*tasks, return_exceptions=True)

    async with classic_duel_lock:
        assert challenger_id not in _active_duels

    alerts = [
        cb.answer.call_args[0][0]
        for cb in callbacks
        if cb.answer.called and len(cb.answer.call_args[0]) > 0
    ]
    # At least 49 were alerted that duel was already finished/cancelled
    alert_cancelled = [a for a in alerts if "уже был завершен" in a or "истёк" in a]
    assert len(alert_cancelled) >= 49


@pytest.mark.asyncio
async def test_watchdog_timeout_recovery_and_balance_safety(isolated_test_db):
    """
    Watchdog timeout test:
    - Duel older than 120s is cleaned up by classic_duel_watchdog_step.
    - Challenger balance is 100% intact (zero balance lost).
    - Message is edited to inform chat that challenge expired.
    """
    db = isolated_test_db
    board_id = "b"
    challenger_id = 701
    stake = 5000

    await add_user_global_balance(db, challenger_id, board_id, 10_000)

    async with classic_duel_lock:
        _active_duels[challenger_id] = {
            "board_id": board_id,
            "amount": stake,
            "ts": time.time() - 150.0,  # 150s ago (> 120s)
            "msg_id": 1111,
            "chat_id": 2222,
            "broadcast_msgs": [(2222, 1111)],
        }

    mock_bot = AsyncMock()
    mock_bot.edit_message_text = AsyncMock()

    await classic_duel_watchdog_step(mock_bot)

    async with classic_duel_lock:
        assert challenger_id not in _active_duels

    # Challenger balance unchanged
    bal = await get_user_global_balance(db, challenger_id)
    assert bal == 10_000

    # Message edited to reflect expiration
    mock_bot.edit_message_text.assert_called_once()
    edited_text = mock_bot.edit_message_text.call_args.kwargs.get("text") or mock_bot.edit_message_text.call_args[0][2]
    assert "ВЫЗОВ НА ДУЭЛЬ ИСТЕК" in edited_text


@pytest.mark.asyncio
async def test_accept_expired_duel_rejected(isolated_test_db):
    """
    Accepting a duel past its _DUEL_TIMEOUT is rejected and popped.
    """
    db = isolated_test_db
    board_id = "b"
    challenger_id = 801
    acceptor_id = 802
    stake = 1000

    await add_user_global_balance(db, challenger_id, board_id, 10_000)
    await add_user_global_balance(db, acceptor_id, board_id, 10_000)

    async with classic_duel_lock:
        _active_duels[challenger_id] = {
            "board_id": board_id,
            "amount": stake,
            "ts": time.time() - 200.0,
            "msg_id": 1212,
            "chat_id": 100,
            "broadcast_msgs": [],
        }

    msg = make_mock_message(acceptor_id)
    await accept_duel_logic(msg, challenger_id, board_id, user_id=acceptor_id)

    msg.answer.assert_called_with("⚔️ Эта дуэль уже истекла.")
    async with classic_duel_lock:
        assert challenger_id not in _active_duels

    b1 = await get_user_global_balance(db, challenger_id)
    b2 = await get_user_global_balance(db, acceptor_id)
    assert b1 == 10_000
    assert b2 == 10_000


@pytest.mark.asyncio
async def test_challenger_balance_drained_before_accept(isolated_test_db):
    """
    Challenger had funds when creating duel, but drained them before accept.
    Opponent acceptance should pop the duel and report challenger drain.
    """
    db = isolated_test_db
    board_id = "b"
    challenger_id = 901
    acceptor_id = 902
    stake = 2000

    # Challenger has only 500 left
    await add_user_global_balance(db, challenger_id, board_id, 500)
    await add_user_global_balance(db, acceptor_id, board_id, 10_000)

    async with classic_duel_lock:
        _active_duels[challenger_id] = {
            "board_id": board_id,
            "amount": stake,
            "ts": time.time(),
            "msg_id": 1313,
            "chat_id": 100,
            "broadcast_msgs": [],
        }

    msg = make_mock_message(acceptor_id)
    await accept_duel_logic(msg, challenger_id, board_id, user_id=acceptor_id)

    ans = msg.answer.call_args[0][0]
    assert "уже не потянет ставку" in ans

    async with classic_duel_lock:
        assert challenger_id not in _active_duels

    # Balances safe
    b1 = await get_user_global_balance(db, challenger_id)
    b2 = await get_user_global_balance(db, acceptor_id)
    assert b1 == 500
    assert b2 == 10_000


@pytest.mark.asyncio
async def test_opponent_insufficient_funds_leaves_duel_open(isolated_test_db):
    """
    Poor opponent tries to accept -> rejected.
    Duel remains in _active_duels so a wealthy player can accept it.
    """
    db = isolated_test_db
    board_id = "b"
    challenger_id = 1001
    poor_user = 1002
    rich_user = 1003
    stake = 3000

    await add_user_global_balance(db, challenger_id, board_id, 10_000)
    await add_user_global_balance(db, poor_user, board_id, 200)
    await add_user_global_balance(db, rich_user, board_id, 10_000)

    async with classic_duel_lock:
        _active_duels[challenger_id] = {
            "board_id": board_id,
            "amount": stake,
            "ts": time.time(),
            "msg_id": 1414,
            "chat_id": 100,
            "broadcast_msgs": [],
        }

    # Poor user attempts
    msg_poor = make_mock_message(poor_user)
    await accept_duel_logic(msg_poor, challenger_id, board_id, user_id=poor_user)

    ans = msg_poor.answer.call_args[0][0]
    assert "недостаточно шекелей" in ans

    # Duel is still open in _active_duels
    async with classic_duel_lock:
        assert challenger_id in _active_duels

    # Rich user attempts -> succeeds!
    msg_rich = make_mock_message(rich_user)
    await accept_duel_logic(msg_rich, challenger_id, board_id, user_id=rich_user)

    async with classic_duel_lock:
        assert challenger_id not in _active_duels

    # Verify money transferred between challenger and rich_user
    b_ch = await get_user_global_balance(db, challenger_id)
    b_rich = await get_user_global_balance(db, rich_user)
    b_poor = await get_user_global_balance(db, poor_user)

    assert b_poor == 200
    rake = max(1, int(stake * 0.05))
    assert (b_ch + b_rich) in (20_000 - rake, 20_000 - rake + 200)
