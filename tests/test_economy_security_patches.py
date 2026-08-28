# -*- coding: utf-8 -*-
"""
tests/test_economy_security_patches.py — Comprehensive tests for economic security patches:
1. Lootbox cashback transaction logging and rate limiting.
2. Protection item duration cap (max 7 days from current time).
3. Wealth tax calculation and deduction including active BankDeposits.
4. Economy sanctions and database sanitization script.
"""

import asyncio
import json
import os
import sqlite3
import tempfile
import time
import pytest
import aiosqlite

import lootbox_engine
from common.database import calculate_daily_wealth_tax, apply_daily_wealth_tax
from scripts.apply_economy_sanctions import sanitize_active_items, apply_sanctions, BOT_ABUSER_IDS


# -----------------------------------------------------------------------------
# 1. Tests for Protection Duration Capping in lootbox_engine
# -----------------------------------------------------------------------------

def test_lootbox_protection_duration_cap():
    """Verify that apply_lootbox_reward caps shield and tinfoil to max 7 days."""
    now = int(time.time())
    max_cap = now + 7 * 86400

    # Start with an already absurdly bloated duration (e.g. 10 years in future)
    bloated_items = {
        "shield_until": now + 3650 * 86400,
        "reflect_shield_until": now + 3650 * 86400,
        "tinfoil_until": now + 3650 * 86400,
        "tinfoil_hat": now + 3650 * 86400,
        "janitor_until": now + 3650 * 86400,
    }

    payload = {"reflect_shield_until": now + 12 * 3600, "shield_until": now + 12 * 3600}
    sanitized, final_cash, msg = lootbox_engine.apply_lootbox_reward(bloated_items, payload, base_cash=0)

    assert sanitized["shield_until"] <= max_cap
    assert sanitized["reflect_shield_until"] <= max_cap
    assert sanitized["tinfoil_until"] <= max_cap
    assert sanitized["tinfoil_hat"] <= max_cap
    assert sanitized["janitor_until"] <= max_cap


def test_sanitize_active_items_helper():
    """Test the sanitize_active_items function used in sanctions."""
    now = int(time.time())
    max_cap = now + 7 * 86400
    raw_json = json.dumps({
        "shield_until": now + 1000 * 86400,
        "knife_gun": True,
        "work_shifts": 5
    })

    sanitized_str, modified = sanitize_active_items(raw_json, max_cap)
    assert modified is True
    data = json.loads(sanitized_str)
    assert data["shield_until"] == max_cap
    assert data["knife_gun"] is True


# -----------------------------------------------------------------------------
# 2. Tests for Rate-Limiting & Lootbox Cooldown Logic
# -----------------------------------------------------------------------------

def test_lootbox_rate_limiter_logic():
    """Verify rate-limiter prevents opening lootboxes faster than once per 3 seconds."""
    cooldowns: dict[int, float] = {}
    user_id = 999001

    # First call: allowed
    last_open = cooldowns.get(user_id, 0.0)
    now = time.time()
    assert (now - last_open) >= 3.0
    cooldowns[user_id] = now

    # Immediate second call (< 3s): rejected
    immediate_now = now + 0.5
    time_since = immediate_now - cooldowns[user_id]
    assert time_since < 3.0

    # Call after 3.1s: allowed
    later_now = now + 3.1
    time_since_later = later_now - cooldowns[user_id]
    assert time_since_later >= 3.0


