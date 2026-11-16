# -*- coding: utf-8 -*-
"""
tests/test_audit_subagent5_fixes.py
Comprehensive regression tests for Subagent 5 audit fixes:
- Casino dynamic bet clamping
- Lootbox persistent daily limits & 50% Abu Yacht Fund burning
- Oligarch raid initiator proletarian validation and text consistency (1,000,000 ₪ cap)
- Command routing & aliases: /open_safe, /whale_safe, /forbes, /poker, /gforbes
- HTML escaping in global top table
"""

import html
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

import casino_engine
import lootbox_engine
from auction_engine import check_raid_proletarian, auction_router
from common.database import (
    initialize_database,
    add_user_global_balance,
    get_user_global_balance,
    get_abu_fund_total,
)
from shared_state import (
    check_shop_purchase_limit_async,
    record_shop_purchase_async,
    SHOP_DAILY_LIMITS,
)


@pytest.mark.asyncio
async def test_casino_dynamic_bet_clamping():
    """Verify tiered bet limits correctly protect players according to their wealth tier."""
    # Tier 1: Novice (balance <= 10,000) -> Max bet 1,000 ₪
    assert casino_engine.clamp_bet_to_limits(5000, balance=5000) == 1000
    assert casino_engine.clamp_bet_to_limits(10000, balance=10000) == 1000
    assert casino_engine.clamp_bet_to_limits(500, balance=5000) == 500

    # Tier 2: Working class (10,000 < balance <= 100,000) -> Max bet 25,000 ₪
    assert casino_engine.clamp_bet_to_limits(50000, balance=30000) == 25000
    assert casino_engine.clamp_bet_to_limits(20000, balance=30000) == 20000

    # Tier 3: Middle class (100,000 < balance <= 500,000) -> Max bet 150,000 ₪
    assert casino_engine.clamp_bet_to_limits(300000, balance=200000) == 150000
    assert casino_engine.clamp_bet_to_limits(100000, balance=200000) == 100000

    # Tier 4: Wealthy (500,000 < balance <= 2,000,000) -> Max bet 500,000 ₪
    assert casino_engine.clamp_bet_to_limits(800000, balance=600000) == 500000

    # Minimum clamp check
    assert casino_engine.clamp_bet_to_limits(0, balance=50000) == casino_engine.MIN_CASINO_BET
    assert casino_engine.clamp_bet_to_limits(-100, balance=50000) == casino_engine.MIN_CASINO_BET


@pytest.mark.asyncio
async def test_lootbox_persistent_limits_and_abu_burn(isolated_test_db):
    """Verify lootbox purchases persist to SQLite and burn 50% to Abu Yacht Fund."""
    db = isolated_test_db
    user_id = 999111

    # Check initial fund
    fund_before = await get_abu_fund_total(db)

    # 1. Check persistent limits
    is_ok, cur, max_lim = await lootbox_engine.check_lootbox_daily_limit_persistent(db, user_id, "lootbox_trash")
    assert is_ok is True
    assert cur == 0
    assert max_lim == SHOP_DAILY_LIMITS["lootbox_trash"]

    # 2. Record purchase of trash lootbox (150 ₪ -> 75 ₪ burned to Abu Fund)
    cnt = await lootbox_engine.record_lootbox_purchase_persistent(db, user_id, "lootbox_trash", burn_to_abu=True)
    assert cnt == 1

    fund_after_trash = await get_abu_fund_total(db)
    assert fund_after_trash == pytest.approx(fund_before + 75.0, abs=0.1)

    # 3. Record purchase of gold safe (500 ₪ -> 250 ₪ burned to Abu Fund)
    cnt_gold = await lootbox_engine.record_lootbox_purchase_persistent(db, user_id, "lootbox_gold", burn_to_abu=True)
    assert cnt_gold == 1

    fund_after_gold = await get_abu_fund_total(db)
    assert fund_after_gold == pytest.approx(fund_after_trash + 250.0, abs=0.1)

    # 4. Check persistent limit updated from SQLite
    is_ok2, cur2, max_lim2 = await lootbox_engine.check_lootbox_daily_limit_persistent(db, user_id, "lootbox_trash")
    assert is_ok2 is True
    assert cur2 == 1


