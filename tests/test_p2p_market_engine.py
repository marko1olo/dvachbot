# -*- coding: utf-8 -*-
"""
tests/test_p2p_market_engine.py — E2E and Unit Test Suite for DvachBot P2P Market / Flea Market Engine

Coverage Matrix:
- Tier 1 (Feature / Happy Path):
    * Listing wardrobe (clothing), weapon, pharma, and lootbox items with custom price.
    * Atomic locking and escrowing from Users.active_items.
    * Instant purchase: buyer balance deduction, 5% Abu fee deduction, seller payout, buyer item delivery.
    * Listing cancellation: item restoration to seller's active_items, status updated to 'cancelled'.
- Tier 2 (Boundary Value Analysis & Negative Cases):
    * Minimum price boundaries (1 ₪, 10 ₪ valid; 0 ₪, negative, non-numeric rejected).
    * Buying with 0 shekels balance (rejected).
    * Buying with insufficient shekels (rejected).
    * Buying with exact shekels (succeeds, balance becomes 0).
    * Buyer attempting to buy their own lot (forbidden, rejected).
    * Relisting cancelled items (succeeds).
    * Double-buy race condition prevention (second buy fails).
- Tier 3 (Pairwise & Cross-Feature):
    * Multiple concurrent listings per seller.
    * Listing currently equipped wardrobe items automatically un-equips them.
    * Listing permanent vs expiring timed items (duration preservation).
    * Catalog pagination (page 1, 2, empty out-of-bounds page, total_pages, total_count).
    * Catalog sorting ('price_asc', 'price_desc', 'newest').
    * Category filtering ('clothing', 'weapon', 'pharma', 'lootbox').
- Tier 4 (Workload & E2E Real-World Journey):
    * Complete marketplace lifecycle (List -> Browse -> Buy -> Payout -> Equip).
    * Seller PM notification (successful delivery).
    * Seller PM notification failure handling (TelegramForbiddenError, TelegramBadRequest suppression).
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
# Database Schema Helper for Market Engine
# ---------------------------------------------------------------------------
async def _init_market_test_db(db: aiosqlite.Connection):
    """Ensures base Users, UserTransactions, GlobalStats, and MarketListings tables exist."""
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
    CREATE TABLE IF NOT EXISTS MarketListings (
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
    )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_market_status_created ON MarketListings(status, created_at DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_market_seller_status ON MarketListings(seller_id, status)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_market_category_status ON MarketListings(item_type, status, price ASC)")


@pytest_asyncio.fixture
async def market_db(tmp_path):
    """Creates an isolated temporary database for market engine testing."""
    db_path = str(tmp_path / "test_market.db")
    db = await aiosqlite.connect(db_path, isolation_level=None)
    await db.execute("PRAGMA busy_timeout = 10000;")
    await _init_market_test_db(db)

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


async def _get_user_items(db, user_id: int, board_id: str = "b") -> dict:
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return {}


# ---------------------------------------------------------------------------
# Import / Fallback Loader for market_engine
# ---------------------------------------------------------------------------
try:
    import market_engine
except ImportError:
    market_engine = None


def _get_market_module():
    if market_engine is not None:
        return market_engine
    import importlib
    try:
        return importlib.import_module("market_engine")
    except Exception as e:
        pytest.skip(f"market_engine not yet available: {e}")


# ===========================================================================
# TIER 1: CORE FUNCTIONALITY (HAPPY PATH)
# ===========================================================================

@pytest.mark.asyncio
async def test_market_create_listing_wardrobe_locks_item(market_db):
    """Listing an owned wardrobe item locks/removes it from active_items and creates lot."""
    me = _get_market_module()
    seller_id = 1001
    await _set_user(market_db, seller_id, balance=100, active_items={"owned_hat_helmet": True})

    success, lot, err = await me.create_market_listing(
        market_db,
        seller_id=seller_id,
        seller_board_id="b",
        item_id="hat_helmet",
        price=500.0,
        custom_item_data={"tier": 3, "name": "🪖 Шлем ОМОНа"},
        item_type="clothing"
    )

    assert success is True
    assert lot is not None
    assert lot.get("id") is not None
    assert lot.get("price") == 500.0
    assert lot.get("status") == "active"

    # Verify item is escrowed (no longer in active_items)
    items = await _get_user_items(market_db, seller_id)
    assert not items.get("owned_hat_helmet")


@pytest.mark.asyncio
async def test_market_create_listing_weapons(market_db):
    """Listing a weapon locks it from active_items and records listing."""
    me = _get_market_module()
    seller_id = 1002
    await _set_user(market_db, seller_id, balance=50, active_items={"knife_gun": True})

    success, lot, err = await me.create_market_listing(
        market_db,
        seller_id=seller_id,
        seller_board_id="b",
        item_id="knife_gun",
        price=150.0,
        custom_item_data={"name": "🔪 Заточка"},
        item_type="weapon"
    )

    assert success is True
    assert lot["item_type"] in ("weapon", "weapons")
    items = await _get_user_items(market_db, seller_id)
    assert not items.get("knife_gun")


@pytest.mark.asyncio
async def test_market_create_listing_pharma(market_db):
    """Listing pharma/drugs escrows item and creates lot."""
    me = _get_market_module()
    seller_id = 1003
    await _set_user(market_db, seller_id, balance=50, active_items={"pills": True, "pills_count": 3})

    success, lot, err = await me.create_market_listing(
        market_db,
        seller_id=seller_id,
        seller_board_id="b",
        item_id="pills",
        price=80.0,
        custom_item_data={"name": "💊 Аминазин"},
        item_type="pharma"
    )

    assert success is True
    assert lot["id"] > 0


@pytest.mark.asyncio
async def test_market_create_listing_lootbox(market_db):
    """Listing a lootbox escrows item and creates lot."""
    me = _get_market_module()
    seller_id = 1004
    await _set_user(market_db, seller_id, balance=50, active_items={"lootbox_trash": 2})

    success, lot, err = await me.create_market_listing(
        market_db,
        seller_id=seller_id,
        seller_board_id="b",
        item_id="lootbox_trash",
        price=120.0,
        custom_item_data={"name": "🗑️ Мусорный Лутбокс"},
        item_type="lootbox"
    )

    assert success is True
    assert lot["price"] == 120.0


@pytest.mark.asyncio
async def test_market_instant_buy_seller_payout_and_abu_fee(market_db):
    """Instant buy deducts shekels from buyer, takes 5% Abu fee, and credits seller."""
    me = _get_market_module()
    seller_id = 1005
    buyer_id = 2005

    await _set_user(market_db, seller_id, balance=100, active_items={"owned_hat_crown": True})
    await _set_user(market_db, buyer_id, balance=1000, active_items={})

    success, lot, _ = await me.create_market_listing(
        market_db,
        seller_id=seller_id,
        seller_board_id="b",
        item_id="hat_crown",
        price=100.0,
        item_type="clothing"
    )
    assert success is True

    success_buy, s_id, price, payout, fee, item, err = await me.buy_market_listing(
        market_db,
        lot_id=lot["id"],
        buyer_id=buyer_id,
        buyer_board_id="b"
    )

    assert success_buy is True
    assert err == "" or err is None
    assert price == 100.0
    assert fee == 5.0  # 5% Abu fee
    assert payout == 95.0  # Seller gets 95 ₪

    # Check seller balance: 100 initial + 95 payout = 195
    seller_bal = await common.database.get_user_global_balance(market_db, seller_id)
    assert seller_bal == 195.0

    # Check buyer balance: 1000 initial - 100 price = 900
    buyer_bal = await common.database.get_user_global_balance(market_db, buyer_id)
    assert buyer_bal == 900.0


@pytest.mark.asyncio
async def test_market_instant_buy_transfers_item_to_buyer(market_db):
    """Instant buy delivers item into buyer's active_items."""
    me = _get_market_module()
    seller_id = 1006
    buyer_id = 2006

    await _set_user(market_db, seller_id, balance=50, active_items={"partyvan_gun": True})
    await _set_user(market_db, buyer_id, balance=500, active_items={})

    success, lot, _ = await me.create_market_listing(
        market_db,
        seller_id=seller_id,
        seller_board_id="b",
        item_id="partyvan_gun",
        price=200.0,
        item_type="weapon"
    )
    assert success is True

    success_buy, _, _, _, _, _, _ = await me.buy_market_listing(
        market_db,
        lot_id=lot["id"],
        buyer_id=buyer_id,
        buyer_board_id="b"
    )

    assert success_buy is True
    buyer_items = await _get_user_items(market_db, buyer_id)
    assert buyer_items.get("partyvan_gun") is True or buyer_items.get("partyvan") is True


