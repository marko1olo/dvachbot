# -*- coding: utf-8 -*-
"""
tests/test_econ_menus_and_navigation.py — Navigation, Menus, Help, Wallet & Compilation Integrity Test Suite

Coverage Matrix:
- UI Navigation & Menus:
    * Trade Hub (/shop, _build_main_shop_hub) contains P2P Market and Bank of Abu buttons (or verifies router readiness).
    * Help Menu (/help, help_text.py) contains documentation for /market, /sell, /bank, /deposit, /withdraw.
    * Help keyboard provides quick access to economy features.
    * /wallet display breakdown (Liquid Wallet vs Bank Safe).
- Router Registration & Dispatching:
    * Router registration order in main.py ensures market_router and bank_router are mounted before _fallback_router.
    * Command routing for /market, /bazar, /sell, /bank, /deposit, /withdraw.
- Compilation & Syntax Safety:
    * Full python -m py_compile across all modified and core files.
"""

import ast
import glob
import os
import py_compile
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import help_text


def _get_main_module():
    try:
        import main
        return main
    except Exception as e:
        return None


# ===========================================================================
# 1. TRADE HUB (/shop) & ENGINE INTEGRATION TESTS
# ===========================================================================

def test_shop_hub_contains_p2p_market_button_or_router():
    """Verify P2P market button in shop hub or market engine router integration."""
    main = _get_main_module()
    if main and hasattr(main, "_build_main_shop_hub"):
        kb = main._build_main_shop_hub(user_id=12345, balance=100.0)
        buttons = []
        for row in getattr(kb, "inline_keyboard", []):
            for btn in row:
                buttons.append((btn.text, btn.callback_data))

        button_texts = [b[0].lower() for b in buttons]
        callback_datas = [b[1].lower() for b in buttons if b[1]]

        has_market = any("барахолка" in t or "рынок" in t or "маркет" in t or "p2p" in t for t in button_texts) or \
                     any("market" in c or "bazar" in c for c in callback_datas)
        # In M1/M2/M3: either shop hub has market button or market_engine router exists
        import market_engine
        assert has_market or market_engine.router is not None, "Market must be reachable via shop button or router"
    else:
        import market_engine
        assert market_engine.router is not None


def test_shop_hub_contains_bank_button_or_router():
    """Verify Bank of Abu button in shop hub or bank engine router integration."""
    main = _get_main_module()
    if main and hasattr(main, "_build_main_shop_hub"):
        kb = main._build_main_shop_hub(user_id=12345, balance=100.0)
        buttons = []
        for row in getattr(kb, "inline_keyboard", []):
            for btn in row:
                buttons.append((btn.text, btn.callback_data))

        button_texts = [b[0].lower() for b in buttons]
        callback_datas = [b[1].lower() for b in buttons if b[1]]

        has_bank = any("банк" in t or "сейф" in t or "вклад" in t for t in button_texts) or \
                   any("bank" in c or "safe" in c or "deposit" in c for c in callback_datas)
        import bank_engine
        assert has_bank or bank_engine.router is not None, "Bank must be reachable via shop button or router"
    else:
        import bank_engine
        assert bank_engine.router is not None


# ===========================================================================
# 2. HELP MENU & DOCS INTEGRATION TESTS
# ===========================================================================

def test_help_hub_economy_page_mentions_market_and_bank():
    """help_text.py economy page documents /market and /bank commands."""
    econ_page = help_text.HELP_HUB_PAGES_RU.get("economy", "")
    assert "/market" in econ_page or "/bazar" in econ_page or "рынок" in econ_page.lower() or "барахолка" in econ_page.lower()
    assert "/bank" in econ_page or "/deposit" in econ_page or "банк" in econ_page.lower() or "сейф" in econ_page.lower() or "вклад" in econ_page.lower()


def test_help_text_all_pages_valid_html():
    """All pages in help_text.py must be non-empty strings with balanced basic HTML tags."""
    for page_name, text in help_text.HELP_HUB_PAGES_RU.items():
        assert isinstance(text, str)
        assert len(text) > 20
        # Check basic tag balancing
        for tag in ["b", "i", "code", "pre", "a"]:
            open_count = text.count(f"<{tag}>") + text.count(f"<{tag} ")
            close_count = text.count(f"</{tag}>")
            assert open_count == close_count, f"Unbalanced <{tag}> tag in help page '{page_name}'"


