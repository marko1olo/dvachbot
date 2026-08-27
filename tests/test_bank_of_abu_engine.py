# -*- coding: utf-8 -*-
"""
tests/test_bank_of_abu_engine.py — E2E and Unit Test Suite for DvachBot Bank of Abu / Safe Engine

Coverage Matrix:
- Tier 1 (Feature / Happy Path):
    * Bank deposit creation for all 3 tiers: 'sych', 'skuf', 'mmm_abu'.
    * Dynamic continuous per-second interest accrual via calculate_deposit_state.
    * Complete deposit isolation: funds in BankDeposits are excluded from get_user_global_balance.
    * Robbery insulation: Bank deposits are completely immune to /rob and street attack thefts.
- Tier 2 (Boundary Value Analysis & Negative Cases):
    * Depositing 0 ₪ or negative shekels (rejected, balance unchanged).
    * Depositing more than liquid wallet balance (rejected, balance unchanged).
    * Withdrawing non-existent or foreign deposit IDs (rejected).
    * Withdrawing immediately (0 elapsed seconds yields 0 interest).
    * Double-withdrawal prevention (cannot withdraw already closed deposit).
- Tier 3 (Lockup Enforcement, Early Penalties & Pyramid Risk):
    * Tier 'sych' (Сейф Сыча): 0.5% daily yield (0.005 / 86400 per sec), 0 lockup, 1% withdrawal fee, 0% risk.
    * Tier 'skuf' (Депозит Скуфа): 2.5% daily yield, 72h lockup (259200 sec).
        - Premature withdrawal (< 72h): loses all accrued interest + 3% principal penalty deducted.
        - Mature withdrawal (>= 72h): 0% penalty, full principal + full accrued interest.
    * Tier 'mmm_abu' (МММ Абу): 6.0% daily yield, 24h lockup (86400 sec).
        - 3% risk of 50% pyramid default / tax audit on withdrawal.
        - Normal withdrawal (no default): full principal + full interest.
- Tier 4 (Workload & E2E Real-World Journey):
    * Multi-day interest accumulation lifecycle.
    * User portfolio summary via get_user_bank_summary.
    * Safe wealth accumulation: user deposits earnings, gets street-attacked with empty wallet, bank funds stay 100% safe and mature for payout.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
import aiosqlite

import common.config
import common.database
import common.db_pool


# ---------------------------------------------------------------------------
# Database Schema Helper for Bank Engine
# ---------------------------------------------------------------------------
async def _init_bank_test_db(db: aiosqlite.Connection):
    """Ensures base Users, UserTransactions, GlobalStats, and BankDeposits tables exist."""
    await db.execute("""
    CREATE TABLE IF NOT EXISTS GlobalStats (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS Users (
        user_id INTEGER NOT NULL,
        board_id TEXT NOT NULL DEFAULT 'b',
        balance REAL DEFAULT 0,
        active_items TEXT DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'active',
        PRIMARY KEY(user_id, board_id)
    )
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS UserTransactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        description TEXT NOT NULL,
        timestamp INTEGER NOT NULL
    )
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS BankDeposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        board_id TEXT NOT NULL DEFAULT 'b',
        tier_id TEXT NOT NULL,
        principal REAL NOT NULL,
        daily_rate REAL NOT NULL,
        created_at REAL NOT NULL,
        locked_until REAL NOT NULL,
        last_accrual_at REAL NOT NULL,
        accrued_interest REAL NOT NULL DEFAULT 0.0,
        status TEXT NOT NULL DEFAULT 'active',
        withdrawn_at REAL,
        withdrawn_amount REAL
    )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_bank_user_status ON BankDeposits(user_id, status)")


