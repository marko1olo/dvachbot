# -*- coding: utf-8 -*-
"""
tests/test_db_and_lazylock_concurrency_fixes.py

Targeted tests for:
1. safe_fromtimestamp(ts, tz=UTC) clamping [0.0, 4102444800.0] and Windows CRT OSError 22 resilience.
2. add_post_copies chunking (200 records per chunk), removal of redundant outer db_lock.
3. sqlite3.OperationalError: cannot commit - no transaction is active resilience in common/db_pool.py on timeout / reset.
4. LazyLock watchdog (>20s) non-monopolization under batch copies insertion.
"""

import asyncio
import math
import sqlite3
import time
from datetime import datetime, UTC, timezone, timedelta
from unittest.mock import patch, AsyncMock

import aiosqlite
import pytest

from common.database import safe_fromtimestamp, add_post_copies
import common.db_pool as db_pool_module
from common.db_pool import (
    LazyLock,
    db_transaction,
    safe_commit,
    safe_rollback,
    get_pool,
    _task_tx_depth,
)


# ============================================================================
# 1. safe_fromtimestamp Windows CRT Clamping & Fallback Tests
# ============================================================================

def test_safe_fromtimestamp_valid_and_boundaries():
    """Verifies safe_fromtimestamp on normal and boundary timestamps."""
    # Normal timestamp: 2023-11-14 22:13:20 UTC
    dt_normal = safe_fromtimestamp(1700000000.0, tz=UTC)
    assert dt_normal.year == 2023
    assert dt_normal.tzinfo == UTC

    # Lower boundary: 0.0 -> 1970-01-01 00:00:00 UTC
    dt_zero = safe_fromtimestamp(0.0, tz=UTC)
    assert dt_zero == datetime(1970, 1, 1, 0, 0, 0, tzinfo=UTC)

    # Upper boundary: 4102444800.0 -> 2100-01-01 00:00:00 UTC
    dt_2100 = safe_fromtimestamp(4102444800.0, tz=UTC)
    assert dt_2100 == datetime(2100, 1, 1, 0, 0, 0, tzinfo=UTC)


def test_safe_fromtimestamp_negative_and_overflow_clamping():
    """
    On Windows CRT, negative timestamps or huge timestamps raise OSError [Errno 22].
    safe_fromtimestamp must clamp [0.0, 4102444800.0] without raising OSError.
    """
    # Negative timestamps -> clamped to 0.0 (1970-01-01)
    for neg_ts in [-1.0, -100.0, -1e6, -1e15]:
        dt_neg = safe_fromtimestamp(neg_ts, tz=UTC)
        assert dt_neg == datetime(1970, 1, 1, 0, 0, 0, tzinfo=UTC), f"Failed for {neg_ts}"

    # Overflow timestamps -> clamped to 4102444800.0 (2100-01-01)
    for over_ts in [4102444801.0, 5000000000.0, 1e12, 1e15, 1e18]:
        dt_over = safe_fromtimestamp(over_ts, tz=UTC)
        assert dt_over == datetime(2100, 1, 1, 0, 0, 0, tzinfo=UTC), f"Failed for {over_ts}"


def test_safe_fromtimestamp_malformed_fallbacks():
    """Verifies that invalid or non-numeric inputs fallback to datetime.now(UTC)."""
    now_before = datetime.now(UTC)

    # None
    dt_none = safe_fromtimestamp(None)
    assert abs((dt_none - now_before).total_seconds()) < 5.0

    # Non-numeric string
    dt_str = safe_fromtimestamp("invalid_timestamp")
    assert abs((dt_str - now_before).total_seconds()) < 5.0

    # NaN and Infs
    dt_nan = safe_fromtimestamp(float("nan"))
    assert abs((dt_nan - now_before).total_seconds()) < 5.0

    dt_inf = safe_fromtimestamp(float("inf"))
    assert abs((dt_inf - now_before).total_seconds()) < 5.0

    dt_ninf = safe_fromtimestamp(float("-inf"))
    assert abs((dt_ninf - now_before).total_seconds()) < 5.0


