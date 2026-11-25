import asyncio
import gc
import json
import os
import sqlite3
import tempfile
import time
import weakref
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

import bot_watchdog
import maintenance
import shared_state
from common import database as dbmod
from common import db_pool
from common import task_manager


def test_shared_state_maps_are_bounded_and_evict():
    """Verifies BoundedDict / BoundedDefaultDict enforce strict ceilings and all hot maps are bounded."""
    bd = shared_state.BoundedDict(max_size=3)
    for i in range(10):
        bd[f"k{i}"] = i
    assert len(bd) == 3
    assert list(bd.keys()) == ["k7", "k8", "k9"]

    bdd = shared_state.BoundedDefaultDict(list, max_size=4)
    for i in range(10):
        bdd[i].append(i * 10)
    assert isinstance(bdd, dict)
    assert len(bdd) == 4
    assert list(bdd.keys()) == [6, 7, 8, 9]
    assert bdd[9] == [90]

    for mapping in (
        shared_state.author_reaction_notify_tracker,
        shared_state._last_persona_dialogue_user_ts,
        shared_state.reaction_ratelimit,
        shared_state._GLOBAL_COMBAT_COOLDOWNS,
        shared_state._TARGET_LAST_ATTACKED_TS,
        shared_state._ATTACKER_SERIES_HISTORY,
        shared_state._VICTIM_ROB_COOLDOWNS,
        shared_state._GLOBAL_WORK_COOLDOWNS,
        shared_state._USER_PARTYVAN_COOLDOWNS,
        shared_state._VICTIM_PARTYVAN_IMMUNITY,
        shared_state._DAILY_SHOP_PURCHASES,
        shared_state._ATTACKER_TARGET_HISTORY,
        shared_state._ATTACKER_ABUSE_WARNINGS,
        shared_state.shadow_fake_post_counters,
        shared_state._stats_cache,
        shared_state._stats_cooldown_tracker,
        shared_state._duel_cooldowns,
        shared_state.messages_storage,
        shared_state.post_to_messages,
        shared_state.message_to_post,
    ):
        assert isinstance(mapping, shared_state.BoundedDict)

    b = shared_state.board_data["_test_bounded_board_"]
    try:
        for key in (
            "last_roll_time",
            "last_info_command_time",
            "last_texts",
            "last_stickers",
            "last_animations",
            "last_audios",
            "spam_violations",
            "spam_tracker",
            "reaction_rate_tracker",
            "reaction_queue",
            "last_reaction_process_time",
            "single_photo_counter",
            "last_photo_group_id",
            "message_counter",
            "last_user_msgs",
            "last_activity",
            "user_state",
            "thread_locks",
            "anime_daily_tracker",
        ):
            assert isinstance(b[key], shared_state.BoundedDict), f"{key} is not BoundedDict"
    finally:
        shared_state.board_data.pop("_test_bounded_board_", None)


@pytest.mark.asyncio
async def test_prune_shared_state_reclaims_expired_and_done_entries():
    now = time.time()
    done_task = asyncio.create_task(asyncio.sleep(0))
    await done_task
    pending_task = asyncio.create_task(asyncio.sleep(10))

    shared_state.pending_edit_tasks[999901] = done_task
    shared_state.pending_edit_tasks[999902] = pending_task
    shared_state._stats_cache["_test_stale"] = {"ts": now - 7200, "photos": [b"x"]}
    shared_state._GLOBAL_COMBAT_COOLDOWNS[999901] = now - 10
    shared_state._DAILY_SHOP_PURCHASES[(999901, "mute", "1999-01-01")] = 2
    shared_state._persona_processed_posts.update(range(1, 3505))
    try:
        removed = shared_state.prune_shared_state(now=now)
        assert removed.get("pending_edit_tasks", 0) >= 1
        assert 999901 not in shared_state.pending_edit_tasks
        assert 999902 in shared_state.pending_edit_tasks
        assert "_test_stale" not in shared_state._stats_cache
        assert 999901 not in shared_state._GLOBAL_COMBAT_COOLDOWNS
        assert (999901, "mute", "1999-01-01") not in shared_state._DAILY_SHOP_PURCHASES
        assert len(shared_state._persona_processed_posts) <= 1500
    finally:
        pending_task.cancel()
        try:
            await pending_task
        except asyncio.CancelledError:
            pass
        shared_state.pending_edit_tasks.pop(999902, None)
        shared_state._persona_processed_posts.clear()