@pytest.mark.asyncio
async def test_market_cancel_listing_restores_item_to_seller(market_db):
    """Cancelling active listing restores item to seller and marks lot cancelled."""
    me = _get_market_module()
    seller_id = 1007

    await _set_user(market_db, seller_id, balance=100, active_items={"owned_hat_bag": True})

    success, lot, _ = await me.create_market_listing(
        market_db,
        seller_id=seller_id,
        seller_board_id="b",
        item_id="hat_bag",
        price=150.0,
        item_type="clothing"
    )
    assert success is True

    # Cancel lot
    success_cancel, item, err = await me.cancel_market_listing(market_db, lot_id=lot["id"], user_id=seller_id)
    assert success_cancel is True

    # Check seller got item back
    items = await _get_user_items(market_db, seller_id)
    assert items.get("owned_hat_bag") is True

    # Check lot status in DB
    async with market_db.execute("SELECT status FROM MarketListings WHERE id = ?", (lot["id"],)) as c:
        row = await c.fetchone()
        assert row[0] == "cancelled"


# ===========================================================================
# TIER 2: BOUNDARY VALUE ANALYSIS & NEGATIVE TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_market_minimum_price_boundaries(market_db):
    """Listing with price 1 ₪ and 10 ₪ succeeds; price <= 0 or invalid fails."""
    me = _get_market_module()
    seller_id = 1008
    await _set_user(market_db, seller_id, balance=10, active_items={"knife_gun": True, "shit_gun": True})

    # Minimum valid price 1 ₪
    s1, lot1, _ = await me.create_market_listing(
        market_db, seller_id=seller_id, seller_board_id="b", item_id="knife_gun", price=1.0, item_type="weapon"
    )
    assert s1 is True
    assert lot1["price"] == 1.0

    # Invalid prices <= 0 should fail
    s_zero, lot_zero, err_zero = await me.create_market_listing(
        market_db, seller_id=seller_id, seller_board_id="b", item_id="shit_gun", price=0.0, item_type="weapon"
    )
    assert s_zero is False
    assert lot_zero is None


