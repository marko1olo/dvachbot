# -*- coding: utf-8 -*-
"""
test_bank_and_market.py — Comprehensive Unit & Integration Tests for:
1. Bank of Abu & Safe Storage System (bank_engine.py)
2. P2P Flea Market / Bazaar (market_engine.py)
"""

import time
import json
import pytest
import aiosqlite
from unittest.mock import MagicMock, AsyncMock, patch

from bank_engine import (
    BANK_TIERS, normalize_tier_id, get_tier_info,
    calculate_deposit_state, create_bank_deposit,
    withdraw_bank_deposit, get_user_bank_summary
)
from market_engine import (
    classify_item, find_item_by_name_or_id,
    extract_item_for_escrow, restore_item_to_active_items,
    create_market_listing, cancel_market_listing, buy_market_listing,
    get_market_catalog, get_user_listings
)


async def create_fresh_test_db():
    """Creates a fresh in-memory database with all required tables."""
    db = await aiosqlite.connect(":memory:")
    await db.execute("""
        CREATE TABLE Users (
            user_id INTEGER NOT NULL,
            board_id TEXT NOT NULL DEFAULT 'b',
            balance REAL DEFAULT 0.0,
            active_items TEXT DEFAULT '{}',
            status TEXT DEFAULT 'active',
            PRIMARY KEY (user_id, board_id)
        );
    """)
    await db.execute("""
        CREATE TABLE UserTransactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT,
            description TEXT,
            timestamp REAL NOT NULL
        );
    """)
    await db.execute("""
        CREATE TABLE GlobalStats (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    await db.execute("""
        CREATE TABLE BankDeposits (
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
            withdrawn_amount REAL DEFAULT 0.0
        );
    """)
    await db.execute("""
        CREATE TABLE MarketListings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            seller_board_id TEXT NOT NULL DEFAULT 'b',
            item_id TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            item_data TEXT NOT NULL DEFAULT '{}',
            price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at REAL NOT NULL,
            buyer_id INTEGER,
            buyer_board_id TEXT,
            sold_at REAL,
            cancelled_at REAL
        );
    """)
    await db.commit()
    return db


# ============================================================================
# 🏦 1. BANK OF ABU UNIT & INTEGRATION TESTS
# ============================================================================

class TestBankEngine:
    def test_continuous_interest_computation(self):
        """Verify continuous non-linear compound calculation in calculate_deposit_state."""
        start_ts = 1000.0
        dep = {
            "id": 1,
            "principal": 1000.0,
            "daily_rate": 0.005,  # 0.5% / day -> 5 ₪ / day
            "last_accrual_at": start_ts,
            "accrued_interest": 0.0,
            "locked_until": start_ts,
            "status": "active",
        }

        # After 0 seconds -> 0
        state0 = calculate_deposit_state(dep, current_ts=start_ts)
        assert state0["accrued_interest"] == 0.0
        assert state0["total_value"] == 1000.0

        # After 12 hours (43200s) -> 2.5 ₪
        state12 = calculate_deposit_state(dep, current_ts=start_ts + 43200)
        assert state12["accrued_interest"] == 2.5
        assert state12["total_value"] == 1002.5

        # After 1 full day (86400s) -> 5.0 ₪
        state24 = calculate_deposit_state(dep, current_ts=start_ts + 86400)
        assert state24["accrued_interest"] == 5.0
        assert state24["total_value"] == 1005.0

    @pytest.mark.asyncio
    async def test_bank_deposit_and_withdrawal_flexible(self):
        """Test flexible deposit creation and instant withdrawal with 1% bank fee."""
        db = await create_fresh_test_db()
        user_id = 111222
        board_id = "b"

        # Give user 1000 ₪
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, ?, ?)", (user_id, board_id, 1000.0))
        await db.commit()

        # 1. Deposit 500 ₪ into Flexible Safe (sych)
        ok, dep_dict, err = await create_bank_deposit(db, user_id, board_id, "sych", 500.0)
        assert ok is True
        assert dep_dict["principal"] == 500.0

        # Check wallet balance: 1000 - 500 = 500
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (user_id,)) as cur:
            assert (await cur.fetchone())[0] == 500.0

        # 2. Withdraw all
        ok_w, payout, principal, interest_paid, fee_or_penalty, is_default, err_w = await withdraw_bank_deposit(
            db, dep_dict["id"], user_id, board_id, force_early=True
        )
        assert ok_w is True
        assert fee_or_penalty == 5.0  # 1% fee of 500 ₪
        assert payout == 495.0

        # Wallet balance: 500 + 495 = 995 ₪
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (user_id,)) as cur:
            assert (await cur.fetchone())[0] == 995.0

        await db.close()

    @pytest.mark.asyncio
    async def test_bank_skuf_early_exit_penalty(self):
        """Test 3-day term deposit early exit penalty (penalty applied and interest wiped)."""
        db = await create_fresh_test_db()
        user_id = 222333
        board_id = "b"

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, ?, ?)", (user_id, board_id, 2000.0))
        await db.commit()

        # Deposit 1000 into 3-day plan (skuf)
        ok, dep, _ = await create_bank_deposit(db, user_id, board_id, "skuf", 1000.0)
        assert ok is True

        # Early withdrawal without force_early should fail
        ok_early_fail, _, _, _, _, _, err = await withdraw_bank_deposit(db, dep["id"], user_id, board_id, force_early=False)
        assert ok_early_fail is False
        assert "заблокирован" in err or "заморожен" in err

        # Early withdrawal with force_early succeeds with penalty
        ok_w, payout, principal, interest_paid, fee_or_penalty, is_default, _ = await withdraw_bank_deposit(
            db, dep["id"], user_id, board_id, force_early=True
        )
        assert ok_w is True
        assert fee_or_penalty > 0.0
        assert payout < 1000.0

        await db.close()

    @pytest.mark.asyncio
    async def test_bank_insufficient_funds_rejected(self):
        """Reject deposits if wallet has insufficient balance."""
        db = await create_fresh_test_db()
        user_id = 333444
        board_id = "b"

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, ?, ?)", (user_id, board_id, 10.0))
        await db.commit()

        ok, dep, err = await create_bank_deposit(db, user_id, board_id, "sych", 500.0)
        assert ok is False
        assert "Недостаточно шекелей" in err

        await db.close()


# ============================================================================
# 🏪 2. P2P FLEA MARKET / BAZAAR TESTS
# ============================================================================

class TestMarketEngine:
    def test_classify_and_search_items(self):
        """Verify item classification and fuzzy searching."""
        t1, name1, _ = classify_item("knife")
        assert t1 == "weapon"
        assert "Заточка" in name1

        t2, name2, _ = classify_item("body_wasserman")
        assert t2 == "clothing"
        assert "Вассерман" in name2

        # Search by Russian alias
        found = find_item_by_name_or_id("заточка")
        assert found is not None
        assert found[0] == "knife"

    def test_escrow_extraction_and_restoration(self):
        """Test item possession, escrow removal, and restoration."""
        inv = {"knife_gun": True, "pills_count": 3, "owned_body_wasserman": True}

        # Extract weapon
        ok, meta, err = extract_item_for_escrow(inv, "knife", "weapon")
        assert ok is True
        assert "knife_gun" not in inv

        # Extract consumables
        ok2, meta2, _ = extract_item_for_escrow(inv, "pills", "pharma")
        assert ok2 is True
        assert inv["pills_count"] == 2

        # Restore weapon
        inv = restore_item_to_active_items(inv, "knife", "weapon", meta)
        assert inv.get("knife_gun") is True

    @pytest.mark.asyncio
    async def test_market_listing_and_escrow(self):
        """Test listing an item: escrow from inventory, lot created in DB."""
        db = await create_fresh_test_db()
        seller_id = 555111
        board_id = "b"

        # Give seller a knife
        inv = {"knife_gun": True}
        await db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?)",
                         (seller_id, board_id, 100.0, json.dumps(inv)))
        await db.commit()

        # 1. List knife for 400 ₪
        ok, lot, err = await create_market_listing(db, seller_id, board_id, "knife", 400.0)
        assert ok is True
        assert lot["price"] == 400.0

        # 2. Check seller's inventory (must be escrowed / removed)
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as cur:
            updated_inv = json.loads((await cur.fetchone())[0])
            assert "knife_gun" not in updated_inv

        # 3. Check MarketListings
        catalog, total_pages, count = await get_market_catalog(db, category="all")
        assert count == 1
        assert catalog[0]["item_id"] == "knife"
        assert catalog[0]["price"] == 400.0

        await db.close()

    @pytest.mark.asyncio
    async def test_market_instant_purchase_with_tax(self):
        """Test complete buy transaction: balance transfer, 5% Abu tax, item delivered."""
        db = await create_fresh_test_db()
        seller_id = 777111
        buyer_id = 888222
        board_id = "b"

        # Setup seller with Wasserman vest, buyer with 5000 ₪
        await db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?)",
                         (seller_id, board_id, 0.0, json.dumps({"owned_body_wasserman": True})))
        await db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?)",
                         (buyer_id, board_id, 5000.0, json.dumps({})))
        await db.commit()

        # 1. Seller lists Wasserman vest for 2000 ₪
        ok_list, lot, _ = await create_market_listing(db, seller_id, board_id, "body_wasserman", 2000.0)
        assert ok_list is True
        lot_id = lot["id"]

        # 2. Buyer purchases lot
        ok_buy, s_id, price, payout, fee, item, err = await buy_market_listing(db, lot_id, buyer_id, board_id)
        assert ok_buy is True
        assert price == 2000.0
        assert fee == 100.0  # 5% of 2000 ₪
        assert payout == 1900.0  # 2000 - 100

        # 3. Check Buyer: balance 5000 - 2000 = 3000, possesses body_wasserman
        async with db.execute("SELECT balance, active_items FROM Users WHERE user_id = ?", (buyer_id,)) as cur:
            row = await cur.fetchone()
            assert row[0] == 3000.0
            buyer_items = json.loads(row[1])
            assert buyer_items.get("owned_body_wasserman") is True

        # 4. Check Seller: balance = 1900 ₪
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (seller_id,)) as cur:
            seller_bal = (await cur.fetchone())[0]
            assert seller_bal == 1900.0

        await db.close()

    @pytest.mark.asyncio
    async def test_market_cancel_listing(self):
        """Test cancelling a lot and retrieving item back to inventory."""
        db = await create_fresh_test_db()
        seller_id = 999333
        board_id = "b"

        await db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?)",
                         (seller_id, board_id, 50.0, json.dumps({"owned_hat_crown": True})))
        await db.commit()

        # List crown
        ok_l, lot, _ = await create_market_listing(db, seller_id, board_id, "hat_crown", 1500.0)
        assert ok_l is True
        lot_id = lot["id"]

        # Cancel lot
        ok_cancel, item_dict, err = await cancel_market_listing(db, lot_id, seller_id, board_id)
        assert ok_cancel is True

        # Check seller got crown back
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as cur:
            inv = json.loads((await cur.fetchone())[0])
            assert inv.get("owned_hat_crown") is True

        # Check listing is no longer active
        _, _, active_count = await get_market_catalog(db, category="all")
        assert active_count == 0

        await db.close()

    @pytest.mark.asyncio
    async def test_market_self_buy_blocked(self):
        """Prevent user from buying their own lot."""
        db = await create_fresh_test_db()
        user_id = 444555
        board_id = "b"

        await db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?)",
                         (user_id, board_id, 1000.0, json.dumps({"pills_count": 5})))
        await db.commit()

        ok_l, lot, _ = await create_market_listing(db, user_id, board_id, "pills", 50.0)
        assert ok_l is True

        # Try to buy own lot
        ok_buy, _, _, _, _, _, err = await buy_market_listing(db, lot["id"], user_id, board_id)
        assert ok_buy is False
        assert "собственный лот" in err

        await db.close()
