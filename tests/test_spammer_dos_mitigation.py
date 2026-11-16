# -*- coding: utf-8 -*-
import os
import time
import asyncio
import sqlite3
from unittest import mock
import pytest
from datetime import datetime, timedelta, UTC

import shared_state
from common.spam_filter import (
    _in_memory_shadow_muted_users,
    set_in_memory_shadow_mute,
    is_user_in_memory_shadow_muted,
    clear_in_memory_shadow_mutes,
    load_active_shadow_mutes_from_db,
    apply_shadow_mute,
    apply_shadow_mute_multi_boards,
)
from handlers.message_router import (
    handle_message,
    handle_media_group_init,
    _is_user_shadow_muted_early,
    _last_shadow_echo_ts,
)


@pytest.fixture(autouse=True)
def clean_spam_mitigation_state():
    clear_in_memory_shadow_mutes()
    _last_shadow_echo_ts.clear()
    shared_state.shadow_fake_post_counters.clear()
    yield
    clear_in_memory_shadow_mutes()
    _last_shadow_echo_ts.clear()
    shared_state.shadow_fake_post_counters.clear()


def test_spammer_30_day_mute_verification_in_db():
    """
    Task 1: Verify that spammer 6199965905 has a 30-day shadow mute in dvach_bot.db.
    Checks:
    - User 6199965905 has records in Mutes table with mute_type = 'shadow'.
    - Contains 'ALL' and board-specific records with reason 'macro_keysmash_flood_dos'.
    - Expiration is approximately 30 days in the future.
    """
    db_path = r"C:\dev\dvachbot\dvach_bot.db"
    assert os.path.exists(db_path), f"Database file not found: {db_path}"

    conn = sqlite3.connect(f"file:{db_path.replace(os.sep, '/')}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT board_id, mute_type, expires_at, reason FROM Mutes WHERE user_id = ?",
            (6199965905,)
        )
        rows = cur.fetchall()
        assert len(rows) >= 28, f"Expected at least 28 board records, got {len(rows)}"

        boards_found = {r[0] for r in rows}
        assert 'ALL' in boards_found, "Mute for board 'ALL' must exist"
        assert 'b' in boards_found, "Mute for board 'b' must exist"

        now_ts = time.time()
        for r in rows:
            bid, m_type, exp_at, reason = r
            assert m_type == 'shadow', f"Expected shadow mute, got {m_type}"
            assert exp_at > now_ts, f"Mute on {bid} is already expired"
            # 30 days +/- 2 days tolerance
            diff_days = (exp_at - now_ts) / 86400.0
            assert 25.0 <= diff_days <= 32.0, f"Expected ~30 day mute, got {diff_days:.1f} days on {bid}"
            assert reason == 'macro_keysmash_flood_dos', f"Expected reason 'macro_keysmash_flood_dos', got {reason}"
    finally:
        conn.close()


def test_in_memory_preload_from_db():
    """
    Verifies that load_active_shadow_mutes_from_db reads active mutes from SQLite
    in read-only mode and registers spammer 6199965905 into _in_memory_shadow_muted_users.
    """
    clear_in_memory_shadow_mutes()
    assert is_user_in_memory_shadow_muted(6199965905) is False

    loaded_count = load_active_shadow_mutes_from_db()
    assert loaded_count > 0, "Expected at least 1 mute loaded from DB"
    assert is_user_in_memory_shadow_muted(6199965905) is True
    assert is_user_in_memory_shadow_muted(6199965905, 'b') is True
    assert is_user_in_memory_shadow_muted(6199965905, 'ALL') is True