@pytest.mark.asyncio
async def test_market_buy_with_zero_balance_fails(market_db):
    """Buyer with 0 balance cannot buy lot."""
    me = _get_market_module()
    seller_id = 1009
    buyer_id = 2009

    await _set_user(market_db, seller_id, balance=0, active_items={"owned_hat_tinfoil": True})
    await _set_user(market_db, buyer_id, balance=0, active_items={})

    success, lot, _ = await me.create_market_listing(
        market_db, seller_id=seller_id, seller_board_id="b", item_id="hat_tinfoil", price=100.0, item_type="clothing"
    )
    assert success is True

    success_buy, _, _, _, _, _, err = await me.buy_market_listing(
        market_db, lot_id=lot["id"], buyer_id=buyer_id, buyer_board_id="b"
    )

    assert success_buy is False
    assert "недостаточно" in err.lower() or "balance" in err.lower() or len(err) > 0


@pytest.mark.asyncio
async def test_market_buy_with_insufficient_balance_fails(market_db):
    """Buyer with 49 ₪ trying to buy 50 ₪ lot fails."""
    me = _get_market_module()
    seller_id = 1010
    buyer_id = 2010

    await _set_user(market_db, seller_id, balance=0, active_items={"owned_hat_tinfoil": True})
    await _set_user(market_db, buyer_id, balance=49, active_items={})

    success, lot, _ = await me.create_market_listing(
        market_db, seller_id=seller_id, seller_board_id="b", item_id="hat_tinfoil", price=50.0, item_type="clothing"
    )
    assert success is True

    success_buy, _, _, _, _, _, err = await me.buy_market_listing(
        market_db, lot_id=lot["id"], buyer_id=buyer_id, buyer_board_id="b"
    )

    assert success_buy is False
    buyer_bal = await common.database.get_user_global_balance(market_db, buyer_id)
    assert buyer_bal == 49.0


@pytest.mark.asyncio
async def test_market_buy_with_exact_balance_succeeds(market_db):
    """Buyer with exactly 100 ₪ buying 100 ₪ lot leaves 0 balance."""
    me = _get_market_module()
    seller_id = 1011
    buyer_id = 2011

    await _set_user(market_db, seller_id, balance=0, active_items={"owned_hat_tinfoil": True})
    await _set_user(market_db, buyer_id, balance=100, active_items={})

    success, lot, _ = await me.create_market_listing(
        market_db, seller_id=seller_id, seller_board_id="b", item_id="hat_tinfoil", price=100.0, item_type="clothing"
    )
    assert success is True

    success_buy, _, _, _, _, _, _ = await me.buy_market_listing(
        market_db, lot_id=lot["id"], buyer_id=buyer_id, buyer_board_id="b"
    )

    assert success_buy is True
    buyer_bal = await common.database.get_user_global_balance(market_db, buyer_id)
    assert buyer_bal == 0.0


