# -*- coding: utf-8 -*-
"""
tests/test_inquisitor_bank_and_transfers.py — Red Team Inquisitor 1 Test Suite
Stress testing Bank of Abu and Shekel Transfers engine.

Covered Directions:
1. 50 Active Deposits:
   - Pagination by 5 items per page (pages 0..9, clamp boundaries).
   - Message text length <= 4000 characters.
   - Single deposit withdrawal (mature skuf, premature skuf without/with force_early, flexible sych).
   - "⚡ Снять все доступные" button: cleans UI, no ghost buttons or hangs after all ready deposits are withdrawn.
   - Partial ready deposits batch withdrawal.
2. Extreme Amounts & Input Values:
   - Negative amounts, float('nan'), float('inf'), -float('inf'), 0, fractional pennies (0.00001), 10^18.
   - Both in bank deposits (create_bank_deposit, parse_deposit_amount) and transfers (transfer_user_balance, _parse_pay_amount).
   - Double withdrawal concurrency: 20 parallel coroutines attacking the exact same deposit atomically.
3. 5★ Federal Wanted (Розыск 5★):
   - Strict block on creating bank deposits.
   - Strict block on withdrawing bank deposits.
   - Strict block on bank withdrawal interactive commands & callbacks.
   - Strict block on sending shekels (/pay & transfer_user_balance) by 5★ sender.
   - Strict block on sending shekels to 5★ receiver (arrested account).
4. Ledger / Transactions (/ledger, /transactions):
   - Generation of 50 long transactions.
   - Strict assertion that formatted ledger text <= 4000 characters.
   - Truncation of oversized descriptions and pagination integrity.
"""

import asyncio
import json
import math
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import aiosqlite

import common.config
import common.database
import common.db_pool
import bank_engine
from main import _format_ledger_view, _parse_pay_amount


# -----------------------------------------------------------------------------
# Fixtures and DB Setup
# -----------------------------------------------------------------------------

async def _init_test_tables(db: aiosqlite.Connection):
    """Initializes required tables for bank and transfer tests."""
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
    await db.execute("CREATE INDEX IF NOT EXISTS idx_inq_bank_user ON BankDeposits(user_id, status)")


@pytest_asyncio.fixture
async def inq_db(tmp_path):
    """Isolated temporary test database."""
    db_path = str(tmp_path / "test_inquisitor.db")
    db = await aiosqlite.connect(db_path, isolation_level=None)
    await db.execute("PRAGMA busy_timeout = 10000;")
    await _init_test_tables(db)

    orig_conn = getattr(common.db_pool, "_db_connection", None)
    common.db_pool._db_connection = db
    pool_mock = AsyncMock(return_value=db)

    with patch.object(common.db_pool, "get_pool", pool_mock), \
         patch.object(common.database, "get_pool", pool_mock), \
         patch.object(common.db_pool, "db_lock", common.db_pool.LazyLock()):
        yield db

    common.db_pool._db_connection = orig_conn
    await db.close()


async def _seed_user(db, user_id: int, balance: float = 0.0, wanted_stars: int = 0, board_id: str = "b"):
    active_items = {"wanted_stars": wanted_stars} if wanted_stars > 0 else {}
    items_json = json.dumps(active_items, ensure_ascii=False)
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = ?, active_items = ?",
        (user_id, board_id, balance, items_json, balance, items_json)
    )