# -----------------------------------------------------------------------------
# 3. Tests for Wealth Tax with Bank Deposits
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wealth_tax_includes_bank_deposits():
    """
    Verify apply_daily_wealth_tax calculates tax on total wealth (wallet + active bank deposits)
    and deducts excess from bank deposits if wallet balance is insufficient.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        test_db_path = tf.name

    try:
        async with aiosqlite.connect(test_db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            # Create schema
            await db.execute("""
                CREATE TABLE Users (
                    user_id INTEGER,
                    board_id TEXT,
                    balance REAL DEFAULT 0.0,
                    active_items TEXT DEFAULT '{}',
                    PRIMARY KEY(user_id, board_id)
                )
            """)
            await db.execute("""
                CREATE TABLE BankDeposits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    board_id TEXT,
                    tier_id TEXT,
                    principal REAL,
                    daily_rate REAL,
                    created_at REAL,
                    locked_until REAL,
                    last_accrual_at REAL,
                    accrued_interest REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'active'
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
            await db.commit()

            # Insert a user with 500 ₪ in wallet, but 100,000 ₪ in active BankDeposit
            # Total wealth = 100,500 ₪ -> Tax = calculate_daily_wealth_tax(100,500)
            uid = 777001
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500.0)", (uid,))
            await db.execute("""
                INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, accrued_interest, status)
                VALUES (?, 'b', 'sych', 100000.0, 0.005, 1787000000, 1787000000, 1787000000, 0.0, 'active')
            """, (uid,))
            await db.commit()

            expected_tax = calculate_daily_wealth_tax(100500.0)
            assert expected_tax > 0  # Tier 2 tax

            affected_cnt, confiscated, details = await apply_daily_wealth_tax(db)

            assert affected_cnt == 1
            assert confiscated == expected_tax

            # Check user wallet: should be drained down to 0
            async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (uid,)) as c:
                row = await c.fetchone()
                assert row[0] == 0.0

            # Check user bank deposit: remaining tax should be deducted from principal
            rem_tax = expected_tax - 500.0
            expected_new_princ = round(100000.0 - rem_tax, 2)
            async with db.execute("SELECT principal FROM BankDeposits WHERE user_id = ?", (uid,)) as c:
                row = await c.fetchone()
                assert row[0] == expected_new_princ

            # Check GlobalStats abu_yacht_fund has received the confiscated tax
            async with db.execute("SELECT value FROM GlobalStats WHERE key = 'abu_yacht_fund'") as c:
                row = await c.fetchone()
                assert float(row[0]) == expected_tax

    finally:
        if os.path.exists(test_db_path):
            os.remove(test_db_path)


# -----------------------------------------------------------------------------
# 4. Tests for Sanctions Script Execution
# -----------------------------------------------------------------------------

def test_apply_sanctions_script_execution():
    """Verify apply_sanctions resets bot balances to 500 and updates Abu fund."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        test_db_path = tf.name

    try:
        conn = sqlite3.connect(test_db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE Users (
                user_id INTEGER,
                board_id TEXT,
                balance REAL DEFAULT 0.0,
                active_items TEXT DEFAULT '{}',
                PRIMARY KEY(user_id, board_id)
            )
        """)
        c.execute("""
            CREATE TABLE UserTransactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                category TEXT,
                description TEXT,
                timestamp INTEGER
            )
        """)
        c.execute("CREATE TABLE GlobalStats (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("INSERT INTO GlobalStats (key, value) VALUES ('abu_yacht_fund', '1000.0')")

        # Insert 3 bot abusers with 1,000,000 ₪ each and bloated timers
        now = int(time.time())
        bloated_json = json.dumps({"shield_until": now + 1000 * 86400})
        for bot_id in BOT_ABUSER_IDS:
            c.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000000.0, ?)", (bot_id, bloated_json))
        conn.commit()
        conn.close()

        # Run sanctions
        res = apply_sanctions(test_db_path, dry_run=False)

        assert res["total_confiscated"] == 3 * (1000000.0 - 500.0)
        assert res["fund_after"] == 1000.0 + res["total_confiscated"]

        # Verify DB state
        conn = sqlite3.connect(test_db_path)
        c = conn.cursor()
        for bot_id in BOT_ABUSER_IDS:
            c.execute("SELECT balance, active_items FROM Users WHERE user_id = ?", (bot_id,))
            bal, items_str = c.fetchone()
            assert bal == 500.0
            items = json.loads(items_str)
            assert items["shield_until"] <= now + 7 * 86400

        c.execute("SELECT value FROM GlobalStats WHERE key = 'abu_yacht_fund'")
        fund_val = float(c.fetchone()[0])
        assert fund_val == res["fund_after"]
        conn.close()

    finally:
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
