import asyncio
import os
import sys
import time
import sqlite3
import pytest
from unittest import mock
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.asyncio
async def test_access_violation_immunity_no_open_files():
    """
    Signature: bot_fatal_crash.log (Windows fatal exception: access violation in psutil.open_files()).
    Verifies that _get_process_memory_snapshot() never calls psutil.open_files(),
    avoids NT handle enumeration crashes, and returns valid diagnostic metrics.
    """
    from main import _get_process_memory_snapshot

    with mock.patch("psutil.Process.open_files", side_effect=RuntimeError("psutil.open_files() must NEVER be called!")):
        snapshot = _get_process_memory_snapshot()

    assert isinstance(snapshot, dict)
    assert "error" not in snapshot
    assert "rss_mb" in snapshot
    assert "private_mb" in snapshot
    assert "threads" in snapshot
    assert "handles" in snapshot
    assert snapshot.get("open_files") == -1  # Explicitly disabled for Windows kernel stability


def test_safe_rotating_file_handler_under_windows_file_locking(tmp_path):
    """
    Signature: PermissionError: [WinError 32] in RotatingFileHandler.rotate() in bot_stdout_utf8.log.
    Verifies WindowsSafeRotatingFileHandler catches PermissionError on rollover,
    defers rotation with cooldown, and does not crash or crash the caller thread.
    """
    from main import WindowsSafeRotatingFileHandler
    import logging

    log_file = tmp_path / "test_runtime.log"
    handler = WindowsSafeRotatingFileHandler(
        str(log_file), maxBytes=50, backupCount=2, encoding="utf-8"
    )
    test_logger = logging.getLogger("test_rollover_logger")
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(handler)

    try:
        # First write: under limit
        test_logger.info("Short message 1")
        assert log_file.exists()

        # Simulate Windows file locking: doRollover raises PermissionError [WinError 32]
        with mock.patch.object(handler, "rotate", side_effect=PermissionError(32, "The process cannot access the file")):
            # Second write: triggers rollover attempt
            test_logger.info("This is a much longer message that definitely exceeds fifty bytes!")
            test_logger.info("Another message during rollover deferral")

        # Must not raise exceptions, stream must still be valid
        assert not handler.stream.closed
        assert handler._rollover_retry_after > time.time()
    finally:
        handler.close()
        test_logger.removeHandler(handler)


@pytest.mark.asyncio
async def test_graceful_shutdown_wal_checkpoint_nonblocking():
    """
    Signature: Supervisor event_loop_deadlock kill during controlled shutdown at 'PRAGMA wal_checkpoint(TRUNCATE)'.
    Verifies wal_checkpoint_truncate() enforces timeout and does not hang the event loop
    when the database or db_lock is contested.
    """
    from common.db_pool import wal_checkpoint_truncate

    # Simulate a slow/hanging sqlite connection
    class _MockHangingConnection:
        def execute(self, query):
            class _HangingCursorContext:
                async def __aenter__(self):
                    await asyncio.sleep(5.0)
                    return self
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass
            return _HangingCursorContext()

    mock_conn = _MockHangingConnection()
    start = time.monotonic()
    # Call real wal_checkpoint_truncate with a short timeout
    ok = await wal_checkpoint_truncate(db=mock_conn, timeout=0.15)
    elapsed = time.monotonic() - start

    # Must finish within timeout without deadlocking the event loop
    assert elapsed < 1.0
    assert ok is False


def test_watchdog_heartbeat_freshness_during_shutdown():
    """
    Signature: bot_watchdog.py killing child with reason=event_loop_deadlock after 45s
    because _heartbeat_is_fresh() returned False when is_shutting_down was True.
    Verifies fresh heartbeats during shutdown are recognized and not prematurely declared deadlocked.
    """
    from bot_watchdog import _heartbeat_is_fresh

    now = time.time()
    # Heartbeat from a child that is currently performing a graceful drain shutdown
    draining_payload = {
        "ts": now - 5.0,
        "pid": 99999,
        "queues_total": 0,
        "is_shutting_down": True,
        "drain_shutdown_requested": True,
    }

    # Must be considered FRESH so supervisor does not prematurely kill with event_loop_deadlock
    assert _heartbeat_is_fresh(draining_payload) is True

    # Truly stale heartbeat must still be considered stale
    stale_payload = {
        "ts": now - 120.0,
        "pid": 99999,
        "queues_total": 0,
        "is_shutting_down": False,
        "drain_shutdown_requested": False,
    }
    assert _heartbeat_is_fresh(stale_payload) is False