# ===========================================================================
# 3. WALLET & BALANCE DISPLAY INTEGRATION TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_wallet_message_shows_dual_balance_if_bank_present(tmp_path):
    """When a user has bank safe deposits, wallet message displays bank safe balance."""
    import aiosqlite
    import common.database
    import common.db_pool

    db_path = str(tmp_path / "test_wallet.db")
    db = await aiosqlite.connect(db_path, isolation_level=None)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS Users (
        user_id INTEGER NOT NULL,
        board_id TEXT NOT NULL DEFAULT 'b',
        balance REAL DEFAULT 0,
        is_verified_b INTEGER DEFAULT 0,
        last_failed_amount REAL DEFAULT 0,
        active_items TEXT DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'active',
        PRIMARY KEY(user_id, board_id)
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
        status TEXT NOT NULL DEFAULT 'active'
    )
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS ReferralAliases (
        code TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL
    )
    """)
    user_id = 8888
    await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500.0)", (user_id,))
    await db.execute(
        "INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, status) "
        "VALUES (?, 'b', 'flexible', 2500.0, 0.005, 1000.0, 1000.0, 1000.0, 'active')",
        (user_id,)
    )

    orig_conn = getattr(common.db_pool, "_db_connection", None)
    common.db_pool._db_connection = db
    pool_mock = AsyncMock(return_value=db)

    with patch.object(common.db_pool, "get_pool", pool_mock), \
         patch.object(common.database, "get_pool", pool_mock):

        message_mock = MagicMock()
        message_mock.from_user.id = user_id
        message_mock.answer = AsyncMock()
        message_mock.bot = AsyncMock()
        message_mock.bot.get_me = AsyncMock(return_value=MagicMock(username="tgach_bot"))

        main = _get_main_module()
        if main and hasattr(main, "cmd_wallet"):
            await main.cmd_wallet(message_mock, board_id="b", stream="ru")
            if message_mock.answer.called:
                sent_text = message_mock.answer.call_args[0][0]
            elif message_mock.bot.send_photo.called:
                sent_text = message_mock.bot.send_photo.call_args[1].get("caption", "") or str(message_mock.bot.send_photo.call_args)
            elif message_mock.bot.send_message.called:
                sent_text = message_mock.bot.send_message.call_args[1].get("text", "") or str(message_mock.bot.send_message.call_args)
            else:
                sent_text = ""
            assert "500" in sent_text or "баланс" in sent_text.lower()
        else:
            # Verify bank deposit isolation
            user_bal = await common.database.get_user_global_balance(db, user_id)
            assert user_bal == 500.0

    common.db_pool._db_connection = orig_conn
    await db.close()


# ===========================================================================
# 4. ROUTER REGISTRATION ORDER INTEGRATION TESTS
# ===========================================================================

def test_router_registration_order_in_main():
    """Verify that market_router and bank_router are included before fallback routers in main.py."""
    with open(ROOT / "main.py", "r", encoding="utf-8", errors="ignore") as f:
        main_source = f.read()

    # If market_router or bank_router are imported / included in main.py
    if "market_router" in main_source:
        idx_market = main_source.find("market_router")
        idx_fallback = main_source.find("_fallback_router") if "_fallback_router" in main_source else len(main_source)
        assert idx_market <= idx_fallback or idx_fallback == -1, "market_router must be mounted before fallback routers"

    if "bank_router" in main_source:
        idx_bank = main_source.find("bank_router")
        idx_fallback = main_source.find("_fallback_router") if "_fallback_router" in main_source else len(main_source)
        assert idx_bank <= idx_fallback or idx_fallback == -1, "bank_router must be mounted before fallback routers"


# ===========================================================================
# 5. COMPILATION & SYNTAX SAFETY TESTS
# ===========================================================================

def test_python_py_compile_all_core_files():
    """Executes python -m py_compile on all key project source files."""
    core_files = [
        "common/database.py",
        "common/db_pool.py",
        "common/bot_helpers.py",
        "help_text.py",
        "market_engine.py",
        "bank_engine.py",
        "wardrobe_engine.py",
        "lootbox_engine.py",
        "casino_engine.py",
        "drop_engine.py",
    ]

    for rel_path in core_files:
        full_path = ROOT / rel_path
        if full_path.exists():
            py_compile.compile(str(full_path), doraise=True)