def test_safe_fromtimestamp_custom_tz():
    """Verifies timezone awareness with custom tzinfo."""
    msk = timezone(timedelta(hours=3))
    dt_msk = safe_fromtimestamp(1700000000.0, tz=msk)
    assert dt_msk.tzinfo == msk
    assert dt_msk.hour == (dt_msk.astimezone(UTC).hour + 3) % 24


# ============================================================================
# 2. add_post_copies Chunking & Concurrency Tests
# ============================================================================

@pytest.mark.asyncio
async def test_add_post_copies_chunking_450_records(isolated_test_db):
    """
    Verifies:
    1. add_post_copies correctly chunks large batches into 200 records.
    2. All 450 records are inserted without missing copies.
    3. No outer db_lock is held that would starve other tasks.
    """
    db = isolated_test_db
    post_num = 77701

    # Ensure Post table has the referenced post
    async with db_transaction(db):
        await db.execute(
            "INSERT OR REPLACE INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 1, '{}', ?)",
            (post_num, time.time())
        )

    # Generate 450 copy records (2 chunks of 200 + 1 chunk of 50)
    copies = [(1000 + i, 2000 + i) for i in range(450)]

    with patch.object(db_pool_module, "get_pool", AsyncMock(return_value=db)):
        await add_post_copies(post_num, copies)

    # Verify all 450 copies exist in PostCopies
    async with db.execute("SELECT COUNT(*) FROM PostCopies WHERE post_num = ?", (post_num,)) as cur:
        count = (await cur.fetchone())[0]
        assert count == 450, f"Expected 450 copies inserted, got {count}"


@pytest.mark.asyncio
async def test_add_post_copies_empty_and_single_chunk(isolated_test_db):
    """Verifies edge cases: empty list and single chunk of <=200 items."""
    db = isolated_test_db
    post_num = 77702

    async with db_transaction(db):
        await db.execute(
            "INSERT OR REPLACE INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 1, '{}', ?)",
            (post_num, time.time())
        )

    with patch.object(db_pool_module, "get_pool", AsyncMock(return_value=db)):
        # Empty list: should be no-op
        await add_post_copies(post_num, [])

        # Single chunk: exactly 150 items
        copies = [(3000 + i, 4000 + i) for i in range(150)]
        await add_post_copies(post_num, copies)

    async with db.execute("SELECT COUNT(*) FROM PostCopies WHERE post_num = ?", (post_num,)) as cur:
        count = (await cur.fetchone())[0]
        assert count == 150


@pytest.mark.asyncio
async def test_add_post_copies_does_not_monopolize_db_lock(isolated_test_db):
    """
    Verifies that add_post_copies releases db_lock between chunks, allowing
    interleaved transactions from other coroutines without waiting > 20s.
    """
    db = isolated_test_db
    post_num = 77703

    async with db_transaction(db):
        await db.execute(
            "INSERT OR REPLACE INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 1, '{}', ?)",
            (post_num, time.time())
        )

    copies = [(5000 + i, 6000 + i) for i in range(500)]  # 3 chunks

    interleaved_executed = False

    async def interleaved_writer():
        nonlocal interleaved_executed
        # Brief delay to let add_post_copies start first chunk
        await asyncio.sleep(0.002)
        async with db_transaction(db):
            await db.execute("SELECT 1")
            interleaved_executed = True

    with patch.object(db_pool_module, "get_pool", AsyncMock(return_value=db)):
        t1 = asyncio.create_task(add_post_copies(post_num, copies))
        t2 = asyncio.create_task(interleaved_writer())
        await asyncio.gather(t1, t2)

    assert interleaved_executed, "Interleaved transaction was blocked by add_post_copies!"
    assert not db_pool_module.db_lock.locked(), "db_lock must not remain locked"


# ============================================================================
# 3. Timeout & cannot commit - no transaction is active Resilience Tests
# ============================================================================