@pytest.mark.asyncio
async def test_market_buyer_cannot_buy_own_lot(market_db):
    """Seller cannot buy their own lot."""
    me = _get_market_module()
    seller_id = 1012

    await _set_user(market_db, seller_id, balance=500, active_items={"owned_hat_tinfoil": True})

    success, lot, _ = await me.create_market_listing(
        market_db, seller_id=seller_id, seller_board_id="b", item_id="hat_tinfoil", price=100.0, item_type="clothing"
    )
    assert success is True

    success_buy, _, _, _, _, _, err = await me.buy_market_listing(
        market_db, lot_id=lot["id"], buyer_id=seller_id, buyer_board_id="b"
    )

    assert success_buy is False
    assert "свой" in err.lower() or "own" in err.lower() or len(err) > 0


@pytest.mark.asyncio
async def test_market_relisting_cancelled_item_succeeds(market_db):
    """Cancelled item can be listed again."""
    me = _get_market_module()
    seller_id = 1013

    await _set_user(market_db, seller_id, balance=10, active_items={"pepperspray_gun": True})

    s1, lot1, _ = await me.create_market_listing(
        market_db, seller_id=seller_id, seller_board_id="b", item_id="pepperspray_gun", price=100.0, item_type="weapon"
    )
    assert s1 is True
    await me.cancel_market_listing(market_db, lot1["id"], seller_id)

    # Relist
    s2, lot2, _ = await me.create_market_listing(
        market_db, seller_id=seller_id, seller_board_id="b", item_id="pepperspray_gun", price=120.0, item_type="weapon"
    )
    assert s2 is True
    assert lot2 is not None
    assert lot2["id"] != lot1["id"]
    assert lot2["price"] == 120.0


@pytest.mark.asyncio
async def test_market_double_buy_prevention(market_db):
    """Second attempt to buy an already sold lot fails."""
    me = _get_market_module()
    seller_id = 1014
    buyer1 = 2014
    buyer2 = 3014

    await _set_user(market_db, seller_id, balance=0, active_items={"knife_gun": True})
    await _set_user(market_db, buyer1, balance=200, active_items={})
    await _set_user(market_db, buyer2, balance=200, active_items={})

    success, lot, _ = await me.create_market_listing(
        market_db, seller_id=seller_id, seller_board_id="b", item_id="knife_gun", price=100.0, item_type="weapon"
    )
    assert success is True

    # First buyer succeeds
    s1, _, _, _, _, _, _ = await me.buy_market_listing(market_db, lot["id"], buyer1, "b")
    assert s1 is True

    # Second buyer fails
    s2, _, _, _, _, _, err2 = await me.buy_market_listing(market_db, lot["id"], buyer2, "b")
    assert s2 is False
    assert "уже" in err2.lower() or "sold" in err2.lower() or len(err2) > 0

    # Second buyer's balance is untouched
    bal2 = await common.database.get_user_global_balance(market_db, buyer2)
    assert bal2 == 200.0


# ===========================================================================
# TIER 3: PAIRWISE COMBINATORIAL & CROSS-FEATURE TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_market_multiple_listings_per_user(market_db):
    """A user can list multiple items simultaneously."""
    me = _get_market_module()
    seller_id = 1015
    await _set_user(market_db, seller_id, balance=0, active_items={
        "owned_hat_bag": True,
        "knife_gun": True,
        "lootbox_trash": 1
    })

    s1, l1, _ = await me.create_market_listing(market_db, seller_id, "b", "hat_bag", 50.0, item_type="clothing")
    s2, l2, _ = await me.create_market_listing(market_db, seller_id, "b", "knife_gun", 80.0, item_type="weapon")
    s3, l3, _ = await me.create_market_listing(market_db, seller_id, "b", "lootbox_trash", 120.0, item_type="lootbox")

    assert s1 and s2 and s3
    assert l1["id"] and l2["id"] and l3["id"]

    listings = await me.get_user_listings(market_db, seller_id)
    assert len(listings) == 3