# =============================================================================
# DIRECTION 1: 50 ACTIVE DEPOSITS & UI / WITHDRAWAL TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_50_active_deposits_withdraw_menu_length_and_pagination(inq_db):
    """
    Stress test with 50 active deposits:
    - View generation: message text length MUST be <= 4000 characters.
    - Pagination by 5 items per page must correctly display pages 0 through 9.
    - Boundary checks for out-of-bounds page requests (negative or overly large).
    """
    user_id = 10101
    await _seed_user(inq_db, user_id, balance=500_000.0)

    # Create 50 active deposits across all tiers
    tiers = ["sych", "skuf", "mmm_abu"]
    for i in range(50):
        t_id = tiers[i % len(tiers)]
        amt = 100.0 + i * 50.0
        ok, dep, err = await bank_engine.create_bank_deposit(inq_db, user_id, "b", t_id, amt)
        assert ok is True, f"Failed to create deposit {i}: {err}"

    # Verify summary has all 50 deposits
    tot_p, tot_a, deposits = await bank_engine.get_user_bank_summary(inq_db, user_id)
    assert len(deposits) == 50

    # 1. Test every page from 0 to 9
    for p in range(10):
        text, kb = bank_engine.build_withdraw_deposits_view(deposits, page=p)
        assert len(text) <= 4000, f"Page {p} text exceeded 4000 chars: {len(text)}"
        assert f"Стр. {p + 1}/10" in text

        # Verify keyboard contains up to 5 deposit selection buttons
        deposit_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.callback_data.startswith("bank_withdraw_sel:")]
        assert len(deposit_buttons) == 5

        # Check navigation buttons
        all_cb_data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        if p > 0:
            assert f"bank_withdraw_page:{p - 1}" in all_cb_data
        if p < 9:
            assert f"bank_withdraw_page:{p + 1}" in all_cb_data

    # 2. Test clamping out-of-bounds page requests
    text_neg, kb_neg = bank_engine.build_withdraw_deposits_view(deposits, page=-5)
    assert "Стр. 1/10" in text_neg
    assert len(text_neg) <= 4000

    text_over, kb_over = bank_engine.build_withdraw_deposits_view(deposits, page=999)
    assert "Стр. 10/10" in text_over
    assert len(text_over) <= 4000


@pytest.mark.asyncio
async def test_50_active_deposits_withdraw_specific_premature_and_mature(inq_db):
    """
    Tests withdrawing specific deposits from the set:
    - Normal withdrawal of mature deposit (credits principal + interest, 0 penalty).
    - Premature withdrawal without force_early fails with penalty warning.
    - Premature withdrawal with force_early burns 100% interest and applies penalty.
    """
    user_id = 10102
    await _seed_user(inq_db, user_id, balance=50_000.0)

    # 1. Mature skuf deposit
    ok, dep1, _ = await bank_engine.create_bank_deposit(inq_db, user_id, "b", "skuf", 1000.0)
    assert ok is True
    dep1_id = dep1["id"]

    # Fast-forward past lockup (72h)
    await inq_db.execute(
        "UPDATE BankDeposits SET created_at = ?, locked_until = ?, last_accrual_at = ? WHERE id = ?",
        (time.time() - 300000, time.time() - 40000, time.time() - 300000, dep1_id)
    )

    ok, payout, principal, interest, fee, is_def, err = await bank_engine.withdraw_bank_deposit(
        inq_db, dep1_id, user_id, "b", force_early=False
    )
    assert ok is True
    assert principal == 1000.0
    assert interest > 0
    assert fee == 0.0
    assert payout == round(principal + interest, 2)

    # 2. Premature skuf deposit without force_early -> should reject
    ok, dep2, _ = await bank_engine.create_bank_deposit(inq_db, user_id, "b", "skuf", 2000.0)
    assert ok is True
    dep2_id = dep2["id"]

    ok, payout, _, _, _, _, err = await bank_engine.withdraw_bank_deposit(
        inq_db, dep2_id, user_id, "b", force_early=False
    )
    assert ok is False
    assert "Депозит Сыча заблокирован" in err

    # 3. Premature skuf deposit with force_early -> burns interest, 3% penalty
    ok, payout, principal, interest, fee, is_def, err = await bank_engine.withdraw_bank_deposit(
        inq_db, dep2_id, user_id, "b", force_early=True
    )
    assert ok is True
    assert principal == 2000.0
    assert interest == 0.0  # 100% burned
    assert fee == 60.0      # 3% of 2000
    assert payout == 1940.0 # 2000 - 60

    # 4. Flexible sych deposit withdrawal -> 1% withdrawal fee
    ok, dep3, _ = await bank_engine.create_bank_deposit(inq_db, user_id, "b", "sych", 5000.0)
    assert ok is True
    dep3_id = dep3["id"]

    ok, payout, principal, interest, fee, is_def, err = await bank_engine.withdraw_bank_deposit(
        inq_db, dep3_id, user_id, "b"
    )
    assert ok is True
    assert fee == round((5000.0 + interest) * 0.01, 2)
    assert payout == round(5000.0 + interest - fee, 2)


