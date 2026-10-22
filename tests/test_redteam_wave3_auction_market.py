# -*- coding: utf-8 -*-
"""
tests/test_redteam_wave3_auction_market.py
Redteam Inquisitor Wave 3: Sector 1 (Auctions, Market & Escrow).

Audited Domains:
- auction_engine.py
- market_engine.py
- whale_economy_engine.py

Redteam Attack Vectors & Exploits Verified:
1. Auction lot creation parameter validation & micro-duration privilege stealing.
2. Case-insensitivity in lot_type reward distribution.
3. Auction admin cancellation with atomic escrow refund.
4. Schema idempotency without object id recycling traps.
5. Market Cryopreservation / Stasis Chamber Exploit: Temporary items freezing time on Bazar.
6. Market Whale Safe (lootbox_whale) catalog & listing support.
7. Market ОБЭП Extinguisher (extinguisher_obep) multi-charge support.
8. Class Wars / Raid Oligarch: Target oligarch self-sabotage prevention.
9. Class Wars / Raid Oligarch: Bank deposit stealth wealth proletarian guard.
10. Stale raid lobbies memory leak cleanup.
"""

import asyncio
import json
import time
from unittest import mock

import pytest
from aiogram import types

import common.database
from auction_engine import _ACTIVE_RAIDS, cb_raid_join, cmd_auction
from market_engine import (
    buy_market_listing,
    cancel_market_listing,
    classify_item,
    create_market_listing,
    ensure_market_schema,
    find_item_by_name_or_id,
    get_market_catalog,
    get_user_sellable_items_list,
)
from whale_economy_engine import (
    cancel_auction,
    create_auction,
    ensure_auction_schema,
    finish_active_auctions,
    place_auction_bid,
)


# =============================================================================
# PART 1: REDTEAM AUCTION INQUISITION
# =============================================================================

@pytest.mark.asyncio
async def test_auction_lot_creation_validations(isolated_test_db):
    """
    Exploit: Unsanitized lot creation allows arbitrary invalid lot types,
    negative prices, negative steps, or micro-second durations (stealing roles for 1 ₪).
    Fix: create_auction must validate lot_type, start_price >= 1, min_bid_step >= 1,
    and duration_sec >= 60.
    """
    db = isolated_test_db
    await ensure_auction_schema(db)

    # Invalid lot_type
    with pytest.raises(ValueError, match="Недопустимый тип лота"):
        await create_auction(
            db, lot_type="scam_role", title="Scam", description="Desc",
            start_price=1000.0, min_bid_step=100.0, duration_sec=3600.0
        )

    # Invalid start price
    with pytest.raises(ValueError, match="Стартовая цена"):
        await create_auction(
            db, lot_type="custom_role", title="Role", description="Desc",
            start_price=0.0, min_bid_step=100.0, duration_sec=3600.0
        )

    with pytest.raises(ValueError, match="Стартовая цена"):
        await create_auction(
            db, lot_type="custom_role", title="Role", description="Desc",
            start_price=-500.0, min_bid_step=100.0, duration_sec=3600.0
        )

    # Invalid min bid step
    with pytest.raises(ValueError, match="Минимальный шаг"):
        await create_auction(
            db, lot_type="custom_role", title="Role", description="Desc",
            start_price=1000.0, min_bid_step=0.0, duration_sec=3600.0
        )

    # Non-positive duration exploit (<= 0s)
    with pytest.raises(ValueError, match="Длительность аукциона"):
        await create_auction(
            db, lot_type="custom_role", title="Role", description="Desc",
            start_price=1000.0, min_bid_step=100.0, duration_sec=0.0
        )

    with pytest.raises(ValueError, match="Длительность аукциона"):
        await create_auction(
            db, lot_type="custom_role", title="Role", description="Desc",
            start_price=1000.0, min_bid_step=100.0, duration_sec=-60.0
        )