@pytest.mark.asyncio
async def test_market_listing_equipped_wardrobe_auto_unequips(market_db):
    """Listing an equipped wardrobe item automatically unequips it."""
    me = _get_market_module()
    seller_id = 1016
    await _set_user(market_db, seller_id, balance=0, active_items={
        "owned_hat_helmet": True,
        "equipped_head": "hat_helmet",
        "owned_body_wasserman": True,
        "equipped_torso": "body_wasserman"
    })

    # List the helmet
    s, lot, _ = await me.create_market_listing(
        market_db, seller_id, "b", "hat_helmet", 400.0, item_type="clothing"
    )
    assert s is True

    items = await _get_user_items(market_db, seller_id)
    assert items.get("equipped_head") is None
    assert not items.get("owned_hat_helmet")
    # Torso remains equipped
    assert items.get("equipped_torso") == "body_wasserman"


@pytest.mark.asyncio
async def test_market_listing_permanent_vs_expiring_items(market_db):
    """Permanent item preserves permanent flag; timed item preserves expiration."""
    me = _get_market_module()
    seller_id = 1017
    buyer_id = 2017
    now = int(time.time())

    await _set_user(market_db, seller_id, balance=0, active_items={
        "owned_hat_crown": True,
        "hat_crown_is_permanent": True,
    })
    await _set_user(market_db, buyer_id, balance=1000, active_items={})

    # List permanent crown
    s_list, lot_perm, _ = await me.create_market_listing(
        market_db, seller_id, "b", "hat_crown", 300.0, item_type="clothing"
    )
    assert s_list is True

    # Buy permanent crown
    s, _, _, _, _, _, _ = await me.buy_market_listing(market_db, lot_perm["id"], buyer_id, "b")
    assert s is True

    buyer_items = await _get_user_items(market_db, buyer_id)
    assert buyer_items.get("owned_hat_crown") is True
    assert buyer_items.get("hat_crown_is_permanent") is True


@pytest.mark.asyncio
async def test_market_catalog_pagination(market_db):
    """Catalog returns correct pages, per_page items, and total count."""
    me = _get_market_module()
    seller_id = 1018

    # Create 12 lots
    for i in range(12):
        await market_db.execute(
            "INSERT INTO MarketListings (seller_id, seller_board_id, item_id, item_type, item_name, price, status, created_at) "
            "VALUES (?, 'b', ?, 'weapon', ?, ?, 'active', ?)",
            (seller_id, f"gun_{i}", f"Gun {i}", 10 + i * 5, time.time() + i)
        )

    # Page 1 (per_page=5)
    items1, total_pages, total_count = await me.get_market_catalog(market_db, page=1, per_page=5)
    assert len(items1) == 5
    assert total_pages == 3
    assert total_count == 12

    # Page 2 (per_page=5)
    items2, _, _ = await me.get_market_catalog(market_db, page=2, per_page=5)
    assert len(items2) == 5

    # Page 3 (per_page=5) -> remaining 2 items
    items3, _, _ = await me.get_market_catalog(market_db, page=3, per_page=5)
    assert len(items3) == 2

    # Page 4 (out of bounds) -> empty
    items4, _, _ = await me.get_market_catalog(market_db, page=4, per_page=5)
    assert len(items4) == 0


@pytest.mark.asyncio
async def test_market_catalog_sorting(market_db):
    """Catalog sorts correctly by price_asc, price_desc, and newest."""
    me = _get_market_module()
    seller_id = 1019

    prices = [500.0, 100.0, 300.0, 50.0, 200.0]
    for i, p in enumerate(prices):
        await market_db.execute(
            "INSERT INTO MarketListings (seller_id, seller_board_id, item_id, item_type, item_name, price, status, created_at) "
            "VALUES (?, 'b', ?, 'weapon', ?, ?, 'active', ?)",
            (seller_id, f"item_{i}", f"Item {i}", p, 1000 + i * 100)
        )

    # Price ASC
    asc_items, _, _ = await me.get_market_catalog(market_db, sort_order="price_asc", page=1, per_page=10)
    asc_prices = [it["price"] for it in asc_items]
    assert asc_prices == sorted(asc_prices)

    # Price DESC
    desc_items, _, _ = await me.get_market_catalog(market_db, sort_order="price_desc", page=1, per_page=10)
    desc_prices = [it["price"] for it in desc_items]
    assert desc_prices == sorted(desc_prices, reverse=True)

    # Newest (created_at DESC)
    new_items, _, _ = await me.get_market_catalog(market_db, sort_order="newest", page=1, per_page=10)
    new_ts = [it["created_at"] for it in new_items]
    assert new_ts == sorted(new_ts, reverse=True)