@pytest.mark.asyncio
async def test_50_active_deposits_withdraw_all_ready_cleans_ui(inq_db):
    """
    Tests '⚡ Снять все доступные' when all 50 deposits are ready:
    - All 50 deposits must be withdrawn in batch.
    - Wallet balance must increase by the sum of all payouts.
    - Re-rendered view MUST show the empty state: no active deposits, no stale buttons, no crash.
    """
    user_id = 10103
    await _seed_user(inq_db, user_id, balance=100_000.0)

    # Create 50 flexible sych deposits (all immediately ready)
    for i in range(50):
        ok, _, _ = await bank_engine.create_bank_deposit(inq_db, user_id, "b", "sych", 100.0)
        assert ok is True

    _, _, deposits = await bank_engine.get_user_bank_summary(inq_db, user_id)
    assert len(deposits) == 50
    assert all(not d["is_locked"] for d in deposits)

    # Mock CallbackQuery
    cb = MagicMock()
    cb.from_user.id = user_id
    cb.data = "bank_withdraw_all_ready"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.chat.id = user_id
    cb.message.message_id = 777

    with patch("bank_engine._render_bank_view", new_callable=AsyncMock) as mock_render:
        await bank_engine.cb_bank_withdraw_all_ready(cb, board_id="b")

        # Must have answered callback toast with 50 withdrawn
        cb.answer.assert_called_once()
        ans_text = cb.answer.call_args[0][0]
        assert "50 вкладов" in ans_text

        # Must have re-rendered view
        mock_render.assert_called_once()
        rendered_target, rendered_text, rendered_kb = mock_render.call_args[0][:3]

        # Verify rendered text is the empty state
        assert "У тебя нет активных вкладов для вывода" in rendered_text
        assert len(rendered_text) <= 4000

        # Verify keyboard does NOT have 'bank_withdraw_all_ready' or any old deposit buttons
        all_cb = [btn.callback_data for row in rendered_kb.inline_keyboard for btn in row]
        assert "bank_withdraw_all_ready" not in all_cb
        assert not any(c.startswith("bank_withdraw_sel:") for c in all_cb)
        assert "bank_deposit_menu" in all_cb
        assert "bank_main_hub" in all_cb

    # Verify DB has 0 active deposits
    _, _, remaining = await bank_engine.get_user_bank_summary(inq_db, user_id)
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_partial_ready_deposits_withdraw_all_ready(inq_db):
    """
    Tests '⚡ Снять все доступные' when only some deposits are ready:
    - 30 locked, 20 ready.
    - All 20 ready are withdrawn.
    - Remaining view shows exactly 30 locked deposits and NO 'Снять все доступные' button!
    """
    user_id = 10104
    await _seed_user(inq_db, user_id, balance=100_000.0)

    # 30 locked (skuf)
    for _ in range(30):
        ok, _, _ = await bank_engine.create_bank_deposit(inq_db, user_id, "b", "skuf", 100.0)
        assert ok is True

    # 20 ready (sych)
    for _ in range(20):
        ok, _, _ = await bank_engine.create_bank_deposit(inq_db, user_id, "b", "sych", 100.0)
        assert ok is True

    cb = MagicMock()
    cb.from_user.id = user_id
    cb.data = "bank_withdraw_all_ready"
    cb.answer = AsyncMock()

    with patch("bank_engine._render_bank_view", new_callable=AsyncMock) as mock_render:
        await bank_engine.cb_bank_withdraw_all_ready(cb, board_id="b")

        assert "20 вкладов" in cb.answer.call_args[0][0]

        mock_render.assert_called_once()
        _, rendered_text, rendered_kb = mock_render.call_args[0][:3]

        assert "Стр. 1/6" in rendered_text  # 30 / 5 = 6 pages
        all_cb = [btn.callback_data for row in rendered_kb.inline_keyboard for btn in row]
        assert "bank_withdraw_all_ready" not in all_cb  # No more ready deposits!

    _, _, remaining = await bank_engine.get_user_bank_summary(inq_db, user_id)
    assert len(remaining) == 30
    assert all(d["is_locked"] for d in remaining)