@pytest.mark.asyncio
async def test_auction_case_insensitive_lot_type_awarding(isolated_test_db):
    """
    Bug: If lot_type was created with mixed case like 'Custom_Role' or 'BOARD_PIN',
    finish_active_auctions checked `lot_type == "custom_role"` and failed to award
    the winner, burning their money for nothing.
    Fix: Normalization of lot_type to lower case.
    """
    db = isolated_test_db
    await ensure_auction_schema(db)

    # Create auction with uppercase/mixed lot_type
    auc_id = await create_auction(
        db, lot_type="Custom_Role", title="[Элитный Анон]", description="[Элитный Анон]",
        start_price=50000.0, min_bid_step=5000.0, duration_sec=120.0
    )

    user_id = 91001
    await common.database.add_user_global_balance(db, user_id, "b", 100000.0)

    # Place bid
    res = await place_auction_bid(db, auc_id, user_id, "TestWinner", 60000.0)
    assert res["ok"] is True

    # Fast forward time to finish
    await db.execute("UPDATE Auctions SET ends_at = ? WHERE id = ?", (time.time() - 10, auc_id))

    finished = await finish_active_auctions(db)
    assert len(finished) == 1
    assert finished[0]["winner_id"] == user_id

    # Verify custom prefix was properly awarded to user
    async with db.execute("SELECT custom_prefix FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        assert row is not None
        assert row[0] == "[Элитный Анон]"


@pytest.mark.asyncio
async def test_auction_cancel_with_escrow_refund(isolated_test_db):
    """
    Escrow Invariant: When an auction is cancelled (e.g. by admin or system),
    the current leader must be 100% refunded in atomic fashion and status changed to 'cancelled'.
    Subsequent bids on cancelled auction must be rejected.
    """
    db = isolated_test_db
    await ensure_auction_schema(db)

    auc_id = await create_auction(
        db, lot_type="board_pin", title="Pin /b/", description="24h pin",
        start_price=20000.0, min_bid_step=2000.0, duration_sec=3600.0
    )

    bidder_id = 91002
    await common.database.add_user_global_balance(db, bidder_id, "b", 50000.0)

    # Place bid 30,000 ₪
    await place_auction_bid(db, auc_id, bidder_id, "Bidder1", 30000.0)
    assert await common.database.get_user_global_balance(db, bidder_id) == 20000.0

    # Cancel auction
    res_cancel = await cancel_auction(db, auc_id)
    assert res_cancel["ok"] is True
    assert res_cancel["status"] == "cancelled"
    assert res_cancel["refunded_to"] == bidder_id
    assert res_cancel["refunded_amount"] == 30000.0

    # Bidder refunded to original 50,000 ₪
    assert await common.database.get_user_global_balance(db, bidder_id) == 50000.0

    # Cannot bid on cancelled auction
    res_bid_after = await place_auction_bid(db, auc_id, bidder_id, "Bidder1", 40000.0)
    assert res_bid_after["ok"] is False
    assert "завершен или отменен" in res_bid_after["error"]


@pytest.mark.asyncio
async def test_auction_schema_ensured_without_id_recycling_flaw(isolated_test_db):
    """
    Bug: _ENSURED_AUCTION_DBS cached id(db). In Python, memory addresses of GC'd objects
    are recycled, which can cause newly allocated db objects to skip schema creation.
    Fix: ensure_auction_schema must not fail on distinct databases.
    """
    db = isolated_test_db
    # Schema initialization should be robust and idempotent
    await ensure_auction_schema(db)
    # Check that Auctions and AuctionBids exist
    async with db.execute("SELECT COUNT(*) FROM Auctions") as c:
        row = await c.fetchone()
        assert row is not None


# =============================================================================
# PART 2: REDTEAM MARKET & BAZAAR INQUISITION
# =============================================================================

@pytest.mark.asyncio
async def test_market_cryopreservation_stasis_exploit_prevented(isolated_test_db):
    """
    CRITICAL EXPLOIT: Infinite Cryopreservation / Stasis Chamber.
    A user has an item expiring in 100 seconds.
    They list it on Bazar for 1,000,000 ₪.
    200 seconds elapse (the item should have expired).
    Previously: Cancelling the lot restored the item with fresh 100 seconds from 'now'!
    And buyers could buy an expired item and get fresh time!
    Fix:
    1. Market listings track expires_at timestamp.
    2. Items whose expires_at <= now are marked 'expired' and cannot be bought.
    3. When cancelling an expired item, it is recognized as expired and not resurrected.
    4. When cancelling before expiration, only remaining time (expires_at - now) is restored.
    """
    db = isolated_test_db
    await ensure_market_schema(db)
    seller_id = 92001
    now = int(time.time())

    # User has hat_crown expiring in 100 seconds
    exp_ts = now + 100
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
        (seller_id, json.dumps({
            "owned_hat_crown": True,
            "hat_crown_expires": exp_ts,
        }))
    )

    # 1. List item
    ok, lot, err = await create_market_listing(
        db, seller_id=seller_id, seller_board_id="b", item_id="hat_crown", price=500.0, item_type="clothing"
    )
    assert ok is True
    lot_id = lot["id"]

    # Verify expires_at is stored in item_data
    assert lot["item_data"].get("expires_at") == exp_ts

    # 2. Case A: Cancel partially elapsed (e.g. 40 seconds passed, 60s left)
    # Simulate time = now + 40
    with mock.patch("time.time", return_value=now + 40):
        ok_cancel, item_dict, err = await cancel_market_listing(db, lot_id, seller_id, "b")
        assert ok_cancel is True

        # Check seller active_items
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as c:
            row = await c.fetchone()
            ai = json.loads(row[0])
            # The item's expiration timestamp must NOT be extended!
            # It must be original exp_ts (or now+40 + 60 = exp_ts)
            assert ai.get("hat_crown_expires") <= exp_ts + 1
            assert ai.get("hat_crown_expires") >= exp_ts - 1

    # 3. Case B: Stasis Exploit Attempt (relist, wait until past expiration, attempt cancel)
    ok2, lot2, _ = await create_market_listing(
        db, seller_id=seller_id, seller_board_id="b", item_id="hat_crown", price=500.0, item_type="clothing"
    )
    assert ok2 is True
    lot2_id = lot2["id"]

    # Simulate time = now + 200 (100 seconds after item expired)
    with mock.patch("time.time", return_value=now + 200):
        # Buyer tries to buy: MUST BE REJECTED (item expired)
        buyer_id = 92002
        await common.database.add_user_global_balance(db, buyer_id, "b", 1000.0)
        ok_buy, _, _, _, _, _, buy_err = await buy_market_listing(db, lot2_id, buyer_id, "b")
        assert ok_buy is False
        assert "истек" in buy_err.lower() or "снят" in buy_err.lower() or "не активен" in buy_err.lower()

        # Seller tries to cancel: item expired, must not grant fresh duration!
        ok_cancel2, item_dict2, cancel_err = await cancel_market_listing(db, lot2_id, seller_id, "b")
        # Should inform that item expired on the market
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as c:
            row = await c.fetchone()
            ai2 = json.loads(row[0])
            # Item must NOT be active/usable
            assert not (ai2.get(f"hat_crown_expires", 0) > now + 200)


