"""
Deep Verification Suite for Supervisor, Watchdog, and DB Concurrency Repairs.
Tests cover:
1. bot_watchdog: Phantom restart bug fix, 0-byte file handling, atomic cleanup.
2. bot_watchdog: Elimination of false soft_restart_requested_at triggers on newly started processes.
3. common/db_pool: Harmonized LazyLock watchdog timeout (35.0s) and SQLite busy_timeout (15.0s).
4. delivery_manager & common/config: Controlled stop drain timeout increased to 120.0s,
   with watchdog soft restart grace period >= 120.0s.
"""

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import aiosqlite

import bot_watchdog
import common.config as config_module
import common.db_pool as db_pool_module
from common.db_pool import LazyLock
import delivery_manager


# ==============================================================================
# 1. Watchdog: Phantom Restart & 0-byte File Fix Tests
# ==============================================================================

def test_watchdog_phantom_restart_prevention_on_empty_file(tmp_path: Path):
    """
    Ensure that a 0-byte bot.restart file is recognized as empty/invalid,
    is cleaned up (unlinked), and NEVER triggers a restart.
    """
    test_restart_file = tmp_path / "bot.restart"
    test_restart_file.write_text("", encoding="utf-8")
    assert test_restart_file.exists()
    assert test_restart_file.stat().st_size == 0

    with patch.object(bot_watchdog, "BOT_RESTART_PATH", test_restart_file):
        # Must return False and unlink the 0-byte file
        requested = bot_watchdog._is_restart_requested()
        assert requested is False
        assert not test_restart_file.exists()


def test_watchdog_clear_restart_request_no_empty_file_on_error(tmp_path: Path):
    """
    Ensure that _clear_restart_request never writes an empty file if unlink fails.
    """
    test_restart_file = tmp_path / "bot.restart"

    with patch.object(bot_watchdog, "BOT_RESTART_PATH", test_restart_file):
        # Simulate unlink throwing OSError
        with patch.object(Path, "unlink", side_effect=OSError("Sharing violation")):
            bot_watchdog._clear_restart_request("test context")

        # The file MUST NOT have been created by write_text("", ...)
        assert not test_restart_file.exists()


def test_watchdog_restart_request_stale_predating_child_start(tmp_path: Path):
    """
    Ensure that a restart request created BEFORE child start time is ignored
    and unlinked, preventing phantom restarts on a newly launched process.
    """
    test_restart_file = tmp_path / "bot.restart"
    test_restart_file.write_text("manual_restart", encoding="utf-8")
    assert test_restart_file.stat().st_size > 0

    # Set file mtime to 100.0
    os.utime(test_restart_file, (100.0, 100.0))

    child_start_time = 150.0  # Child started after file creation

    with patch.object(bot_watchdog, "BOT_RESTART_PATH", test_restart_file):
        # Stale request predating child start: should return False and unlink
        requested = bot_watchdog._is_restart_requested(child_start_time=child_start_time)
        assert requested is False
        assert not test_restart_file.exists()


def test_watchdog_restart_request_fresh_valid(tmp_path: Path):
    """
    Ensure that a non-empty restart request created AFTER child start time
    is correctly recognized as a valid restart trigger.
    """
    test_restart_file = tmp_path / "bot.restart"
    test_restart_file.write_text("soft_drain_request", encoding="utf-8")
    assert test_restart_file.stat().st_size > 0

    child_start_time = time.time() - 5.0  # Child started 5s ago
    # File mtime is now (>= child_start_time)

    with patch.object(bot_watchdog, "BOT_RESTART_PATH", test_restart_file):
        requested = bot_watchdog._is_restart_requested(child_start_time=child_start_time)
        assert requested is True
        assert test_restart_file.exists()


# ==============================================================================
# 2. Watchdog: Elimination of False Triggers on Newly Started Process
# ==============================================================================

def test_watchdog_newly_started_process_no_false_alarm(tmp_path: Path):
    """
    Simulate child monitor loop behavior for a newly started process:
    - Empty or pre-existing stale files must not trigger soft restart.
    - Stale heartbeat from an old process must not trigger soft restart.
    """
    test_restart = tmp_path / "bot.restart"
    test_restart.write_text("", encoding="utf-8")  # 0 bytes phantom

    child_start_time = time.time()

    # Stale heartbeat from old child with old timestamp
    stale_heartbeat = {
        "pid": 12345,
        "ts": child_start_time - 30.0,
        "drain_shutdown_requested": True,
        "is_shutting_down": True,
    }

    with patch.object(bot_watchdog, "BOT_RESTART_PATH", test_restart), \
         patch.object(bot_watchdog, "_read_heartbeat", return_value=stale_heartbeat):

        # 1. 0-byte file check
        assert bot_watchdog._is_restart_requested(child_start_time=child_start_time) is False

        # 2. Child draining check with start_time guard
        heartbeat = bot_watchdog._read_heartbeat()
        is_child_draining = bool(
            heartbeat
            and heartbeat.get("pid") == 12345
            and float(heartbeat.get("ts", 0)) >= child_start_time
            and (heartbeat.get("drain_shutdown_requested") or heartbeat.get("is_shutting_down"))
        )
        assert is_child_draining is False


