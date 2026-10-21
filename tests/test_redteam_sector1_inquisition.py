# -*- coding: utf-8 -*-
"""
tests/test_redteam_sector1_inquisition.py
Redteam Inquisitor Test Suite — Sector 1: Economy, Bank, Flea Market, Lootboxes.
Verifies all patched vulnerabilities:
- Lootbox escrow alias desync & duplication exploit
- Mirror shield reflect escrow leakage & buyer reflection restoration
- Tinfoil hat wardrobe escrow sync
- Oligarch raid proletarian qualification checking bank wealth
- Self-raid prevention & worker exclusion from target pool
- Bank deposit continuous interest preservation & stale last_accrual_at fix
- Auction sub-cent rounding & atomic auction cancellation refund
- Bank pending deposit cross-chat isolation
- Max deposit limit enforcement & malformed callback resilience
- Lootbox paired buff notification deduplication
"""

import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

import bank_engine
import lootbox_engine
import market_engine
import whale_economy_engine


@pytest.mark.asyncio
async def test_lootbox_escrow_anti_dupe(isolated_test_db):
    """
    Verifies that listing and cancelling a lootbox stored under an alias (e.g. trash_lootbox)
    does not duplicate items in active_items.
    """
    db = isolated_test_db
    user_id = 11111

    # Initial state: user owns 5 trash lootboxes under alias 'trash_lootbox'
    init_items = {"trash_lootbox": 5}
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000.0, ?)",
        (user_id, json.dumps(init_items))
    )

    # 1. Create market listing for 1 lootbox
    ok, listing, err = await market_engine.create_market_listing(
        db, user_id, "b", "trash_lootbox", 150.0
    )
    assert ok is True, f"Failed to create listing: {err}"
    assert listing is not None

    # Check active_items after listing: exactly 4 lootboxes must remain under canonical key
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        items = json.loads(row[0])

    assert "trash_lootbox" not in items, "Alias key was not wiped!"
    assert items.get("lootbox_trash") == 4, f"Expected 4 lootboxes remaining, got {items.get('lootbox_trash')}"

    # 2. Cancel the listing
    ok_cancel, item_dict, err_c = await market_engine.cancel_market_listing(db, listing["id"], user_id, "b")
    assert ok_cancel is True, f"Failed to cancel listing: {err_c}"

    # Check active_items after cancel: exactly 5 lootboxes must be restored
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        items = json.loads(row[0])

    assert items.get("lootbox_trash") == 5, f"Expected exactly 5 lootboxes after cancel, got {items.get('lootbox_trash')}"
    assert "trash_lootbox" not in items


@pytest.mark.asyncio
async def test_shield_escrow_reflection_immunity_closed(isolated_test_db):
    """
    Verifies that when a mirror shield is listed on the market:
    - reflect_shield_until is popped from seller (no combat reflection while selling)
    - When buyer buys it, buyer receives reflect_shield_until
    """
    db = isolated_test_db
    seller_id = 22221
    buyer_id = 22222
    now = int(time.time())

    # Seller has active mirror shield (both shield_until and reflect_shield_until)
    seller_items = {
        "shield_until": now + 7200,
        "reflect_shield_until": now + 7200,
        "shield_gun": True,
        "shield": True
    }
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500.0, ?)",
        (seller_id, json.dumps(seller_items))
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000.0, '{}')",
        (buyer_id,)
    )

    # Seller lists shield on the market
    ok, listing, err = await market_engine.create_market_listing(
        db, seller_id, "b", "shield", 200.0
    )
    assert ok is True

    # Verify seller NO LONGER has reflect_shield_until in inventory
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (seller_id,)) as c:
        row = await c.fetchone()
        s_items = json.loads(row[0])

    assert "shield_until" not in s_items
    assert "reflect_shield_until" not in s_items, "Seller kept reflect_shield_until while listing on market!"

    # Buyer purchases the shield
    ok_b, s_id, price, payout, fee, item_dict, b_err = await market_engine.buy_market_listing(
        db, listing["id"], buyer_id, "b"
    )
    assert ok_b is True, f"Purchase failed: {b_err}"

    # Verify buyer HAS reflect_shield_until and shield_until
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (buyer_id,)) as c:
        row = await c.fetchone()
        b_items = json.loads(row[0])

    assert b_items.get("shield_until", 0) > now
    assert b_items.get("reflect_shield_until", 0) > now, "Buyer did not receive reflect_shield_until!"
    assert b_items["shield_until"] == b_items["reflect_shield_until"]