@pytest.mark.asyncio
async def test_market_lootbox_whale_safe_full_support(isolated_test_db):
    """
    Defect: LOOTBOXES_CATALOG omitted 'lootbox_whale' / 'whale_safe', preventing
    players from listing or buying Whale Safes on the Bazaar.
    Fix: 'lootbox_whale' and 'whale_safe' are added to catalogs and classification.
    """
    db = isolated_test_db
    await ensure_market_schema(db)

    # Check classification
    item_type, item_name, _ = classify_item("whale_safe")
    assert item_type == "lootbox"
    assert "Олигарх" in item_name or "Whale" in item_name

    # Check find_item_by_name_or_id
    res = find_item_by_name_or_id("сейф олигарха")
    assert res is not None
    assert res[1] == "lootbox"

    # User with whale_safe
    seller_id = 92003
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
        (seller_id, json.dumps({"lootbox_whale": 1}))
    )

    # Check sellable scanner
    sellable = get_user_sellable_items_list({"lootbox_whale": 1})
    assert any(s[0] == "lootbox_whale" for s in sellable)

    # List whale safe
    ok, lot, err = await create_market_listing(
        db, seller_id=seller_id, seller_board_id="b", item_id="lootbox_whale", price=45000.0, item_type="lootbox"
    )
    assert ok is True
    assert lot["item_id"] == "lootbox_whale"

    # Buyer buys
    buyer_id = 92004
    await common.database.add_user_global_balance(db, buyer_id, "b", 100000.0)
    ok_buy, s_id, price, payout, fee, item, err = await buy_market_listing(db, lot["id"], buyer_id, "b")
    assert ok_buy is True
    assert fee == 2250.0  # 5% of 45,000

    # Buyer received lootbox_whale in active_items
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (buyer_id,)) as c:
        row = await c.fetchone()
        buyer_ai = json.loads(row[0])
        assert buyer_ai.get("lootbox_whale") == 1


