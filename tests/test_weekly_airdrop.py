# -*- coding: utf-8 -*-
import pytest
import aiosqlite
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from weekly_airdrop_engine import (
    calculate_weekly_pool,
    compute_airdrop_allocations,
    seconds_until_next_sunday_2100,
    fetch_weekly_contributors,
    execute_weekly_airdrop,
    MIN_WEEKLY_POOL,
    POST_BONUS_RATE,
    MAX_USER_SHARE
)
from market_event import seconds_until_next_midnight_msk


def test_calculate_weekly_pool():
    # 0 posts -> base minimum
    assert calculate_weekly_pool(0) == MIN_WEEKLY_POOL
    # Negative -> base minimum
    assert calculate_weekly_pool(-10) == MIN_WEEKLY_POOL
    # 10,000 posts -> base + 100,000
    expected = MIN_WEEKLY_POOL + 10000 * POST_BONUS_RATE
    assert calculate_weekly_pool(10000) == expected


def test_compute_airdrop_allocations_empty():
    assert compute_airdrop_allocations([], 100_000) == []
    assert compute_airdrop_allocations([{"user_id": 1, "posts_count": 10}], 0) == []


def test_compute_airdrop_allocations_proportional_and_capped():
    pool = 100_000.0
    contributors = [
        {"user_id": 101, "posts_count": 5000},  # Giant whale (5000 posts)
        {"user_id": 102, "posts_count": 2000},  # Second whale (2000 posts)
        {"user_id": 103, "posts_count": 500},   # Medium (500 posts)
        {"user_id": 104, "posts_count": 100},   # Active (100 posts)
        {"user_id": 105, "posts_count": 50},    # Regular (50 posts)
        {"user_id": 106, "posts_count": 10},    # Small (10 posts)
        {"user_id": 107, "posts_count": 5},     # Threshold (5 posts)
    ]
    allocations = compute_airdrop_allocations(contributors, pool, max_share=0.15)

    assert len(allocations) == len(contributors)

    # 1. Whale cannot exceed max_share (15% = 15,000 ₪)
    whale = next(a for a in allocations if a["user_id"] == 101)
    assert whale["payout"] <= pool * 0.15 + 1  # 15,000 ₪ max

    # 2. Ordered by payout
    payouts = [a["payout"] for a in allocations]
    assert payouts == sorted(payouts, reverse=True)

    # 3. Smaller active user still gets a solid payout
    small = next(a for a in allocations if a["user_id"] == 106)
    assert small["payout"] > 500  # Gets hundreds of shekels, not 0

    # 4. Total sum distributed is very close to pool (within rounding tolerance)
    total_distributed = sum(payouts)
    assert abs(total_distributed - pool) < 50


def test_get_seconds_until_next_weekly_run():
    from weekly_airdrop_engine import get_seconds_until_next_weekly_run
    # 1. First run ever (last_run_ts <= 0) -> exactly 900 seconds (15 min)
    target, sleep_sec = get_seconds_until_next_weekly_run(0.0, 1000.0)
    assert sleep_sec == 900.0

    # 2. Subsequent run -> exactly 7 days (604800s) from last run
    last_run = 1000.0
    now = 1000.0 + 86400.0  # 1 day later
    target, sleep_sec = get_seconds_until_next_weekly_run(last_run, now)
    assert sleep_sec == 6 * 86400.0

def test_seconds_until_next_sunday_2100():
    msk = timezone(timedelta(hours=3))
    now = datetime.now(timezone.utc).astimezone(msk)
    target, sleep_sec = seconds_until_next_sunday_2100(now)

    assert sleep_sec > 0
    assert target.weekday() == 6  # Sunday
    assert target.hour == 21
    assert target.minute == 0


def test_seconds_until_next_midnight_msk():
    msk = timezone(timedelta(hours=3))
    now = datetime.now(timezone.utc).astimezone(msk)
    target, sleep_sec = seconds_until_next_midnight_msk(now)

    assert sleep_sec > 0
    assert target.hour == 0
    assert target.minute == 0


@pytest.mark.asyncio
async def test_fetch_weekly_contributors_and_execute_airdrop():
    # Setup in-memory SQLite db
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE Posts (
                post_num INTEGER PRIMARY KEY,
                board_id TEXT,
                author_id INTEGER,
                content TEXT,
                timestamp REAL,
                is_shadow INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE Users (
                user_id INTEGER,
                board_id TEXT,
                balance REAL DEFAULT 0.0,
                PRIMARY KEY (user_id, board_id)
            )
        """)
        await db.execute("""
            CREATE TABLE UserTransactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                category TEXT,
                description TEXT,
                timestamp INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE GlobalStats (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("INSERT INTO GlobalStats (key, value) VALUES ('abu_yacht_fund', '1000000')")
        await db.commit()

        # Insert test posts:
        # User 1: 10 posts (recent)
        # User 2: 5 posts (recent)
        # User 3: 2 posts (recent, below min_posts=3 threshold)
        # User 4: 10 posts (old, > 7 days ago)
        now = time.time()
        for i in range(10):
            await db.execute(
                "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES ('b', 1, '{\"type\":\"text\"}', ?, 0)",
                (now - i * 100,)
            )
        for i in range(5):
            await db.execute(
                "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES ('b', 2, '{\"type\":\"text\"}', ?, 0)",
                (now - i * 200,)
            )
        for i in range(2):
            await db.execute(
                "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES ('b', 3, '{\"type\":\"text\"}', ?, 0)",
                (now - i * 300,)
            )
        for i in range(10):
            await db.execute(
                "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES ('b', 4, '{\"type\":\"text\"}', ?, 0)",
                (now - 10 * 86400,)  # 10 days ago
            )
        await db.commit()

        # 1. Fetch contributors
        contributors = await fetch_weekly_contributors(db, days=7, min_posts=3)
        uids = [c["user_id"] for c in contributors]
        assert uids == [1, 2]  # User 3 (<3 posts) and User 4 (>7 days) excluded!

        # 2. Execute airdrop
        mock_bot = AsyncMock()
        bots = {"b": mock_bot}
        res = await execute_weekly_airdrop(db, bots)

        assert res["status"] == "success"
        assert res["recipients_count"] == 2
        assert res["total_posts"] == 15

        # Check balances
        async with db.execute("SELECT user_id, balance FROM Users") as cur:
            rows = await cur.fetchall()
            balances = dict(rows)
            assert balances[1] > 0
            assert balances[2] > 0
            assert balances[1] > balances[2]  # User 1 had 10 posts vs User 2's 5 posts

        # Check transactions recorded
        async with db.execute("SELECT COUNT(*) FROM UserTransactions WHERE category='airdrop'") as cur:
            tx_count = (await cur.fetchone())[0]
            assert tx_count == 2

        # Check duplicate protection: running immediately again should be skipped
        res2 = await execute_weekly_airdrop(db, bots)
        assert res2["status"] == "skipped"
        assert res2["reason"] == "already_ran_recently"
