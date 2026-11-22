import pytest
import asyncio
import time
import os
import tempfile
import sqlite3
import aiosqlite
from unittest.mock import patch, AsyncMock

import common.db_pool as db_pool_module
from common.db_pool import (
    LazyLock,
    db_transaction,
    db_sleep,
    has_pending_high_priority,
    get_pool,
    close_pool,
    safe_begin_immediate,
    safe_commit,
    safe_rollback,
    _task_tx_depth,
)
from common.database import create_post, clean_old_postcopies_daily
from maintenance import clean_old_postcopies


@pytest.fixture(autouse=True)
def reset_db_locks():
    """Ensure clean LazyLock and task depth for every test."""
    db_pool_module.db_lock = LazyLock()
    db_pool_module._reconnect_lock = LazyLock()
    yield
    db_pool_module.db_lock = LazyLock()
    db_pool_module._reconnect_lock = LazyLock()


# ============================================================================
# SCENARIO 1: Deadlock and Starvation Torture (50 Low vs 10 High Priority)
# ============================================================================
@pytest.mark.asyncio
async def test_priority_queue_adversarial_starvation_50_vs_10():
    """
    Induce extreme lock contention by queueing 50 low-priority tasks and then
    firing 10 high-priority tasks simultaneously.
    Verifies:
    1. Zero deadlocks.
    2. All 10 high-priority tasks execute BEFORE any of the queued low-priority tasks.
    3. has_pending_high_priority() correctly reflects queue state.
    4. All 50 low-priority tasks eventually complete successfully without starvation.
    """
    lock = LazyLock()
    execution_order = []
    low_count = 50
    high_count = 10

    async def low_worker(idx):
        await lock.acquire(priority=False)
        try:
            execution_order.append(("low", idx))
            await asyncio.sleep(0.002)
        finally:
            lock.release()

    async def high_worker(idx):
        await lock.acquire(priority=True)
        try:
            execution_order.append(("high", idx))
            await asyncio.sleep(0.002)
        finally:
            lock.release()

    # 1. Hold lock with blocker
    await lock.acquire(priority=False)

    # 2. Queue 50 low-priority tasks
    low_tasks = [asyncio.create_task(low_worker(i)) for i in range(low_count)]
    await asyncio.sleep(0.02)  # Give them time to enqueue in _low_waiters

    assert len(lock._low_waiters) == low_count, f"Expected {low_count} low waiters"
    assert not lock.has_pending_high_priority()

    # 3. Fire 10 high-priority tasks
    high_tasks = [asyncio.create_task(high_worker(i)) for i in range(high_count)]
    await asyncio.sleep(0.01)  # Give them time to enqueue in _high_waiters

    assert len(lock._high_waiters) == high_count, f"Expected {high_count} high waiters"
    assert lock.has_pending_high_priority(), "has_pending_high_priority() must be True"

    # 4. Release blocker: high priority tasks MUST cut in front!
    lock.release()

    await asyncio.gather(*high_tasks, *low_tasks)

    # All high priority tasks must have completed before any low priority task
    first_10 = [kind for kind, _ in execution_order[:10]]
    remaining_50 = [kind for kind, _ in execution_order[10:]]

    assert all(k == "high" for k in first_10), f"Starvation detected! High tasks did not cut in front: {first_10}"
    assert all(k == "low" for k in remaining_50), f"Expected low tasks in remaining 50, got: {remaining_50[:10]}"
    assert len(execution_order) == low_count + high_count


