# -*- coding: utf-8 -*-
"""
tests/test_r4_econ_tax_and_lootbox_persistence.py
Comprehensive test suite for Worker R4 (v2):
1. Dynamic Real-Time Bank Interest in Abu Wealth Tax (apply_daily_wealth_tax).
2. SQLite Persistence for Daily Shop / Lootbox Limits (UserDailyLimits).
3. Lootbox Engine Integration with Persistent Daily Limits.
"""

import asyncio
import time
from datetime import datetime, timezone
import pytest

import common.database as db_mod
import lootbox_engine
import shared_state


@pytest.fixture(autouse=True)
def reset_daily_purchases():
    """Clear in-memory purchases before and after each test."""
    shared_state._DAILY_SHOP_PURCHASES.clear()
    yield
    shared_state._DAILY_SHOP_PURCHASES.clear()


# =============================================================================
# 1. DYNAMIC INTEREST WEALTH TAX TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_wealth_tax_calculates_dynamic_interest_in_real_time(isolated_test_db):
    """
    Test that active bank deposits continuously accrue real-time interest based on
    elapsed seconds and daily_rate, and that accrued interest is fully included
    in taxable wealth.
    """
    db = isolated_test_db
    uid = 999001
    # User has 0 in wallet, but 100,000 in active BankDeposit
    # Deposit created 2 days (172,800 seconds) ago with 2.5% daily rate (skuf tier)
    # Expected dynamic interest = 100,000 * 0.025 * 2 = +5,000 ₪
    # Total wealth = 100,000 + 5,000 = 105,000 ₪
    base_ts = 1787000000.0
    now_ts = base_ts + 2 * 86400.0

    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0.0)",
        (uid,)
    )
    await db.execute("""
        INSERT INTO BankDeposits (
            user_id, board_id, tier_id, principal, daily_rate, created_at,
            locked_until, last_accrual_at, accrued_interest, status
        ) VALUES (?, 'b', 'skuf', 100000.0, 0.025, ?, ?, ?, 0.0, 'active')
    """, (uid, base_ts, base_ts + 86400, base_ts))
    await db.commit()

    # Without dynamic interest, wealth would be 100,000 -> tax = 635.0 ₪
    # With dynamic interest (+5,000 ₪), wealth is 105,000 -> tax = 685.0 ₪
    tax_without_dynamic = db_mod.calculate_daily_wealth_tax(100000.0)
    tax_with_dynamic = db_mod.calculate_daily_wealth_tax(105000.0)
    assert tax_without_dynamic == 635.0
    assert tax_with_dynamic == 685.0
    assert tax_with_dynamic > tax_without_dynamic

    affected_cnt, confiscated, details = await db_mod.apply_daily_wealth_tax(db, current_ts=now_ts)

    assert affected_cnt == 1
    assert confiscated == tax_with_dynamic
    assert details[0]["old_wealth"] == 105000.0

    # Check BankDeposit record: tax (685.0 ₪) was deducted from principal
    # Remaining principal = 100,000 - 685 = 99,315 ₪
    # Accrued interest crystallized at 5,000 ₪
    # last_accrual_at updated to now_ts
    async with db.execute(
        "SELECT principal, accrued_interest, last_accrual_at FROM BankDeposits WHERE user_id = ?",
        (uid,)
    ) as c:
        row = await c.fetchone()
        assert row[0] == 99315.0
        assert row[1] == 5000.0
        assert row[2] == now_ts


@pytest.mark.asyncio
async def test_wealth_tax_handles_deposit_only_user_without_users_row(isolated_test_db):
    """
    Verify that users with active bank deposits who have no row in Users table
    are properly detected and taxed via CTE join.
    """
    db = isolated_test_db
    uid = 999002
    base_ts = 1787000000.0
    now_ts = base_ts + 86400.0

    # User exists ONLY in BankDeposits, NOT in Users table
    await db.execute("""
        INSERT INTO BankDeposits (
            user_id, board_id, tier_id, principal, daily_rate, created_at,
            locked_until, last_accrual_at, accrued_interest, status
        ) VALUES (?, 'b', 'mmm_abu', 200000.0, 0.060, ?, ?, ?, 0.0, 'active')
    """, (uid, base_ts, base_ts + 86400, base_ts))
    await db.commit()

    # 6% daily on 200k = +12,000 ₪ interest in 1 day
    # Total wealth = 212,000 ₪
    expected_tax = db_mod.calculate_daily_wealth_tax(212000.0)
    affected_cnt, confiscated, details = await db_mod.apply_daily_wealth_tax(db, current_ts=now_ts)

    assert affected_cnt == 1
    assert confiscated == expected_tax
    assert details[0]["user_id"] == uid


# =============================================================================
# 2. SQLITE PERSISTENCE FOR DAILY PURCHASE LIMITS
# =============================================================================