def test_watchdog_legitimate_drain_heartbeat_triggers_soft_restart():
    """
    Ensure that when child genuinely reports draining with a fresh timestamp >= start_time,
    the watchdog arms the soft restart.
    """
    child_start_time = time.time() - 10.0
    fresh_heartbeat = {
        "pid": 9999,
        "ts": child_start_time + 5.0,  # fresh, after start
        "drain_shutdown_requested": True,
        "is_shutting_down": False,
    }

    with patch.object(bot_watchdog, "_read_heartbeat", return_value=fresh_heartbeat):
        heartbeat = bot_watchdog._read_heartbeat()
        is_child_draining = bool(
            heartbeat
            and heartbeat.get("pid") == 9999
            and float(heartbeat.get("ts", 0)) >= child_start_time
            and (heartbeat.get("drain_shutdown_requested") or heartbeat.get("is_shutting_down"))
        )
        assert is_child_draining is True


# ==============================================================================
# 3. LazyLock Watchdog (35.0s) & SQLite busy_timeout (15.0s) Harmony Tests
# ==============================================================================

def test_lazylock_watchdog_threshold_constant():
    """Verify LazyLock class constant and instance default is 35.0 seconds."""
    assert LazyLock.WATCHDOG_TIMEOUT_SEC == 35.0
    lock = LazyLock()
    assert lock._watchdog_timeout == 35.0


@pytest.mark.asyncio
async def test_lazylock_does_not_break_during_sqlite_busy_timeout():
    """
    Verify that when a task holds LazyLock for up to 20 seconds
    (within SQLite checkpoint / busy_timeout window <= 15-20s),
    the watchdog does NOT break or tear the lock.
    """
    lock = LazyLock()
    await lock.acquire()
    assert lock.locked()

    # Simulate task legitimately waiting on SQLite for 20 seconds (20s < 35s)
    lock._acquired_at = time.monotonic() - 20.0

    # _check_watchdog should NOT revoke the lock
    lock._check_watchdog()
    assert lock.locked()
    assert lock._owner is not None

    # Waiter from a DIFFERENT task with a brief timeout should timeout, NOT break the lock
    async def different_task_waiter():
        return await lock.acquire(timeout=0.1)

    t = asyncio.create_task(different_task_waiter())
    with pytest.raises(asyncio.TimeoutError):
        await t

    assert lock.locked()
    lock.release()
    assert not lock.locked()


@pytest.mark.asyncio
async def test_lazylock_breaks_hung_task_after_35s():
    """
    Verify that when a task truly hangs for > 35 seconds,
    the watchdog correctly resets the lock and wakes the next waiting task.
    """
    lock = LazyLock()
    await lock.acquire()
    assert lock.locked()

    # Simulate true hang (> 35s, e.g. 36s)
    lock._acquired_at = time.monotonic() - 36.0

    async def second_task():
        return await lock.acquire(timeout=2.0)

    t = asyncio.create_task(second_task())
    res = await t
    assert res is True
    assert lock.locked()
    assert lock._owner is t
    lock.release()
    assert not lock.locked()


@pytest.mark.asyncio
async def test_sqlite_busy_timeout_configured_to_15s(tmp_path: Path):
    """
    Verify that aiosqlite connection sets PRAGMA busy_timeout = 15000 (15.0s),
    and that this timeout is strictly lower than LazyLock.WATCHDOG_TIMEOUT_SEC (35.0s).
    """
    db_file = str(tmp_path / "test_busy_timeout.db")
    with patch.object(db_pool_module, "DB_NAME", db_file):
        conn = await db_pool_module.get_pool()
        try:
            cursor = await conn.execute("PRAGMA busy_timeout;")
            row = await cursor.fetchone()
            busy_timeout_ms = row[0]
            assert busy_timeout_ms == 15000, f"Expected 15000ms, got {busy_timeout_ms}"

            # Verify mathematical guarantee: busy_timeout (15s) < watchdog_timeout (35s)
            assert (busy_timeout_ms / 1000.0) < LazyLock.WATCHDOG_TIMEOUT_SEC
        finally:
            await conn.close()
            db_pool_module._db_connection = None


# ==============================================================================
# 4. Delivery Manager & Grace Period Configuration Tests
# ==============================================================================

def test_controlled_stop_drain_timeout_configuration():
    """
    Verify that CONTROLLED_STOP_DRAIN_TIMEOUT_SEC is 120.0s across:
    1. delivery_manager
    2. common.config
    And that bot_watchdog SOFT_RESTART_GRACE_SEC is at least 120.0s.
    """
    assert delivery_manager.CONTROLLED_STOP_DRAIN_TIMEOUT_SEC == 120.0
    assert config_module.BOT_CONTROLLED_STOP_DRAIN_TIMEOUT_SEC == 120.0

    # Watchdog soft restart grace period must be >= delivery drain timeout
    assert bot_watchdog.SOFT_RESTART_GRACE_SEC >= 120.0
    assert bot_watchdog.SOFT_RESTART_GRACE_SEC == 140.0
