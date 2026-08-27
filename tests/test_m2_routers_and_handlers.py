# -*- coding: utf-8 -*-
"""
tests/test_m2_routers_and_handlers.py — Comprehensive Unit & Integration Test Suite for Milestone 2:
- Telegram Routers & Handlers in market_engine.py & bank_engine.py
- Command dispatch (/market, /sell, /bank, /deposit, /withdraw and all Russian aliases)
- Callback query handling (navigation, catalog pagination, buy flow, sell presets, cancel, deposit wizard, withdraw flow)
- Seller PM notification triggers and exception safety
- Router mounting order in main.py & unshadowing of cmd_shop aliases
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
from aiogram import Bot, types
from aiogram.types import Chat, Message, User, CallbackQuery, InlineKeyboardMarkup

from common.database import (
    _apply_migrations,
    _create_indices,
    _create_tables,
    _insert_initial_data,
    add_to_abu_fund,
    add_user_global_balance,
    deduct_user_global_balance,
    get_abu_fund_total,
    get_user_global_balance,
    get_user_recent_transactions,
)
from market_engine import (
    MARKET_CATEGORIES,
    WEAPONS_CATALOG,
    PHARMA_CATALOG,
    LOOTBOXES_CATALOG,
    market_router,
    cmd_market,
    cmd_sell,
    cb_market_main_hub,
    cb_market_cat,
    cb_market_lot,
    cb_market_buy,
    cb_market_my_lots,
    cb_market_cancel,
    cb_market_sell_menu,
    cb_market_sell_item,
    cb_market_do_sell,
    create_market_listing,
    buy_market_listing,
    cancel_market_listing,
    get_market_catalog,
    get_user_listings,
    get_market_listing,
    notify_seller_lot_sold,
    classify_item,
    find_item_by_name_or_id,
    get_user_sellable_items_list,
)
from bank_engine import (
    BANK_TIERS,
    bank_router,
    cmd_bank,
    cmd_deposit,
    cmd_withdraw,
    cb_bank_hub,
    cb_bank_refresh,
    cb_bank_deposit_menu,
    cb_bank_deposit_tier,
    cb_bank_do_deposit,
    cb_bank_withdraw_menu,
    cb_bank_withdraw_sel,
    cb_bank_withdraw_confirm,
    calculate_deposit_state,
    create_bank_deposit,
    withdraw_bank_deposit,
    get_user_bank_summary,
    normalize_tier_id,
    get_tier_info,
)


def make_mock_message(user_id: int = 1001, text: str = "/market", chat_id: int = 1001) -> MagicMock:
    """Creates a mock aiogram Message for testing command handlers."""
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    
    user = User(id=user_id, is_bot=False, first_name="Anon", username="anon2ch")
    chat = Chat(id=chat_id, type="private")
    
    msg = MagicMock(spec=Message)
    msg.message_id = 999
    msg.date = int(time.time())
    msg.chat = chat
    msg.from_user = user
    msg.text = text
    msg.caption = None
    msg.photo = []
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()
    msg.bot = bot
    return msg


def make_mock_callback(user_id: int = 1001, data: str = "market_main_hub", chat_id: int = 1001) -> MagicMock:
    """Creates a mock aiogram CallbackQuery for testing callback handlers."""
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    
    user = User(id=user_id, is_bot=False, first_name="Anon", username="anon2ch")
    chat = Chat(id=chat_id, type="private")
    
    orig_msg = MagicMock(spec=Message)
    orig_msg.message_id = 888
    orig_msg.date = int(time.time())
    orig_msg.chat = chat
    orig_msg.from_user = user
    orig_msg.text = "Previous menu text"
    orig_msg.caption = None
    orig_msg.photo = []
    orig_msg.edit_text = AsyncMock()
    orig_msg.edit_caption = AsyncMock()
    orig_msg.answer = AsyncMock()
    orig_msg.delete = AsyncMock()
    orig_msg.bot = bot

    cb = MagicMock(spec=CallbackQuery)
    cb.id = "cb_test_123"
    cb.from_user = user
    cb.chat_instance = "ci_123"
    cb.message = orig_msg
    cb.data = data
    cb.answer = AsyncMock()
    cb.bot = bot
    return cb


class TestM2RoutersAndHandlers(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_econ_m2.db")
        self.db = await aiosqlite.connect(self.db_path, isolation_level=None)
        await self.db.execute("PRAGMA foreign_keys = ON;")
        await _create_tables(self.db)
        await _apply_migrations(self.db)
        await _create_indices(self.db)
        await _insert_initial_data(self.db)

        # Patch get_pool to return our isolated test db
        self.pool_patch = patch("market_engine.get_pool", AsyncMock(return_value=self.db))
        self.pool_patch_bank = patch("bank_engine.get_pool", AsyncMock(return_value=self.db))
        self.pool_patch.start()
        self.pool_patch_bank.start()

        # Patch banner_manager.send_banner_message to route to bot.send_message
        async def _mock_send_banner(bot, chat_id, caption, reply_markup=None, category=None, parse_mode="HTML", **kwargs):
            return await bot.send_message(chat_id=chat_id, text=caption, reply_markup=reply_markup, parse_mode=parse_mode)

        self.banner_patch_m = patch("market_engine._render_market_view")
        self.banner_patch_b = patch("bank_engine._render_bank_view")
        
        # We can implement a clean transparent render wrapper
        async def _test_render_market(target, text, kb, category="shop"):
            if isinstance(target, CallbackQuery) or hasattr(target, "message"):
                msg = getattr(target, "message", target)
                if hasattr(msg, "edit_text"):
                    await msg.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            else:
                await target.answer(text=text, reply_markup=kb, parse_mode="HTML")

        async def _test_render_bank(target, text, kb, category="wallet"):
            if isinstance(target, CallbackQuery) or hasattr(target, "message"):
                msg = getattr(target, "message", target)
                if hasattr(msg, "edit_text"):
                    await msg.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            else:
                await target.answer(text=text, reply_markup=kb, parse_mode="HTML")

        self.mock_render_m = self.banner_patch_m.start()
        self.mock_render_b = self.banner_patch_b.start()
        self.mock_render_m.side_effect = _test_render_market
        self.mock_render_b.side_effect = _test_render_bank

    async def asyncTearDown(self):
        self.banner_patch_m.stop()
        self.banner_patch_b.stop()
        self.pool_patch.stop()
        self.pool_patch_bank.stop()
        await self.db.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Router Existence & Integration Checks
    # -------------------------------------------------------------------------
    def test_routers_configured_properly(self):
        """Validates market_router and bank_router are configured aiogram Routers."""
        self.assertEqual(market_router.name, "market_router")
        self.assertEqual(bank_router.name, "bank_router")

    def test_main_py_router_mount_order_and_unshadowing(self):
        """Verifies market_router & bank_router are mounted before _fallback_router and /market is unshadowed from cmd_shop."""
        with open("main.py", "r", encoding="utf-8") as f:
            main_source = f.read()

        # 1. Check imports and mounting
        self.assertIn("from market_engine import market_router", main_source)
        self.assertIn("from bank_engine import bank_router", main_source)
        self.assertIn("dp.include_router(market_router)", main_source)
        self.assertIn("dp.include_router(bank_router)", main_source)

        idx_market = main_source.find("dp.include_router(market_router)")
        idx_bank = main_source.find("dp.include_router(bank_router)")
        idx_fallback = main_source.find("dp.include_router(_fallback_router)")

        self.assertNotEqual(idx_market, -1)
        self.assertNotEqual(idx_bank, -1)
        self.assertNotEqual(idx_fallback, -1)
        self.assertLess(idx_market, idx_fallback, "market_router must be included before _fallback_router")
        self.assertLess(idx_bank, idx_fallback, "bank_router must be included before _fallback_router")

        # 2. Check unshadowing: cmd_shop must not capture 'market' or 'рынок'
        shop_match = [line for line in main_source.splitlines() if "@dp.message(Command(" in line and "cmd_shop" in main_source[main_source.find(line):main_source.find(line)+200]]
        self.assertTrue(len(shop_match) > 0)
        for line in shop_match:
            self.assertNotIn('"market"', line, "cmd_shop must not capture 'market'")
            self.assertNotIn('"рынок"', line, "cmd_shop must not capture 'рынок'")

    # -------------------------------------------------------------------------
    # 2. Market Command Handlers Tests
    # -------------------------------------------------------------------------
    async def test_cmd_market_main_view(self):
        """Verifies /market command renders main marketplace hub with category buttons."""
        user_id = 1101
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 2500)", (user_id,))

        msg = make_mock_message(user_id=user_id, text="/market")
        await cmd_market(msg, board_id="b")

        msg.answer.assert_called_once()
        call_args = msg.answer.call_args
        sent_text = call_args.kwargs.get("text")
        sent_kb = call_args.kwargs.get("reply_markup")

        self.assertIn("P2P БАРАХОЛКА", sent_text)
        self.assertIn("2,500.00 ₪", sent_text)
        self.assertIsInstance(sent_kb, InlineKeyboardMarkup)

        callback_datas = [btn.callback_data for row in sent_kb.inline_keyboard for btn in row]
        self.assertIn("market_cat:weapon:price_asc:1", callback_datas)
        self.assertIn("market_cat:clothing:price_asc:1", callback_datas)
        self.assertIn("market_cat:pharma:price_asc:1", callback_datas)
        self.assertIn("market_cat:lootbox:price_asc:1", callback_datas)
        self.assertIn("market_cat:all:price_asc:1", callback_datas)
        self.assertIn("market_my_lots:1", callback_datas)
        self.assertIn("market_sell_menu", callback_datas)

    async def test_cmd_sell_no_args_with_items_and_empty_inventory(self):
        """Verifies /sell without args lists sellable items when present, and gives helpful message when empty."""
        user_id_empty = 1102
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500, '{}')", (user_id_empty,))

        msg_empty = make_mock_message(user_id=user_id_empty, text="/sell")
        await cmd_sell(msg_empty, board_id="b")

        call_args = msg_empty.answer.call_args
        sent_text = call_args.kwargs.get("text")
        self.assertIn("Твой инвентарь пуст", sent_text)

        user_id_rich = 1103
        items = {"knife_gun": True, "pills_count": 3, "lootbox_trash": 1}
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500, ?)", (user_id_rich, json.dumps(items)))

        msg_rich = make_mock_message(user_id=user_id_rich, text="/sell")
        await cmd_sell(msg_rich, board_id="b")

        call_args2 = msg_rich.answer.call_args
        sent_text2 = call_args2.kwargs.get("text")
        sent_kb2 = call_args2.kwargs.get("reply_markup")

        self.assertIn("ВЫБЕРИ ПРЕДМЕТ ДЛЯ ПРОДАЖИ", sent_text2)
        cb_datas = [btn.callback_data for row in sent_kb2.inline_keyboard for btn in row]
        self.assertIn("market_sell_item:knife", cb_datas)
        self.assertIn("market_sell_item:pills", cb_datas)
        self.assertIn("market_sell_item:lootbox_trash", cb_datas)

    async def test_cmd_sell_with_arguments_success_and_failures(self):
        """Verifies /sell <item> <price> creates listing or returns appropriate validation error."""
        user_id = 1104
        items = {"knife_gun": True}
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500, ?)", (user_id, json.dumps(items)))

        # 1. Success creation: /sell заточка 450
        msg_ok = make_mock_message(user_id=user_id, text="/sell заточка 450")
        await cmd_sell(msg_ok, board_id="b")
        msg_ok.answer.assert_called_once()
        sent_text = msg_ok.answer.call_args.args[0] if msg_ok.answer.call_args.args else msg_ok.answer.call_args.kwargs.get("text")
        self.assertIn("УСПЕШНО ВЫСТАВЛЕН", sent_text)
        self.assertIn("450.00 ₪", sent_text)

        listings = await get_user_listings(self.db, user_id)
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["price"], 450.0)

        # 2. Failure: trying to sell item not owned
        msg_err_owned = make_mock_message(user_id=user_id, text="/sell вассерман 1000")
        await cmd_sell(msg_err_owned, board_id="b")
        sent_text_err = msg_err_owned.answer.call_args.args[0] if msg_err_owned.answer.call_args.args else msg_err_owned.answer.call_args.kwargs.get("text")
        self.assertIn("Ошибка", sent_text_err)

        # 3. Failure: invalid price format
        msg_bad_price = make_mock_message(user_id=user_id, text="/sell заточка abc")
        await cmd_sell(msg_bad_price, board_id="b")
        sent_text_bad = msg_bad_price.answer.call_args.args[0] if msg_bad_price.answer.call_args.args else msg_bad_price.answer.call_args.kwargs.get("text")
        self.assertIn("Неверный формат цены", sent_text_bad)

    # -------------------------------------------------------------------------
    # 3. Market Callback Handlers Tests
    # -------------------------------------------------------------------------
    async def test_cb_market_cat_pagination_and_sorting(self):
        """Verifies catalog browsing callback with category filter, sorting, and pagination."""
        seller_id = 1201
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500, '{}')", (seller_id,))

        for i in range(1, 8):
            await self.db.execute(
                """
                INSERT INTO MarketListings (seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status, created_at)
                VALUES (?, 'b', ?, 'weapon', ?, '{}', ?, 'active', ?)
                """,
                (seller_id, f"gun_{i}", f"Пушка {i}", float(i * 100), time.time() + i)
            )

        cb = make_mock_callback(user_id=1202, data="market_cat:weapon:price_asc:1")
        await cb_market_cat(cb, board_id="b")

        cb.message.edit_text.assert_called_once()
        edit_call = cb.message.edit_text.call_args
        sent_text = edit_call.kwargs.get("text")
        sent_kb = edit_call.kwargs.get("reply_markup")

        self.assertIn("КАТАЛОГ БАРАХОЛКИ — ⚔️ Оружие", sent_text)
        self.assertIn("Стр. 1/2", sent_text)
        self.assertIn("Лотов: <b>7</b>", sent_text)

        cb_datas = [btn.callback_data for row in sent_kb.inline_keyboard for btn in row]
        self.assertIn("market_cat:weapon:price_asc:2", cb_datas)

    async def test_cb_market_lot_view_and_buy_execution_with_notification(self):
        """Verifies lot view, instant buy execution, balance transfer, and seller PM notification."""
        seller_id = 1203
        buyer_id = 1204
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 100, '{}')", (seller_id,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000, '{}')", (buyer_id,))

        cursor = await self.db.execute(
            """
            INSERT INTO MarketListings (seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status, created_at)
            VALUES (?, 'b', 'knife', 'weapon', '🔪 Заточка', '{}', 400.0, 'active', ?)
            """,
            (seller_id, time.time())
        )
        lot_id = cursor.lastrowid

        # 1. Test Lot Details View (as buyer)
        cb_view = make_mock_callback(user_id=buyer_id, data=f"market_lot:{lot_id}")
        await cb_market_lot(cb_view, board_id="b")
        cb_view.message.edit_text.assert_called_once()
        edit_args = cb_view.message.edit_text.call_args
        text_view = edit_args.kwargs.get("text")
        self.assertIn("🔪 Заточка", text_view)
        self.assertIn("400 ₪", text_view)

        # 2. Test Instant Buy Execution
        cb_buy = make_mock_callback(user_id=buyer_id, data=f"market_buy:{lot_id}")
        await cb_market_buy(cb_buy, board_id="b")

        # Buyer deducted: 1000 - 400 = 600
        bal_buyer = await get_user_global_balance(self.db, buyer_id)
        self.assertEqual(bal_buyer, 600.0)

        # Seller credited: 100 + (400 - 20 fee) = 480
        bal_seller = await get_user_global_balance(self.db, seller_id)
        self.assertEqual(bal_seller, 480.0)

        # Abu Fund got 20.0 fee
        self.assertEqual(await get_abu_fund_total(self.db), 20.0)

        # Check Seller PM notification was sent
        cb_buy.bot.send_message.assert_awaited_once()
        pm_call_args = cb_buy.bot.send_message.call_args
        self.assertEqual(pm_call_args.kwargs.get("chat_id"), seller_id)
        self.assertIn("ТВОЙ ЛОТ ПРОДАН НА БАЗАРЕ", pm_call_args.kwargs.get("text"))

    async def test_cb_market_cancel_and_restore_item(self):
        """Verifies cancelling active listing restores item to seller active_items."""
        seller_id = 1205
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500, '{}')", (seller_id,))

        cursor = await self.db.execute(
            """
            INSERT INTO MarketListings (seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status, created_at)
            VALUES (?, 'b', 'shield', 'pharma', '🔰 Зеркальный Щит', '{"remaining_seconds": 3600}', 250.0, 'active', ?)
            """,
            (seller_id, time.time())
        )
        lot_id = cursor.lastrowid

        cb_cancel = make_mock_callback(user_id=seller_id, data=f"market_cancel:{lot_id}")
        await cb_market_cancel(cb_cancel, board_id="b")

        lot = await get_market_listing(self.db, lot_id)
        self.assertEqual(lot["status"], "cancelled")

        async with self.db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as c:
            row = await c.fetchone()
            items = json.loads(row[0])
            self.assertTrue(items.get("shield") or items.get("shield_gun") or items.get("shield_until"))

    async def test_cb_market_sell_item_preset_creation(self):
        """Verifies market_sell_item shows presets and market_do_sell creates listing."""
        user_id = 1206
        items = {"knife_gun": True}
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500, ?)", (user_id, json.dumps(items)))

        # 1. Preset menu
        cb_preset = make_mock_callback(user_id=user_id, data="market_sell_item:knife")
        await cb_market_sell_item(cb_preset, board_id="b")
        cb_preset.message.edit_text.assert_called_once()
        edit_args = cb_preset.message.edit_text.call_args
        sent_kb = edit_args.kwargs.get("reply_markup")
        cb_datas = [btn.callback_data for row in sent_kb.inline_keyboard for btn in row]
        self.assertIn("market_do_sell:knife:50", cb_datas)
        self.assertIn("market_do_sell:knife:100", cb_datas)
        self.assertIn("market_do_sell:knife:250", cb_datas)

        # 2. Click preset 250 ₪
        cb_do = make_mock_callback(user_id=user_id, data="market_do_sell:knife:250")
        await cb_market_do_sell(cb_do, board_id="b")

        listings = await get_user_listings(self.db, user_id)
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["price"], 250.0)

    # -------------------------------------------------------------------------
    # 4. Bank Command Handlers Tests
    # -------------------------------------------------------------------------
    async def test_cmd_bank_dashboard_view(self):
        """Verifies /bank dashboard shows dual balances, accrued interest, and action buttons."""
        user_id = 2101
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 3500)", (user_id,))
        await create_bank_deposit(self.db, user_id, "b", "skuf", 1000.0)

        msg = make_mock_message(user_id=user_id, text="/bank")
        await cmd_bank(msg, board_id="b")

        msg.answer.assert_called_once()
        call_args = msg.answer.call_args
        sent_text = call_args.kwargs.get("text")
        sent_kb = call_args.kwargs.get("reply_markup")

        self.assertIn("БАНК АБУ — ЗАЩИЩЕННЫЙ СЕЙФ", sent_text)
        self.assertIn("2,500.00 ₪", sent_text)  # 3500 - 1000 in safe
        self.assertIn("1,000.00 ₪", sent_text)  # In safe
        self.assertIn("Депозит Скуфа", sent_text)

        cb_datas = [btn.callback_data for row in sent_kb.inline_keyboard for btn in row]
        self.assertIn("bank_deposit_menu", cb_datas)
        self.assertIn("bank_withdraw_menu", cb_datas)
        self.assertIn("bank_refresh", cb_datas)

    async def test_cmd_deposit_args_and_wizard(self):
        """Verifies /deposit with amount opens deposit, and without args opens tier wizard."""
        user_id = 2102
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 4000)", (user_id,))

        # 1. Deposit command: /deposit 1500 skuf
        msg_dep = make_mock_message(user_id=user_id, text="/deposit 1500 skuf")
        await cmd_deposit(msg_dep, board_id="b")
        msg_dep.answer.assert_called_once()
        sent_text = msg_dep.answer.call_args.args[0] if msg_dep.answer.call_args.args else msg_dep.answer.call_args.kwargs.get("text")
        self.assertIn("ВКЛАД УСПЕШНО ОФОРМЛЕН", sent_text)
        self.assertIn("1,500.00 ₪", sent_text)

        self.assertEqual(await get_user_global_balance(self.db, user_id), 2500.0)

        # 2. Deposit wizard: /deposit
        msg_wiz = make_mock_message(user_id=user_id, text="/deposit")
        await cmd_deposit(msg_wiz, board_id="b")
        msg_wiz.answer.assert_called_once()
        call_args = msg_wiz.answer.call_args
        sent_text_wiz = call_args.kwargs.get("text")
        sent_kb_wiz = call_args.kwargs.get("reply_markup")

        self.assertIn("ОФОРМЛЕНИЕ ВКЛАДА", sent_text_wiz)
        cb_datas = [btn.callback_data for row in sent_kb_wiz.inline_keyboard for btn in row]
        self.assertIn("bank_deposit_tier:sych", cb_datas)
        self.assertIn("bank_deposit_tier:skuf", cb_datas)
        self.assertIn("bank_deposit_tier:mmm_abu", cb_datas)

    async def test_cmd_withdraw_locked_skuf_warns_early_penalty(self):
        """Verifies /withdraw <id> on locked skuf deposit warns about early exit penalty."""
        user_id = 2103
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (user_id,))
        ok, dep, _ = await create_bank_deposit(self.db, user_id, "b", "skuf", 2000.0)
        dep_id = dep["id"]

        msg = make_mock_message(user_id=user_id, text=f"/withdraw {dep_id}")
        await cmd_withdraw(msg, board_id="b")

        msg.answer.assert_called_once()
        sent_text = msg.answer.call_args.args[0] if msg.answer.call_args.args else msg.answer.call_args.kwargs.get("text")
        sent_kb = msg.answer.call_args.kwargs.get("reply_markup")

        self.assertIn("ДОСРОЧНОЕ СНЯТИЕ ВКЛАДА", sent_text)
        self.assertIn("Штраф: <b>-60.00 ₪</b>", sent_text)  # 3% of 2000
        self.assertIn("1,940.00 ₪", sent_text)

        cb_datas = [btn.callback_data for row in sent_kb.inline_keyboard for btn in row]
        self.assertIn(f"bank_withdraw_confirm:{dep_id}", cb_datas)

    # -------------------------------------------------------------------------
    # 5. Bank Callback Handlers Tests
    # -------------------------------------------------------------------------
    async def test_cb_bank_deposit_tier_presets_and_do_deposit(self):
        """Verifies bank_deposit_tier shows percentage and fixed presets, and bank_do_deposit executes deposit."""
        user_id = 2201
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 2000)", (user_id,))

        # 1. View Sych tier presets
        cb_tier = make_mock_callback(user_id=user_id, data="bank_deposit_tier:sych")
        await cb_bank_deposit_tier(cb_tier, board_id="b")
        cb_tier.message.edit_text.assert_called_once()
        edit_args = cb_tier.message.edit_text.call_args
        sent_text = edit_args.kwargs.get("text")
        sent_kb = edit_args.kwargs.get("reply_markup")

        self.assertIn("Сейф Сыча", sent_text)
        cb_datas = [btn.callback_data for row in sent_kb.inline_keyboard for btn in row]
        self.assertIn("bank_do_deposit:sych:500.0", cb_datas)
        self.assertIn("bank_do_deposit:sych:1000.0", cb_datas)
        self.assertIn("bank_do_deposit:sych:2000.0", cb_datas)

        # 2. Click 500 ₪ preset
        cb_do = make_mock_callback(user_id=user_id, data="bank_do_deposit:sych:500.0")
        await cb_bank_do_deposit(cb_do, board_id="b")

        tot_p, tot_a, deps = await get_user_bank_summary(self.db, user_id)
        self.assertEqual(tot_p, 500.0)
        self.assertEqual(len(deps), 1)

    async def test_cb_bank_refresh_recalculates_yield_in_place(self):
        """Verifies bank_refresh recalculates continuous per-second interest and updates in-place."""
        user_id = 2202
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 20000)", (user_id,))
        ok, dep, _ = await create_bank_deposit(self.db, user_id, "b", "skuf", 10000.0)
        self.assertTrue(ok)
        dep_id = dep["id"]

        # Fast forward time in DB by 24h (86,400s) -> 2.5% daily rate = 250 ₪
        past_ts = time.time() - 86400.0
        await self.db.execute(
            "UPDATE BankDeposits SET created_at = ?, locked_until = ?, last_accrual_at = ? WHERE id = ?",
            (past_ts, past_ts + 72 * 3600, past_ts, dep_id)
        )

        cb_ref = make_mock_callback(user_id=user_id, data="bank_refresh")
        await cb_bank_refresh(cb_ref, board_id="b")

        cb_ref.answer.assert_called_once_with("🔄 Проценты пересчитаны!", show_alert=False)
        cb_ref.message.edit_text.assert_called_once()
        edit_args = cb_ref.message.edit_text.call_args
        sent_text = edit_args.kwargs.get("text")

        self.assertIn("+250.00 ₪", sent_text)

    async def test_cb_bank_withdraw_menu_and_confirm_early_skuf(self):
        """Verifies bank_withdraw_menu lists deposits, and bank_withdraw_confirm executes early withdrawal with 3% penalty."""
        user_id = 2203
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (user_id,))
        ok, dep, _ = await create_bank_deposit(self.db, user_id, "b", "skuf", 1000.0)
        self.assertTrue(ok)
        dep_id = dep["id"]

        # 1. Withdraw menu
        cb_menu = make_mock_callback(user_id=user_id, data="bank_withdraw_menu")
        await cb_bank_withdraw_menu(cb_menu, board_id="b")
        cb_menu.message.edit_text.assert_called_once()
        edit_args = cb_menu.message.edit_text.call_args
        sent_kb = edit_args.kwargs.get("reply_markup")
        cb_datas = [btn.callback_data for row in sent_kb.inline_keyboard for btn in row]
        self.assertIn(f"bank_withdraw_sel:{dep_id}", cb_datas)

        # 2. Withdraw sel (shows warning)
        cb_sel = make_mock_callback(user_id=user_id, data=f"bank_withdraw_sel:{dep_id}")
        await cb_bank_withdraw_sel(cb_sel, board_id="b")
        cb_sel.message.edit_text.assert_called_once()
        edit_args_sel = cb_sel.message.edit_text.call_args
        text_sel = edit_args_sel.kwargs.get("text")
        self.assertIn("ДОСРОЧНОЕ СНЯТИЕ ВКЛАДА", text_sel)
        self.assertIn("-30.00 ₪", text_sel)  # 3% of 1000

        # 3. Confirm early withdrawal
        abu_before = await get_abu_fund_total(self.db)
        cb_conf = make_mock_callback(user_id=user_id, data=f"bank_withdraw_confirm:{dep_id}")
        await cb_bank_withdraw_confirm(cb_conf, board_id="b")

        self.assertEqual(await get_abu_fund_total(self.db), abu_before + 30.0)
        self.assertEqual(await get_user_global_balance(self.db, user_id), 4970.0)

        tot_p, _, deps = await get_user_bank_summary(self.db, user_id)
        self.assertEqual(tot_p, 0.0)
        self.assertEqual(len(deps), 0)


if __name__ == "__main__":
    unittest.main()