@pytest.mark.asyncio
async def test_daily_limits_db_crud(isolated_test_db):
    """Test record_user_daily_limit, get_user_daily_limit, load_all_user_daily_limits."""
    db = isolated_test_db
    uid = 555111
    today = "2026-09-08"

    # Initially 0
    val0 = await db_mod.get_user_daily_limit(db, uid, "lootbox_gold", today)
    assert val0 == 0

    # Record 1 purchase
    val1 = await db_mod.record_user_daily_limit(db, uid, "lootbox_gold", today, increment=1)
    assert val1 == 1

    # Record 4 more purchases
    val5 = await db_mod.record_user_daily_limit(db, uid, "lootbox_gold", today, increment=4)
    assert val5 == 5

    # Check get_user_daily_limit
    val_check = await db_mod.get_user_daily_limit(db, uid, "lootbox_gold", today)
    assert val_check == 5

    # Load all
    all_limits = await db_mod.load_all_user_daily_limits(db, today)
    assert (uid, "lootbox_gold", today) in all_limits
    assert all_limits[(uid, "lootbox_gold", today)] == 5


@pytest.mark.asyncio
async def test_daily_limits_survives_bot_restart_via_sync(isolated_test_db):
    """
    Test that daily purchase counts survive simulated bot restart:
    Purchases saved to DB are rehydrated into shared_state._DAILY_SHOP_PURCHASES via sync_daily_limits_from_db.
    """
    db = isolated_test_db
    uid = 8858659148  # Bot user from report_r4
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Simulate purchasing 40 gold safes (the daily limit)
    await db_mod.record_user_daily_limit(db, uid, "lootbox_gold", today, increment=40)

    # SIMULATE BOT RESTART:
    # 1. In-memory dictionary is completely wiped
    shared_state._DAILY_SHOP_PURCHASES.clear()
    assert shared_state.get_user_daily_shop_buys(uid, "lootbox_gold") == 0

    # 2. Bot startup runs sync_daily_limits_from_db
    synced = await db_mod.sync_daily_limits_from_db(db, today)
    assert synced >= 1

    # 3. Now in-memory dictionary is restored
    assert shared_state.get_user_daily_shop_buys(uid, "lootbox_gold") == 40
    assert shared_state.get_user_daily_shop_buys(uid, "gold_safe") == 40  # Alias also synced

    # 4. Limit check now BLOCKS additional purchases
    allowed, cur, lim = shared_state.check_shop_purchase_limit(uid, "lootbox_gold")
    assert not allowed
    assert cur == 40
    assert lim == 40

    # Alias also blocked
    allowed_alias, cur_alias, lim_alias = shared_state.check_shop_purchase_limit(uid, "gold_safe")
    assert not allowed_alias
    assert cur_alias == 40
    assert lim_alias == 40


@pytest.mark.asyncio
async def test_cleanup_old_user_daily_limits(isolated_test_db):
    """Test cleanup_old_user_daily_limits cleans records older than keep_days."""
    db = isolated_test_db
    uid = 777888
    old_day = "2026-08-01"
    recent_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    await db_mod.record_user_daily_limit(db, uid, "lootbox_trash", old_day, 10)
    await db_mod.record_user_daily_limit(db, uid, "lootbox_trash", recent_day, 5)

    # Clean older than 7 days
    deleted = await db_mod.cleanup_old_user_daily_limits(db, keep_days=7)
    assert deleted == 1

    # Old day is deleted
    old_cnt = await db_mod.get_user_daily_limit(db, uid, "lootbox_trash", old_day)
    assert old_cnt == 0

    # Recent day remains
    recent_cnt = await db_mod.get_user_daily_limit(db, uid, "lootbox_trash", recent_day)
    assert recent_cnt == 5


# =============================================================================
# 3. LOOTBOX ENGINE PERSISTENT LIMITS INTEGRATION
# =============================================================================

@pytest.mark.asyncio
async def test_lootbox_engine_daily_limits_helpers(isolated_test_db):
    """Verify lootbox_engine helper methods for daily limits and persistence."""
    db = isolated_test_db
    uid = 123456

    # Check limits defined
    assert lootbox_engine.get_lootbox_daily_limit("trash") == 100
    assert lootbox_engine.get_lootbox_daily_limit("lootbox_trash") == 100
    assert lootbox_engine.get_lootbox_daily_limit("gold") == 40
    assert lootbox_engine.get_lootbox_daily_limit("lootbox_gold") == 40
    assert lootbox_engine.get_lootbox_daily_limit("gold_safe") == 40

    # Initially allowed
    assert lootbox_engine.can_open_lootbox(uid, "gold") is True
    allowed, cur, lim = lootbox_engine.check_lootbox_daily_limit(uid, "gold")
    assert allowed is True
    assert cur == 0
    assert lim == 40

    # Record persistent purchase via lootbox_engine
    new_cnt = await lootbox_engine.record_lootbox_purchase_persistent(db, uid, "gold")
    assert new_cnt == 1

    # Verify both memory and DB reflect the purchase
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db_cnt = await db_mod.get_user_daily_limit(db, uid, "lootbox_gold", today)
    assert db_cnt == 1

    # Record 39 more to hit the 40 limit
    for _ in range(39):
        await lootbox_engine.record_lootbox_purchase_persistent(db, uid, "gold")

    # Now limit should be reached
    assert lootbox_engine.can_open_lootbox(uid, "gold") is False
    allowed_p, cur_p, lim_p = await lootbox_engine.check_lootbox_daily_limit_persistent(db, uid, "gold")
    assert allowed_p is False
    assert cur_p == 40
    assert lim_p == 40

    # Aliases are also blocked
    assert lootbox_engine.can_open_lootbox(uid, "gold_safe") is False
    assert lootbox_engine.can_open_lootbox(uid, "lootbox_gold") is False
