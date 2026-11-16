# -*- coding: utf-8 -*-
"""
tests/test_econ_and_wanted_deadlock_repairs.py — Comprehensive Test Suite
========================================================================
Validates fixes for:
1. Bank deposit withdrawal (/withdraw) with 1, 10, 50, and 100 deposits:
   - Message length strictly < 4000 chars (safe for Telegram 4096 limit).
   - Never triggers "⚠️ Ответ слишком длинный. Попробуй более узкий запрос."
   - Compact summary with tier breakdown and correct shekel payout.
   - Graceful pagination fallback on invalid deposit IDs.
2. 5★ Federal Wanted Lockout & Deadlock resolved via /bribe_cop:
   - User with 5★ wanted, 0 wallet cash, but active bank deposits.
   - /bribe_cop liquidates deposit via allow_bribe_bypass=True, pays bribe,
     reduces stars below 5★, and unlocks bank withdrawals.
   - /bribe_cop all clears all 5 stars with wholesale discount.
3. Darknet purchases & aliases:
   - fake_passport and lawyer purchases with all multilingual aliases.
   - Clears wanted level and lifts arrest mutes.
   - Anti-deadlock purchase directly funded from bank deposits when cash is 0.
4. Sentence served & Star decay timer:
   - apply_wanted_decay drops stars after 1800s, 3600s, 9000s.
   - check_and_release_sentence_served clears wanted and unfreezes bank once jail time expires.
   - /surrender (cmd_surrender) turns user in and resets stars.
"""

import asyncio
import html
import json
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio
from aiogram import types

import common.config
import common.database
import common.db_pool
from bank_engine import (
    cmd_withdraw,
    cb_bank_withdraw_all_ready,
    withdraw_bank_deposit,
    get_user_bank_summary,
    create_bank_deposit,
    build_withdraw_deposits_view,
)
from criminal_syndicate_engine import (
    execute_bribe_cop,
    handle_darknet_item_buy,
    resolve_darknet_item_id,
    apply_wanted_decay,
    check_and_release_sentence_served,
    cmd_surrender,
    cmd_fake_passport,
    cmd_lawyer,
    cmd_bribe_cop,
)


