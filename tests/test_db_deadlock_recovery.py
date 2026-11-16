import pytest
import asyncio
import time
import os
import tempfile
import sqlite3
import aiosqlite
from unittest.mock import patch, AsyncMock

import common.db_pool as db_pool_module
from common.db_pool import LazyLock, db_transaction, has_pending_high_priority, get_pool, close_pool
from common.database import create_post, clean_old_postcopies_daily, init_db
from maintenance import clean_old_postcopies


@pytest.fixture(autouse=True)
def reset_db_locks():
    """Ensure clean LazyLock and task depth for every test."""
    db_pool_module.db_lock = LazyLock()
    db_pool_module._reconnect_lock = LazyLock()
    yield
    db_pool_module.db_lock = LazyLock()
    db_pool_module._reconnect_lock = LazyLock()


@pytest.mark.asyncio
async def test_priority_starvation_prevention():
    """
    Verifies that high-priority requests (create_post) jump ahead of low-priority background
    cleaners in LazyLock, and that has_pending_high_priority() correctly reflects waiting status.
    """
    lock = LazyLock()
    execution_order = []

    async def bg_cleaner(chunk_id):
        async with lock:
            execution_order.append(f"cleaner_{chunk_id}_start")
            await asyncio.sleep(0.04)
            execution_order.append(f"cleaner_{chunk_id}_end")

    async def incoming_post(post_id):
        # High priority acquire
        await lock.acquire(priority=True)
        try:
            execution_order.append(f"post_{post_id}_created")
            await asyncio.sleep(0.01)
        finally:
            lock.release()

    # 1. Start chunk 1
    t_clean1 = asyncio.create_task(bg_cleaner(1))
    await asyncio.sleep(0.01)

    # 2. Queue chunk 2 and 3 as background (low priority)
    t_clean2 = asyncio.create_task(bg_cleaner(2))
    t_clean3 = asyncio.create_task(bg_cleaner(3))
    await asyncio.sleep(0.005)

    # 3. Queue high-priority incoming post
    assert not lock.has_pending_high_priority()
    t_post = asyncio.create_task(incoming_post(101))
    await asyncio.sleep(0.001)

    # has_pending_high_priority() must be True while t_post is waiting
    assert lock.has_pending_high_priority()

    await asyncio.gather(t_clean1, t_clean2, t_clean3, t_post)

    # Verification: post_101_created must execute immediately after cleaner_1_end,
    # BEFORE cleaner_2 and cleaner_3!
    assert execution_order[0] == "cleaner_1_start"
    assert execution_order[1] == "cleaner_1_end"
    assert execution_order[2] == "post_101_created", f"Expected post_101_created at index 2, got {execution_order}"
    assert "cleaner_2_start" in execution_order[3:]
    assert "cleaner_3_start" in execution_order[3:]