@pytest_asyncio.fixture
async def bank_db(tmp_path):
    """Creates an isolated temporary database for bank engine testing."""
    db_path = str(tmp_path / "test_bank.db")
    db = await aiosqlite.connect(db_path, isolation_level=None)
    await db.execute("PRAGMA busy_timeout = 10000;")
    await _init_bank_test_db(db)

    orig_conn = getattr(common.db_pool, "_db_connection", None)
    common.db_pool._db_connection = db
    pool_mock = AsyncMock(return_value=db)

    with patch.object(common.db_pool, "get_pool", pool_mock), \
         patch.object(common.database, "get_pool", pool_mock), \
         patch.object(common.db_pool, "db_lock", common.db_pool.LazyLock()):
        yield db

    common.db_pool._db_connection = orig_conn
    await db.close()


async def _set_user(db, user_id: int, balance: float = 0.0, active_items: dict = None, board_id: str = "b"):
    items_json = json.dumps(active_items or {}, ensure_ascii=False)
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = ?, active_items = ?",
        (user_id, board_id, balance, items_json, balance, items_json)
    )


# ---------------------------------------------------------------------------
# Import / Fallback Loader for bank_engine
# ---------------------------------------------------------------------------
try:
    import bank_engine
except ImportError:
    bank_engine = None


def _get_bank_module():
    if bank_engine is not None:
        return bank_engine
    import importlib
    try:
        return importlib.import_module("bank_engine")
    except Exception as e:
        pytest.skip(f"bank_engine not yet available: {e}")


# ===========================================================================
# TIER 1: CORE FUNCTIONALITY (HAPPY PATH)
# ===========================================================================

@pytest.mark.asyncio
async def test_bank_deposit_creation_sych_tier(bank_db):
    """Deposit into 'sych' tier deducts wallet balance and creates deposit record."""
    be = _get_bank_module()
    user_id = 3001
    await _set_user(bank_db, user_id, balance=1000.0)

    success, deposit, err = await be.create_bank_deposit(
        bank_db, user_id=user_id, board_id="b", tier_id="sych", amount=500.0
    )

    assert success is True
    assert err == "" or err is None
    assert deposit["principal"] == 500.0
    assert deposit["tier_id"] == "sych"
    assert deposit["status"] == "active"

    # Wallet balance must be 500
    bal = await common.database.get_user_global_balance(bank_db, user_id)
    assert bal == 500.0


@pytest.mark.asyncio
async def test_bank_deposit_creation_skuf_tier(bank_db):
    """Deposit into 'skuf' tier creates 3-day term deposit."""
    be = _get_bank_module()
    user_id = 3002
    await _set_user(bank_db, user_id, balance=2000.0)

    success, deposit, err = await be.create_bank_deposit(
        bank_db, user_id=user_id, board_id="b", tier_id="skuf", amount=1500.0
    )

    assert success is True
    assert deposit["tier_id"] == "skuf"
    assert deposit["principal"] == 1500.0

    bal = await common.database.get_user_global_balance(bank_db, user_id)
    assert bal == 500.0


@pytest.mark.asyncio
async def test_bank_deposit_creation_mmm_abu_tier(bank_db):
    """Deposit into 'mmm_abu' high-yield tier creates deposit."""
    be = _get_bank_module()
    user_id = 3003
    await _set_user(bank_db, user_id, balance=5000.0)

    success, deposit, err = await be.create_bank_deposit(
        bank_db, user_id=user_id, board_id="b", tier_id="mmm_abu", amount=3000.0
    )

    assert success is True
    assert deposit["tier_id"] == "mmm_abu"
    assert deposit["principal"] == 3000.0


@pytest.mark.asyncio
async def test_bank_deposit_safe_isolation_from_global_balance(bank_db):
    """Deposited funds are not counted in get_user_global_balance (Wallet)."""
    be = _get_bank_module()
    user_id = 3004
    await _set_user(bank_db, user_id, balance=10000.0)

    # Deposit 9500 in bank
    await be.create_bank_deposit(bank_db, user_id=user_id, board_id="b", tier_id="sych", amount=9500.0)

    # Liquid wallet balance must strictly be 500
    wallet_bal = await common.database.get_user_global_balance(bank_db, user_id)
    assert wallet_bal == 500.0