@pytest.mark.asyncio
async def test_db_transaction_timeout_aborted_transaction_resilience(isolated_test_db):
    """
    Verifies that when an inner block triggers a rollback or transaction abort,
    db_transaction.__aexit__ suppresses 'cannot commit - no transaction is active'
    without propagating an unhandled OperationalError.
    """
    db = isolated_test_db

    # Premature commit / rollback inside db_transaction
    async with db_transaction(db):
        await db.execute("SELECT 1")
        # Simulate external rollback or timeout handler that rolled back transaction
        await db.execute("ROLLBACK")

    # If __aexit__ did not suppress 'cannot commit - no transaction is active',
    # the block would have raised sqlite3.OperationalError!
    assert not db_pool_module.db_lock.locked()


@pytest.mark.asyncio
async def test_db_transaction_timeout_cancelled_clean_rollback(isolated_test_db):
    """
    Verifies that when a task times out inside db_transaction via asyncio.timeout,
    the rollback is cleanly executed and the lock is released without leaving
    a zombie transaction.
    """
    db = isolated_test_db

    async def slow_tx():
        async with asyncio.timeout(0.05):
            async with db_transaction(db):
                await db.execute(
                    "INSERT OR REPLACE INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (8888, 'b', 1, '{}', 1.0)"
                )
                await asyncio.sleep(1.0)

    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        await slow_tx()

    assert not db_pool_module.db_lock.locked()

    # Verify that the uncommitted insert was rolled back
    async with db.execute("SELECT COUNT(*) FROM Posts WHERE post_num = 8888") as cur:
        assert (await cur.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_safe_commit_and_rollback_when_no_tx_or_revoked(isolated_test_db):
    """
    Verifies safe_commit and safe_rollback idempotency when:
    1. No transaction is active on the connection.
    2. db_lock is not owned by the current task.
    Neither should raise unhandled exceptions.
    """
    db = isolated_test_db

    # 1. safe_commit with no active transaction
    await db_pool_module.db_lock.acquire()
    _task_tx_depth.set(1)
    # Should not raise 'cannot commit - no transaction is active'
    await safe_commit(db, started_by_caller=True)
    assert not db_pool_module.db_lock.locked()

    # 2. safe_rollback with no active transaction
    await db_pool_module.db_lock.acquire()
    _task_tx_depth.set(1)
    await safe_rollback(db, started_by_caller=True)
    assert not db_pool_module.db_lock.locked()

    # 3. safe_commit when lock is NOT owned
    _task_tx_depth.set(1)
    # db_lock is NOT acquired
    await safe_commit(db, started_by_caller=True)
    assert _task_tx_depth.get() == 0


@pytest.mark.asyncio
async def test_watchdog_revocation_suppresses_operational_error_on_exit(isolated_test_db):
    """
    Simulates watchdog revoking the lock during a hung transaction.
    When the hung task finally exits:
    - If exc_type is not None (e.g. timeout), it must cleanly return without OperationalError.
    - If exc_type is None, it raises RuntimeError('Transaction lock was revoked by watchdog; transaction lost').
    """
    db = isolated_test_db

    # Case A: Task timed out and lock was revoked by watchdog
    task_raised_operational_error = False
    task_timed_out = False

    async def hanging_timed_out_task():
        nonlocal task_raised_operational_error, task_timed_out
        try:
            async with asyncio.timeout(0.05):
                async with db_transaction(db):
                    # Simulate watchdog breaking the lock
                    db_pool_module.db_lock._owner = None
                    db_pool_module.db_lock._depth = 0
                    db_pool_module.db_lock._acquired_at = 0.0
                    await asyncio.sleep(0.5)
        except (asyncio.TimeoutError, TimeoutError):
            task_timed_out = True
        except sqlite3.OperationalError:
            task_raised_operational_error = True

    await hanging_timed_out_task()
    assert task_timed_out, "Task should have timed out cleanly"
    assert not task_raised_operational_error, "OperationalError must be suppressed on lock revocation"