# =============================================================================
# DIRECTION 2: EXTREME AMOUNTS, INPUT VALIDATION & CONCURRENCY
# =============================================================================

@pytest.mark.asyncio
async def test_extreme_amounts_bank_deposit(inq_db):
    """
    Bank deposit extreme value injection attacks:
    Negative amounts, float('nan'), float('inf'), -float('inf'), 0,
    fractional micro-pennies (0.00001), 10^18.
    All MUST be cleanly rejected, leaving user balance intact.
    """
    user_id = 20201
    initial_balance = 50_000.0
    await _seed_user(inq_db, user_id, balance=initial_balance)

    bad_amounts = [
        -100.0,
        -0.01,
        0.0,
        float("nan"),
        float("inf"),
        float("-inf"),
        0.00001,
        0.004,
        10**18,
        1e20,
    ]

    for bad_amt in bad_amounts:
        ok, dep, err = await bank_engine.create_bank_deposit(inq_db, user_id, "b", "sych", bad_amt)
        assert ok is False, f"Extreme amount {bad_amt} unexpectedly succeeded!"
        assert dep is None
        assert err != ""

    # Verify balance was never modified
    current_bal = await common.database.get_user_global_balance(inq_db, user_id)
    assert current_bal == initial_balance


def test_extreme_amounts_parse_deposit_amount():
    """
    Direct parser test for parse_deposit_amount on edge/malformed strings:
    NaN, Inf, negative, micro fractions, overflow exponent, etc.
    """
    wallet = 1000.0
    assert bank_engine.parse_deposit_amount("-500", wallet) is None
    assert bank_engine.parse_deposit_amount("0", wallet) is None
    assert bank_engine.parse_deposit_amount("nan", wallet) is None
    assert bank_engine.parse_deposit_amount("inf", wallet) is None
    assert bank_engine.parse_deposit_amount("-inf", wallet) is None
    assert bank_engine.parse_deposit_amount("0.00001", wallet) is None
    assert bank_engine.parse_deposit_amount("0.004", wallet) is None
    assert bank_engine.parse_deposit_amount("1e18", wallet) is None
    assert bank_engine.parse_deposit_amount("1e999999", wallet) is None


@pytest.mark.asyncio
async def test_extreme_amounts_transfer_user_balance(inq_db):
    """
    Transfer extreme value attacks on transfer_user_balance:
    Negative, nan, inf, 0, micro penny 0.00001, 10^18.
    All MUST fail with invalid_amount or amount_too_large.
    """
    sender = 20202
    receiver = 20203
    await _seed_user(inq_db, sender, balance=10_000.0)
    await _seed_user(inq_db, receiver, balance=100.0)

    extreme_values = [
        -500.0,
        -0.01,
        0.0,
        float("nan"),
        float("inf"),
        float("-inf"),
        0.00001,
        0.004,
        10**18,
    ]

    for val in extreme_values:
        ok, reason, s_bal, r_bal = await common.database.transfer_user_balance(
            inq_db, sender, receiver, val, board_id="b"
        )
        assert ok is False, f"Transfer extreme amount {val} unexpectedly succeeded!"
        assert reason in ("invalid_amount", "amount_too_large")

    assert await common.database.get_user_global_balance(inq_db, sender) == 10_000.0
    assert await common.database.get_user_global_balance(inq_db, receiver) == 100.0