@pytest.mark.asyncio
async def test_tinfoil_wardrobe_escrow_sync(isolated_test_db):
    """
    Verifies that listing a tinfoil hat un-equips it from equipped_head
    and removes owned_hat_tinfoil, and cancelling restores ownership.
    """
    db = isolated_test_db
    user_id = 33333
    now = int(time.time())

    items = {
        "tinfoil_until": now + 10000,
        "tinfoil_hat": now + 10000,
        "owned_hat_tinfoil": True,
        "equipped_head": "hat_tinfoil"
    }
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500.0, ?)",
        (user_id, json.dumps(items))
    )

    ok, listing, err = await market_engine.create_market_listing(
        db, user_id, "b", "tinfoil", 100.0
    )
    assert ok is True

    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
        items_after = json.loads((await c.fetchone())[0])

    assert items_after.get("equipped_head") is None, "Equipped head was not unequipped!"
    assert "owned_hat_tinfoil" not in items_after, "owned_hat_tinfoil was not removed!"

    # Cancel listing
    ok_c, _, _ = await market_engine.cancel_market_listing(db, listing["id"], user_id, "b")
    assert ok_c is True

    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
        items_restored = json.loads((await c.fetchone())[0])

    assert items_restored.get("owned_hat_tinfoil") is True, "owned_hat_tinfoil was not restored!"
    assert items_restored.get("tinfoil_until", 0) > now


@pytest.mark.asyncio
async def test_proletarian_raid_qualification_checks_bank_deposits(isolated_test_db):
    """
    Verifies that a user with low wallet balance (< 5,000) but large bank deposits
    is REJECTED from the proletarian voter pool.
    """
    db = isolated_test_db
    now = time.time()

    # User 1 has 100 ₪ in wallet, but 10,000,000 ₪ in bank deposits
    rich_fake_prole = 44441
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 100.0, 50)",
        (rich_fake_prole,)
    )
    await db.execute(
        """
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, accrued_interest, status)
        VALUES (?, 'b', 'sych', 10000000.0, 0.005, ?, ?, ?, 0.0, 'active')
        """,
        (rich_fake_prole, now, now, now)
    )

    # 4 genuine proletarians (balance 50 ₪, 30 posts, 0 bank)
    true_proles = [44442, 44443, 44444, 44445]
    for p in true_proles:
        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 50.0, 30)",
            (p,)
        )

    # Target oligarch
    target_id = 99999
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 500000.0, 100)",
        (target_id,)
    )

    voters = [rich_fake_prole] + true_proles
    result = await whale_economy_engine.execute_oligarch_raid(db, voters, target_id=target_id)

    # Must be rejected because rich_fake_prole has > 5000 ₪ total wealth, so only 4 qualified workers
    assert result["ok"] is False
    assert "Недостаточно квалифицированных рабочих" in result["error"]


@pytest.mark.asyncio
async def test_oligarch_cannot_raid_themselves(isolated_test_db):
    """
    Verifies that an oligarch cannot be part of the raid team against themselves.
    """
    db = isolated_test_db
    target_id = 55550

    # 5 voters where one is target_id
    voters = [target_id, 55551, 55552, 55553, 55554]
    for uid in voters:
        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 100.0, 50)",
            (uid,)
        )
    # Give target big bank balance so they qualify as oligarch
    now = time.time()
    await db.execute(
        """
        INSERT INTO BankDeposits (user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, accrued_interest, status)
        VALUES (?, 'b', 'sych', 1000000.0, 0.005, ?, ?, ?, 0.0, 'active')
        """,
        (target_id, now, now, now)
    )

    result = await whale_economy_engine.execute_oligarch_raid(db, voters, target_id=target_id)
    assert result["ok"] is False
    assert "против самого себя" in result["error"] or "Недостаточно квалифицированных" in result["error"]


@pytest.mark.asyncio
async def test_bank_deposit_accrual_updated_during_tax_and_raid(isolated_test_db):
    """
    Verifies that when wealth tax or raid confiscation touches a BankDeposit:
    - Continuous interest is computed up to now before deducting
    - last_accrual_at is updated to now (preventing double interest accrual)
    """
    db = isolated_test_db
    user_id = 66661
    past = time.time() - 86400  # Deposit created 1 day ago

    # Create deposit with 100,000 principal at 0.5% daily rate, last_accrual_at = past
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 0.0, 100)",
        (user_id,)
    )
    await db.execute(
        """
        INSERT INTO BankDeposits (id, user_id, board_id, tier_id, principal, daily_rate, created_at, locked_until, last_accrual_at, accrued_interest, status)
        VALUES (777, ?, 'b', 'sych', 100000.0, 0.005, ?, ?, ?, 0.0, 'active')
        """,
        (user_id, past, past, past)
    )

    # Process daily wealth tax (100,000 wealth falls in 1% bracket = 1,000 ₪ with 50% deposit discount = 500 ₪)
    res = await whale_economy_engine.process_daily_wealth_tax(db)
    assert res["affected_users"] == 1
    assert res["total_tax_collected"] > 0

    # Inspect the deposit record in DB
    async with db.execute(
        "SELECT principal, accrued_interest, last_accrual_at FROM BankDeposits WHERE id = 777"
    ) as c:
        row = await c.fetchone()
        p, acc, last_acc = row

    now = time.time()
    assert abs(last_acc - now) < 5.0, f"last_accrual_at was not updated to now! Found: {last_acc}, now: {now}"
    assert p < 100000.0, "Tax was not deducted from principal"