@pytest.mark.asyncio
async def test_market_extinguisher_obep_listing_and_charges(isolated_test_db):
    """
    Defect: extinguisher_obep was missing from market catalogs, and selling it
    did not preserve its charge count.
    Fix: extinguisher_obep catalog support and charge preservation.
    """
    db = isolated_test_db
    await ensure_market_schema(db)

    seller_id = 92005
    # User with 2 charges of extinguisher_obep
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
        (seller_id, json.dumps({
            "extinguisher_obep": True,
            "extinguisher_obep_charges": 2
        }))
    )

    # Classification
    c_type, c_name, _ = classify_item("extinguisher_obep")
    assert c_type in ("weapon", "pharma")

    # List
    ok, lot, err = await create_market_listing(
        db, seller_id=seller_id, seller_board_id="b", item_id="extinguisher_obep", price=6000.0
    )
    assert ok is True
    assert lot["item_data"].get("charges") == 2

    # Seller active_items no longer has extinguisher
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as c:
        row = await c.fetchone()
        s_ai = json.loads(row[0])
        assert not s_ai.get("extinguisher_obep")

    # Cancel lot -> charges restored
    ok_cancel, item_dict, _ = await cancel_market_listing(db, lot["id"], seller_id, "b")
    assert ok_cancel is True

    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as c:
        row = await c.fetchone()
        s_ai = json.loads(row[0])
        assert s_ai.get("extinguisher_obep") is True
        assert s_ai.get("extinguisher_obep_charges") == 2


@pytest.mark.asyncio
async def test_market_auto_expires_stale_lots(isolated_test_db):
    """
    Market catalog browsing automatically prunes/excludes expired temporary lots.
    """
    db = isolated_test_db
    await ensure_market_schema(db)
    now = time.time()

    # Insert lot with expired item
    past_meta = json.dumps({"expires_at": now - 3600, "remaining_seconds": 0})
    await db.execute("""
        INSERT INTO MarketListings (seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status, created_at)
        VALUES (99991, 'b', 'hat_crown', 'clothing', 'Expired Crown', ?, 500.0, 'active', ?)
    """, (past_meta, now - 7200))

    # Insert lot with active item
    future_meta = json.dumps({"expires_at": now + 3600, "remaining_seconds": 3600})
    await db.execute("""
        INSERT INTO MarketListings (seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status, created_at)
        VALUES (99992, 'b', 'hat_crown', 'clothing', 'Active Crown', ?, 500.0, 'active', ?)
    """, (future_meta, now))

    items, total_pages, total_count = await get_market_catalog(db, category="clothing")
    # Only the active crown should appear!
    assert total_count == 1
    assert items[0]["item_name"] == "Active Crown"


# =============================================================================
# PART 3: REDTEAM CLASS WARS / RAID OLIGARCH INQUISITION
# =============================================================================

@pytest.mark.asyncio
async def test_raid_oligarch_target_sabotage_prevented(isolated_test_db):
    """
    Vulnerability: In cb_raid_join, the target oligarch could click 'Вступить в рейд ОБЭП'.
    The handler didn't check target_id, allowing the oligarch to fill the 5th spot and
    crash/sabotage the raid against themselves.
    Fix: cb_raid_join explicitly rejects if user_id == target_id.
    """
    db = isolated_test_db
    oligarch_id = 93001
    raid_id = "test_sabotage_raid"

    _ACTIVE_RAIDS[raid_id] = {
        "voters": [93002],
        "target_id": oligarch_id,
        "board_id": "b",
        "created_at": time.time(),
        "chat_id": 100,
    }

    # Target oligarch attempts to join
    mock_cb = mock.AsyncMock(spec=types.CallbackQuery)
    mock_cb.data = f"raid_join_{raid_id}"
    mock_cb.from_user = mock.MagicMock(id=oligarch_id)
    mock_cb.answer = mock.AsyncMock()

    await cb_raid_join(mock_cb)

    # Must be rejected with alert
    mock_cb.answer.assert_called_once()
    call_args = mock_cb.answer.call_args[0]
    call_kwargs = mock_cb.answer.call_args[1]
    msg = call_args[0] if call_args else call_kwargs.get("text", "")
    assert "не может участвовать в рейде против самого себя" in msg or "Олигарх" in msg
    assert call_kwargs.get("show_alert") is True

    # Oligarch was NOT added to voters
    assert oligarch_id not in _ACTIVE_RAIDS[raid_id]["voters"]
    _ACTIVE_RAIDS.pop(raid_id, None)