@pytest.mark.asyncio
async def test_bank_robbery_insulation(bank_db):
    """Funds deposited in Bank of Abu cannot be stolen by /rob or street attacks."""
    be = _get_bank_module()
    victim_id = 3005

    # Victim has 0 liquid wallet balance, but 50,000 in bank
    await _set_user(bank_db, victim_id, balance=50000.0)
    await be.create_bank_deposit(bank_db, victim_id, "b", "skuf", 50000.0)

    # Liquid balance is 0
    victim_liquid = await common.database.get_user_global_balance(bank_db, victim_id)
    assert victim_liquid == 0.0

    # Attacker tries to deduct / steal shekels from victim
    stolen, new_bal = await common.database.deduct_user_global_balance(bank_db, victim_id, "b", 1000.0)
    assert stolen is False  # Cannot steal from 0 liquid balance
    assert new_bal == 0.0


def test_bank_continuous_per_second_interest_accrual():
    """calculate_deposit_state continuously accrues interest per elapsed second."""
    be = _get_bank_module()
    now = 1700000000.0
    principal = 10000.0

    # 1. Sych (0.5% daily = 0.005 / 86400 per second)
    deposit_sych = {
        "principal": principal,
        "daily_rate": 0.005,
        "tier_id": "sych",
        "created_at": now,
        "last_accrual_at": now,
        "locked_until": now,
    }

    # At 86400s (1 day): interest = 10000 * 0.005 = 50.0 ₪
    state_1d = be.calculate_deposit_state(deposit_sych, now + 86400)
    assert pytest.approx(state_1d["accrued_interest"], rel=1e-3) == 50.0
    assert pytest.approx(state_1d["total_value"], rel=1e-3) == 10050.0
    assert state_1d["is_locked"] is False

    # At 43200s (12 hours): interest = 25.0 ₪
    state_half = be.calculate_deposit_state(deposit_sych, now + 43200)
    assert pytest.approx(state_half["accrued_interest"], rel=1e-3) == 25.0


# ===========================================================================
# TIER 2: BOUNDARY VALUE ANALYSIS & NEGATIVE TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_bank_deposit_zero_or_negative_amount_fails(bank_db):
    """Depositing 0 or negative shekels fails and leaves balance unchanged."""
    be = _get_bank_module()
    user_id = 3006
    await _set_user(bank_db, user_id, balance=500.0)

    # 0 amount
    s1, _, err1 = await be.create_bank_deposit(bank_db, user_id, "b", "sych", 0.0)
    assert s1 is False

    # Negative amount
    s2, _, err2 = await be.create_bank_deposit(bank_db, user_id, "b", "sych", -100.0)
    assert s2 is False

    bal = await common.database.get_user_global_balance(bank_db, user_id)
    assert bal == 500.0


@pytest.mark.asyncio
async def test_bank_deposit_more_than_wallet_balance_fails(bank_db):
    """Depositing 1000 ₪ with 200 ₪ in wallet fails."""
    be = _get_bank_module()
    user_id = 3007
    await _set_user(bank_db, user_id, balance=200.0)

    success, _, err = await be.create_bank_deposit(bank_db, user_id, "b", "sych", 1000.0)
    assert success is False
    assert "недостаточно" in err.lower() or "balance" in err.lower() or len(err) > 0

    bal = await common.database.get_user_global_balance(bank_db, user_id)
    assert bal == 200.0


@pytest.mark.asyncio
async def test_bank_withdraw_non_existent_deposit_fails(bank_db):
    """Withdrawing invalid deposit ID returns error."""
    be = _get_bank_module()
    user_id = 3008
    await _set_user(bank_db, user_id, balance=100.0)

    success, _, _, _, _, _, err = await be.withdraw_bank_deposit(bank_db, deposit_id=999999, user_id=user_id, board_id="b")
    assert success is False
    assert "найден" in err.lower() or "found" in err.lower() or len(err) > 0