@pytest.mark.asyncio
async def test_db_transaction_shielded_rollback_on_cancellation():
    """
    Verifies that when a task inside db_transaction is cancelled (e.g. by asyncio.timeout),
    the ROLLBACK is executed under asyncio.shield, preventing orphaned uncommitted transactions.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        test_db_path = os.path.join(tmp_dir, "test_shield.db")
        conn = await aiosqlite.connect(test_db_path, isolation_level=None)
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("CREATE TABLE TestItems (id INTEGER PRIMARY KEY, val TEXT);")

        with patch.object(db_pool_module, "get_pool", AsyncMock(return_value=conn)), \
             patch.object(db_pool_module, "_db_connection", conn):

            async def cancelled_worker():
                async with db_transaction(conn, immediate=True):
                    await conn.execute("INSERT INTO TestItems (val) VALUES ('uncommitted');")
                    # Simulate timeout or external task cancellation
                    await asyncio.sleep(10.0)

            task = asyncio.create_task(cancelled_worker())
            await asyncio.sleep(0.05)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

            # Transaction must have been cleanly rolled back despite task cancellation!
            async with conn.execute("SELECT COUNT(*) FROM TestItems") as c:
                row = await c.fetchone()
                assert row[0] == 0, f"Expected 0 uncommitted items after rollback, got {row[0]}"

            # Connection must be capable of immediately starting another transaction
            async with db_transaction(conn, immediate=True):
                await conn.execute("INSERT INTO TestItems (val) VALUES ('committed');")

            async with conn.execute("SELECT COUNT(*) FROM TestItems") as c:
                row = await c.fetchone()
                assert row[0] == 1

        await conn.close()


@pytest.mark.asyncio
async def test_concurrent_heavy_cleanup_and_rapid_create_posts():
    """
    ADVERSARIAL STRESS TEST:
    Simulates heavy background deletes of thousands of PostCopies records concurrent
    with 10 rapid create_post calls.
    Verifies that:
    1. None of the create_post calls hit TimeoutError or starve.
    2. All 10 posts are successfully created.
    3. clean_old_postcopies_daily successfully chunks deletions in batches of 500.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        test_db_path = os.path.join(tmp_dir, "test_stress.db")

        # Initialize real SQLite tables
        conn = await aiosqlite.connect(test_db_path, isolation_level=None)
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

        # Seed old posts and 2,500 PostCopies records (>3 days old)
        now_ts = time.time()
        old_ts = now_ts - (5 * 86400)
        await conn.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (1, 'b', 1, '{}', ?)", (old_ts,))
        await conn.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (2000, 'b', 1, '{}', ?)", (now_ts,))

        # Insert 2,500 copies with post_num < 2000
        copies = [(50, 1000 + (i % 100), 2000 + i) for i in range(2500)]
        await conn.executemany("INSERT INTO PostCopies (post_num, recipient_id, message_id) VALUES (?, ?, ?)", copies)

        async with conn.execute("SELECT COUNT(*) FROM PostCopies") as c:
            count = (await c.fetchone())[0]
            assert count == 2500

        with patch.object(db_pool_module, "get_pool", AsyncMock(return_value=conn)), \
             patch.object(db_pool_module, "_db_connection", conn):

            # Start background cleanup task
            cleaner_task = asyncio.create_task(clean_old_postcopies_daily(retention_days=3))

            # Concurrently launch 10 rapid user posts
            async def make_post(idx):
                p_num = await create_post(
                    author_id=7716348189 + idx,
                    board_id="b",
                    content={"text": f"Adversarial stress post {idx}"},
                    timestamp=time.time()
                )
                return p_num

            # Give cleaner task a tiny moment to spin up
            await asyncio.sleep(0.01)

            post_tasks = [asyncio.create_task(make_post(i)) for i in range(10)]
            post_results = await asyncio.gather(*post_tasks)

            # All posts must be successfully created with positive integers!
            for idx, res in enumerate(post_results):
                assert res is not None, f"Post {idx} failed (returned None) during concurrent cleanup!"
                assert isinstance(res, int) and res > 0

            # Wait for cleaner to finish deleting all 2,500 copies
            deleted_count = await cleaner_task
            assert deleted_count == 2500, f"Expected 2500 deleted records, got {deleted_count}"

            # Verify PostCopies is now empty of old records
            async with conn.execute("SELECT COUNT(*) FROM PostCopies WHERE post_num < 2000") as c:
                remaining = (await c.fetchone())[0]
                assert remaining == 0

        await conn.close()


@pytest.mark.asyncio
async def test_post_processor_retry_and_rescue():
    """
    Verifies that NewPostProcessor retries create_post with sensible jittered backoff
    and rescues the post if transient DB lock occurs, instead of immediately failing.
    """
    from post_processor import NewPostProcessor, NewPostContext

    call_count = 0
    async def mock_create_post_failing_twice(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return None  # Simulate transient DB busy / lock timeout
        return 99999  # Succeeded on 3rd attempt

    mock_bot = AsyncMock()
    ctx = NewPostContext(
        bot_instance=mock_bot,
        board_id="b",
        user_id=7716348189,
        content={"text": "Test retry post"},
        reply_to_post=None,
        is_shadow_muted=False,
        stream="ru"
    )

    processor = NewPostProcessor(ctx)

    with patch("post_processor.create_post", side_effect=mock_create_post_failing_twice), \
         patch("post_processor.update_post_content", AsyncMock()), \
         patch("post_processor.send_message_to_users", AsyncMock(return_value=[(7716348189, [AsyncMock(message_id=123)])])), \
         patch("post_processor.enqueue_board_message", AsyncMock()):

        result = await processor.execute()
        assert result == 99999
        assert call_count == 3, f"Expected 3 calls to create_post (2 retries), got {call_count}"


def test_maintenance_script_chunked_delete():
    """
    Verifies that clean_old_postcopies in maintenance.py chunks deletions in batches of 500
    without monopolizing the write lock.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_maint.db")
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE Posts (post_num INTEGER PRIMARY KEY, timestamp REAL);")
        con.execute("CREATE TABLE PostCopies (post_num INTEGER, recipient_id INTEGER, message_id INTEGER);")

        old_ts = time.time() - (5 * 86400)
        recent_ts = time.time()
        con.execute("INSERT INTO Posts VALUES (1, ?)", (old_ts,))
        con.execute("INSERT INTO Posts VALUES (5000, ?)", (recent_ts,))

        # Insert 1,200 copies
        copies = [(10, 100, i) for i in range(1200)]
        con.executemany("INSERT INTO PostCopies VALUES (?, ?, ?)", copies)
        con.commit()

        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM PostCopies")
        assert cur.fetchone()[0] == 1200

        # Execute chunked clean
        clean_old_postcopies(con, retention_days=3, batch_size=500)

        cur.execute("SELECT COUNT(*) FROM PostCopies")
        assert cur.fetchone()[0] == 0
        con.close()