@pytest.mark.asyncio
async def test_load_state_from_db_respects_startup_memory_caps(monkeypatch):
    """Ensures load_state_from_db does not hydrate unbounded PostCopies or archived thread posts."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_hydration.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.executescript("""
            CREATE TABLE Boards (board_id TEXT PRIMARY KEY, name TEXT, settings TEXT);
            INSERT INTO Boards VALUES ('b', 'Random', '{}'), ('thread', 'Threads', '{}');
            CREATE TABLE Users (
                user_id INTEGER, board_id TEXT, status TEXT, location TEXT,
                nsfw_spoiler INTEGER DEFAULT 0, hidden_words TEXT DEFAULT '[]',
                shadow_ban_gif INTEGER DEFAULT 0, shadow_ban_sticker INTEGER DEFAULT 0,
                shadow_ban_media INTEGER DEFAULT 0, lie_media INTEGER DEFAULT 0,
                disable_ai_roasts INTEGER DEFAULT 0, is_isolated INTEGER DEFAULT 0,
                isolation_last_toggle REAL DEFAULT 0.0,
                PRIMARY KEY (user_id, board_id)
            );
            CREATE TABLE Mutes (user_id INTEGER, board_id TEXT, mute_type TEXT, expires_at REAL);
            CREATE TABLE Threads (
                thread_id TEXT PRIMARY KEY, board_id TEXT, op_id INTEGER,
                title TEXT, created_at REAL, is_archived INTEGER DEFAULT 0,
                last_updated_at REAL, stream TEXT DEFAULT 'ru'
            );
            CREATE TABLE Posts (
                post_num INTEGER PRIMARY KEY, board_id TEXT, thread_id TEXT,
                author_id INTEGER, content TEXT, timestamp REAL, reply_to_post_num INTEGER,
                is_shadow INTEGER DEFAULT 0
            );
            CREATE TABLE PostCopies (post_num INTEGER, recipient_id INTEGER, message_id INTEGER);
        """)
        now = time.time()
        await conn.execute(
            "INSERT INTO Threads VALUES ('t_arch', 'thread', 1, 'Archived', ?, 1, ?, 'ru')",
            (now - 9999, now - 9999),
        )
        await conn.execute(
            "INSERT INTO Threads VALUES ('t_live', 'thread', 1, 'Live', ?, 0, ?, 'ru')",
            (now, now),
        )
        posts_rows = []
        copies_rows = []
        for pnum in range(1, 51):
            tid = "t_arch" if pnum <= 25 else "t_live"
            posts_rows.append((pnum, "thread", tid, 100, json.dumps({"text": f"p{pnum}"}), now + pnum, None, 0))
            for rec in range(1, 21):
                copies_rows.append((pnum, 1000 + rec, pnum * 100 + rec))
        await conn.executemany("INSERT INTO Posts VALUES (?, ?, ?, ?, ?, ?, ?, ?)", posts_rows)
        await conn.executemany("INSERT INTO PostCopies VALUES (?, ?, ?)", copies_rows)

        monkeypatch.setenv("BOT_POST_CACHE_LIMIT", "15")
        monkeypatch.setenv("BOT_COPY_CACHE_POST_LIMIT", "10")
        monkeypatch.setenv("BOT_MESSAGE_TO_POST_LIMIT", "50")
        monkeypatch.setenv("BOT_STARTUP_MAX_COPY_ENTRIES", "90")

        with patch.object(db_pool, "get_pool", AsyncMock(return_value=conn)), \
             patch.object(db_pool, "_db_connection", conn):
            loaded = await dbmod.load_state_from_db({"thread"})

        assert len(loaded["messages_storage"]) == 15
        assert list(loaded["messages_storage"].keys())[-1] == 50
        assert len(loaded["post_to_messages"]) <= 5
        total_p2m_entries = sum(len(v) for v in loaded["post_to_messages"].values())
        assert total_p2m_entries <= 100
        assert 50 in loaded["post_to_messages"]
        assert len(loaded["message_to_post"]) == 50
        # Newest post's copy must be retained in message_to_post
        assert loaded["message_to_post"].get((1020, 50 * 100 + 20)) == 50
        # Archived thread must not hydrate post list
        assert loaded["board_data"]["thread"]["threads_data"]["t_arch"]["posts"] == []
        assert len(loaded["board_data"]["thread"]["threads_data"]["t_live"]["posts"]) == 25
        await conn.close()


@pytest.mark.asyncio
async def test_incremental_db_housekeeping_cleans_all_bloated_tables():
    """Tests batch cleanup of PostCopies, ChannelCopies, MirrorQueue, MoneyDropMessages, MediaReposts."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_housekeeping.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.executescript("""
            CREATE TABLE Posts (post_num INTEGER PRIMARY KEY, timestamp REAL);
            CREATE TABLE PostCopies (post_num INTEGER, recipient_id INTEGER, message_id INTEGER);
            CREATE INDEX idx_postcopies_post_num ON PostCopies(post_num);
            CREATE TABLE ChannelCopies (post_num INTEGER, channel_id INTEGER, message_id INTEGER);
            CREATE INDEX idx_channelcopies_post ON ChannelCopies(post_num);
            CREATE TABLE FileMirrors (file_id TEXT, mirror_type TEXT, url TEXT, PRIMARY KEY (file_id, mirror_type));
            CREATE TABLE MirrorQueue (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, mirror_type TEXT, attempts INTEGER DEFAULT 0, next_run_at REAL DEFAULT 0);
            CREATE INDEX idx_mirror_queue_run ON MirrorQueue(next_run_at);
            CREATE INDEX idx_mirror_queue_attempts ON MirrorQueue(attempts);
            CREATE TABLE MoneyDrops (drop_id TEXT PRIMARY KEY, status TEXT, created_at REAL, claimed_at REAL, refunded_at REAL);
            CREATE TABLE MoneyDropMessages (drop_id TEXT, chat_id INTEGER, message_id INTEGER);
            CREATE INDEX idx_moneydropmessages_drop_id ON MoneyDropMessages(drop_id);
            CREATE TABLE MediaReposts (board_id TEXT, file_unique_id TEXT, times INTEGER, first_post_num INTEGER, first_seen REAL);
            CREATE INDEX idx_mediareposts_singleton_age ON MediaReposts(first_seen) WHERE times = 1;
        """)
        now = time.time()
        await conn.execute("INSERT INTO Posts VALUES (100, ?)", (now - 10 * 86400,))
        await conn.execute("INSERT INTO Posts VALUES (200, ?)", (now - 5 * 86400,))
        await conn.execute("INSERT INTO Posts VALUES (300, ?)", (now,))

        # PostCopies: 650 old (<200) + 10 recent (>=200)
        await conn.executemany(
            "INSERT INTO PostCopies VALUES (?, ?, ?)",
            [(100, 1, i) for i in range(650)] + [(300, 1, 10000 + i) for i in range(10)],
        )
        # ChannelCopies: 300 old (<200) + 5 recent (>=300)
        await conn.executemany(
            "INSERT INTO ChannelCopies VALUES (?, ?, ?)",
            [(100, -100, i) for i in range(300)] + [(300, -100, 20000 + i) for i in range(5)],
        )
        # MirrorQueue: 1 already mirrored, 1 stale (>7d), 1 exhausted (attempts=10), 1 valid pending
        await conn.execute("INSERT INTO FileMirrors VALUES ('f_done', 'catbox', 'https://x')")
        await conn.executemany(
            "INSERT INTO MirrorQueue (file_id, mirror_type, attempts, next_run_at) VALUES (?, ?, ?, ?)",
            [
                ("f_done", "catbox", 0, now),
                ("f_stale", "catbox", 0, now - 10 * 86400),
                ("f_dead", "catbox", 10, now + 100),
                ("f_keep", "catbox", 1, now + 100),
            ],
        )
        # MoneyDropMessages: 1 claimed >24h, 1 orphan, 1 active
        await conn.execute("INSERT INTO MoneyDrops VALUES ('d_old', 'claimed', ?, ?, NULL)", (now - 5 * 86400, now - 2 * 86400))
        await conn.execute("INSERT INTO MoneyDrops VALUES ('d_live', 'active', ?, NULL, NULL)", (now,))
        await conn.executemany(
            "INSERT INTO MoneyDropMessages VALUES (?, ?, ?)",
            [("d_old", 1, 1), ("d_orphan", 1, 2), ("d_live", 1, 3)],
        )
        # MediaReposts: 1 old singleton, 1 old repeat (times=5 must survive), 1 fresh singleton
        await conn.executemany(
            "INSERT INTO MediaReposts VALUES (?, ?, ?, ?, ?)",
            [
                ("b", "u_old1", 1, 10, now - 200 * 86400),
                ("b", "u_bayan", 5, 11, now - 200 * 86400),
                ("b", "u_fresh", 1, 300, now),
            ],
        )

        with patch.object(db_pool, "get_pool", AsyncMock(return_value=conn)), \
             patch.object(db_pool, "_db_connection", conn):
            res = await dbmod.run_incremental_db_housekeeping(max_batches_per_table=10)

        assert res["PostCopies"] == 650
        assert res["ChannelCopies"] == 300
        assert res["MirrorQueue"] == 3
        assert res["MoneyDropMessages"] == 2
        assert res["MediaReposts"] == 1

        async with conn.execute("SELECT COUNT(*) FROM PostCopies") as c:
            assert (await c.fetchone())[0] == 10
        async with conn.execute("SELECT COUNT(*) FROM ChannelCopies") as c:
            assert (await c.fetchone())[0] == 5
        async with conn.execute("SELECT file_id FROM MirrorQueue") as c:
            assert [r[0] for r in await c.fetchall()] == ["f_keep"]
        async with conn.execute("SELECT drop_id FROM MoneyDropMessages") as c:
            assert [r[0] for r in await c.fetchall()] == ["d_live"]
        async with conn.execute("SELECT file_unique_id FROM MediaReposts ORDER BY file_unique_id") as c:
            assert [r[0] for r in await c.fetchall()] == ["u_bayan", "u_fresh"]

        await conn.close()


def test_maintenance_sync_cleaners():
    """Verifies sync cleaners in maintenance.py remove ChannelCopies, MirrorQueue, MoneyDropMessages, MediaReposts."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_maint_all.db")
        con = sqlite3.connect(db_path)
        con.executescript("""
            CREATE TABLE Posts (post_num INTEGER PRIMARY KEY, timestamp REAL);
            CREATE TABLE PostCopies (post_num INTEGER, recipient_id INTEGER, message_id INTEGER);
            CREATE TABLE ChannelCopies (post_num INTEGER, channel_id INTEGER, message_id INTEGER);
            CREATE TABLE FileMirrors (file_id TEXT, mirror_type TEXT, url TEXT);
            CREATE TABLE MirrorQueue (file_id TEXT, mirror_type TEXT, attempts INTEGER, next_run_at REAL);
            CREATE TABLE MoneyDrops (drop_id TEXT PRIMARY KEY, status TEXT, created_at REAL, claimed_at REAL, refunded_at REAL);
            CREATE TABLE MoneyDropMessages (drop_id TEXT, chat_id INTEGER, message_id INTEGER);
            CREATE TABLE MediaReposts (board_id TEXT, file_unique_id TEXT, times INTEGER, first_post_num INTEGER, first_seen REAL);
        """)
        now = time.time()
        con.execute("INSERT INTO Posts VALUES (10, ?)", (now - 10 * 86400,))
        con.execute("INSERT INTO Posts VALUES (100, ?)", (now,))
        con.execute("INSERT INTO ChannelCopies VALUES (10, -1, 1)")
        con.execute("INSERT INTO ChannelCopies VALUES (100, -1, 2)")
        con.execute("INSERT INTO MirrorQueue VALUES ('f1', 'catbox', 12, ?)", (now,))
        con.execute("INSERT INTO MirrorQueue VALUES ('f2', 'catbox', 0, ?)", (now,))
        con.execute("INSERT INTO MoneyDrops VALUES ('d1', 'expired', ?, NULL, ?)", (now - 86400 * 3, now - 86400 * 2))
        con.execute("INSERT INTO MoneyDropMessages VALUES ('d1', 1, 1)")
        con.execute("INSERT INTO MediaReposts VALUES ('b', 'old', 1, 10, ?)", (now - 200 * 86400,))
        con.commit()

        assert maintenance.clean_old_channelcopies(con, retention_days=7, batch_size=100) == 1
        assert maintenance.clean_stale_mirror_queue(con, retention_days=7, max_attempts=10, batch_size=100) == 1
        assert maintenance.clean_old_moneydrop_messages(con, retention_hours=24, batch_size=100) == 1
        assert maintenance.clean_old_media_reposts(con, retention_days=180, batch_size=100) == 1
        con.close()