def test_extreme_amounts_pay_amount_parser():
    """
    Test Telegram /pay token parser on extreme inputs.
    """
    bal = 5000.0
    amt, err = _parse_pay_amount("-100", bal)
    assert amt is None and err == "negative_or_zero"

    amt, err = _parse_pay_amount("0", bal)
    assert amt is None and err == "negative_or_zero"

    amt, err = _parse_pay_amount("0.00001", bal)
    assert amt is None and err == "negative_or_zero"

    amt, err = _parse_pay_amount("nan", bal)
    assert amt is None and err in ("invalid_format", "negative_or_zero")

    amt, err = _parse_pay_amount("inf", bal)
    assert amt is None and err in ("too_large", "negative_or_zero")

    amt, err = _parse_pay_amount("1000000000000000000", bal)
    assert amt is None and err == "too_large"

    amt, err = _parse_pay_amount("1e999999", bal)
    assert amt is None and err in ("too_large", "invalid_format")


@pytest.mark.asyncio
async def test_double_withdrawal_concurrency_race(inq_db):
    """
    Double-withdrawal concurrency stress test:
    Launch 20 concurrent coroutines attempting to withdraw the exact same active deposit.
    Exactly ONE coroutine must succeed; exactly 19 must fail.
    The wallet must be credited for exactly ONE payout.
    """
    user_id = 20204
    await _seed_user(inq_db, user_id, balance=10_000.0)

    # Create a 10,000 ₪ flexible deposit
    ok, dep, _ = await bank_engine.create_bank_deposit(inq_db, user_id, "b", "sych", 10_000.0)
    assert ok is True
    dep_id = dep["id"]
    assert await common.database.get_user_global_balance(inq_db, user_id) == 0.0

    # Launch 20 parallel withdrawal coroutines
    concurrency_count = 20
    tasks = [
        bank_engine.withdraw_bank_deposit(inq_db, dep_id, user_id, board_id="b")
        for _ in range(concurrency_count)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if isinstance(r, tuple) and r[0] is True]
    failures = [r for r in results if isinstance(r, tuple) and r[0] is False]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}!"
    assert len(failures) == concurrency_count - 1

    # Check failure reason
    for f in failures:
        assert "Депозит уже закрыт" in f[6]

    # Verify final balance is credited only once (10,000 minus 1% fee = 9,900)
    final_balance = await common.database.get_user_global_balance(inq_db, user_id)
    assert final_balance == successes[0][1]
    assert 9890.0 <= final_balance <= 9910.0


# =============================================================================
# DIRECTION 3: 5★ FEDERAL WANTED (РОЗЫСК 5★) SECURITY LOCKS
# =============================================================================

@pytest.mark.asyncio
async def test_wanted_5_stars_cannot_create_bank_deposit(inq_db):
    """
    A user with 5★ wanted status is strictly blocked from opening bank deposits.
    """
    user_id = 30301
    await _seed_user(inq_db, user_id, balance=50_000.0, wanted_stars=5)

    ok, dep, err = await bank_engine.create_bank_deposit(inq_db, user_id, "b", "sych", 1000.0)
    assert ok is False
    assert dep is None
    assert "СЛУЖБА БЕЗОПАСНОСТИ БАНКА АБУ" in err
    assert "5★" in err

    # Balance remains untouched
    assert await common.database.get_user_global_balance(inq_db, user_id) == 50_000.0


