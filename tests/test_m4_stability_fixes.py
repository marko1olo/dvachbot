import pytest
import asyncio
import aiosqlite
from common.spam_filter import check_flood, _user_request_timestamps
from common.database import get_abu_fund_total
import drop_engine


@pytest.mark.asyncio
async def test_check_flood_record_history_false():
    """
    Verifies that check_flood with record_history=False:
    1. Correctly detects flood if prior timestamps exceed threshold (BURST_FLOOD_LIMIT = 8).
    2. Does NOT append the new timestamp to tracker deque.
    3. Correctly returns non-flood if threshold is not exceeded, without appending to deque.
    """
    user_id = 987654321
    board_id = "b"
    t0 = 1000.0

    # Clear state for user
    _user_request_timestamps[user_id].clear()

    # Step 1: When no prior messages, record_history=False should return not flooding and leave tracker empty
    is_fl, reason = check_flood(user_id, board_id, now_ts=t0, record_history=False, is_reply=False)
    assert not is_fl, f"Should not be flood: {reason}"
    assert len(_user_request_timestamps[user_id]) == 0, "Tracker deque must remain empty when record_history=False"

    # Step 2: Simulate 8 normal messages recorded in history (BURST_FLOOD_LIMIT is 8)
    for i in range(8):
        is_fl, _ = check_flood(user_id, board_id, now_ts=t0 + (i * 0.4), record_history=True, is_reply=False)
        assert not is_fl
    assert len(_user_request_timestamps[user_id]) == 8

    # Step 3: 9th message at t0 + 3.5 with record_history=False
    # 8 prior + 1 current = 9 messages within 3.5s (<= 4.0s window), exceeding burst limit of 8
    is_fl, reason = check_flood(user_id, board_id, now_ts=t0 + 3.5, record_history=False, is_reply=False)
    assert is_fl, "Should detect burst flood even when record_history=False"
    assert "Burst флуд" in reason
    # Crucial: Tracker must NOT have the 9th timestamp appended
    assert len(_user_request_timestamps[user_id]) == 8, "Tracker must NOT append timestamp when record_history=False"

    # Clean up
    _user_request_timestamps[user_id].clear()


@pytest.mark.asyncio
async def test_create_money_drop_fee_handling():
    """
    Verifies that create_money_drop:
    1. Defaults to fee_percent=0.0 (100% amount to drop, 0 fee to Abu Fund).
    2. Supports custom fee_percent (e.g. 0.05, 0.10) with exact fee deducted to Abu Fund.
    """
    db_lock = asyncio.Lock()
    async with aiosqlite.connect(":memory:") as db:
        await db.execute(
            """CREATE TABLE Users (
                user_id INTEGER,
                board_id TEXT,
                balance INTEGER DEFAULT 0,
                PRIMARY KEY(user_id, board_id)
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS MoneyDrops (
                drop_id TEXT PRIMARY KEY,
                donor_id INTEGER,
                board_id TEXT,
                amount REAL,
                status TEXT,
                created_at REAL,
                claimed_by INTEGER,
                claimed_board_id TEXT,
                claimed_at REAL,
                refunded_at REAL
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS UserTransactions (
                tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                tx_type TEXT,
                details TEXT,
                created_at REAL
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS GlobalStats (
                key TEXT PRIMARY KEY,
                value TEXT
            )"""
        )

        donor_id = 111222
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 50000)", (donor_id,))
        await db.commit()

        # Case A: Default fee (0%)
        drop_engine.reset_drop_cooldowns()
        ok_a, msg_a, drop_a = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="DonorA",
            board_id="b",
            amount=1000,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
        )
        assert ok_a, f"Failed to create drop: {msg_a}"
        assert drop_a.amount == 1000, f"Expected 1000 in drop_a, got {drop_a.amount}"

        # Verify AbuFund is still 0
        abu_bal = await get_abu_fund_total(db)
        assert abu_bal == 0.0, f"AbuFund should have 0 fee, got {abu_bal}"

        # Case B: 5% fee explicitly passed
        drop_engine.reset_drop_cooldowns()
        ok_b, msg_b, drop_b = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="DonorB",
            board_id="b",
            amount=1000,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
            fee_percent=0.05,
        )
        assert ok_b, f"Failed to create drop: {msg_b}"
        assert drop_b.amount == 950, f"Expected 950 in drop_b (5% fee), got {drop_b.amount}"

        # Verify AbuFund received 50
        abu_bal = await get_abu_fund_total(db)
        assert abu_bal == 50.0, f"AbuFund should have received 50 ₪ fee, got {abu_bal}"

        # Case C: 10% fee explicitly passed
        drop_engine.reset_drop_cooldowns()
        ok_c, msg_c, drop_c = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="DonorC",
            board_id="b",
            amount=2000,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
            fee_percent=0.10,
        )
        assert ok_c, f"Failed to create drop: {msg_c}"
        assert drop_c.amount == 1800, f"Expected 1800 in drop_c (10% fee), got {drop_c.amount}"

        # Verify AbuFund received additional 200 (total 250)
        abu_bal = await get_abu_fund_total(db)
        assert abu_bal == 250.0, f"AbuFund should have received total 250 ₪, got {abu_bal}"