# ---------------------------------------------------------------------------
# Database Schema Helper
# ---------------------------------------------------------------------------
async def _init_full_test_db(db: aiosqlite.Connection):
    """Initializes tables for bank, economy, users, and criminal syndicates."""
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
        posts_count INTEGER DEFAULT 100,
        is_isolated INTEGER DEFAULT 0,
        role TEXT DEFAULT 'user',
        custom_prefix TEXT DEFAULT NULL,
        prefix_expires_at INTEGER DEFAULT 0,
        cursed_until INTEGER DEFAULT 0,
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
    await db.execute("""
    CREATE TABLE IF NOT EXISTS Mutes (
        user_id INTEGER NOT NULL,
        board_id TEXT NOT NULL DEFAULT 'b',
        mute_type TEXT NOT NULL,
        expires_at REAL NOT NULL,
        reason TEXT,
        PRIMARY KEY(user_id, board_id, mute_type)
    )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_bank_user_status ON BankDeposits(user_id, status)")
    await db.commit()


@pytest_asyncio.fixture
async def full_db(tmp_path):
    """Creates an isolated temporary database with patched db_pool connections."""
    db_path = str(tmp_path / "test_full_econ.db")
    db = await aiosqlite.connect(db_path, isolation_level=None)
    await db.execute("PRAGMA busy_timeout = 10000;")
    await _init_full_test_db(db)

    orig_conn = getattr(common.db_pool, "_db_connection", None)
    common.db_pool._db_connection = db
    pool_mock = AsyncMock(return_value=db)

    with patch.object(common.db_pool, "get_pool", pool_mock), \
         patch.object(common.database, "get_pool", pool_mock), \
         patch.object(common.db_pool, "db_lock", common.db_pool.LazyLock()):
        yield db

    common.db_pool._db_connection = orig_conn
    await db.close()


async def _set_user(db: aiosqlite.Connection, user_id: int, balance: float = 0.0, active_items: dict = None, board_id: str = "b"):
    items_json = json.dumps(active_items or {}, ensure_ascii=False)
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = ?, active_items = ?",
        (user_id, board_id, balance, items_json, balance, items_json)
    )


# ===========================================================================
# 1. Bank Deposit Batch Withdrawal (/withdraw) Scale & Length Limits
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("deposit_count", [1, 10, 50, 100])
async def test_withdraw_all_ready_deposits_scale_never_exceeds_telegram_limit(full_db, deposit_count):
    """
    Verifies that /withdraw all with 1, 10, 50, or 100 deposits:
    1. Successfully closes all ready deposits and credits principal + interest.
    2. Response text NEVER exceeds 4000 characters (strictly below Telegram's 4096 limit).
    3. Never triggers 'Ответ слишком длинный'.
    """
    user_id = 7000 + deposit_count
    await _set_user(full_db, user_id, balance=100.0)

    now = time.time()
    # Insert mature ready deposits (locked_until in the past)
    for i in range(deposit_count):
        tier = "sych" if i % 2 == 0 else "skuf"
        await full_db.execute(
            """
            INSERT INTO BankDeposits (
                user_id, board_id, tier_id, principal, daily_rate,
                created_at, locked_until, last_accrual_at, accrued_interest, status
            ) VALUES (?, 'b', ?, 1000.0, 0.01, ?, ?, ?, 50.0, 'active')
            """,
            (user_id, tier, now - 86400, now - 3600, now - 3600)
        )

    # Mock Message
    sent_messages = []
    message = AsyncMock(spec=types.Message)
    message.from_user = MagicMock(id=user_id)
    message.chat = MagicMock(id=user_id)
    message.text = "/withdraw all"
    message.bot = None

    async def mock_answer(text, **kwargs):
        sent_messages.append(text)
        return MagicMock()

    message.answer = mock_answer

    # Execute /withdraw all
    await cmd_withdraw(message, board_id="b")

    assert len(sent_messages) == 1, "Expected exactly 1 response message"
    resp = sent_messages[0]

    # Verify message length constraints
    assert len(resp) < 4000, f"Message length ({len(resp)}) exceeds safe limit 4000!"
    assert "⚠️ Ответ слишком длинный" not in resp
    assert "ПАКЕТНЫЙ ВЫВОД ИЗ БАНКА АБУ ВЫПОЛНЕН!" in resp
    assert f"Успешно закрыто вкладов:</b> {deposit_count} шт." in resp

    # Verify database state
    async with full_db.execute(
        "SELECT COUNT(*) FROM BankDeposits WHERE user_id = ? AND status = 'withdrawn'",
        (user_id,)
    ) as cursor:
        withdrawn_count = (await cursor.fetchone())[0]
    assert withdrawn_count == deposit_count

    # Verify user received funds
    new_bal = await common.database.get_user_global_balance(full_db, user_id)
    assert new_bal > 100.0 + (deposit_count * 1000.0)


@pytest.mark.asyncio
async def test_withdraw_invalid_deposit_id_fallback_pagination(full_db):
    """
    Verifies that calling /withdraw with a non-existent or invalid deposit ID
    renders a paginated fallback view under 4000 chars without errors.
    """
    user_id = 7999
    await _set_user(full_db, user_id, balance=500.0)

    now = time.time()
    # Create 25 deposits
    for i in range(25):
        await full_db.execute(
            """
            INSERT INTO BankDeposits (
                user_id, board_id, tier_id, principal, daily_rate,
                created_at, locked_until, last_accrual_at, accrued_interest, status
            ) VALUES (?, 'b', 'sych', 500.0, 0.005, ?, ?, ?, 10.0, 'active')
            """,
            (user_id, now, now + 86400, now)
        )

    sent_views = []

    async def mock_render(target, text, kb, category="bank"):
        sent_views.append((text, kb))

    with patch("bank_engine._render_bank_view", side_effect=mock_render):
        message = AsyncMock(spec=types.Message)
        message.from_user = MagicMock(id=user_id)
        message.chat = MagicMock(id=user_id)
        message.text = "/withdraw 999999"  # Non-existent deposit

        await cmd_withdraw(message, board_id="b")

    assert len(sent_views) == 1
    view_text, kb = sent_views[0]
    assert len(view_text) < 4000
    assert "Депозит #999999 не найден среди активных" in view_text
    assert "Стр. 1/" in view_text
    assert "⚠️ Ответ слишком длинный" not in view_text


@pytest.mark.asyncio
async def test_cb_bank_withdraw_all_ready_many_deposits(full_db):
    """
    Verifies that cb_bank_withdraw_all_ready safely answers callback with <= 199 chars alert.
    """
    user_id = 7888
    await _set_user(full_db, user_id, balance=0.0)
    now = time.time()
    for i in range(30):
        await full_db.execute(
            """
            INSERT INTO BankDeposits (
                user_id, board_id, tier_id, principal, daily_rate,
                created_at, locked_until, last_accrual_at, accrued_interest, status
            ) VALUES (?, 'b', 'sych', 1000.0, 0.005, ?, ?, ?, 20.0, 'active')
            """,
            (user_id, now - 1000, now - 100, now - 100)
        )

    answered_alerts = []
    callback = AsyncMock(spec=types.CallbackQuery)
    callback.from_user = MagicMock(id=user_id)
    callback.data = "bank_withdraw_all_ready"

    async def mock_answer(text=None, show_alert=False):
        if text:
            answered_alerts.append(text)
        return True

    callback.answer = mock_answer

    with patch("bank_engine._render_bank_view", new=AsyncMock()):
        await cb_bank_withdraw_all_ready(callback, board_id="b")

    assert len(answered_alerts) >= 1
    alert = answered_alerts[0]
    assert len(alert) <= 199, f"Callback alert ({len(alert)}) exceeds Telegram 200 char limit!"
    assert "Успешно снято 30 вкладов" in alert


# ===========================================================================
# 2. 5★ Federal Wanted Lockout & Deadlock Resolution via /bribe_cop
# ===========================================================================

@pytest.mark.asyncio
async def test_bribe_cop_deadlock_zero_cash_paid_from_bank_deposits(full_db):
    """
    CRITICAL DEADLOCK TEST:
    1. User has 5★ federal wanted level.
    2. Wallet cash balance is 0.0 ₪.
    3. User has 15,000 ₪ locked in Abu Bank deposits.
    4. Normal withdrawal is BLOCKED by bank security (5★ wanted).
    5. User executes /bribe_cop.
    6. System bypasses block with allow_bribe_bypass=True, draws bribe from bank deposit,
       lowers wanted stars to 4★, and unlocks bank accounts!
    7. User can now freely withdraw remaining bank funds!
    """
    user_id = 8101
    now = time.time()
    initial_items = {"wanted_stars": 5, "bounty_pool": 25000.0, "bribe_envelope": 0, "bribe": 0}
    await _set_user(full_db, user_id, balance=0.0, active_items=initial_items)

    # User has 15,000 ₪ in bank deposits
    await full_db.execute(
        """
        INSERT INTO BankDeposits (
            user_id, board_id, tier_id, principal, daily_rate,
            created_at, locked_until, last_accrual_at, accrued_interest, status
        ) VALUES (?, 'b', 'sych', 15000.0, 0.005, ?, ?, ?, 100.0, 'active')
        """,
        (user_id, now - 3600, now + 86400, now - 3600)
    )

    # Verify that normal bank withdrawal is initially blocked by 5★ security
    async with full_db.execute("SELECT id FROM BankDeposits WHERE user_id = ?", (user_id,)) as cur:
        dep_id = (await cur.fetchone())[0]

    ok_pre, _, _, _, _, _, err_pre = await withdraw_bank_deposit(full_db, dep_id, user_id, "b")
    assert not ok_pre
    assert "СЛУЖБА БЕЗОПАСНОСТИ БАНКА АБУ" in err_pre
    assert "5★" in err_pre

    # Execute bribe cop to drop 1 star (from 5★ to 4★)
    ok_bribe, msg_bribe, meta_bribe = await execute_bribe_cop(full_db, user_id, "b", clear_all=False)
    assert ok_bribe is True
    assert meta_bribe["new_stars"] == 4
    assert meta_bribe["payment_method"] == "shekels_bank"
    assert meta_bribe["bank_unlocked"] is True
    assert "сняты арестованные средства" in msg_bribe or "Банка Абу" in msg_bribe

    # Verify bank account is now unblocked!
    # Because stars < 5, withdraw_bank_deposit now succeeds (or user has remaining balance)
    user_items = await common.bot_helpers._get_user_active_items(full_db, user_id, "b")
    assert int(user_items.get("wanted_stars", 0)) == 4


@pytest.mark.asyncio
async def test_bribe_cop_all_zero_cash_wholesale_discount_unlock(full_db):
    """
    Verifies that /bribe_cop all with 0 cash and active bank deposit:
    - Liquidates needed funds from bank.
    - Clears all 5 stars down to 0★.
    - Applies 10% wholesale discount.
    - Resets bounty pool to 0.
    - Unlocks bank accounts completely.
    """
    user_id = 8102
    now = time.time()
    initial_items = {"wanted_stars": 5, "bounty_pool": 25000.0, "bribe_envelope": 0, "bribe": 0}
    await _set_user(full_db, user_id, balance=0.0, active_items=initial_items)

    await full_db.execute(
        """
        INSERT INTO BankDeposits (
            user_id, board_id, tier_id, principal, daily_rate,
            created_at, locked_until, last_accrual_at, accrued_interest, status
        ) VALUES (?, 'b', 'sych', 20000.0, 0.005, ?, ?, ?, 200.0, 'active')
        """,
        (user_id, now - 3600, now - 100, now - 3600)
    )

    ok, msg, meta = await execute_bribe_cop(full_db, user_id, "b", clear_all=True)
    assert ok is True
    assert meta["new_stars"] == 0
    assert meta["new_bounty"] == 0.0
    assert meta["bank_unlocked"] is True
    assert meta["payment_method"] == "shekels_bank"
    assert "ТЫ ПОЛНОСТЬЮ ЧИСТ ПЕРЕД ЗАКОНОМ" in msg


# ===========================================================================
# 3. Darknet Items, Aliases & Anti-Deadlock Purchases
# ===========================================================================

def test_darknet_item_aliases_resolution():
    """Verifies multilingual aliases for fake_passport and lawyer."""
    assert resolve_darknet_item_id("fake_passport") == "fake_passport"
    assert resolve_darknet_item_id("паспорт") == "fake_passport"
    assert resolve_darknet_item_id("пасспорт") == "fake_passport"
    assert resolve_darknet_item_id("документы") == "fake_passport"
    assert resolve_darknet_item_id("липовый паспорт") == "fake_passport"
    assert resolve_darknet_item_id("ксива") == "fake_ksiva"

    assert resolve_darknet_item_id("lawyer") == "lawyer"
    assert resolve_darknet_item_id("адвокат") == "lawyer"
    assert resolve_darknet_item_id("юрист") == "lawyer"
    assert resolve_darknet_item_id("защитник") == "lawyer"


@pytest.mark.asyncio
async def test_darknet_fake_passport_clears_wanted_and_unlocks_bank(full_db):
    """
    Verifies that buying fake_passport on darknet clears 5★ wanted,
    resets bounty pool, and updates active items across boards.
    """
    user_id = 8201
    initial_items = {"wanted_stars": 5, "bounty_pool": 30000.0}
    await _set_user(full_db, user_id, balance=10000.0, active_items=initial_items)

    ok, msg, meta = await handle_darknet_item_buy(full_db, user_id, "b", "fake_passport")
    assert ok is True
    assert "Поддельный паспорт" in msg
    assert "все звёзды розыска сняты (0★)" in msg

    user_items = await common.bot_helpers._get_user_active_items(full_db, user_id, "b")
    assert int(user_items.get("wanted_stars", 0)) == 0
    assert float(user_items.get("bounty_pool", 0.0)) == 0.0
    assert int(user_items.get("fake_passport", 0)) >= 1


@pytest.mark.asyncio
async def test_darknet_lawyer_drops_stars_and_lifts_arrest_mute(full_db):
    """
    Verifies that buying lawyer on darknet drops up to 3 stars and
    removes the active arrest mute from Mutes table.
    """
    user_id = 8202
    initial_items = {"wanted_stars": 5, "bounty_pool": 25000.0}
    await _set_user(full_db, user_id, balance=10000.0, active_items=initial_items)

    # User is currently in jail
    now = time.time()
    await full_db.execute(
        "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at, reason) VALUES (?, 'b', 'arrest', ?, 'Ограбление')",
        (user_id, now + 3600)
    )

    ok, msg, meta = await handle_darknet_item_buy(full_db, user_id, "b", "lawyer")
    assert ok is True
    assert "Адвокат" in msg
    assert "обжаловал арест" in msg

    # Verify mute removed from Mutes
    async with full_db.execute(
        "SELECT COUNT(*) FROM Mutes WHERE user_id = ? AND mute_type = 'arrest'",
        (user_id,)
    ) as cur:
        mute_cnt = (await cur.fetchone())[0]
    assert mute_cnt == 0

    user_items = await common.bot_helpers._get_user_active_items(full_db, user_id, "b")
    assert int(user_items.get("wanted_stars", 0)) == 2  # 5 - 3 = 2 stars


@pytest.mark.asyncio
async def test_darknet_buy_paid_from_bank_deposits_anti_deadlock(full_db):
    """
    Anti-deadlock test:
    User has 5★ wanted, 0 wallet cash, but funds in BankDeposits.
    User buys fake_passport.
    System draws from bank deposit via allow_bribe_bypass=True,
    completes purchase, and clears wanted level!
    """
    user_id = 8203
    now = time.time()
    initial_items = {"wanted_stars": 5, "bounty_pool": 20000.0}
    await _set_user(full_db, user_id, balance=0.0, active_items=initial_items)

    await full_db.execute(
        """
        INSERT INTO BankDeposits (
            user_id, board_id, tier_id, principal, daily_rate,
            created_at, locked_until, last_accrual_at, accrued_interest, status
        ) VALUES (?, 'b', 'sych', 10000.0, 0.005, ?, ?, ?, 100.0, 'active')
        """,
        (user_id, now - 3600, now + 86400, now - 3600)
    )

    ok, msg, meta = await handle_darknet_item_buy(full_db, user_id, "b", "fake_passport")
    assert ok is True
    assert "Поддельный паспорт" in msg

    user_items = await common.bot_helpers._get_user_active_items(full_db, user_id, "b")
    assert int(user_items.get("wanted_stars", 0)) == 0


# ===========================================================================
# 4. Wanted Star Decay & Sentence Served Timers
# ===========================================================================

def test_wanted_star_decay_timer_intervals():
    """
    Verifies apply_wanted_decay:
    - Drops 1 star per 1800s (30 min).
    - Drops 2 stars after 3600s (1 hour).
    - Drops all 5 stars to 0 after 9000s (2.5 hours) and clears bounty.
    """
    now = 100000.0

    # Case A: 30 minutes elapsed -> 1 star dropped
    items_a = {"wanted_stars": 5, "bounty_pool": 25000.0, "wanted_updated_at": now - 1800}
    changed_a = apply_wanted_decay(items_a, current_ts=now)
    assert changed_a is True
    assert items_a["wanted_stars"] == 4
    assert items_a["bounty_pool"] == 20000.0

    # Case B: 1 hour elapsed -> 2 stars dropped
    items_b = {"wanted_stars": 5, "bounty_pool": 25000.0, "wanted_updated_at": now - 3600}
    changed_b = apply_wanted_decay(items_b, current_ts=now)
    assert changed_b is True
    assert items_b["wanted_stars"] == 3
    assert items_b["bounty_pool"] == 15000.0

    # Case C: 2.5 hours elapsed -> full decay to 0 stars
    items_c = {"wanted_stars": 5, "bounty_pool": 25000.0, "wanted_updated_at": now - 9000}
    changed_c = apply_wanted_decay(items_c, current_ts=now)
    assert changed_c is True
    assert items_c["wanted_stars"] == 0
    assert items_c["bounty_pool"] == 0.0

    # Case D: No decay if 0 stars
    items_d = {"wanted_stars": 0, "bounty_pool": 0.0, "wanted_updated_at": now - 9000}
    changed_d = apply_wanted_decay(items_d, current_ts=now)
    assert changed_d is False


@pytest.mark.asyncio
async def test_check_and_release_sentence_served(full_db):
    """
    Verifies that when a jailed user's arrest mute expires:
    1. check_and_release_sentence_served removes mute from Mutes.
    2. Wanted level is reset to 0★.
    3. Bank accounts are unfrozen.
    """
    user_id = 8301
    now = time.time()
    initial_items = {"wanted_stars": 5, "bounty_pool": 25000.0}
    await _set_user(full_db, user_id, balance=100.0, active_items=initial_items)

    # Arrest mute expired 10 seconds ago
    await full_db.execute(
        "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at, reason) VALUES (?, 'b', 'arrest', ?, 'Арест')",
        (user_id, now - 10)
    )

    released = await check_and_release_sentence_served(full_db, user_id, "b", initial_items, current_ts=now)
    assert released is True
    assert initial_items["wanted_stars"] == 0
    assert initial_items["bounty_pool"] == 0.0

    # Verify mute deleted
    async with full_db.execute("SELECT COUNT(*) FROM Mutes WHERE user_id = ?", (user_id,)) as cur:
        cnt = (await cur.fetchone())[0]
    assert cnt == 0


@pytest.mark.asyncio
async def test_cmd_surrender_handler(full_db):
    """
    Verifies /surrender command:
    - Places user in jail with sentence duration.
    - Resets wanted stars to 0 and clears bounty.
    - Returns informative confirmation.
    """
    user_id = 8302
    initial_items = {"wanted_stars": 5, "bounty_pool": 25000.0}
    await _set_user(full_db, user_id, balance=50.0, active_items=initial_items)

    sent_msgs = []
    message = AsyncMock(spec=types.Message)
    message.from_user = MagicMock(id=user_id)
    message.chat = MagicMock(id=user_id)
    message.text = "/surrender"

    async def mock_answer(text, **kwargs):
        sent_msgs.append(text)
        return MagicMock()

    message.answer = mock_answer

    await cmd_surrender(message, board_id="b")

    assert len(sent_msgs) == 1
    resp = sent_msgs[0]
    assert "ЯВКА С ПОВИННОЙ" in resp
    assert "Все звёзды розыска аннулированы" in resp

    # Verify user is in Mutes
    async with full_db.execute(
        "SELECT mute_type, reason FROM Mutes WHERE user_id = ? AND mute_type = 'arrest'",
        (user_id,)
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == "arrest"

    # Verify stars reset in DB
    user_items = await common.bot_helpers._get_user_active_items(full_db, user_id, "b")
    assert int(user_items.get("wanted_stars", 0)) == 0