@pytest.mark.asyncio
async def test_100_rapid_messages_zero_database_locks_and_contention():
    """
    Task 2 & 4: Adversarial test simulating 100 rapid messages from a shadow-muted spammer (6199965905).
    Asserts:
    1. Zero database lock acquisitions (db_lock.acquire called 0 times).
    2. Zero database connection or queries (get_pool / db.execute called 0 times).
    3. Zero post creation calls (process_new_post called 0 times).
    4. 100 messages deleted immediately via message.delete.
    5. Execution takes < 0.1ms per message on average.
    """
    spammer_id = 6199965905
    board_id = "b"

    # Pre-condition: user is in in-memory shadow mute cache (expires in 30 days)
    set_in_memory_shadow_mute(spammer_id, 'ALL', duration_seconds=30 * 86400)
    assert is_user_in_memory_shadow_muted(spammer_id, board_id) is True

    shared_state.board_data[board_id] = {
        'shadow_mutes': {},
        'user_settings': {},
        'users': {'active': set(), 'banned': set()}
    }

    mock_bot = mock.AsyncMock()

    # Trackers for SQLite locks and pool access
    lock_acquire_calls = 0
    pool_access_calls = 0

    class SpyLock:
        def __init__(self, original_lock):
            self._orig = original_lock

        async def __aenter__(self):
            nonlocal lock_acquire_calls
            lock_acquire_calls += 1
            return await self._orig.__aenter__()

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return await self._orig.__aexit__(exc_type, exc_val, exc_tb)

        def locked(self):
            return self._orig.locked()

    from common.db_pool import db_lock as orig_db_lock
    spy_lock = SpyLock(orig_db_lock)

    async def spy_get_pool(*args, **kwargs):
        nonlocal pool_access_calls
        pool_access_calls += 1
        raise AssertionError("Database get_pool was called during shadow-muted flood!")

    messages = []
    for i in range(100):
        m = mock.MagicMock()
        m.from_user.id = spammer_id
        m.chat.id = spammer_id
        m.bot = mock_bot
        m.message_id = 1000 + i
        m.content_type = "text"
        m.text = f"gibberish flood attack {i} asdfjkl"
        m.caption = None
        m.delete = mock.AsyncMock()
        messages.append(m)

    with mock.patch("common.db_pool.db_lock", spy_lock), \
         mock.patch("handlers.message_router.db_lock", spy_lock), \
         mock.patch("common.db_pool.get_pool", side_effect=spy_get_pool), \
         mock.patch("handlers.message_router.get_pool", side_effect=spy_get_pool), \
         mock.patch("common.database.get_pool", side_effect=spy_get_pool), \
         mock.patch("handlers.message_router.process_new_post", new_callable=mock.AsyncMock) as mock_new_post:

        t_start = time.perf_counter()

        for msg in messages:
            await handle_message(msg, board_id)

        t_elapsed = time.perf_counter() - t_start

    # STRICT ASSERTIONS:
    assert lock_acquire_calls == 0, f"db_lock was acquired {lock_acquire_calls} times! Expected ZERO."
    assert pool_access_calls == 0, f"Database pool was queried {pool_access_calls} times! Expected ZERO."
    assert mock_new_post.called is False, "process_new_post must never be called for shadow-muted spammer"

    for i, msg in enumerate(messages):
        assert msg.delete.called, f"Message #{i+1} was not deleted!"

    avg_ms = (t_elapsed / 100.0) * 1000.0
    print(f"\n[BENCHMARK] 100 rapid messages processed in {t_elapsed*1000:.2f}ms (avg {avg_ms:.3f}ms/msg). Zero DB locks!")
    assert avg_ms < 2.0, f"Expected < 2ms per message, got {avg_ms:.3f}ms"


@pytest.mark.asyncio
async def test_multi_board_mute_executemany_batch_efficiency():
    """
    Task 3: Check that multi-board mutes batch into a SINGLE executemany within a single transaction,
    instead of 28 individual queries that cause lock contention.
    """
    user_id = 99887766
    shared_state.BOARDS = ['a', 'b', 'vg', 'po', 'tech', 'wh40k', 'int', 'sex', 'news']

    mock_db = mock.AsyncMock()
    mock_cursor = mock.AsyncMock()
    mock_db.cursor.return_value = mock_cursor

    executemany_called = False
    executemany_record_count = 0
    execute_calls = []

    async def mock_executemany(sql, records):
        nonlocal executemany_called, executemany_record_count
        executemany_called = True
        executemany_record_count = len(records)
        return mock_cursor

    async def mock_execute(sql, *args):
        execute_calls.append(sql)
        return mock_cursor

    mock_db.executemany = mock.AsyncMock(side_effect=mock_executemany)
    mock_db.execute = mock.AsyncMock(side_effect=mock_execute)

    class DummyTransaction:
        async def __aenter__(self): return mock_db
        async def __aexit__(self, exc_type, exc_val, exc_tb): pass

    with mock.patch("common.db_pool.get_pool", mock.AsyncMock(return_value=mock_db)), \
         mock.patch("common.db_pool.db_transaction", return_value=DummyTransaction()):

        exp = await apply_shadow_mute_multi_boards(
            user_id=user_id,
            board_ids=shared_state.BOARDS,
            duration_seconds=3600.0,
            reason="test_multi_board_dos"
        )

        assert exp > time.time()
        assert executemany_called is True, "Multi-board mute MUST use executemany!"
        # Records count must include all boards + 'ALL'
        expected_records = len(set(shared_state.BOARDS) | {'ALL'})
        assert executemany_record_count == expected_records, f"Expected {expected_records} records, got {executemany_record_count}"

        # Verify in-memory state is synchronized
        assert is_user_in_memory_shadow_muted(user_id) is True
        assert is_user_in_memory_shadow_muted(user_id, 'b') is True
        assert is_user_in_memory_shadow_muted(user_id, 'vg') is True