@pytest.mark.asyncio
async def test_wanted_5_stars_cannot_withdraw_bank_deposit(inq_db):
    """
    A user who acquires 5★ wanted status is strictly blocked from withdrawing deposits.
    """
    user_id = 30302
    await _seed_user(inq_db, user_id, balance=20_000.0, wanted_stars=0)

    # Open deposit while clean
    ok, dep, _ = await bank_engine.create_bank_deposit(inq_db, user_id, "b", "sych", 5000.0)
    assert ok is True
    dep_id = dep["id"]

    # Now user gets 5★ wanted status
    await inq_db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps({"wanted_stars": 5}), user_id)
    )

    # Attempt withdrawal
    ok, payout, _, _, _, _, err = await bank_engine.withdraw_bank_deposit(
        inq_db, dep_id, user_id, board_id="b"
    )
    assert ok is False
    assert payout == 0.0
    assert "СЛУЖБА БЕЗОПАСНОСТИ БАНКА АБУ" in err
    assert "5★" in err

    # Deposit remains active
    async with inq_db.execute("SELECT status FROM BankDeposits WHERE id = ?", (dep_id,)) as c:
        row = await c.fetchone()
        assert row[0] == "active"


@pytest.mark.asyncio
async def test_wanted_5_stars_cannot_withdraw_via_cmd_or_callbacks(inq_db):
    """
    Interactive commands and callbacks (/withdraw, cb_bank_withdraw_menu, cb_bank_withdraw_all_ready, cb_bank_withdraw_sel)
    must immediately reject users with 5★ wanted status.
    """
    user_id = 30303
    await _seed_user(inq_db, user_id, balance=20_000.0, wanted_stars=5)

    # 1. /withdraw command
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.text = "/withdraw"
    msg.answer = AsyncMock()

    await bank_engine.cmd_withdraw(msg, board_id="b")
    msg.answer.assert_called_once()
    assert "СЛУЖБА БЕЗОПАСНОСТИ БАНКА АБУ" in msg.answer.call_args[0][0]
    assert "5★" in msg.answer.call_args[0][0]

    # 2. cb_bank_withdraw_menu
    cb_menu = MagicMock()
    cb_menu.from_user.id = user_id
    cb_menu.data = "bank_withdraw_menu"
    cb_menu.answer = AsyncMock()

    await bank_engine.cb_bank_withdraw_menu(cb_menu, board_id="b")
    cb_menu.answer.assert_called_once()
    assert "5★" in cb_menu.answer.call_args[0][0]

    # 3. cb_bank_withdraw_all_ready
    cb_all = MagicMock()
    cb_all.from_user.id = user_id
    cb_all.data = "bank_withdraw_all_ready"
    cb_all.answer = AsyncMock()

    await bank_engine.cb_bank_withdraw_all_ready(cb_all, board_id="b")
    cb_all.answer.assert_called_once()
    assert "5★" in cb_all.answer.call_args[0][0]

    # 4. cb_bank_withdraw_sel
    cb_sel = MagicMock()
    cb_sel.from_user.id = user_id
    cb_sel.data = "bank_withdraw_sel:1"
    cb_sel.answer = AsyncMock()

    await bank_engine.cb_bank_withdraw_sel(cb_sel, board_id="b")
    cb_sel.answer.assert_called_once()
    assert "5★" in cb_sel.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_wanted_5_stars_cannot_send_transfer(inq_db):
    """
    A sender with 5★ wanted status cannot transfer shekels (account frozen by financial intelligence).
    """
    sender = 30304
    receiver = 30305
    await _seed_user(inq_db, sender, balance=10_000.0, wanted_stars=5)
    await _seed_user(inq_db, receiver, balance=500.0, wanted_stars=0)

    ok, reason, s_bal, r_bal = await common.database.transfer_user_balance(
        inq_db, sender, receiver, 1000.0, board_id="b"
    )
    assert ok is False
    assert reason == "sender_wanted_5_stars"
    assert s_bal == 10_000.0
    assert r_bal == 500.0

    # Ensure DB balances untouched
    assert await common.database.get_user_global_balance(inq_db, sender) == 10_000.0
    assert await common.database.get_user_global_balance(inq_db, receiver) == 500.0