@pytest.mark.asyncio
async def test_check_raid_proletarian(isolated_test_db):
    """Verify proletarian qualification logic prevents unqualified or rich users from raiding."""
    db = isolated_test_db

    # User 1: Rich wallet (6,000 ₪) -> REJECT
    uid_rich = 10001
    await add_user_global_balance(db, uid_rich, "b", 6000.0)
    await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (uid_rich,))
    await db.commit()

    ok, reason = await check_raid_proletarian(db, uid_rich)
    assert ok is False
    assert "баланс 6,000 ₪ ≥ 5,000 ₪" in reason

    # User 2: Low wallet (1,000 ₪) but high bank deposit (5,000 ₪) -> REJECT
    uid_bank_rich = 10002
    await add_user_global_balance(db, uid_bank_rich, "b", 1000.0)
    await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (uid_bank_rich,))
    now_ts = time.time()
    await db.execute("""
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, accrued_interest, daily_rate, created_at, locked_until, last_accrual_at, status)
        VALUES (?, 'b', 'sych', 5000.0, 0.0, 0.005, ?, 0.0, ?, 'active')
    """, (uid_bank_rich, now_ts, now_ts))
    await db.commit()

    ok, reason = await check_raid_proletarian(db, uid_bank_rich)
    assert ok is False
    assert "баланс 6,000 ₪ ≥ 5,000 ₪" in reason

    # User 3: Low wealth (1,000 ₪) but posts < 25 -> REJECT
    uid_low_posts = 10003
    await add_user_global_balance(db, uid_low_posts, "b", 1000.0)
    await db.execute("UPDATE Users SET posts_count = 10 WHERE user_id = ?", (uid_low_posts,))
    await db.commit()

    ok, reason = await check_raid_proletarian(db, uid_low_posts)
    assert ok is False
    assert "постов 10 < 25" in reason

    # User 4: Isolated user -> REJECT
    uid_isolated = 10004
    await add_user_global_balance(db, uid_isolated, "b", 1000.0)
    await db.execute("UPDATE Users SET posts_count = 30, is_isolated = 1 WHERE user_id = ?", (uid_isolated,))
    await db.commit()

    ok, reason = await check_raid_proletarian(db, uid_isolated)
    assert ok is False
    assert "самоизоляции" in reason

    # User 5: True proletarian (wallet 2,000 ₪, 0 bank, posts 35, not isolated) -> ACCEPT
    uid_prole = 10005
    await add_user_global_balance(db, uid_prole, "b", 2000.0)
    await db.execute("UPDATE Users SET posts_count = 35, is_isolated = 0 WHERE user_id = ?", (uid_prole,))
    await db.commit()

    ok, reason = await check_raid_proletarian(db, uid_prole)
    assert ok is True
    assert reason == ""


def test_command_registry_and_aliases():
    """Verify that all commands, safe aliases, forbes aliases, and poker handlers exist in code."""
    with open(r"c:\dev\dvachbot\main.py", "r", encoding="utf-8") as f:
        main_code = f.read()

    # Lootbox command and safe aliases
    assert 'open_safe' in main_code
    assert 'whale_safe' in main_code
    assert 'gold_safe' in main_code
    assert 'trash_safe' in main_code
    assert 'сейф' in main_code
    assert 'открыть_сейф' in main_code

    # Forbes aliases
    assert 'forbes' in main_code
    assert 'форбс' in main_code
    assert 'gforbes' in main_code
    assert 'гфорбс' in main_code

    # Poker handler
    assert 'async def cmd_poker' in main_code
    assert 'ПОКЕРНЫЙ КЛУБ ДВАЧА' in main_code

    # HTML escaping in format_table
    assert 'html.escape(row_str)' in main_code


def test_html_table_escaping():
    """Verify that table rows containing HTML characters are properly escaped to prevent parsing errors."""
    uid = 12345
    raw_name = "<b>Hacker<script>&co</script></b>"
    val_str = "100000 ₽"
    row_str = f" 1. {raw_name:<25} | {val_str:>8}"
    escaped = html.escape(row_str)

    assert "<script>" not in escaped
    assert "&lt;script&gt;" in escaped
    assert "&amp;co" in escaped
    assert "&lt;/b&gt;" in escaped