@pytest.mark.asyncio
async def test_db_transaction_commit_resilience(isolated_test_db):
    """
    Signature: sqlite3.OperationalError: cannot commit - no transaction is active in bot_stdout_utf8.log.1.
    Verifies db_transaction.__aexit__ suppresses 'cannot commit - no transaction is active'
    without propagating error or corrupting connection state.
    """
    from common.db_pool import db_transaction

    # Case 1: Normal transaction commit
    async with db_transaction(isolated_test_db) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS _test_redteam (id INT PRIMARY KEY, val TEXT)")
        await db.execute("INSERT OR REPLACE INTO _test_redteam VALUES (1, 'ok')")

    # Verify write committed
    async with isolated_test_db.execute("SELECT val FROM _test_redteam WHERE id = 1") as cur:
        row = await cur.fetchone()
        assert row[0] == "ok"

    # Case 2: External/accidental commit occurred before __aexit__
    # (Simulates commit executed by lower layer, leaving no transaction active on __aexit__)
    async with db_transaction(isolated_test_db) as db:
        await db.execute("INSERT OR REPLACE INTO _test_redteam VALUES (2, 'premature')")
        await db.execute("COMMIT")  # premature manual commit

    # Should not raise sqlite3.OperationalError: cannot commit - no transaction is active
    async with isolated_test_db.execute("SELECT val FROM _test_redteam WHERE id = 2") as cur:
        row = await cur.fetchone()
        assert row[0] == "premature"


def test_maintenance_blocks_on_active_bot_lock(tmp_path):
    """
    Signature: Database locked errors when maintenance.py runs while bot is alive.
    Verifies maintenance.run_maintenance() aborts if bot.lock indicates an active bot process.
    """
    from maintenance import run_maintenance

    # Create dummy database and active bot.lock with current process PID
    dummy_db = tmp_path / "test_maint.db"
    dummy_db.touch()
    dummy_lock = tmp_path / "bot.lock"
    dummy_lock.write_text(str(os.getpid()), encoding="utf-8")

    with mock.patch("maintenance.DB_NAME", str(dummy_db)):
        result = run_maintenance()

    # Must refuse to run and return False
    assert result is False


@pytest.mark.asyncio
async def test_spawn_task_unhandled_exception_isolation():
    """
    Signature: Unhandled exceptions causing background task silent failure or unhandled crash.
    Verifies common.task_manager.spawn_task retains references, catches errors in callback,
    and discards task without raising unhandled exceptions to event loop.
    """
    from common.task_manager import spawn_task, _background_tasks

    failed_task_done = asyncio.Event()

    async def _failing_coroutine():
        try:
            await asyncio.sleep(0.01)
            raise ValueError("Simulated unexpected background error!")
        finally:
            failed_task_done.set()

    task = spawn_task(_failing_coroutine(), name="test_failing_coro")
    assert task in _background_tasks

    await failed_task_done.wait()
    await asyncio.sleep(0.05)  # Allow done callback to process

    # Task must have failed, but callback should have safely processed it
    assert task.done()
    assert isinstance(task.exception(), ValueError)
    assert task not in _background_tasks


@pytest.mark.asyncio
async def test_add_post_copies_timeout_and_error_handling(isolated_test_db):
    """
    Signature: DeliveryQueue delete timeout / add_post_copies timeout in bot_stdout_utf8.log.
    Verifies add_post_copies catches TimeoutError gracefully without crashing delivery worker.
    """
    from common.database import add_post_copies

    # Ensure parent post exists for foreign key constraint
    await isolated_test_db.execute(
        "INSERT OR IGNORE INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (12345, 'b', 1001, '{\"text\": \"test\"}', 1234567.0)"
    )

    # Case 1: Normal insertion
    await add_post_copies(12345, [(1001, 2001), (1002, 2002)])

    async with isolated_test_db.execute("SELECT recipient_id, message_id FROM PostCopies WHERE post_num = 12345") as cur:
        rows = await cur.fetchall()
        assert len(rows) == 2

    # Case 2: TimeoutError simulation
    with mock.patch("common.db_pool.db_lock.acquire", side_effect=asyncio.TimeoutError("Lock busy")):
        # Must catch TimeoutError and NOT raise to caller
        await add_post_copies(12346, [(1001, 2003)])