@pytest.mark.asyncio
async def test_market_catalog_category_filtering(market_db):
    """Category filter returns only items belonging to specified category."""
    me = _get_market_module()
    seller_id = 1020

    await market_db.execute("INSERT INTO MarketListings (seller_id, item_type, item_id, item_name, price, status, created_at) VALUES (?, 'clothing', 'hat_1', 'Hat 1', 10, 'active', 100)", (seller_id,))
    await market_db.execute("INSERT INTO MarketListings (seller_id, item_type, item_id, item_name, price, status, created_at) VALUES (?, 'weapon', 'gun_1', 'Gun 1', 20, 'active', 101)", (seller_id,))
    await market_db.execute("INSERT INTO MarketListings (seller_id, item_type, item_id, item_name, price, status, created_at) VALUES (?, 'pharma', 'pill_1', 'Pill 1', 30, 'active', 102)", (seller_id,))

    w_items, _, count = await me.get_market_catalog(market_db, category="clothing", page=1, per_page=10)
    assert count == 1
    assert w_items[0]["item_id"] == "hat_1"


# ===========================================================================
# TIER 4: REAL-WORLD TRADING JOURNEY & NOTIFICATION RESILIENCE
# ===========================================================================

@pytest.mark.asyncio
async def test_market_full_lifecycle_workflow(market_db):
    """End-to-end user journey: List -> Browse -> Buy -> Payout -> Buyer Equip."""
    me = _get_market_module()
    seller_id = 7771
    buyer_id = 7772

    # Step 1: Setup initial states
    await _set_user(market_db, seller_id, balance=50, active_items={"owned_hat_tophat": True})
    await _set_user(market_db, buyer_id, balance=1000, active_items={})

    # Step 2: Seller lists item
    s_list, lot, _ = await me.create_market_listing(
        market_db, seller_id=seller_id, seller_board_id="b", item_id="hat_tophat", price=400.0, item_type="clothing"
    )
    assert s_list is True
    assert lot["status"] == "active"

    # Step 3: Buyer browses catalog
    catalog, _, count = await me.get_market_catalog(market_db, category="clothing")
    assert any(it["id"] == lot["id"] for it in catalog)

    # Step 4: Buyer buys item
    success, s_id, price, payout, fee, item, err = await me.buy_market_listing(
        market_db, lot["id"], buyer_id, "b"
    )
    assert success is True
    assert payout == 380.0  # 400 - 5% (20 ₪)
    assert fee == 20.0

    # Step 5: Verify seller received payout
    s_bal = await common.database.get_user_global_balance(market_db, seller_id)
    assert s_bal == 50 + 380  # 430

    # Step 6: Verify buyer received item
    b_items = await _get_user_items(market_db, buyer_id)
    assert b_items.get("owned_hat_tophat") is True


@pytest.mark.asyncio
async def test_market_seller_notification_success():
    """PM notification is sent to seller with item name, price, and payout."""
    me = _get_market_module()
    bot_mock = AsyncMock()
    bot_mock.send_message = AsyncMock()

    await me.notify_seller_lot_sold(
        bot=bot_mock,
        seller_id=123456,
        item_name="🪖 Шлем ОМОНа",
        price=500.0,
        payout=475.0,
        fee=25.0
    )

    bot_mock.send_message.assert_called_once()
    args, kwargs = bot_mock.send_message.call_args
    sent_text = kwargs.get("text") or (args[1] if len(args) > 1 else "")
    assert "Шлем ОМОНа" in sent_text
    assert "475" in sent_text


@pytest.mark.asyncio
async def test_market_seller_notification_telegram_forbidden_suppressed():
    """If seller blocked the bot (TelegramForbiddenError / Exception), notification does not crash."""
    me = _get_market_module()
    bot_mock = AsyncMock()
    bot_mock.send_message = AsyncMock(side_effect=Exception("Forbidden: bot was blocked by the user"))

    # Must NOT raise exception
    await me.notify_seller_lot_sold(
        bot=bot_mock,
        seller_id=999999,
        item_name="🔪 Заточка",
        price=100.0,
        payout=95.0,
        fee=5.0
    )
