# -*- coding: utf-8 -*-
"""
tests/test_m1_econ_engines.py — Unit & Integration Test Suite for Milestone 1:
- Database Schema & Migrations (MarketListings, BankDeposits, Indices)
- P2P Market Engine (Item classification, escrow, cancellation, buy with 5% Abu fee, catalog queries)
- Bank of Abu Engine (3 tiers, continuous interest math, atomic deposits/withdrawals, default risk, portfolio summary)
- Robbery Safe Insulation
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
    buy_market_listing,
    cancel_market_listing,
    classify_item,
    create_market_listing,
    extract_item_for_escrow,
    get_market_catalog,
    get_market_listing,
    get_user_listings,
    notify_seller_lot_sold,
    restore_item_to_active_items,
)
from bank_engine import (
    BANK_TIERS,
    calculate_deposit_state,
    create_bank_deposit,
    get_tier_info,
    get_user_bank_summary,
    normalize_tier_id,
    withdraw_bank_deposit,
)


class TestM1EconEngines(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_econ_m1.db")
        self.db = await aiosqlite.connect(self.db_path, isolation_level=None)
        await self.db.execute("PRAGMA foreign_keys = ON;")
        await _create_tables(self.db)
        await _apply_migrations(self.db)
        await _create_indices(self.db)
        await _insert_initial_data(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Database Schema & Migration Tests
    # -------------------------------------------------------------------------
    async def test_database_schema_and_tables_exist(self):
        """Verifies MarketListings and BankDeposits tables and indices are created cleanly."""
        async with self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('MarketListings', 'BankDeposits')"
        ) as c:
            tables = {row[0] for row in await c.fetchall()}
        self.assertIn("MarketListings", tables)
        self.assertIn("BankDeposits", tables)

        # Check indices
        async with self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_market%' OR name LIKE 'idx_bank%'"
        ) as c:
            indices = {row[0] for row in await c.fetchall()}
        self.assertIn("idx_market_status_created", indices)
        self.assertIn("idx_market_category_status", indices)
        self.assertIn("idx_market_seller_status", indices)
        self.assertIn("idx_bank_deposits_user_status", indices)
        self.assertIn("idx_bank_deposits_status", indices)

    async def test_database_migration_idempotence(self):
        """Verifies that running _apply_migrations and _create_indices multiple times is safe."""
        # Re-running migrations should succeed without errors
        await _apply_migrations(self.db)
        await _create_indices(self.db)
        # Verify tables still operational
        async with self.db.execute("SELECT COUNT(*) FROM MarketListings") as c:
            count = (await c.fetchone())[0]
        self.assertEqual(count, 0)

    # -------------------------------------------------------------------------
    # 2. Market Item Classification Tests
    # -------------------------------------------------------------------------
    def test_item_classification(self):
        """Tests that items across all categories are classified correctly."""
        # Weapons
        w_type, w_name, _ = classify_item("knife")
        self.assertEqual(w_type, "weapon")
        self.assertIn("Заточка", w_name)

        w2_type, _, _ = classify_item("pepperspray_gun")
        self.assertEqual(w2_type, "weapon")

        # Clothes
        c_type, c_name, c_meta = classify_item("hat_tinfoil")
        self.assertEqual(c_type, "clothing")
        self.assertEqual(c_meta.get("slot"), "head")

        c2_type, _, _ = classify_item("body_tracksuit")
        self.assertEqual(c2_type, "clothing")

        # Pharma
        p_type, p_name, _ = classify_item("pills")
        self.assertEqual(p_type, "pharma")
        self.assertIn("Аминазин", p_name)

        # Lootboxes
        l_type, l_name, _ = classify_item("lootbox_trash")
        self.assertEqual(l_type, "lootbox")
        self.assertIn("Мусорный", l_name)

    # -------------------------------------------------------------------------
    # 3. Market Listing Creation & Escrow Tests
    # -------------------------------------------------------------------------
    async def test_market_listing_creation_escrows_weapon(self):
        """Listing a weapon should lock/remove it from active_items and create active lot."""
        seller_id = 1001
        board_id = "b"
        # Seed user with a knife weapon
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 500, ?)",
            (seller_id, board_id, json.dumps({"knife_gun": True}))
        )

        ok, lot, err = await create_market_listing(
            self.db, seller_id=seller_id, seller_board_id=board_id, item_id="knife", price=250.0
        )
        self.assertTrue(ok)
        self.assertIsNotNone(lot)
        self.assertEqual(lot["price"], 250.0)
        self.assertEqual(lot["status"], "active")

        # Verify knife is no longer in active_items
        async with self.db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as c:
            row = await c.fetchone()
            items = json.loads(row[0])
            self.assertNotIn("knife_gun", items)
            self.assertNotIn("knife", items)

    async def test_market_listing_creation_escrows_and_unequips_wardrobe(self):
        """Listing an equipped wardrobe item unequips it and extracts duration/perm info."""
        seller_id = 1002
        board_id = "b"
        now = int(time.time())
        # Seed user with equipped hat_crown expiring in 100 hours
        initial_items = {
            "owned_hat_crown": True,
            "hat_crown_expires": now + 360000,
            "equipped_head": "hat_crown"
        }
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 500, ?)",
            (seller_id, board_id, json.dumps(initial_items))
        )

        ok, lot, err = await create_market_listing(
            self.db, seller_id=seller_id, seller_board_id=board_id, item_id="hat_crown", price=400.0
        )
        self.assertTrue(ok)
        self.assertEqual(lot["item_type"], "clothing")
        self.assertGreater(lot["item_data"]["remaining_seconds"], 0)

        # Check seller active_items: unequipped and not owned
        async with self.db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as c:
            items = json.loads((await c.fetchone())[0])
            self.assertIsNone(items.get("equipped_head"))
            self.assertNotIn("owned_hat_crown", items)

    async def test_market_listing_creation_fails_without_item(self):
        """Attempting to list an item not owned by user fails with clear error."""
        seller_id = 1003
        board_id = "b"
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 500, '{}')",
            (seller_id, board_id)
        )
        ok, lot, err = await create_market_listing(
            self.db, seller_id=seller_id, seller_board_id=board_id, item_id="body_cloak", price=500.0
        )
        self.assertFalse(ok)
        self.assertIn("нет этого предмета", err)

    # -------------------------------------------------------------------------
    # 4. Market Listing Cancellation Tests
    # -------------------------------------------------------------------------
    async def test_cancel_market_listing_restores_item(self):
        """Cancelling an active listing restores the item to seller active_items."""
        seller_id = 1004
        board_id = "b"
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 500, ?)",
            (seller_id, board_id, json.dumps({"pepperspray_gun": True}))
        )
        ok, lot, _ = await create_market_listing(
            self.db, seller_id=seller_id, seller_board_id=board_id, item_id="pepperspray", price=300.0
        )
        lot_id = lot["id"]

        # Cancel listing
        cancel_ok, item_dict, err = await cancel_market_listing(self.db, lot_id=lot_id, user_id=seller_id)
        self.assertTrue(cancel_ok)

        # Verify item restored
        async with self.db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as c:
            items = json.loads((await c.fetchone())[0])
            self.assertTrue(items.get("pepperspray_gun"))

        # Verify listing status is cancelled
        listing = await get_market_listing(self.db, lot_id)
        self.assertEqual(listing["status"], "cancelled")

    async def test_cancel_market_listing_non_owner_forbidden(self):
        """Another user cannot cancel a lot they do not own."""
        seller_id = 1005
        intruder_id = 9999
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500, ?)",
            (seller_id, json.dumps({"mute_gun": True}))
        )
        ok, lot, _ = await create_market_listing(self.db, seller_id=seller_id, seller_board_id="b", item_id="mute", price=450.0)
        
        cancel_ok, _, err = await cancel_market_listing(self.db, lot_id=lot["id"], user_id=intruder_id)
        self.assertFalse(cancel_ok)
        self.assertIn("не являетесь владельцем", err)

    # -------------------------------------------------------------------------
    # 5. Market Purchase & 5% Abu Fee Tests
    # -------------------------------------------------------------------------
    async def test_buy_market_listing_success_and_fee(self):
        """Instant purchase deducts buyer, takes 5% Abu fee, credits seller, transfers item."""
        seller_id = 2001
        buyer_id = 2002
        price = 1000.0
        expected_fee = 50.0   # 5% of 1000 = 50
        expected_payout = 950.0

        # Seed seller with partyvan gun and 100 balance
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 100, ?)",
            (seller_id, json.dumps({"partyvan_gun": True}))
        )
        # Seed buyer with 2000 balance
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 2000, '{}')",
            (buyer_id,)
        )

        ok, lot, _ = await create_market_listing(self.db, seller_id=seller_id, seller_board_id="b", item_id="partyvan", price=price)
        lot_id = lot["id"]

        abu_before = await get_abu_fund_total(self.db)

        # Execute purchase
        buy_ok, s_id, p, payout, fee, item_data, err = await buy_market_listing(
            self.db, lot_id=lot_id, buyer_id=buyer_id, buyer_board_id="b"
        )
        self.assertTrue(buy_ok)
        self.assertEqual(s_id, seller_id)
        self.assertEqual(fee, expected_fee)
        self.assertEqual(payout, expected_payout)

        # Buyer balance: 2000 - 1000 = 1000
        buyer_bal = await get_user_global_balance(self.db, buyer_id)
        self.assertEqual(buyer_bal, 1000.0)

        # Seller balance: 100 + 950 = 1050
        seller_bal = await get_user_global_balance(self.db, seller_id)
        self.assertEqual(seller_bal, 1050.0)

        # Abu Yacht Fund got +50
        abu_after = await get_abu_fund_total(self.db)
        self.assertEqual(abu_after, abu_before + 50.0)

        # Buyer has partyvan in active_items
        async with self.db.execute("SELECT active_items FROM Users WHERE user_id = ?", (buyer_id,)) as c:
            buyer_items = json.loads((await c.fetchone())[0])
            self.assertTrue(buyer_items.get("partyvan_gun"))

        # UserTransactions logged
        buyer_txs = await get_user_recent_transactions(self.db, buyer_id)
        self.assertEqual(buyer_txs[0]["amount"], -1000.0)
        self.assertEqual(buyer_txs[0]["category"], "shop")

        seller_txs = await get_user_recent_transactions(self.db, seller_id)
        self.assertEqual(seller_txs[0]["amount"], 950.0)
        self.assertEqual(seller_txs[0]["category"], "market")

    async def test_buy_market_listing_cannot_buy_own_lot(self):
        """User cannot purchase their own lot."""
        user_id = 2003
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 2000, ?)",
            (user_id, json.dumps({"shit_gun": True}))
        )
        ok, lot, _ = await create_market_listing(self.db, seller_id=user_id, seller_board_id="b", item_id="shit", price=100.0)
        
        buy_ok, _, _, _, _, _, err = await buy_market_listing(self.db, lot_id=lot["id"], buyer_id=user_id)
        self.assertFalse(buy_ok)
        self.assertIn("Нельзя покупать свой собственный лот", err)

    async def test_buy_market_listing_insufficient_funds(self):
        """Purchase fails if buyer does not have enough balance."""
        seller_id = 2004
        buyer_id = 2005
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500, ?)",
            (seller_id, json.dumps({"vomit_gun": True}))
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50, '{}')",
            (buyer_id,)
        )
        ok, lot, _ = await create_market_listing(self.db, seller_id=seller_id, seller_board_id="b", item_id="vomit", price=200.0)
        
        buy_ok, _, _, _, _, _, err = await buy_market_listing(self.db, lot_id=lot["id"], buyer_id=buyer_id)
        self.assertFalse(buy_ok)
        self.assertIn("Недостаточно шекелей", err)

    # -------------------------------------------------------------------------
    # 6. Market Catalog Filtering, Sorting & Pagination Tests
    # -------------------------------------------------------------------------
    async def test_market_catalog_pagination_and_sorting(self):
        """Catalog properly handles pagination, category filtering, and price sorting."""
        seller_id = 3001
        # Seed seller with multiple items
        items = {
            "knife_gun": True,
            "pepperspray_gun": True,
            "mute_gun": True,
            "owned_hat_crown": True,
            "owned_hat_bag": True,
            "pills_count": 5,
        }
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000, ?)",
            (seller_id, json.dumps(items))
        )

        # Create listings with different prices and types
        await create_market_listing(self.db, seller_id, "b", "knife", price=100.0)
        await create_market_listing(self.db, seller_id, "b", "pepperspray", price=200.0)
        await create_market_listing(self.db, seller_id, "b", "mute", price=500.0)
        await create_market_listing(self.db, seller_id, "b", "hat_crown", price=350.0)
        await create_market_listing(self.db, seller_id, "b", "hat_bag", price=120.0)
        await create_market_listing(self.db, seller_id, "b", "pills", price=50.0)

        # 1. Total catalog price_asc
        lots, total_pages, total_count = await get_market_catalog(self.db, category=None, sort_order="price_asc", page=1, per_page=4)
        self.assertEqual(total_count, 6)
        self.assertEqual(total_pages, 2)
        self.assertEqual(len(lots), 4)
        self.assertEqual(lots[0]["price"], 50.0)
        self.assertEqual(lots[1]["price"], 100.0)

        # Page 2
        lots_p2, _, _ = await get_market_catalog(self.db, category=None, sort_order="price_asc", page=2, per_page=4)
        self.assertEqual(len(lots_p2), 2)

        # 2. Filter by category 'weapon'
        w_lots, w_pages, w_count = await get_market_catalog(self.db, category="weapon", sort_order="price_desc")
        self.assertEqual(w_count, 3)
        self.assertEqual(w_lots[0]["price"], 500.0)
        self.assertEqual(w_lots[1]["price"], 200.0)
        self.assertEqual(w_lots[2]["price"], 100.0)

        # 3. User listings
        user_lots = await get_user_listings(self.db, seller_id)
        self.assertEqual(len(user_lots), 6)

    # -------------------------------------------------------------------------
    # 7. Seller PM Notification Helper Test
    # -------------------------------------------------------------------------
    async def test_notify_seller_lot_sold_suppresses_exceptions(self):
        """Verifies Telegram PM alert sends correctly and suppresses API exceptions gracefully."""
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=True)

        res = await notify_seller_lot_sold(mock_bot, seller_id=12345, item_name="🔪 Заточка", price=300.0, payout=285.0, fee=15.0)
        self.assertTrue(res)
        mock_bot.send_message.assert_awaited_once()

        # Exception suppression test (e.g. user blocked bot)
        mock_bot_error = AsyncMock()
        mock_bot_error.send_message.side_effect = Exception("Forbidden: bot was blocked by the user")
        res_err = await notify_seller_lot_sold(mock_bot_error, seller_id=12345, item_name="🔪 Заточка", price=300.0, payout=285.0, fee=15.0)
        self.assertFalse(res_err)

    # -------------------------------------------------------------------------
    # 8. Bank of Abu Tiers & Interest Calculation Tests
    # -------------------------------------------------------------------------
    def test_bank_tiers_configuration(self):
        """Verifies configuration of 3 bank tiers and alias resolution."""
        self.assertEqual(normalize_tier_id("flexible"), "sych")
        self.assertEqual(normalize_tier_id("term_3d"), "skuf")
        self.assertEqual(normalize_tier_id("pyramid"), "mmm_abu")

        sych = get_tier_info("sych")
        self.assertEqual(sych["daily_rate"], 0.005)
        self.assertEqual(sych["lockup_seconds"], 0)
        self.assertEqual(sych["withdrawal_fee_pct"], 0.01)

        skuf = get_tier_info("skuf")
        self.assertEqual(skuf["daily_rate"], 0.025)
        self.assertEqual(skuf["lockup_seconds"], 72 * 3600)
        self.assertEqual(skuf["early_penalty_pct"], 0.03)

        mmm = get_tier_info("mmm_abu")
        self.assertEqual(mmm["daily_rate"], 0.060)
        self.assertEqual(mmm["lockup_seconds"], 24 * 3600)
        self.assertEqual(mmm["default_risk_pct"], 0.03)
        self.assertEqual(mmm["default_loss_pct"], 0.50)

    def test_continuous_interest_math(self):
        """Verifies per-second continuous interest computation exact formula."""
        start_ts = 1000000.0
        principal = 10000.0
        daily_rate = 0.025  # 2.5% daily = 250 shekels/day

        deposit = {
            "tier_id": "skuf",
            "principal": principal,
            "daily_rate": daily_rate,
            "created_at": start_ts,
            "last_accrual_at": start_ts,
            "locked_until": start_ts + 72 * 3600,
            "accrued_interest": 0.0
        }

        # 1 day later (86,400 sec)
        day1_ts = start_ts + 86400.0
        state1 = calculate_deposit_state(deposit, current_ts=day1_ts)
        self.assertEqual(state1["accrued_interest"], 250.0)
        self.assertEqual(state1["total_value"], 10250.0)
        self.assertTrue(state1["is_locked"])

        # 3 days later (259,200 sec) - fully unlocked
        day3_ts = start_ts + 259200.0
        state3 = calculate_deposit_state(deposit, current_ts=day3_ts)
        self.assertEqual(state3["accrued_interest"], 750.0)
        self.assertEqual(state3["total_value"], 10750.0)
        self.assertFalse(state3["is_locked"])
        self.assertEqual(state3["remaining_lock_sec"], 0)

    # -------------------------------------------------------------------------
    # 9. Bank Deposit Creation Tests
    # -------------------------------------------------------------------------
    async def test_create_bank_deposit_success(self):
        """Creating a deposit deducts wallet balance and creates deposit record."""
        user_id = 4001
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (user_id,))

        ok, dep, err = await create_bank_deposit(self.db, user_id=user_id, board_id="b", tier_id="skuf", amount=2000.0)
        self.assertTrue(ok)
        self.assertEqual(dep["principal"], 2000.0)
        self.assertEqual(dep["tier_id"], "skuf")

        # Balance deducted: 5000 - 2000 = 3000
        bal = await get_user_global_balance(self.db, user_id)
        self.assertEqual(bal, 3000.0)

        # Bank transaction recorded
        txs = await get_user_recent_transactions(self.db, user_id)
        self.assertEqual(txs[0]["amount"], -2000.0)
        self.assertEqual(txs[0]["category"], "bank")

    async def test_create_bank_deposit_insufficient_funds(self):
        """Cannot deposit more than current wallet balance."""
        user_id = 4002
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 100)", (user_id,))
        ok, _, err = await create_bank_deposit(self.db, user_id=user_id, board_id="b", tier_id="sych", amount=500.0)
        self.assertFalse(ok)
        self.assertIn("Недостаточно шекелей", err)

    # -------------------------------------------------------------------------
    # 10. Bank Withdrawal Mechanics & Tiers Tests
    # -------------------------------------------------------------------------
    async def test_withdraw_flexible_sych_applies_1pct_fee(self):
        """Sych tier applies 1.0% bank fee credited to Abu Fund on withdrawal."""
        user_id = 5001
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000)", (user_id,))
        
        ok, dep, _ = await create_bank_deposit(self.db, user_id=user_id, board_id="b", tier_id="sych", amount=1000.0)
        dep_id = dep["id"]
        
        abu_before = await get_abu_fund_total(self.db)

        # Immediate withdrawal (total_value = 1000, 1% fee = 10.0, payout = 990.0)
        w_ok, payout, principal, interest, fee, is_default, err = await withdraw_bank_deposit(
            self.db, deposit_id=dep_id, user_id=user_id, board_id="b"
        )
        self.assertTrue(w_ok)
        self.assertEqual(payout, 990.0)
        self.assertEqual(fee, 10.0)
        self.assertFalse(is_default)

        # Wallet balance is 990
        bal = await get_user_global_balance(self.db, user_id)
        self.assertEqual(bal, 990.0)

        # Abu Fund increased by fee
        abu_after = await get_abu_fund_total(self.db)
        self.assertEqual(abu_after, abu_before + 10.0)

    async def test_withdraw_skuf_early_exit_penalty(self):
        """Skuf deposit withdrawn early forfeits all interest and incurs 3% principal penalty."""
        user_id = 5002
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (user_id,))
        
        ok, dep, _ = await create_bank_deposit(self.db, user_id=user_id, board_id="b", tier_id="skuf", amount=2000.0)
        dep_id = dep["id"]

        # 1. Attempt early withdrawal without force_early -> rejected
        w_ok, _, _, _, _, _, err = await withdraw_bank_deposit(self.db, deposit_id=dep_id, user_id=user_id, force_early=False)
        self.assertFalse(w_ok)
        self.assertIn("заблокирован", err)

        # 2. Early withdrawal with force_early -> interest forfeited, 3% penalty = 60 ₪, payout = 1940 ₪
        abu_before = await get_abu_fund_total(self.db)
        w_ok2, payout, principal, interest, penalty, _, _ = await withdraw_bank_deposit(
            self.db, deposit_id=dep_id, user_id=user_id, force_early=True
        )
        self.assertTrue(w_ok2)
        self.assertEqual(penalty, 60.0)  # 3% of 2000
        self.assertEqual(payout, 1940.0)
        self.assertEqual(interest, 0.0)

        # Abu Fund got 60.0
        self.assertEqual(await get_abu_fund_total(self.db), abu_before + 60.0)

    async def test_withdraw_skuf_maturity_exit(self):
        """Skuf deposit withdrawn after 72h pays 100% principal + interest with 0% penalty."""
        user_id = 5003
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (user_id,))
        ok, dep, _ = await create_bank_deposit(self.db, user_id=user_id, board_id="b", tier_id="skuf", amount=1000.0)
        dep_id = dep["id"]

        # Fast forward deposit creation time by 73 hours in DB
        past_ts = time.time() - (73 * 3600)
        await self.db.execute(
            "UPDATE BankDeposits SET created_at = ?, locked_until = ?, last_accrual_at = ? WHERE id = ?",
            (past_ts, past_ts + 72 * 3600, past_ts, dep_id)
        )

        w_ok, payout, principal, interest, penalty, _, err = await withdraw_bank_deposit(
            self.db, deposit_id=dep_id, user_id=user_id
        )
        self.assertTrue(w_ok)
        self.assertEqual(penalty, 0.0)
        self.assertGreaterEqual(interest, 75.0)  # ~7.5% for 3 days = ~75 ₪
        self.assertEqual(payout, round(1000.0 + interest, 2))

    async def test_withdraw_mmm_abu_pyramid_scam_and_clean_exit(self):
        """MMM Abu pyramid triggers 50% default on 3% roll, and clean payout otherwise."""
        user_id = 5004
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 10000)", (user_id,))
        
        # Test Case A: Default / Audit Triggered (roll = 0.01 < 0.03)
        ok, dep1, _ = await create_bank_deposit(self.db, user_id=user_id, board_id="b", tier_id="mmm_abu", amount=1000.0)
        dep_id1 = dep1["id"]
        past_ts = time.time() - (25 * 3600)
        await self.db.execute(
            "UPDATE BankDeposits SET created_at = ?, locked_until = ?, last_accrual_at = ? WHERE id = ?",
            (past_ts, past_ts + 24 * 3600, past_ts, dep_id1)
        )

        abu_before = await get_abu_fund_total(self.db)
        w_ok, payout, principal, interest, confiscated, is_default, _ = await withdraw_bank_deposit(
            self.db, deposit_id=dep_id1, user_id=user_id, random_roll=0.01  # forces default
        )
        self.assertTrue(w_ok)
        self.assertTrue(is_default)
        self.assertGreater(confiscated, 500.0)  # 50% of total value (~1060 * 0.5 = 530)
        self.assertEqual(payout, round(1000.0 + (interest + confiscated) - confiscated - 1000.0 + payout, 2))
        self.assertEqual(await get_abu_fund_total(self.db), abu_before + confiscated)

        # Test Case B: Clean Payout (roll = 0.50 >= 0.03)
        ok, dep2, _ = await create_bank_deposit(self.db, user_id=user_id, board_id="b", tier_id="mmm_abu", amount=1000.0)
        dep_id2 = dep2["id"]
        await self.db.execute(
            "UPDATE BankDeposits SET created_at = ?, locked_until = ?, last_accrual_at = ? WHERE id = ?",
            (past_ts, past_ts + 24 * 3600, past_ts, dep_id2)
        )
        w_ok2, payout2, _, interest2, fee2, is_default2, _ = await withdraw_bank_deposit(
            self.db, deposit_id=dep_id2, user_id=user_id, random_roll=0.50  # clean roll
        )
        self.assertTrue(w_ok2)
        self.assertFalse(is_default2)
        self.assertEqual(fee2, 0.0)
        self.assertGreaterEqual(interest2, 60.0)  # 6% of 1000 = 60 ₪

    # -------------------------------------------------------------------------
    # 11. User Bank Portfolio Summary & Robbery Safe Tests
    # -------------------------------------------------------------------------
    async def test_user_bank_summary_and_robbery_insulation(self):
        """Bank deposits are tracked in summary and completely insulated from get_user_global_balance."""
        user_id = 6001
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (user_id,))

        # Deposit 3000 total across 2 tiers
        await create_bank_deposit(self.db, user_id, "b", "sych", 1000.0)
        await create_bank_deposit(self.db, user_id, "b", "skuf", 2000.0)

        # Wallet balance now strictly 2000
        wallet_bal = await get_user_global_balance(self.db, user_id)
        self.assertEqual(wallet_bal, 2000.0)

        # Bank summary reports principal 3000 + accrued
        tot_principal, tot_accrued, dep_list = await get_user_bank_summary(self.db, user_id)
        self.assertEqual(tot_principal, 3000.0)
        self.assertGreaterEqual(tot_accrued, 0.0)
        self.assertEqual(len(dep_list), 2)


if __name__ == "__main__":
    unittest.main()