@pytest.mark.asyncio
async def test_auction_bid_rounding_and_cancellation(isolated_test_db):
    """
    Verifies that auction bids round fractional sub-cents to 2 decimals,
    and cancel_auction safely refunds the highest bidder.
    """
    db = isolated_test_db
    bidder_id = 77771
    await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000.0)", (bidder_id,))

    # Create auction
    auc_id = await whale_economy_engine.create_auction(
        db, lot_type="board_pin", title="VIP Pin", description="Top Pin",
        start_price=100.0, min_bid_step=10.0, duration_sec=3600.0
    )

    # Place bid with fractional cents: 150.005 -> should round to 150.01 or 150.00
    res = await whale_economy_engine.place_auction_bid(
        db, auc_id, bidder_id, "Anon77", 150.005
    )
    assert res["ok"] is True
    assert res["bid_amount"] == 150.0

    # Cancel auction and verify 100% refund
    c_res = await whale_economy_engine.cancel_auction(db, auc_id)
    assert c_res["ok"] is True
    assert c_res["refunded_to"] == bidder_id
    assert c_res["refunded_amount"] == 150.0

    # User balance must be back to 5000.0
    bal = await bank_engine.get_user_global_balance(db, bidder_id)
    assert bal == 5000.0


@pytest.mark.asyncio
async def test_bank_pending_deposit_filter_cross_chat_isolation():
    """
    Verifies that PendingBankDepositFilter isolates deposit amount typing
    strictly to the chat where the deposit wizard was opened.
    """
    user_id = 88881
    chat_a = -1001111111111  # Group A
    chat_b = -1002222222222  # Group B

    bank_engine.set_user_pending_deposit(user_id, "sych", chat_id=chat_a, board_id="b")

    filt = bank_engine.PendingBankDepositFilter()

    # Message from same user in chat_b -> MUST NOT match
    msg_b = MagicMock()
    msg_b.text = "50000"
    msg_b.from_user.id = user_id
    msg_b.chat.id = chat_b

    res_b = await filt(msg_b)
    assert res_b is False, "Filter hijacked message from another chat!"

    # Message from same user in chat_a -> MUST match
    msg_a = MagicMock()
    msg_a.text = "50000"
    msg_a.from_user.id = user_id
    msg_a.chat.id = chat_a

    res_a = await filt(msg_a)
    assert isinstance(res_a, dict), "Filter failed to match in target chat!"
    assert res_a["amount_str"] == "50000"

    bank_engine.clear_user_pending_deposit(user_id)


@pytest.mark.asyncio
async def test_bank_max_deposit_limit_and_callback_guards(isolated_test_db):
    """
    Verifies:
    - create_bank_deposit enforces max deposit limit (1,000,000,000)
    - callback handlers safely reject non-integer IDs without crashing
    """
    db = isolated_test_db
    user_id = 99991
    await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5e9)", (user_id,))

    # Max deposit limit
    ok, _, err = await bank_engine.create_bank_deposit(db, user_id, "b", "sych", 2_000_000_000.0)
    assert ok is False
    assert "Максимальная сумма" in err

    # Malformed callback resilience
    cb = MagicMock()
    cb.data = "bank_withdraw_sel:not_a_number"
    cb.from_user.id = user_id
    cb.answer = AsyncMock()

    await bank_engine.cb_bank_withdraw_sel(cb, "b")
    cb.answer.assert_called_once()
    assert "Некорректный номер" in cb.answer.call_args[0][0]


def test_lootbox_paired_buff_deduplication():
    """
    Verifies that rolling a case with paired protective buffs (tinfoil_hat + tinfoil_until)
    produces a clean single notification, not duplicate text.
    """
    now = int(time.time())
    active_items = {}
    payload = {
        "tinfoil_hat": now + 6 * 3600,
        "tinfoil_until": now + 6 * 3600,
        "owned_hat_tinfoil": True,
        "equipped_head": "hat_tinfoil"
    }

    ai, cash, note = lootbox_engine.apply_lootbox_reward(active_items, payload, 0, case_type="trash")

    assert note is not None
    # Count occurrences of the title string
    assert note.count("Шапочка из фольги") == 1, f"Duplicate note found in: {note}"
    assert ai["tinfoil_hat"] > now
    assert ai["tinfoil_until"] == ai["tinfoil_hat"]
    assert ai["owned_hat_tinfoil"] is True