@pytest.mark.asyncio
async def test_bank_withdraw_foreign_user_deposit_fails(bank_db):
    """User B cannot withdraw User A's deposit."""
    be = _get_bank_module()
    user_a = 3009
    user_b = 3010

    await _set_user(bank_db, user_a, balance=1000.0)
    await _set_user(bank_db, user_b, balance=0.0)

    _, deposit, _ = await be.create_bank_deposit(bank_db, user_a, "b", "sych", 500.0)

    # User B attempts to withdraw User A's deposit
    success, _, _, _, _, _, err = await be.withdraw_bank_deposit(bank_db, deposit["id"], user_b, "b")
    assert success is False


@pytest.mark.asyncio
async def test_bank_withdraw_zero_elapsed_seconds(bank_db):
    """Withdrawing immediately with 0 elapsed seconds pays out 0 interest."""
    be = _get_bank_module()
    user_id = 3011
    await _set_user(bank_db, user_id, balance=1000.0)

    _, deposit, _ = await be.create_bank_deposit(bank_db, user_id, "b", "sych", 1000.0)

    # Withdraw immediately
    success, payout, principal, interest, fee, _, _ = await be.withdraw_bank_deposit(
        bank_db, deposit["id"], user_id, "b"
    )

    assert success is True
    assert interest == 0.0 or interest < 1.0
    assert principal == 1000.0
    # Sych 1% fee on 1000 = 10 ₪ -> payout = 990 ₪
    assert payout == 990.0 or payout == 1000.0 - fee


@pytest.mark.asyncio
async def test_bank_double_withdrawal_prevention(bank_db):
    """Second withdrawal of the same deposit fails."""
    be = _get_bank_module()
    user_id = 3012
    await _set_user(bank_db, user_id, balance=1000.0)

    _, deposit, _ = await be.create_bank_deposit(bank_db, user_id, "b", "sych", 1000.0)

    # First withdrawal
    s1, _, _, _, _, _, _ = await be.withdraw_bank_deposit(bank_db, deposit["id"], user_id, "b")
    assert s1 is True

    # Second withdrawal
    s2, _, _, _, _, _, err2 = await be.withdraw_bank_deposit(bank_db, deposit["id"], user_id, "b")
    assert s2 is False
    assert "закрыт" in err2.lower() or "withdrawn" in err2.lower() or "уже" in err2.lower() or "найден" in err2.lower() or len(err2) > 0


# ===========================================================================
# TIER 3: LOCKUP & PENALTIES PER TIER
# ===========================================================================

@pytest.mark.asyncio
async def test_bank_tier_sych_yield_and_withdrawal_fee(bank_db):
    """Sych: 0.5% daily, 0 lockup, 1% fee deducted on withdrawal."""
    be = _get_bank_module()
    user_id = 3013
    principal = 2000.0
    created_at = time.time() - 86400 * 2  # 2 days ago

    await _set_user(bank_db, user_id, balance=0.0)
    await bank_db.execute(
        """
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, status)
        VALUES (?, 'b', 'sych', ?, 0.005, ?, ?, ?, 'active')
        """,
        (user_id, principal, created_at, created_at, created_at)
    )
    async with bank_db.execute("SELECT last_insert_rowid()") as c:
        dep_id = (await c.fetchone())[0]

    success, payout, princ, interest, fee, _, _ = await be.withdraw_bank_deposit(
        bank_db, dep_id, user_id, "b"
    )

    assert success is True
    # 2 days at 0.5% = 1.0% of 2000 = 20 ₪
    assert interest >= 19.0 and interest <= 21.0
    # Total before fee ~ 2020 ₪. 1% fee ~ 20.2 ₪. Payout ~ 2000 ₪
    assert fee >= 19.0 and fee <= 21.0
    assert payout == round(princ + interest - fee, 2)

    # Wallet credited with payout
    bal = await common.database.get_user_global_balance(bank_db, user_id)
    assert bal == payout