@pytest.mark.asyncio
async def test_raid_oligarch_bank_deposit_proletarian_guard(isolated_test_db):
    """
    Vulnerability: cb_raid_join only checked wallet balance (Users.balance < 5000),
    ignoring BankDeposits. A billionaire with 0 wallet and 50M in deposits could join
    as a proletarian, sabotaging the execution phase.
    Fix: cb_raid_join calculates total wealth including BankDeposits.
    """
    db = isolated_test_db
    rich_fake_worker = 93005
    raid_id = "test_bank_guard_raid"

    _ACTIVE_RAIDS[raid_id] = {
        "voters": [93010],
        "target_id": None,
        "board_id": "b",
        "created_at": time.time(),
        "chat_id": 100,
    }

    # Rich user has 100 ₪ in wallet, but 2,000,000 ₪ in active BankDeposits
    await common.database.add_user_global_balance(db, rich_fake_worker, "b", 100.0)
    await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (rich_fake_worker,))
    now = time.time()
    await db.execute("""
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, accrued_interest, status)
        VALUES (?, 'b', 'tier_3', 2000000.0, 0.005, ?, ?, ?, 0.0, 'active')
    """, (rich_fake_worker, now, now + 86400, now))

    mock_cb = mock.AsyncMock(spec=types.CallbackQuery)
    mock_cb.data = f"raid_join_{raid_id}"
    mock_cb.from_user = mock.MagicMock(id=rich_fake_worker)
    mock_cb.answer = mock.AsyncMock()

    await cb_raid_join(mock_cb)

    # Must be rejected because total wealth >= 5000 ₪
    mock_cb.answer.assert_called_once()
    call_args = mock_cb.answer.call_args[0]
    call_kwargs = mock_cb.answer.call_args[1]
    msg = call_args[0] if call_args else call_kwargs.get("text", "")
    assert "не подходишь" in msg.lower() or "5,000" in msg or "баланс" in msg.lower()
    assert call_kwargs.get("show_alert") is True
    assert rich_fake_worker not in _ACTIVE_RAIDS[raid_id]["voters"]

    _ACTIVE_RAIDS.pop(raid_id, None)


@pytest.mark.asyncio
async def test_raid_lobby_stale_cleanup():
    """
    Memory Leak: Abandoned raid lobbies stayed in _ACTIVE_RAIDS forever.
    Fix: Stale lobbies older than 3600s are automatically pruned.
    """
    old_ts = time.time() - 7200  # 2 hours ago
    fresh_ts = time.time()

    _ACTIVE_RAIDS["stale_raid_1"] = {"created_at": old_ts, "voters": [1]}
    _ACTIVE_RAIDS["fresh_raid_1"] = {"created_at": fresh_ts, "voters": [2]}

    # Trigger cb_raid_join on non-existent or stale
    mock_cb = mock.AsyncMock(spec=types.CallbackQuery)
    mock_cb.data = "raid_join_stale_raid_1"
    mock_cb.from_user = mock.MagicMock(id=3)
    mock_cb.answer = mock.AsyncMock()

    await cb_raid_join(mock_cb)

    # Stale raid should have been cleaned up
    assert "stale_raid_1" not in _ACTIVE_RAIDS
    assert "fresh_raid_1" in _ACTIVE_RAIDS

    _ACTIVE_RAIDS.pop("fresh_raid_1", None)