@pytest.mark.asyncio
async def test_wanted_5_stars_cannot_receive_transfer(inq_db):
    """
    A receiver with 5★ wanted status cannot receive shekels (account arrested by police).
    """
    sender = 30306
    receiver = 30307
    await _seed_user(inq_db, sender, balance=10_000.0, wanted_stars=0)
    await _seed_user(inq_db, receiver, balance=500.0, wanted_stars=5)

    ok, reason, s_bal, r_bal = await common.database.transfer_user_balance(
        inq_db, sender, receiver, 1000.0, board_id="b"
    )
    assert ok is False
    assert reason == "receiver_wanted_5_stars"
    assert s_bal == 10_000.0
    assert r_bal == 500.0

    assert await common.database.get_user_global_balance(inq_db, sender) == 10_000.0
    assert await common.database.get_user_global_balance(inq_db, receiver) == 500.0


# =============================================================================
# DIRECTION 4: ACCOUNT STATEMENT & LEDGER (/ledger, /transactions)
# =============================================================================

@pytest.mark.asyncio
async def test_ledger_50_long_transactions_message_length_under_4000(inq_db):
    """
    Generates 50 lengthy transactions in the ledger.
    Asserts that _format_ledger_view strictly stays <= 4000 characters across all pages.
    """
    user_id = 40401
    await _seed_user(inq_db, user_id, balance=50_000.0)

    now_ts = int(time.time())
    long_desc = "Перевод анону [Локада123456] за покупку премиумного сета брони на аукционе Абу с комиссией и страховкой"

    # Insert 50 transactions
    for i in range(50):
        await inq_db.execute(
            """
            INSERT INTO UserTransactions (user_id, amount, category, description, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, 100.0 + i, "transfer", f"{long_desc} #{i}", now_ts - i * 60)
        )

    all_txs = await common.database.get_user_recent_transactions(inq_db, user_id, limit=50)
    summary = await common.database.get_user_transaction_summary(inq_db, user_id)

    # 1. Test passing all 50 transactions directly to _format_ledger_view
    text_50, kb_50 = _format_ledger_view(user_id, 50_000.0, all_txs, summary, offset=0)
    assert len(text_50) <= 4000, f"Ledger text exceeded 4000 chars: {len(text_50)}"
    assert "ВЫПИСКА И ИСТОРИЯ ОПЕРАЦИЙ" in text_50

    # 2. Test paginating with limit=10 across multiple offsets
    for off in (0, 10, 20, 30, 40):
        page_txs = await common.database.get_user_recent_transactions(inq_db, user_id, limit=10, offset=off)
        text_page, kb_page = _format_ledger_view(user_id, 50_000.0, page_txs, summary, offset=off)
        assert len(text_page) <= 4000, f"Offset {off} text exceeded 4000 chars: {len(text_page)}"
        page_num = (off // 10) + 1
        assert f"Стр. {page_num}/" in [btn.text for row in kb_page.inline_keyboard for btn in row if "Стр." in btn.text][0]


def test_ledger_extremely_long_descriptions_clamped():
    """
    Test _format_ledger_view when transactions contain extremely long descriptions (500+ chars each).
    Verifies descriptions are truncated and text is guaranteed <= 4000 chars.
    """
    user_id = 40402
    giant_desc = "X" * 600
    mock_txs = [
        {
            "amount": 500.0,
            "category": "pay",
            "description": f"Super long transaction {i}: {giant_desc}",
            "timestamp": int(time.time()),
        }
        for i in range(15)
    ]
    summary = {"total_earned": 5000, "total_spent": 0, "total_ops": 15}

    text, kb = _format_ledger_view(user_id, 10_000.0, mock_txs, summary, offset=0)
    assert len(text) <= 4000, f"Giant descriptions produced text > 4000 chars: {len(text)}"
    assert "..." in text  # Truncation indicator present