@pytest.mark.asyncio
async def test_bank_tier_skuf_mature_withdrawal_zero_penalty(bank_db):
    """Skuf: 2.5% daily, 72h lockup. Mature withdrawal after 72h has 0% penalty and full interest."""
    be = _get_bank_module()
    user_id = 3014
    principal = 1000.0
    now = time.time()
    created_at = now - (72 * 3600 + 10)  # 72 hours and 10 seconds ago
    locked_until = created_at + 72 * 3600

    await _set_user(bank_db, user_id, balance=0.0)
    await bank_db.execute(
        """
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, status)
        VALUES (?, 'b', 'skuf', ?, 0.025, ?, ?, ?, 'active')
        """,
        (user_id, principal, created_at, locked_until, created_at)
    )
    async with bank_db.execute("SELECT last_insert_rowid()") as c:
        dep_id = (await c.fetchone())[0]

    success, payout, princ, interest, penalty, _, _ = await be.withdraw_bank_deposit(
        bank_db, dep_id, user_id, "b"
    )

    assert success is True
    assert penalty == 0.0  # Mature -> 0 penalty
    # 3 days at 2.5% = 7.5% of 1000 = 75 ₪
    assert interest >= 74.0 and interest <= 76.0
    assert payout == round(princ + interest, 2)


@pytest.mark.asyncio
async def test_bank_tier_skuf_premature_withdrawal_penalty(bank_db):
    """Skuf: premature withdrawal (< 72h) forfeits interest and deducts 3% principal penalty."""
    be = _get_bank_module()
    user_id = 3015
    principal = 10000.0
    now = time.time()
    created_at = now - (24 * 3600)  # 24 hours ago (less than 72h lockup)
    locked_until = created_at + 72 * 3600

    await _set_user(bank_db, user_id, balance=0.0)
    await bank_db.execute(
        """
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, status)
        VALUES (?, 'b', 'skuf', ?, 0.025, ?, ?, ?, 'active')
        """,
        (user_id, principal, created_at, locked_until, created_at)
    )
    async with bank_db.execute("SELECT last_insert_rowid()") as c:
        dep_id = (await c.fetchone())[0]

    success, payout, princ, interest, penalty, _, _ = await be.withdraw_bank_deposit(
        bank_db, dep_id, user_id, "b", force_early=True
    )

    assert success is True
    assert interest == 0.0  # Forfeited
    # 3% of 10,000 = 300 ₪ penalty
    assert penalty == 300.0
    assert payout == 9700.0  # 10000 - 300


@pytest.mark.asyncio
async def test_bank_tier_mmm_abu_mature_withdrawal_normal(bank_db):
    """MMM Abu: 6.0% daily, 24h lockup. Mature withdrawal with no default pays full interest."""
    be = _get_bank_module()
    user_id = 3016
    principal = 5000.0
    now = time.time()
    created_at = now - (86400 + 10)  # 24 hours ago
    locked_until = created_at + 86400

    await _set_user(bank_db, user_id, balance=0.0)
    await bank_db.execute(
        """
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, status)
        VALUES (?, 'b', 'mmm_abu', ?, 0.060, ?, ?, ?, 'active')
        """,
        (user_id, principal, created_at, locked_until, created_at)
    )
    async with bank_db.execute("SELECT last_insert_rowid()") as c:
        dep_id = (await c.fetchone())[0]

    success, payout, princ, interest, penalty, is_default, _ = await be.withdraw_bank_deposit(
        bank_db, dep_id, user_id, "b", random_roll=0.50  # > 0.03 -> no default
    )

    assert success is True
    assert is_default is False
    # 1 day at 6.0% = 300 ₪
    assert interest >= 295.0 and interest <= 305.0
    assert payout == round(princ + interest, 2)


@pytest.mark.asyncio
async def test_bank_tier_mmm_abu_default_risk_triggers_50_percent_loss(bank_db):
    """MMM Abu: when 3% default risk triggers, user loses 50% of total payout."""
    be = _get_bank_module()
    user_id = 3017
    principal = 10000.0
    now = time.time()
    created_at = now - (86400 * 2)  # 2 days ago
    locked_until = created_at + 86400

    await _set_user(bank_db, user_id, balance=0.0)
    await bank_db.execute(
        """
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, status)
        VALUES (?, 'b', 'mmm_abu', ?, 0.060, ?, ?, ?, 'active')
        """,
        (user_id, principal, created_at, locked_until, created_at)
    )
    async with bank_db.execute("SELECT last_insert_rowid()") as c:
        dep_id = (await c.fetchone())[0]

    success, payout, princ, interest, penalty, is_default, _ = await be.withdraw_bank_deposit(
        bank_db, dep_id, user_id, "b", random_roll=0.01  # < 0.03 -> default triggers!
    )

    assert success is True
    assert is_default is True
    # Total ~ 11200 ₪ -> Payout ~ 5600 ₪
    assert payout > 5000.0 and payout < 6000.0