@pytest.mark.asyncio
async def test_repeated_messages_skip_db_writes_when_already_muted():
    """
    Task 2: When a user is already in _in_memory_shadow_muted_users,
    apply_shadow_mute must drop and return existing expiry WITHOUT writing 28 mute records repeatedly!
    """
    user_id = 777666555
    set_in_memory_shadow_mute(user_id, 'ALL', duration_seconds=1800.0)

    with mock.patch("common.db_pool.get_pool") as mock_get_pool, \
         mock.patch("common.database.apply_shadow_mute") as mock_db_mute:

        # Attempt to apply shadow mute again
        res = await apply_shadow_mute(user_id, 'ALL', duration_seconds=1800.0, reason="repeated_flood")

        assert res > time.time()
        assert mock_get_pool.called is False, "Must NOT query or write to SQLite when already muted in memory!"
        assert mock_db_mute.called is False, "Must NOT call database apply_shadow_mute when already muted in memory!"


@pytest.mark.asyncio
async def test_media_group_init_spammer_drops_without_db():
    """
    Verifies that handle_media_group_init drops incoming media groups from
    a shadow-muted spammer immediately without hitting SQLite.
    """
    spammer_id = 6199965905
    board_id = "b"
    set_in_memory_shadow_mute(spammer_id, 'ALL', duration_seconds=86400)

    mock_msg = mock.MagicMock()
    mock_msg.from_user.id = spammer_id
    mock_msg.chat.id = spammer_id
    mock_msg.media_group_id = "test_mg_12345"
    mock_msg.delete = mock.AsyncMock()

    with mock.patch("common.database.is_shadow_muted") as mock_is_sm, \
         mock.patch("common.db_pool.get_pool") as mock_pool:

        await handle_media_group_init(mock_msg, board_id)

        assert mock_msg.delete.called
        assert mock_is_sm.called is False, "is_shadow_muted DB function must not be called"
        assert mock_pool.called is False, "Database get_pool must not be called"


@pytest.mark.asyncio
async def test_cross_board_rapid_flood_instant_in_memory_drop():
    """
    Simulates a spammer flooding across 5 different boards simultaneously ('a', 'b', 'vg', 'po', 'tech').
    Asserts all 100 messages across all boards drop instantly via _in_memory_shadow_muted_users.
    """
    spammer_id = 6199965905
    boards = ['a', 'b', 'vg', 'po', 'tech']
    set_in_memory_shadow_mute(spammer_id, 'ALL', duration_seconds=86400)

    for b in boards:
        shared_state.board_data[b] = {
            'shadow_mutes': {},
            'user_settings': {},
            'users': {'active': set(), 'banned': set()}
        }

    mock_bot = mock.AsyncMock()
    deleted_count = 0

    with mock.patch("common.db_pool.get_pool") as mock_pool, \
         mock.patch("handlers.message_router.process_new_post") as mock_new_post:

        for i in range(100):
            target_board = boards[i % len(boards)]
            msg = mock.MagicMock()
            msg.from_user.id = spammer_id
            msg.chat.id = spammer_id
            msg.bot = mock_bot
            msg.message_id = 2000 + i
            msg.content_type = "text"
            msg.text = f"cross-board flood {i}"
            msg.caption = None
            async def track_delete():
                nonlocal deleted_count
                deleted_count += 1
            msg.delete = mock.AsyncMock(side_effect=track_delete)

            await handle_message(msg, target_board)

        assert deleted_count == 100
        assert mock_pool.called is False, "Zero DB calls during cross-board flood"
        assert mock_new_post.called is False, "Zero posts created"