@pytest.mark.asyncio
async def test_task_manager_zero_task_and_http_client_leaks():
    """Verifies spawned tasks auto-clean on completion and WeakSet releases abandoned HTTP clients."""
    task_manager._background_tasks.clear()
    task_manager._tracked_http_clients.clear()

    async def quick(x):
        await asyncio.sleep(0)
        return x

    tasks = [task_manager.spawn_task(quick(i), name=f"q_{i}") for i in range(50)]
    await asyncio.gather(*tasks)
    await asyncio.sleep(0.01)
    assert len(task_manager._background_tasks) == 0

    # Exception-failing task must not leak from _background_tasks
    async def boom():
        raise ValueError("expected_test_boom")

    t_err = task_manager.spawn_task(boom(), name="boom_task")
    with pytest.raises(ValueError):
        await t_err
    await asyncio.sleep(0.01)
    assert t_err not in task_manager._background_tasks

    # WeakSet HTTP client release check
    class DummyClient:
        is_closed = False

    c = DummyClient()
    ref = weakref.ref(c)
    task_manager.register_http_client(c)
    assert len(task_manager._tracked_http_clients) == 1
    del c
    gc.collect()
    assert ref() is None
    assert len(task_manager._tracked_http_clients) == 0


def test_watchdog_rss_requires_sustained_breach():
    """Transient 1-poll RSS spike must not trigger bot.restart; sustained 3-poll breach must."""
    child = MagicMock()
    child.pid = 4321
    # 1st poll: spike above threshold; 2nd poll: normal; 3rd-5th polls: sustained breach -> restart
    poll_returns = [None, None, None, None, None, 0]
    child.poll.side_effect = poll_returns
    rss_high = int(bot_watchdog.SOFT_RESTART_RSS_BYTES + 100 * 1024 * 1024)
    rss_ok = int(bot_watchdog.SOFT_RESTART_RSS_BYTES // 2)
    mem_seq = [
        (rss_high, rss_high),  # transient spike (1/3)
        (rss_ok, rss_ok),      # drops -> resets streak
        (rss_high, rss_high),  # 1/3
        (rss_high, rss_high),  # 2/3
        (rss_high, rss_high),  # 3/3 -> writes bot.restart
    ]

    with tempfile.TemporaryDirectory() as td:
        restart_file = os.path.join(td, "bot.restart")
        from pathlib import Path
        restart_path = Path(restart_file)

        with patch.object(bot_watchdog, "WARMUP_SEC", 0.0), \
             patch.object(bot_watchdog, "POLL_SEC", 0.001), \
             patch.object(bot_watchdog, "RSS_HIGH_CONSECUTIVE_POLLS", 3), \
             patch.object(bot_watchdog, "BOT_RESTART_PATH", restart_path), \
             patch("bot_watchdog._get_child_memory_metrics", side_effect=mem_seq), \
             patch("bot_watchdog._read_lock_pid", return_value=None), \
             patch("bot_watchdog._read_heartbeat", return_value={"pid": 4321, "ts": time.time()}), \
             patch("bot_watchdog._heartbeat_is_fresh", return_value=True), \
             patch("bot_watchdog._is_restart_requested", return_value=False), \
             patch("bot_watchdog._close_child_log"), \
             patch("bot_watchdog._stop_requested", return_value=True), \
             patch("bot_watchdog._clear_bot_lock"):
            bot_watchdog._monitor_child(child)

        assert restart_path.exists()
        assert "rss_limit_exceeded" in restart_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_refresh_random_indexes_caps_per_board():
    """Ensures _VIDEO_CACHE, _IMAGE_CACHE, _THREAD_CACHE never exceed MAX_RANDOM_CACHE_PER_BOARD."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_random_cache.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.executescript("""
            CREATE TABLE Posts (
                post_num INTEGER PRIMARY KEY, board_id TEXT, thread_id TEXT,
                content TEXT, is_shadow INTEGER DEFAULT 0
            );
            CREATE TABLE Threads (
                thread_id TEXT PRIMARY KEY, board_id TEXT, thread_num INTEGER,
                is_archived INTEGER DEFAULT 0
            );
        """)
        rows = [
            (i, "b", None, json.dumps({"files": [{"type": "image", "file_id": f"fid_{i}"}]}), 0)
            for i in range(1, 2001)
        ]
        await conn.executemany("INSERT INTO Posts VALUES (?, ?, ?, ?, ?)", rows)

        old_v, old_i, old_t = dbmod._VIDEO_CACHE, dbmod._IMAGE_CACHE, dbmod._THREAD_CACHE
        old_max = dbmod._LAST_MAX_POST_NUM
        try:
            dbmod._VIDEO_CACHE = dbmod.defaultdict(list)
            dbmod._IMAGE_CACHE = dbmod.defaultdict(list)
            dbmod._THREAD_CACHE = dbmod.defaultdict(list)
            dbmod._LAST_MAX_POST_NUM = 0
            with patch.object(db_pool, "get_pool", AsyncMock(return_value=conn)), \
                 patch.object(dbmod, "get_pool", AsyncMock(return_value=conn)), \
                 patch.object(db_pool, "_db_connection", conn):
                await dbmod.refresh_random_indexes()
                assert len(dbmod._IMAGE_CACHE["b"]) == dbmod.MAX_RANDOM_CACHE_PER_BOARD
                assert dbmod._IMAGE_CACHE["b"][-1][0] == 2000
        finally:
            dbmod._VIDEO_CACHE, dbmod._IMAGE_CACHE, dbmod._THREAD_CACHE = old_v, old_i, old_t
            dbmod._LAST_MAX_POST_NUM = old_max
        await conn.close()


@pytest.mark.asyncio
async def test_db_transaction_releases_lock_and_resets_depth_on_error():
    """Verifies db_transaction rolls back, resets _task_tx_depth, and releases db_lock on failure."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_tx_leak.db")
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        await conn.execute("CREATE TABLE T (x INTEGER);")

        with patch.object(db_pool, "get_pool", AsyncMock(return_value=conn)):
            with pytest.raises(RuntimeError, match="boom"):
                async with db_pool.db_transaction(conn, immediate=True):
                    await conn.execute("INSERT INTO T VALUES (1)")
                    raise RuntimeError("boom")

            assert not db_pool.db_lock.locked()
            assert db_pool._task_tx_depth.get() == 0
            async with conn.execute("SELECT COUNT(*) FROM T") as c:
                assert (await c.fetchone())[0] == 0

            # Subsequent transaction must succeed cleanly without 'cannot start a transaction'
            async with db_pool.db_transaction(conn, immediate=True):
                await conn.execute("INSERT INTO T VALUES (42)")
            async with conn.execute("SELECT x FROM T") as c:
                assert [r[0] for r in await c.fetchall()] == [42]

        await conn.close()