# ===========================================================================
# TIER 4: REAL-WORLD BANKING JOURNEY & ACCUMULATION
# ===========================================================================

@pytest.mark.asyncio
async def test_bank_user_portfolio_summary(bank_db):
    """get_user_bank_summary aggregates principal, accrued interest, and active deposits."""
    be = _get_bank_module()
    user_id = 3018
    now = time.time()

    await _set_user(bank_db, user_id, balance=0.0)
    # 2 active deposits, 1 withdrawn
    await bank_db.execute(
        """
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, status)
        VALUES (?, 'b', 'sych', 1000.0, 0.005, ?, ?, ?, 'active')
        """,
        (user_id, now - 86400, now - 86400, now - 86400)
    )
    await bank_db.execute(
        """
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, status)
        VALUES (?, 'b', 'skuf', 2000.0, 0.025, ?, ?, ?, 'active')
        """,
        (user_id, now - 86400 * 2, now + 86400, now - 86400 * 2)
    )
    await bank_db.execute(
        """
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, status)
        VALUES (?, 'b', 'sych', 500.0, 0.005, ?, ?, ?, 'withdrawn')
        """,
        (user_id, now - 86400 * 5, now - 86400 * 5, now - 86400 * 5)
    )

    tot_principal, tot_accrued, deposits = await be.get_user_bank_summary(bank_db, user_id)

    assert tot_principal == 3000.0  # 1000 + 2000
    assert len(deposits) == 2  # 2 active deposits
    assert tot_accrued > 0.0


@pytest.mark.asyncio
async def test_bank_safe_wealth_accumulation_during_street_attacks(bank_db):
    """Complete E2E workflow: Deposit -> Street attacks -> Compound Growth -> Mature Withdrawal."""
    be = _get_bank_module()
    user_id = 9991
    robber_id = 9992

    # Step 1: User earns 10,000 shekels and deposits 9,500 into 3-Day Skuf Deposit
    await _set_user(bank_db, user_id, balance=10000.0)
    await _set_user(bank_db, robber_id, balance=500.0)

    s, dep, _ = await be.create_bank_deposit(bank_db, user_id, "b", "skuf", 9500.0)
    assert s is True

    # Step 2: Robber attacks user on the street. Only remaining 500 wallet balance can be touched.
    stolen, new_bal = await common.database.deduct_user_global_balance(bank_db, user_id, "b", 500.0)
    assert stolen is True
    assert new_bal == 0.0

    # Further robbery attempts yield 0
    s2, _ = await common.database.deduct_user_global_balance(bank_db, user_id, "b", 100.0)
    assert s2 is False

    # Step 3: Fast forward 72 hours (3 days)
    created_at = time.time() - (72 * 3600 + 60)
    locked_until = created_at + 72 * 3600
    await bank_db.execute(
        "UPDATE BankDeposits SET created_at = ?, locked_until = ?, last_accrual_at = ? WHERE id = ?",
        (created_at, locked_until, created_at, dep["id"])
    )

    # Step 4: User withdraws mature funds safely
    success, payout, princ, interest, penalty, _, _ = await be.withdraw_bank_deposit(
        bank_db, dep["id"], user_id, "b"
    )

    assert success is True
    assert penalty == 0.0
    # 3 days * 2.5% = 7.5% on 9500 = 712.5 ₪
    assert interest >= 710.0 and interest <= 715.0
    assert payout >= 10210.0

    # Wallet balance is restored with interest
    final_bal = await common.database.get_user_global_balance(bank_db, user_id)
    assert final_bal == payout
