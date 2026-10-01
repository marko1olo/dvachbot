# -*- coding: utf-8 -*-
import asyncio
import json
import time
from unittest import mock
import pytest

from daily_abu_airdrop_engine import (
    pick_daily_winners,
    format_daily_board_announcement,
    format_daily_pm,
    check_and_grant_newbie_post_bonus,
    fetch_daily_qualified_users,
    execute_daily_airdrop,
    DAILY_PRIZE_PER_WINNER,
    NEWBIE_GRANT_AMOUNT,
)


def test_pick_daily_winners_equal_chance():
    qualified = list(range(1001, 1021))  # 20 users
    winners = pick_daily_winners(qualified)
    assert len(winners) == 10
    assert len(set(winners)) == 10
    for w in winners:
        assert w in qualified


def test_pick_daily_winners_small_pool():
    qualified = [101, 102]
    winners = pick_daily_winners(qualified)
    assert set(winners) == {101, 102}


def test_format_daily_board_announcement():
    winners = [5264555563, 7414244332, 123605834]
    text = format_daily_board_announcement(winners, pool_size=15, payout=5000)
    assert "5,000 ₪" in text
    assert "3 из 15" in text
    assert "СЧАСТЛИВЧИКИ СЕГОДНЯ" in text


def test_format_daily_pm():
    text = format_daily_pm(payout=5000, winner_count=5, pool_size=20)
    assert "5,000 ₪" in text
    assert "/wallet" in text


@pytest.mark.asyncio
async def test_newbie_grant_logic(isolated_test_db):
    db = isolated_test_db
    user_id = 999001
    board_id = "b"

    # Seed initial Abu yacht fund
    await db.execute(
        "INSERT INTO GlobalStats (key, value) VALUES ('abu_yacht_fund', '100000') "
        "ON CONFLICT(key) DO UPDATE SET value = '100000'"
    )
    # Seed user with 2 posts
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, posts_count, active_items) "
        "VALUES (?, ?, 0, 2, '{}')",
        (user_id, board_id)
    )
    await db.commit()

    mock_bot = mock.AsyncMock()

    with mock.patch("common.db_pool.get_pool", return_value=db):
        # 1st call: grant given
        res1 = await check_and_grant_newbie_post_bonus(user_id, board_id, mock_bot)
        assert res1 is True
        mock_bot.send_message.assert_awaited_once()

        # Check balance
        async with db.execute("SELECT balance, active_items FROM Users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            assert row[0] == float(NEWBIE_GRANT_AMOUNT)
            items = json.loads(row[1])
            assert items.get("newbie_abu_grant") is True

        # 2nd call: already granted -> False
        mock_bot.reset_mock()
        res2 = await check_and_grant_newbie_post_bonus(user_id, board_id, mock_bot)
        assert res2 is False
        mock_bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_daily_airdrop_execution(isolated_test_db):
    db = isolated_test_db
    now_ts = time.time()

    # Seed Abu fund
    await db.execute(
        "INSERT INTO GlobalStats (key, value) VALUES ('abu_yacht_fund', '500000') "
        "ON CONFLICT(key) DO UPDATE SET value = '500000'"
    )

    # Seed 5 users with > 2 posts in last 24h
    for uid in [8001, 8002, 8003, 8004, 8005]:
        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 0, 10)",
            (uid,)
        )
        for i in range(3):
            await db.execute(
                "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) "
                "VALUES ('b', ?, '{\"text\": \"post\"}', ?, 0)",
                (uid, now_ts - 1000 - i * 10)
            )

    # Seed 1 user with only 1 post (should NOT qualify)
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (8099, 'b', 0, 1)",
    )
    await db.execute(
        "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) "
        "VALUES ('b', 8099, '{\"text\": \"single\"}', ?, 0)",
        (now_ts - 500,)
    )
    await db.commit()

    with mock.patch("common.db_pool.get_pool", return_value=db):
        qualified = await fetch_daily_qualified_users(db)
        assert len(qualified) == 5
        assert 8099 not in qualified

        mock_bot = mock.AsyncMock()
        bots = {"b": mock_bot}
        res = await execute_daily_airdrop(db, bots)
        assert res["status"] == "success"
        assert res["winner_count"] == 5
        assert res["payout_per_winner"] == DAILY_PRIZE_PER_WINNER

        # Verify all 5 transactions were recorded without data loss
        async with db.execute("SELECT COUNT(*) FROM UserTransactions WHERE category = 'daily_airdrop'") as cur:
            tx_count = (await cur.fetchone())[0]
            assert tx_count == 5

        # Duplicate run within 20h window is skipped
        res_dup = await execute_daily_airdrop(db, bots)
        assert res_dup["status"] == "skipped"
        assert res_dup["reason"] == "already_ran_recently"


@pytest.mark.asyncio
async def test_newbie_grant_empty_abu_fund(isolated_test_db):
    db = isolated_test_db
    user_id = 999888
    # Abu fund is 0
    await db.execute(
        "INSERT INTO GlobalStats (key, value) VALUES ('abu_yacht_fund', '0') "
        "ON CONFLICT(key) DO UPDATE SET value = '0'"
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, posts_count, active_items) VALUES (?, 'b', 0, 1, '{}')",
        (user_id,)
    )
    await db.commit()

    mock_bot = mock.AsyncMock()
    with mock.patch("common.db_pool.get_pool", return_value=db):
        res = await check_and_grant_newbie_post_bonus(user_id, "b", mock_bot)
        assert res is False

        # Balance remains 0
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (user_id,)) as cur:
            assert (await cur.fetchone())[0] == 0.0


@pytest.mark.asyncio
async def test_daily_airdrop_empty_fund_skipped(isolated_test_db):
    db = isolated_test_db
    now_ts = time.time()
    await db.execute(
        "INSERT INTO GlobalStats (key, value) VALUES ('abu_yacht_fund', '0') "
        "ON CONFLICT(key) DO UPDATE SET value = '0'"
    )
    # 3 active users
    for uid in [7001, 7002, 7003]:
        await db.execute("INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 0, 5)", (uid,))
        for i in range(3):
            await db.execute(
                "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES ('b', ?, '{}', ?, 0)",
                (uid, now_ts - 100 - i * 10)
            )
    await db.commit()

    with mock.patch("common.db_pool.get_pool", return_value=db):
        res = await execute_daily_airdrop(db, {})
        assert res["status"] == "skipped"
        assert res["reason"] == "abu_fund_empty"


@pytest.mark.asyncio
async def test_fetch_daily_qualified_users_excludes_banned(isolated_test_db):
    db = isolated_test_db
    now_ts = time.time()
    # User 6001: active, 3 posts
    await db.execute("INSERT INTO Users (user_id, board_id, balance, posts_count, status) VALUES (6001, 'b', 0, 3, 'active')")
    for i in range(3):
        await db.execute("INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES ('b', 6001, '{}', ?, 0)", (now_ts - 50,))
    # User 6002: banned, 3 posts
    await db.execute("INSERT INTO Users (user_id, board_id, balance, posts_count, status) VALUES (6002, 'b', 0, 3, 'banned')")
    for i in range(3):
        await db.execute("INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES ('b', 6002, '{}', ?, 0)", (now_ts - 50,))
    await db.commit()

    qualified = await fetch_daily_qualified_users(db)
    assert 6001 in qualified
    assert 6002 not in qualified


def test_pick_daily_winners_deduplicates_input():
    # List with duplicated user IDs
    qualified_with_dupes = [101, 101, 102, 102, 103, 103]
    winners = pick_daily_winners(qualified_with_dupes)
    assert len(winners) == len(set(winners))

