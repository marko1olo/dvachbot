# -*- coding: utf-8 -*-
"""
tests/test_work_action_concurrency.py
Unit tests for concurrent work engine calls and db_transaction idempotency.
Specifically validates:
1. Treez scenario: cb_work_action('work_bottles') concurrent calls without
   "sqlite3.OperationalError: cannot commit - no transaction is active" or
   "RuntimeError: Database transaction collision: connection already in transaction".
2. db_transaction idempotency when COMMIT was executed prior to block exit.
3. Concurrent cb_work_claim_quests execution without transaction collisions.
4. Atomicity of user balance and active_items updates under concurrent load.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from common.db_pool import db_transaction, get_pool
from common.database import get_user_global_balance
from economy_extension import cb_work_action, cb_work_claim_quests
from shared_state import set_user_work_cooldown, get_user_work_cooldowns


def _create_mock_callback(user_id: int, data: str) -> MagicMock:
    cb = MagicMock()
    cb.id = f"cb_{user_id}_{data}_{time.time()}"
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.photo = None
    cb.message.edit_caption = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_db_transaction_handles_premature_commit_idempotently(isolated_test_db):
    """
    Directly tests that if an inner call issues COMMIT inside db_transaction,
    the __aexit__ does NOT raise RuntimeError, but logs warning and breaks cleanly.
    """
    db = isolated_test_db
    user_id = 999111
    board_id = "b"

    # Insert test user
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 100.0, '{}')",
        (user_id, board_id)
    )

    # Simulate inner premature commit inside db_transaction
    async with db_transaction(db):
        await db.execute("UPDATE Users SET balance = 250.0 WHERE user_id = ?", (user_id,))
        # Premature commit simulates old buggy code or external commit
        await db.commit()

    # Verify transaction committed and balance is updated
    bal = await get_user_global_balance(db, user_id)
    assert bal == 250.0


@pytest.mark.asyncio
async def test_cb_work_bottles_single_invocation(isolated_test_db):
    """
    Verifies that calling cb_work_action for 'work_bottles' succeeds completely,
    persisting balance, active_items, and answering the callback with reward message.
    """
    db = isolated_test_db
    user_id = 777001
    board_id = "b"

    # Setup user
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('b', 'Бред')")
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 0.0, '{}')",
        (user_id, board_id)
    )
    # Clear shared cooldown
    set_user_work_cooldown(user_id, "last_bottles", 0)

    cb = _create_mock_callback(user_id, "work_bottles")

    with patch("main.get_pool", return_value=db), \
         patch("economy_extension.get_pool", return_value=db):
        await cb_work_action(cb, board_id=board_id)

    assert cb.answer.called
    ans_text = cb.answer.call_args[0][0]
    assert "стеклотар" in ans_text or "залутал" in ans_text

    # Verify balance was credited in DB
    bal = await get_user_global_balance(db, user_id)
    assert bal >= 150, f"Expected balance >= 150, got {bal}"

    # Verify active_items has last_bottles timestamp
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as cur:
        row = await cur.fetchone()
        assert row is not None
        items = json.loads(row[0])
        assert items.get("last_bottles", 0) > 0


@pytest.mark.asyncio
async def test_cb_work_bottles_concurrent_calls_no_collision(isolated_test_db):
    """
    Simulates concurrent clicks on 'work_bottles' by the same user (e.g. Treez rapid double/triple tap).
    Must:
    1. Not raise any RuntimeError or OperationalError.
    2. Exactly 1 request succeeds to collect bottles; subsequent concurrent requests hit cooldown.
    3. Final balance reflects exactly 1 payout.
    """
    db = isolated_test_db
    user_id = 777002
    board_id = "b"

    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('b', 'Бред')")
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 0.0, '{}')",
        (user_id, board_id)
    )
    set_user_work_cooldown(user_id, "last_bottles", 0)

    cbs = [_create_mock_callback(user_id, "work_bottles") for _ in range(5)]

    with patch("main.get_pool", return_value=db), \
         patch("economy_extension.get_pool", return_value=db):
        # Run 5 concurrent calls
        tasks = [cb_work_action(cb, board_id=board_id) for cb in cbs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Ensure no exceptions were raised
    for idx, res in enumerate(results):
        assert not isinstance(res, Exception), f"Task {idx} raised an exception: {res}"

    # Check answers
    success_count = 0
    cooldown_count = 0
    for cb in cbs:
        assert cb.answer.called
        text = cb.answer.call_args[0][0]
        if "стеклотар" in text or "залутал" in text:
            success_count += 1
        elif "закрыты на переучет" in text:
            cooldown_count += 1

    assert success_count == 1, f"Expected exactly 1 success, got {success_count}"
    assert cooldown_count == 4, f"Expected 4 cooldown rejections, got {cooldown_count}"

    # Balance must be credited only once
    bal = await get_user_global_balance(db, user_id)
    assert 150 <= bal <= 750, f"Balance {bal} outside single reward range"


@pytest.mark.asyncio
async def test_cb_work_bottles_multiuser_concurrent_calls(isolated_test_db):
    """
    Simulates multiple different users (e.g. Treez and others) performing work_bottles concurrently.
    All distinct users must succeed without any db transaction collision.
    """
    db = isolated_test_db
    board_id = "b"
    users = [888101, 888102, 888103, 888104]

    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('b', 'Бред')")
    for u in users:
        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 0.0, '{}')",
            (u, board_id)
        )
        set_user_work_cooldown(u, "last_bottles", 0)

    cbs = [_create_mock_callback(u, "work_bottles") for u in users]

    with patch("main.get_pool", return_value=db), \
         patch("economy_extension.get_pool", return_value=db):
        tasks = [cb_work_action(cb, board_id=board_id) for cb in cbs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for idx, res in enumerate(results):
        assert not isinstance(res, Exception), f"User {users[idx]} failed with: {res}"

    for u, cb in zip(users, cbs):
        assert cb.answer.called
        text = cb.answer.call_args[0][0]
        assert "стеклотар" in text or "залутал" in text
        bal = await get_user_global_balance(db, u)
        assert bal >= 150


@pytest.mark.asyncio
async def test_cb_work_claim_quests_concurrency(isolated_test_db):
    """
    Simulates concurrent requests to claim daily quests rewards (cb_work_claim_quests).
    Verifies that:
    1. No db collision occurs.
    2. Exactly 1 claim succeeds and receives the 7500 reward.
    3. Concurrent claims receive 'уже забрал премию' notification.
    """
    db = isolated_test_db
    user_id = 777005
    board_id = "b"

    # Setup user with completed daily quests
    now = int(time.time())
    from common.daily_quests_engine import get_or_create_daily_quests
    items = {}
    dq = get_or_create_daily_quests(items, now=now)
    for q in dq["quests"]:
        q["progress"] = q["target"]

    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('b', 'Бред')")
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 0.0, ?)",
        (user_id, board_id, json.dumps(items))
    )

    cbs = [_create_mock_callback(user_id, "work_claim_quests") for _ in range(4)]

    with patch("main.get_pool", return_value=db), \
         patch("economy_extension.get_pool", return_value=db):
        tasks = [cb_work_claim_quests(cb, board_id=board_id) for cb in cbs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for idx, res in enumerate(results):
        assert not isinstance(res, Exception), f"Claim task {idx} raised: {res}"

    success_claims = 0
    already_claimed = 0
    for cb in cbs:
        assert cb.answer.called
        text = cb.answer.call_args[0][0]
        if "успешно получена" in text:
            success_claims += 1
        elif "уже забрал" in text:
            already_claimed += 1

    assert success_claims == 1, f"Expected 1 claim success, got {success_claims}"
    assert already_claimed == 3, f"Expected 3 rejected claims, got {already_claimed}"

    # Balance must be exactly 7500
    bal = await get_user_global_balance(db, user_id)
    assert bal == 7500.0, f"Expected balance 7500.0, got {bal}"