# ============================================================================
# SCENARIO 2: Zombie Transaction Prevention on Cancellation
# ============================================================================
@pytest.mark.asyncio
async def test_zombie_tx_prevention_on_enter_cancellation():
    """
    Tortures cancellation occurring in db_transaction.__aenter__ right as BEGIN
    completes in SQLite. Verifies shielded ROLLBACK resets connection so no zombie
    transaction lingers.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_path = os.path.join(td, "test_zombie_enter.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.execute("CREATE TABLE Test (id INT);")

        orig_exec = conn.execute
        cancelled_once = False

        async def cancel_on_begin_exec(sql, *args, **kwargs):
            nonlocal cancelled_once
            res = await orig_exec(sql, *args, **kwargs)
            if "BEGIN" in sql and not cancelled_once:
                cancelled_once = True
                raise asyncio.CancelledError()
            return res

        conn.execute = cancel_on_begin_exec

        tx = db_transaction(conn, immediate=True)
        try:
            async with tx:
                pass
        except asyncio.CancelledError:
            pass

        assert cancelled_once, "Cancellation must have been triggered after BEGIN"
        assert not db_pool_module.db_lock.locked(), "db_lock must be released"

        # Restore original execute and test that connection has NO active transaction
        conn.execute = orig_exec
        # If there were a zombie transaction, this BEGIN IMMEDIATE would raise OperationalError
        async with db_transaction(conn, immediate=True):
            await conn.execute("INSERT INTO Test VALUES (100);")

        async with conn.execute("SELECT COUNT(*) FROM Test WHERE id = 100") as c:
            assert (await c.fetchone())[0] == 1

        await conn.close()


@pytest.mark.asyncio
async def test_zombie_tx_prevention_on_exit_commit_cancellation():
    """
    Tortures cancellation occurring in db_transaction.__aexit__ during COMMIT.
    Verifies that COMMIT is protected by asyncio.shield, preventing zombie transactions.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_path = os.path.join(td, "test_zombie_exit.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.execute("CREATE TABLE Test (id INT);")

        orig_exec = conn.execute
        commit_cancelled = False

        async def cancel_on_commit_exec(sql, *args, **kwargs):
            nonlocal commit_cancelled
            if "COMMIT" in sql and not commit_cancelled:
                commit_cancelled = True
                raise asyncio.CancelledError()
            return await orig_exec(sql, *args, **kwargs)

        conn.execute = cancel_on_commit_exec

        tx = db_transaction(conn, immediate=True)
        try:
            async with tx:
                await orig_exec("INSERT INTO Test VALUES (200);")
        except asyncio.CancelledError:
            pass

        assert not db_pool_module.db_lock.locked(), "db_lock must be released"

        # Connection must be clean and immediately usable
        conn.execute = orig_exec
        async with db_transaction(conn, immediate=True):
            await conn.execute("INSERT INTO Test VALUES (300);")

        async with conn.execute("SELECT COUNT(*) FROM Test WHERE id = 300") as c:
            assert (await c.fetchone())[0] == 1

        await conn.close()


@pytest.mark.asyncio
async def test_zombie_tx_prevention_on_body_cancellation():
    """
    Verifies that when an external cancellation occurs while the task is executing
    inside the async with block, changes are cleanly rolled back under shield.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_path = os.path.join(td, "test_zombie_body.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.execute("CREATE TABLE Test (id INT);")

        async def worker():
            async with db_transaction(conn, immediate=True):
                await conn.execute("INSERT INTO Test VALUES (999);")
                await asyncio.sleep(5.0)

        task = asyncio.create_task(worker())
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert not db_pool_module.db_lock.locked()

        # Uncommitted insert must have been rolled back
        async with conn.execute("SELECT COUNT(*) FROM Test WHERE id = 999") as c:
            assert (await c.fetchone())[0] == 0

        # Connection must be clean
        async with db_transaction(conn, immediate=True):
            await conn.execute("INSERT INTO Test VALUES (1);")

        async with conn.execute("SELECT COUNT(*) FROM Test") as c:
            assert (await c.fetchone())[0] == 1

        await conn.close()


# ============================================================================
# SCENARIO 3: Savepoint Stress & Collision Torture across 20 Concurrent Tasks
# ============================================================================
@pytest.mark.asyncio
async def test_savepoint_name_collisions_20_concurrent_nested_tasks():
    """
    Launches 20 concurrent tasks, each running deeply nested savepoint transactions
    with intentional rollbacks at intermediate levels.
    Verifies:
    1. Zero savepoint name collisions across all tasks.
    2. Inner rollbacks only revert inner changes without breaking outer savepoints.
    3. Outer commits successfully persist all valid levels.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_path = os.path.join(td, "test_sp_collision.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.execute("CREATE TABLE NestedLog (task_id INT, level INT, status TEXT);")

        seen_savepoints = set()
        duplicate_savepoints = []

        orig_exec = conn.execute

        async def savepoint_tracking_exec(sql, *args, **kwargs):
            if "SAVEPOINT" in sql:
                sp_name = sql.split()[1]
                if sp_name in seen_savepoints:
                    duplicate_savepoints.append(sp_name)
                seen_savepoints.add(sp_name)
            return await orig_exec(sql, *args, **kwargs)

        conn.execute = savepoint_tracking_exec

        async def nested_worker(task_id):
            # Level 1: Outer transaction (BEGIN IMMEDIATE)
            async with db_transaction(conn, immediate=True):
                await conn.execute("INSERT INTO NestedLog VALUES (?, 1, 'ok')", (task_id,))

                # Level 2: Nested savepoint
                async with db_transaction(conn):
                    await conn.execute("INSERT INTO NestedLog VALUES (?, 2, 'ok')", (task_id,))

                    # Level 3: Nested savepoint that rolls back!
                    try:
                        async with db_transaction(conn):
                            await conn.execute("INSERT INTO NestedLog VALUES (?, 3, 'rolled_back')", (task_id,))
                            raise RuntimeError(f"Task {task_id} inner failure")
                    except RuntimeError:
                        pass

                    # Level 4: Sibling savepoint after rollback
                    async with db_transaction(conn):
                        await conn.execute("INSERT INTO NestedLog VALUES (?, 4, 'ok')", (task_id,))

        tasks = [asyncio.create_task(nested_worker(i)) for i in range(20)]
        await asyncio.gather(*tasks)

        assert len(duplicate_savepoints) == 0, f"Colliding savepoint names found: {duplicate_savepoints}"
        assert len(seen_savepoints) == 60, f"Expected 60 unique savepoints (3 per task x 20 tasks), got {len(seen_savepoints)}"

        conn.execute = orig_exec

        # Verify DB: levels 1, 2, 4 must have 20 rows each. Level 3 must have 0 rows!
        async with conn.execute("SELECT level, count(*) FROM NestedLog GROUP BY level ORDER BY level") as c:
            rows = await c.fetchall()

        assert rows == [(1, 20), (2, 20), (4, 20)], f"Unexpected rows in DB: {rows}"
        await conn.close()


# ============================================================================
# SCENARIO 4: Database Connection Disconnect & Mid-Transaction Error Torture
# ============================================================================
@pytest.mark.asyncio
async def test_db_disconnect_mid_transaction_lock_safety():
    """
    Verifies that if a query fails mid-transaction or the connection abruptly closes,
    LazyLock is NEVER stuck and subsequent operations can proceed.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_path = os.path.join(td, "test_disc.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.execute("CREATE TABLE Items (val TEXT PRIMARY KEY);")

        # 4A: Query failure (unique constraint violation)
        await conn.execute("INSERT INTO Items VALUES ('duplicate');")
        with pytest.raises(sqlite3.IntegrityError):
            async with db_transaction(conn, immediate=True):
                await conn.execute("INSERT INTO Items VALUES ('duplicate');")

        assert not db_pool_module.db_lock.locked(), "Lock must be released on IntegrityError"

        # 4B: Abrupt connection close mid-transaction
        with pytest.raises(Exception):
            async with db_transaction(conn, immediate=True):
                await conn.execute("INSERT INTO Items VALUES ('valid');")
                await conn.close()
                await conn.execute("INSERT INTO Items VALUES ('never');")

        assert not db_pool_module.db_lock.locked(), "Lock must be released on connection close"


# ============================================================================
# SCENARIO 5: Watchdog Revocation & Cross-Task Data Corruption Prevention
# ============================================================================
@pytest.mark.asyncio
async def test_watchdog_revocation_prevents_cross_task_data_corruption():
    """
    ADVERSARIAL TORTURE:
    Task 1 hangs inside db_transaction (>20s).
    Watchdog breaks Task 1's lock and hands it to Task 2.
    Task 2 starts writing uncommitted step 1 data.
    Task 1 unfreezes and exits __aexit__.
    Verifies:
    1. Task 1 detects watchdog revoked its lock.
    2. Task 1 DOES NOT commit or rollback Task 2's uncommitted data!
    3. Task 1 DOES NOT release Task 2's lock.
    4. Task 2 can cleanly rollback its own transaction with zero corruption.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_path = os.path.join(td, "test_watchdog_corrupt.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.execute("CREATE TABLE Ledger (entry TEXT);")

        task1_raised = False
        task2_rolled_back = False

        async def hanging_task():
            nonlocal task1_raised
            try:
                async with db_transaction(conn, immediate=True):
                    await conn.execute("INSERT INTO Ledger VALUES ('task1_initial');")
                    # Simulate hang > 35s watchdog threshold
                    db_pool_module.db_lock._acquired_at = time.monotonic() - 40.0
                    await asyncio.sleep(0.06)
            except RuntimeError as e:
                if "revoked by watchdog" in str(e):
                    task1_raised = True

        async def incoming_task():
            nonlocal task2_rolled_back
            await asyncio.sleep(0.01)
            # This acquire should trigger watchdog break of hanging_task
            try:
                async with db_transaction(conn, immediate=True):
                    # Write uncommitted partial state
                    await conn.execute("INSERT INTO Ledger VALUES ('task2_step1');")
                    await asyncio.sleep(0.08)  # Let hanging_task wake up and attempt __aexit__
                    # Task 2 encounters an intentional error: MUST ROLLBACK step1!
                    raise ValueError("Task 2 failed, rolling back")
            except ValueError:
                task2_rolled_back = True

        t1 = asyncio.create_task(hanging_task())
        t2 = asyncio.create_task(incoming_task())

        await asyncio.gather(t1, t2)

        assert task1_raised, "Task 1 must have detected lock revocation and raised RuntimeError"
        assert task2_rolled_back, "Task 2 must have completed its rollback"

        # CRITICAL ASSERTION: The Ledger table must be COMPLETELY EMPTY!
        # If Task 1 had committed while exiting, 'task2_step1' would be leaked into the DB!
        async with conn.execute("SELECT entry FROM Ledger") as c:
            rows = await c.fetchall()

        assert rows == [], f"DATA CORRUPTION DETECTED! Uncommitted rows persisted: {rows}"
        await conn.close()


# ============================================================================
# SCENARIO 6: Task Transaction Depth Isolation Across Spawned Child Tasks
# ============================================================================
@pytest.mark.asyncio
async def test_task_tx_depth_isolation_across_spawned_child_tasks():
    """
    Verifies that _task_tx_depth is strictly task-isolated and does not leak
    into child tasks created via asyncio.create_task().
    Child tasks must start with depth == 0 and execute transactions cleanly.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_path = os.path.join(td, "test_task_isolation.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.execute("CREATE TABLE TaskItems (source TEXT);")

        async def child_worker(idx):
            # Verify child task sees depth == 0 even though parent was at depth 1 when creating it
            initial_depth = _task_tx_depth.get()
            assert initial_depth == 0, f"Child task {idx} inherited dirty depth: {initial_depth}"

            # Child task can start its own independent transaction
            async with db_transaction(conn, immediate=True):
                await conn.execute("INSERT INTO TaskItems VALUES (?)", (f"child_{idx}",))

        async def parent_worker():
            async with db_transaction(conn, immediate=True):
                await conn.execute("INSERT INTO TaskItems VALUES ('parent');")
                # Spawn 10 child tasks while parent is inside active transaction
                children = [asyncio.create_task(child_worker(i)) for i in range(10)]

            # Parent has committed and released lock; wait for children
            await asyncio.gather(*children)

        await parent_worker()

        async with conn.execute("SELECT count(*) FROM TaskItems") as c:
            count = (await c.fetchone())[0]
            assert count == 11, f"Expected 11 items (1 parent + 10 children), got {count}"

        await conn.close()


# ============================================================================
# SCENARIO 7: Heavy Chunked Cleanup Concurrency Torture (3,000 Records vs 15 Posts)
# ============================================================================
@pytest.mark.asyncio
async def test_heavy_chunked_cleanup_vs_rapid_create_posts_stress():
    """
    Simulates high load: 3,000 PostCopies records being cleaned up in batches of 500
    while 15 rapid create_post calls with priority=True are fired.
    Verifies:
    1. Zero timeouts.
    2. All 15 posts are created.
    3. All 3,000 old records are purged cleanly.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_path = os.path.join(td, "test_heavy_stress.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA busy_timeout=25000;")
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS Boards (board_id TEXT PRIMARY KEY, name TEXT);
            INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('b', 'b');
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER, board_id TEXT, posts_count INTEGER DEFAULT 0,
                status TEXT, location TEXT, stream TEXT, created_at REAL,
                PRIMARY KEY (user_id, board_id)
            );
            CREATE TABLE IF NOT EXISTS Posts (
                post_num INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id TEXT, author_id INTEGER, content TEXT, timestamp REAL,
                thread_id TEXT, reply_to_post_num INTEGER, stream TEXT,
                is_shadow INTEGER DEFAULT 0, ip TEXT
            );
            CREATE TABLE IF NOT EXISTS PostCopies (
                post_num INTEGER, recipient_id INTEGER, message_id INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_postcopies_post_num ON PostCopies(post_num);
            CREATE TABLE IF NOT EXISTS FileRegistry (
                sha256 TEXT PRIMARY KEY, file_id TEXT, thumbnail_id TEXT,
                file_type TEXT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS PostFiles (
                post_num INTEGER, file_type TEXT, original_file_id TEXT,
                thumbnail_file_id TEXT, original_url TEXT, thumbnail_url TEXT
            );
            CREATE TABLE IF NOT EXISTS BroadcastQueue (
                post_num INTEGER, created_at REAL, is_sent_to_tg INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS Threads (
                thread_id TEXT PRIMARY KEY, thread_num INTEGER DEFAULT 0,
                last_updated_at REAL, is_archived INTEGER DEFAULT 0
            );
        """)

        old_ts = time.time() - (5 * 86400)
        recent_ts = time.time()
        await conn.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (1, 'b', 1, '{}', ?)", (old_ts,))
        await conn.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (5000, 'b', 1, '{}', ?)", (recent_ts,))

        # Seed 3,000 old records
        copies = [(10, 5000 + i, 8000 + i) for i in range(3000)]
        await conn.executemany("INSERT INTO PostCopies VALUES (?, ?, ?)", copies)

        with patch.object(db_pool_module, "get_pool", AsyncMock(return_value=conn)), \
             patch.object(db_pool_module, "_db_connection", conn):

            cleaner_task = asyncio.create_task(clean_old_postcopies_daily(retention_days=3))
            await asyncio.sleep(0.01)

            # Fire 15 rapid posts
            async def make_post(idx):
                return await create_post(
                    author_id=990000 + idx,
                    board_id="b",
                    content={"text": f"Stress post #{idx}"},
                    timestamp=time.time()
                )

            post_tasks = [asyncio.create_task(make_post(i)) for i in range(15)]
            post_results = await asyncio.gather(*post_tasks)

            for idx, res in enumerate(post_results):
                assert res is not None, f"Post {idx} failed during cleaner contention"
                assert isinstance(res, int) and res > 0

            deleted = await cleaner_task
            assert deleted == 3000, f"Expected 3000 deleted rows, got {deleted}"

        await conn.close()


# ============================================================================
# SCENARIO 8: Maintenance Chunked Clean Safety
# ============================================================================
def test_maintenance_clean_old_postcopies_variations():
    """
    Verifies clean_old_postcopies in maintenance.py under:
    - Empty database
    - Database with zero matching rows
    - Database with 1,350 rows (requiring multiple chunks + final partial chunk)
    """
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "test_maint_variations.db")
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE Posts (post_num INTEGER PRIMARY KEY, timestamp REAL);")
        con.execute("CREATE TABLE PostCopies (post_num INTEGER, recipient_id INTEGER, message_id INTEGER);")

        # 1. Empty table: should not raise
        clean_old_postcopies(con, retention_days=3, batch_size=500)

        # 2. Add posts and 1,350 copies
        old_ts = time.time() - (5 * 86400)
        recent_ts = time.time()
        con.execute("INSERT INTO Posts VALUES (1, ?)", (old_ts,))
        con.execute("INSERT INTO Posts VALUES (10000, ?)", (recent_ts,))

        copies = [(50, 100, i) for i in range(1350)]
        con.executemany("INSERT INTO PostCopies VALUES (?, ?, ?)", copies)
        con.commit()

        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM PostCopies")
        assert cur.fetchone()[0] == 1350

        clean_old_postcopies(con, retention_days=3, batch_size=500)

        cur.execute("SELECT COUNT(*) FROM PostCopies")
        assert cur.fetchone()[0] == 0

        con.close()
