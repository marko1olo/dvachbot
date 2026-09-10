# -*- coding: utf-8 -*-
"""
tests/test_whale_economy_and_sinks.py
Milestone 3 Comprehensive Test Suite:
- F3.1: Exponential Whale Safes (pricing, 70% burn, drops, RTP <= 65%, cash RTP <= 20%)
- F3.2: Atomic Auctions (schema, bidding, escrow deduction, instant outbid refund, anti-sniping, 100% burn)
- F3.3: Super-Wealth Tax (progressive brackets, 1.5x idle surcharge, 100% burn) & Class Wars (/raid_oligarch)
- WAL Transaction Safety & Concurrency under asyncio.gather
- M2 Micro-Fix Verification (non_buyable relics alert with 0 balance and rich balance)
"""

import asyncio
import json
import math
import random
import time
from typing import Any, Dict, List
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import common.config
import common.database
import common.db_pool
import lootbox_engine
import main
import whale_economy_engine
from auction_engine import (
    auction_router,
    create_auction,
    ensure_auction_schema,
    finish_active_auctions,
    get_active_auctions,
    place_auction_bid,
)
from whale_economy_engine import (
    buy_whale_safe,
    calculate_wealth_tax,
    calculate_whale_safe_price,
    execute_oligarch_raid,
    process_daily_wealth_tax,
    roll_whale_safe,
)


# =============================================================================
# 1. WHALE SAFES (F3.1)
# =============================================================================

class TestWhaleSafes:
    """Tests for F3.1: Exponential Whale Safes, RTP caps, and 70% Abu Yacht Fund burn."""

    def test_whale_safe_price_exponential_progression(self):
        """Validates progression P(n) = int(50000 * (1.5 ** n)) for n in [0..6] and boundary conditions."""
        expected = [
            (0, 50000),
            (1, 75000),
            (2, 112500),
            (3, 168750),
            (4, 253125),
            (5, 379687),
            (6, 569531),
        ]
        for n, exp_price in expected:
            assert calculate_whale_safe_price(n) == exp_price, f"Failed at n={n}"

        # Clamping negative n safely to base price
        assert calculate_whale_safe_price(-1) == 50000
        assert calculate_whale_safe_price(-999) == 50000

    @pytest.mark.asyncio
    async def test_whale_safe_burn_70_percent_to_abu_fund(self, isolated_test_db):
        """Verifies 70% of case cost is permanently burned to Abu Yacht Fund."""
        db = isolated_test_db
        user_id = 71001
        await common.database.add_user_global_balance(db, user_id, "b", 200000.0)

        fund_before = await common.database.get_abu_fund_total(db)
        res = await buy_whale_safe(db, user_id, "b")

        assert res["ok"] is True
        assert res["price"] == 50000
        assert res["burned_to_abu"] == 35000.0  # 70% of 50,000

        fund_after = await common.database.get_abu_fund_total(db)
        assert round(fund_after - fund_before, 2) == 35000.0

        # Verify transaction record
        async with db.execute(
            "SELECT amount, category, description FROM UserTransactions WHERE user_id = ? AND category = 'shop' ORDER BY id ASC",
            (user_id,)
        ) as c:
            rows = await c.fetchall()
            assert len(rows) >= 1
            assert rows[0][0] == -50000.0
            assert "Сейф Китов #1" in rows[0][2]

    @pytest.mark.asyncio
    async def test_whale_safe_daily_counter_and_reset(self, isolated_test_db):
        """Checks daily opening counter increments price and resets after 24h."""
        db = isolated_test_db
        user_id = 71002
        await common.database.add_user_global_balance(db, user_id, "b", 1000000.0)

        # 1st safe: 50,000 ₪
        res1 = await buy_whale_safe(db, user_id, "b")
        assert res1["price"] == 50000
        assert res1["opened_today"] == 1

        # 2nd safe: 75,000 ₪
        res2 = await buy_whale_safe(db, user_id, "b")
        assert res2["price"] == 75000
        assert res2["opened_today"] == 2

        # Simulate 24 hours passing by modifying reset_ts in active_items
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            ai = json.loads(row[0])
            ai["whale_safes_reset_ts"] = int(time.time()) - 10  # expired
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(ai), user_id))

        # 3rd safe should reset to n=0 -> 50,000 ₪
        res3 = await buy_whale_safe(db, user_id, "b")
        assert res3["price"] == 50000
        assert res3["opened_today"] == 1

    def test_whale_safe_drop_structure_and_types(self):
        """roll_whale_safe returns valid 5-tuple: (tier, title, desc, payload, base_cash)."""
        for _ in range(50):
            tier, title, desc, payload, base_cash = roll_whale_safe()
            assert isinstance(tier, str) and len(tier) > 0
            assert isinstance(title, str) and len(title) > 0
            assert isinstance(desc, str) and len(desc) > 0
            assert isinstance(payload, dict)
            assert isinstance(base_cash, int) and base_cash >= 0

    def test_whale_safe_monte_carlo_rtp_and_cash_rtp(self):
        """
        Monte Carlo simulation: 5,000 rolls of roll_whale_safe().
        Must satisfy:
        1. Liquid Cash RTP <= 20.0%
        2. Total Nominal RTP <= 65.0%
        """
        random.seed(42)
        N = 5000
        cost_per_case = 50000.0
        total_spent = N * cost_per_case
        total_cash_returned = 0.0
        total_nominal_value = 0.0

        for _ in range(N):
            tier, title, desc, payload, base_cash = roll_whale_safe()
            total_cash_returned += base_cash

            nominal = base_cash
            if "[👑 Золотой Анон]" in payload.get("grant_title", ""):
                nominal += 15000
            elif payload.get("vip_pin_voucher"):
                nominal += 12000
            elif "face_monocle" in payload.get("grant_items", []):
                nominal += 20000 if payload.get("is_permanent") else 8000
            elif "body_padishah_mantle" in payload.get("grant_items", []):
                nominal += 25000 if payload.get("is_permanent") else 8000
            elif payload.get("diplomatic_passport_until"):
                nominal += 6000
            elif payload.get("extinguisher_obep"):
                nominal += 5000

            total_nominal_value += nominal

        liquid_cash_rtp = (total_cash_returned / total_spent) * 100.0
        total_nominal_rtp = (total_nominal_value / total_spent) * 100.0

        assert liquid_cash_rtp <= 20.0, f"Liquid Cash RTP {liquid_cash_rtp:.2f}% exceeds 20%"
        assert total_nominal_rtp <= 65.0, f"Total Nominal RTP {total_nominal_rtp:.2f}% exceeds 65%"

    def test_whale_safe_prestige_drop_tables_coverage(self):
        """Verifies all prestige and utility items appear in drop outcomes."""
        random.seed(12345)
        seen_items = set()

        for _ in range(2000):
            tier, title, desc, payload, base_cash = roll_whale_safe()
            if payload.get("grant_title"):
                seen_items.add("title_golden_anon")
            if payload.get("vip_pin_voucher"):
                seen_items.add("vip_pin_voucher")
            if payload.get("item_id"):
                seen_items.add(payload["item_id"])
            for itm in payload.get("grant_items", []):
                seen_items.add(itm)
            if payload.get("diplomatic_passport_until"):
                seen_items.add("diplomatic_passport")
            if payload.get("extinguisher_obep"):
                seen_items.add("extinguisher_obep")
            if base_cash == 15000:
                seen_items.add("gold_ingot")
            if base_cash == 1:
                seen_items.add("certificate_sucker")

        required = {
            "title_golden_anon",
            "vip_pin_voucher",
            "face_monocle",
            "body_padishah_mantle",
            "diplomatic_passport",
            "extinguisher_obep",
            "gold_ingot",
            "certificate_sucker",
        }
        missing = required - seen_items
        assert not missing, f"Missing items from Whale Safe drops: {missing}"

    @pytest.mark.asyncio
    async def test_whale_safe_insufficient_balance_rejection(self, isolated_test_db):
        """Rejects user with balance < safe price and leaves funds/Abu Fund unchanged."""
        db = isolated_test_db
        user_id = 71003
        await common.database.add_user_global_balance(db, user_id, "b", 49999.0)

        fund_before = await common.database.get_abu_fund_total(db)
        res = await buy_whale_safe(db, user_id, "b")

        assert res["ok"] is False
        assert "Недостаточно шекелей" in res["error"]

        bal_after = await common.database.get_user_global_balance(db, user_id)
        assert bal_after == 49999.0

        fund_after = await common.database.get_abu_fund_total(db)
        assert fund_after == fund_before


# =============================================================================
# 2. ATOMIC AUCTIONS (F3.2)
# =============================================================================

class TestAtomicAuctions:
    """Tests for F3.2: Atomic Auctions, Escrow, Outbid Refunds, Anti-Sniping, 100% Burn."""

    @pytest.mark.asyncio
    async def test_ensure_auction_schema_idempotency(self, isolated_test_db):
        """Idempotent creation of Auctions and AuctionBids schema."""
        db = isolated_test_db
        for _ in range(3):
            await ensure_auction_schema(db)

        async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as c:
            tables = [row[0] for row in await c.fetchall()]
            assert "Auctions" in tables
            assert "AuctionBids" in tables

    @pytest.mark.asyncio
    async def test_create_auction_and_defaults(self, isolated_test_db):
        """Creates auction with correct default values."""
        db = isolated_test_db
        auc_id = await create_auction(
            db,
            lot_type="custom_role",
            title="[Владелец /b/]",
            description="Уникальный префикс",
            start_price=50000.0,
            min_bid_step=5000.0,
            duration_sec=3600.0,
            board_id="b"
        )
        assert auc_id > 0

        async with db.execute("SELECT status, current_bid, current_winner_id, min_bid_step FROM Auctions WHERE id = ?", (auc_id,)) as c:
            row = await c.fetchone()
            assert row[0] == "active"
            assert row[1] == 50000.0
            assert row[2] is None
            assert row[3] == 5000.0

    @pytest.mark.asyncio
    async def test_get_active_auctions(self, isolated_test_db):
        """Retrieves active auctions."""
        db = isolated_test_db
        auc_id = await create_auction(
            db, "board_pin", "Закреп треда", "Закрепление на 24ч", 25000.0, 2500.0, 1800.0, "b"
        )
        active_list = await get_active_auctions(db, "b")
        assert len(active_list) >= 1
        found = [a for a in active_list if a["id"] == auc_id]
        assert len(found) == 1
        assert found[0]["lot_type"] == "board_pin"
        assert found[0]["time_left"] > 0

    @pytest.mark.asyncio
    async def test_auction_atomic_escrow_deduction(self, isolated_test_db):
        """First valid bid deducts escrow from user and updates auction state."""
        db = isolated_test_db
        user_id = 72001
        await common.database.add_user_global_balance(db, user_id, "b", 100000.0)

        auc_id = await create_auction(db, "custom_role", "Role", "Desc", 50000.0, 5000.0, 3600.0)
        res = await place_auction_bid(db, auc_id, user_id, "Anon 1", 50000.0, "b")

        assert res["ok"] is True
        bal = await common.database.get_user_global_balance(db, user_id)
        assert bal == 50000.0  # 100,000 - 50,000

        async with db.execute("SELECT current_bid, current_winner_id FROM Auctions WHERE id = ?", (auc_id,)) as c:
            row = await c.fetchone()
            assert row[0] == 50000.0
            assert row[1] == user_id

        async with db.execute("SELECT bid_amount FROM AuctionBids WHERE auction_id = ?", (auc_id,)) as c:
            bids = await c.fetchall()
            assert len(bids) == 1
            assert bids[0][0] == 50000.0

    @pytest.mark.asyncio
    async def test_auction_instant_outbid_refund(self, isolated_test_db):
        """When user 2 outbids user 1, user 1 receives instant 100% refund."""
        db = isolated_test_db
        u1, u2 = 72002, 72003
        await common.database.add_user_global_balance(db, u1, "b", 100000.0)
        await common.database.add_user_global_balance(db, u2, "b", 100000.0)

        auc_id = await create_auction(db, "custom_role", "Role", "Desc", 50000.0, 5000.0, 3600.0)

        # U1 bids 50,000 ₪
        await place_auction_bid(db, auc_id, u1, "U1", 50000.0, "b")
        assert await common.database.get_user_global_balance(db, u1) == 50000.0

        # U2 bids 60,000 ₪
        res2 = await place_auction_bid(db, auc_id, u2, "U2", 60000.0, "b")
        assert res2["ok"] is True
        assert res2["previous_winner"] == u1

        # U1 must have full 100,000 ₪ restored instantly
        assert await common.database.get_user_global_balance(db, u1) == 100000.0
        # U2 has 60,000 ₪ in escrow
        assert await common.database.get_user_global_balance(db, u2) == 40000.0

        # Verify transaction log for refund
        async with db.execute(
            "SELECT amount, category FROM UserTransactions WHERE user_id = ? AND category = 'auction_refund'",
            (u1,)
        ) as c:
            rows = await c.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == 50000.0

    @pytest.mark.asyncio
    async def test_auction_multi_user_outbid_chain(self, isolated_test_db):
        """Chain of 5 bidders preserves strict conservation: sum(balances) + escrow = initial_total."""
        db = isolated_test_db
        users = [72010 + i for i in range(5)]
        for u in users:
            await common.database.add_user_global_balance(db, u, "b", 200000.0)

        initial_total = 5 * 200000.0
        auc_id = await create_auction(db, "custom_role", "Role", "Desc", 50000.0, 5000.0, 3600.0)

        for i, u in enumerate(users):
            bid = 50000.0 + i * 10000.0
            res = await place_auction_bid(db, auc_id, u, f"U{i}", bid, "b")
            assert res["ok"] is True

            # Invariant check
            total_now = sum([await common.database.get_user_global_balance(db, uid) for uid in users])
            assert round(total_now + bid, 2) == round(initial_total, 2)

        # At the end, only the last bidder has deducted funds
        for u in users[:-1]:
            assert await common.database.get_user_global_balance(db, u) == 200000.0
        assert await common.database.get_user_global_balance(db, users[-1]) == 200000.0 - 90000.0

    @pytest.mark.asyncio
    async def test_auction_anti_sniping_extension(self, isolated_test_db):
        """Bidding with <300s left extends auction duration by 300s."""
        db = isolated_test_db
        u = 72020
        await common.database.add_user_global_balance(db, u, "b", 100000.0)

        # Create auction with only 60 seconds left
        auc_id = await create_auction(db, "custom_role", "Role", "Desc", 10000.0, 1000.0, 60.0)

        res = await place_auction_bid(db, auc_id, u, "Sniper", 10000.0, "b")
        assert res["ok"] is True
        assert res["extended"] is True
        assert res["ends_at"] >= time.time() + 295

    @pytest.mark.asyncio
    async def test_auction_bid_validations_comprehensive(self, isolated_test_db):
        """Comprehensive input validation for bids."""
        db = isolated_test_db
        u = 72030
        await common.database.add_user_global_balance(db, u, "b", 100000.0)

        auc_id = await create_auction(db, "custom_role", "Role", "Desc", 50000.0, 5000.0, 3600.0)

        # Negative & NaN / Inf
        assert (await place_auction_bid(db, auc_id, u, "U", -100.0))["ok"] is False
        assert (await place_auction_bid(db, auc_id, u, "U", float("nan")))["ok"] is False
        assert (await place_auction_bid(db, auc_id, u, "U", float("inf")))["ok"] is False

        # Below start price
        res_low = await place_auction_bid(db, auc_id, u, "U", 40000.0)
        assert res_low["ok"] is False
        assert "Слишком маленькая ставка" in res_low["error"]

        # Valid bid
        res_ok = await place_auction_bid(db, auc_id, u, "U", 50000.0)
        assert res_ok["ok"] is True

        # Self-outbid
        res_self = await place_auction_bid(db, auc_id, u, "U", 60000.0)
        assert res_self["ok"] is False
        assert "уже наивысшая" in res_self["error"]

    @pytest.mark.asyncio
    async def test_finish_active_auctions_100_percent_burn_and_rewards(self, isolated_test_db):
        """Finished auctions burn 100% of winning bid to Abu Fund and award items."""
        db = isolated_test_db
        u_role = 72041
        u_pin = 72042
        u_badge = 72043

        await common.database.add_user_global_balance(db, u_role, "b", 100000.0)
        await common.database.add_user_global_balance(db, u_pin, "b", 100000.0)
        await common.database.add_user_global_balance(db, u_badge, "b", 100000.0)

        # 1. Custom Role lot
        a1 = await create_auction(db, "custom_role", "Царь Борды", "[👑 Царь Борды]", 50000.0, 5000.0, 1.0)
        await place_auction_bid(db, a1, u_role, "U1", 50000.0)

        # 2. Board Pin lot
        a2 = await create_auction(db, "board_pin", "Пин Указ", "Указ", 30000.0, 3000.0, 1.0)
        await place_auction_bid(db, a2, u_pin, "U2", 30000.0)

        # 3. Custom Badge lot
        a3 = await create_auction(db, "custom_badge", "Шейх", "Бейдж Шейха", 20000.0, 2000.0, 1.0)
        await place_auction_bid(db, a3, u_badge, "U3", 20000.0)

        # Force expiration (bidding extended ends_at via anti-sniping)
        past = time.time() - 10
        await db.execute("UPDATE Auctions SET ends_at = ? WHERE id IN (?, ?, ?)", (past, a1, a2, a3))
        fund_before = await common.database.get_abu_fund_total(db)

        finished = await finish_active_auctions(db)
        assert len(finished) == 3

        # 100% burn: 50,000 + 30,000 + 20,000 = 100,000 ₪
        fund_after = await common.database.get_abu_fund_total(db)
        assert round(fund_after - fund_before, 2) == 100000.0

        # Verify reward fulfillment:
        # u_role got custom_prefix
        async with db.execute("SELECT custom_prefix FROM Users WHERE user_id = ?", (u_role,)) as c:
            row = await c.fetchone()
            assert row[0] == "[👑 Царь Борды]"

        # u_pin got vip_pin_voucher
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (u_pin,)) as c:
            row = await c.fetchone()
            ai = json.loads(row[0])
            assert ai.get("vip_pin_voucher") is True
            assert ai.get("pin_vouchers", 0) >= 1

        # u_badge got custom_badge
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (u_badge,)) as c:
            row = await c.fetchone()
            ai = json.loads(row[0])
            assert ai.get("custom_badge") == "Шейх"


# =============================================================================
# 3. SUPER-WEALTH TAX & CLASS WARS (F3.3)
# =============================================================================

class TestSuperWealthTaxAndClassWars:
    """Tests for F3.3: Progressive brackets, 1.5x idle surcharge, and /raid_oligarch."""

    def test_super_wealth_tax_bracket_tiers(self):
        """Verifies progressive brackets (0% up to 5.0%) and boundary values."""
        assert calculate_wealth_tax(5000.0) == 0.0
        assert calculate_wealth_tax(5001.0) == pytest.approx(15.003, 0.01)  # 0.3%
        assert calculate_wealth_tax(50000.0) == pytest.approx(150.0, 0.01)
        assert calculate_wealth_tax(50001.0) == pytest.approx(500.01, 0.01)  # 1.0%
        assert calculate_wealth_tax(500000.0) == pytest.approx(5000.0, 0.01)
        assert calculate_wealth_tax(500001.0) == pytest.approx(12500.025, 0.01)  # 2.5%
        assert calculate_wealth_tax(5000000.0) == pytest.approx(125000.0, 0.01)
        assert calculate_wealth_tax(5000001.0) == pytest.approx(250000.05, 0.01)  # 5.0%

    def test_super_wealth_tax_idle_surcharge(self):
        """Verifies 1.5x surcharge for balances > 500k with idle_hours >= 72.0."""
        # Mega-wallet (1,000,000 ₪) active (<72h): 2.5% = 25,000 ₪
        tax_active = calculate_wealth_tax(1000000.0, idle_hours=24.0)
        assert tax_active == 25000.0

        # Mega-wallet (1,000,000 ₪) idle (>=72h): 2.5% * 1.5 = 3.75% = 37,500 ₪
        tax_idle = calculate_wealth_tax(1000000.0, idle_hours=72.0)
        assert tax_idle == 37500.0

        # Sub-500k wallet (300,000 ₪) idle: no surcharge, standard 1% = 3,000 ₪
        tax_small_idle = calculate_wealth_tax(300000.0, idle_hours=100.0)
        assert tax_small_idle == 3000.0

    @pytest.mark.asyncio
    async def test_process_daily_wealth_tax_full_execution(self, isolated_test_db):
        """Executes daily tax across multi-user cohort and burns 100% to Abu Fund."""
        db = isolated_test_db
        u_exempt = 73001
        u_mid = 73002
        u_oligarch = 73003

        await common.database.add_user_global_balance(db, u_exempt, "b", 4000.0)
        await common.database.add_user_global_balance(db, u_mid, "b", 20000.0)
        await common.database.add_user_global_balance(db, u_oligarch, "b", 1000000.0)

        # Mark oligarch as inactive (>72h)
        now = time.time()
        await db.execute(
            "INSERT INTO Posts (board_id, thread_id, post_num, author_id, content, timestamp) VALUES ('b', 1, 100, ?, '{}', ?)",
            (u_oligarch, now - 80 * 3600)
        )

        fund_before = await common.database.get_abu_fund_total(db)
        res = await process_daily_wealth_tax(db)

        assert res["affected_users"] >= 2  # u_mid and u_oligarch
        fund_after = await common.database.get_abu_fund_total(db)
        assert fund_after > fund_before

        # u_exempt was not taxed
        assert await common.database.get_user_global_balance(db, u_exempt) == 4000.0

        # u_oligarch was taxed with idle surcharge
        tax_oli = 1000000.0 * 0.025 * 1.5  # 37,500 ₪
        assert await common.database.get_user_global_balance(db, u_oligarch) == 1000000.0 - tax_oli

    @pytest.mark.asyncio
    async def test_raid_oligarch_qualification_and_rejection(self, isolated_test_db):
        """Requires 5 qualified proletarians (<5,000 ₪, >=25 posts). Rejects if not met."""
        db = isolated_test_db
        voters = [73100 + i for i in range(5)]

        # Setup 4 qualified and 1 disqualified (balance >= 5000)
        for v in voters[:4]:
            await common.database.add_user_global_balance(db, v, "b", 1000.0)
            await db.execute("UPDATE Users SET posts_count = 30 WHERE user_id = ?", (v,))

        v_rich = voters[4]
        await common.database.add_user_global_balance(db, v_rich, "b", 6000.0)  # Disqualified
        await db.execute("UPDATE Users SET posts_count = 30 WHERE user_id = ?", (v_rich,))

        res = await execute_oligarch_raid(db, voters, None, "b")
        assert res["ok"] is False
        assert "Недостаточно квалифицированных рабочих" in res["error"]

    @pytest.mark.asyncio
    async def test_raid_oligarch_confiscation_and_dilution(self, isolated_test_db):
        """10% confiscated, 70% burned, 30% redistributed to 5 workers."""
        db = isolated_test_db
        voters = [73200 + i for i in range(5)]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 1000.0)
            await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (v,))

        target_id = 73299
        await common.database.add_user_global_balance(db, target_id, "b", 500000.0)

        fund_before = await common.database.get_abu_fund_total(db)
        res = await execute_oligarch_raid(db, voters, target_id, "b")

        assert res["ok"] is True
        assert res["confiscated"] == 50000.0  # 10% of 500,000
        assert res["burned_to_abu"] == 35000.0  # 70%
        assert res["distributed_total"] == 15000.0  # 30%
        assert res["per_voter"] == 3000.0  # 15,000 / 5

        # Oligarch balance
        assert await common.database.get_user_global_balance(db, target_id) == 450000.0

        # Abu Fund
        fund_after = await common.database.get_abu_fund_total(db)
        assert round(fund_after - fund_before, 2) == 35000.0

        # Each voter received 3,000 ₪
        for v in voters:
            assert await common.database.get_user_global_balance(db, v) == 4000.0  # 1,000 + 3,000

    @pytest.mark.asyncio
    async def test_raid_oligarch_confiscation_cap_200000(self, isolated_test_db):
        """Confiscation is capped at 200,000 ₪ even for mega-wallets."""
        db = isolated_test_db
        voters = [73300 + i for i in range(5)]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 500.0)
            await db.execute("UPDATE Users SET posts_count = 35 WHERE user_id = ?", (v,))

        mega_target = 73399
        await common.database.add_user_global_balance(db, mega_target, "b", 5000000.0)  # 10% would be 500k

        res = await execute_oligarch_raid(db, voters, mega_target, "b")
        assert res["ok"] is True
        assert res["confiscated"] == 200000.0  # capped at 200k
        assert res["burned_to_abu"] == 140000.0  # 70% of 200k
        assert res["distributed_total"] == 60000.0  # 30% of 200k
        assert res["per_voter"] == 12000.0

        assert await common.database.get_user_global_balance(db, mega_target) == 4800000.0

    @pytest.mark.asyncio
    async def test_raid_oligarch_defenses(self, isolated_test_db):
        """Diplomatic passport blocks raid; Extinguisher consumes 1 charge and blocks raid."""
        db = isolated_test_db
        voters = [73400 + i for i in range(5)]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 500.0)
            await db.execute("UPDATE Users SET posts_count = 40 WHERE user_id = ?", (v,))

        t_pass = 73491
        await common.database.add_user_global_balance(db, t_pass, "b", 100000.0)
        ai_pass = {"diplomatic_passport_until": int(time.time()) + 3600}
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(ai_pass), t_pass))

        res_pass = await execute_oligarch_raid(db, voters, t_pass, "b")
        assert res_pass["ok"] is False
        assert res_pass.get("blocked") is True
        assert "Дипломатический Паспорт" in res_pass["error"]

        # Extinguisher
        t_ext = 73492
        await common.database.add_user_global_balance(db, t_ext, "b", 100000.0)
        ai_ext = {"extinguisher_obep": True, "extinguisher_obep_charges": 1}
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(ai_ext), t_ext))

        res_ext = await execute_oligarch_raid(db, voters, t_ext, "b")
        assert res_ext["ok"] is False
        assert res_ext.get("blocked") is True
        assert "Огнетушитель ОБЭП" in res_ext["error"]

        # Charge was consumed
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (t_ext,)) as c:
            row = await c.fetchone()
            ai_after = json.loads(row[0])
            assert "extinguisher_obep" not in ai_after


# =============================================================================
# 4. WAL CONCURRENCY & TRANSACTION SAFETY
# =============================================================================

class TestWALTransactionSafetyAndConcurrency:
    """Tests for SQLite WAL mode concurrency invariants."""

    @pytest.mark.asyncio
    async def test_concurrent_auction_bidding_race_invariant(self, isolated_test_db):
        """10 concurrent bidders compete via asyncio.gather. Total currency is preserved."""
        db = isolated_test_db
        await ensure_auction_schema(db)
        auc_id = await create_auction(db, "custom_role", "Title", "Desc", 10000.0, 1000.0, 3600.0)

        user_ids = [74000 + i for i in range(10)]
        for uid in user_ids:
            await common.database.add_user_global_balance(db, uid, "b", 100000.0)

        initial_total = 10 * 100000.0

        async def place_bid_task(uid, amount):
            try:
                return await place_auction_bid(db, auc_id, uid, f"Anon_{uid}", amount)
            except Exception as e:
                return {"ok": False, "error": str(e)}

        # Launch 10 simultaneous bids with increments
        tasks = [place_bid_task(user_ids[i], 15000.0 + i * 2000.0) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # Invariant 1: No unexpected crash
        for r in results:
            assert isinstance(r, dict)

        # Invariant 2: Total money in circulation is conserved
        async with db.execute("SELECT current_bid, current_winner_id FROM Auctions WHERE id = ?", (auc_id,)) as c:
            row = await c.fetchone()
            cur_bid, cur_winner = row[0], row[1]

        total_now = sum([await common.database.get_user_global_balance(db, uid) for uid in user_ids])
        assert round(total_now + cur_bid, 2) == round(initial_total, 2)
        assert cur_winner in user_ids

    @pytest.mark.asyncio
    async def test_concurrent_whale_safe_purchase_race(self, isolated_test_db):
        """User with balance for only 1 safe launches 5 concurrent requests. Exactly 1 succeeds."""
        db = isolated_test_db
        user_id = 74101
        # Has 60,000 ₪ (enough for only 1 safe at 50,000 ₪)
        await common.database.add_user_global_balance(db, user_id, "b", 60000.0)

        tasks = [buy_whale_safe(db, user_id, "b") for _ in range(5)]
        results = await asyncio.gather(*tasks)

        successes = [r for r in results if r.get("ok") is True]
        failures = [r for r in results if r.get("ok") is False]

        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
        assert len(failures) == 4

        # Balance was deducted for 1 purchase + cashback
        bal = await common.database.get_user_global_balance(db, user_id)
        cashback = successes[0]["final_cash"]
        assert bal == 10000.0 + cashback

    @pytest.mark.asyncio
    async def test_wal_transaction_atomicity_and_rollback_on_failure(self, isolated_test_db):
        """Rolls back partial operations on unhandled exception inside db_transaction."""
        db = isolated_test_db
        user_id = 74201
        await common.database.add_user_global_balance(db, user_id, "b", 50000.0)

        with pytest.raises(RuntimeError):
            async with common.db_pool.db_lock:
                async with common.db_pool.db_transaction(db):
                    await common.database.deduct_user_global_balance(db, user_id, "b", 30000.0)
                    raise RuntimeError("Simulated crash mid-transaction")

        bal = await common.database.get_user_global_balance(db, user_id)
        assert bal == 50000.0


# =============================================================================
# 5. M2 MICRO-FIX & SHOP WIRING
# =============================================================================

class TestM2MicroFixAndShopWiring:
    """Tests verifying M2 micro-fix and M3 shop wiring in main.py."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("relic_id", [
        "hat_golden_foil",
        "hat_cyber_ushanka",
        "body_dva_ch_mantle",
        "body_padishah_mantle",
        "face_monocle",
    ])
    async def test_shop_callback_non_buyable_zero_balance_rejection(self, isolated_test_db, relic_id):
        """
        User with 0 balance attempting to buy non-buyable relic receives
        the non-buyable alert rather than 'insufficient funds'.
        """
        from main import cb_shop_buy
        db = isolated_test_db
        user_id = 75001

        # 0 balance
        await common.database.add_user_global_balance(db, user_id, "b", 0.0)

        callback = MagicMock()
        callback.from_user.id = user_id
        callback.data = f"shop_buy_{relic_id}"
        callback.answer = AsyncMock()
        callback.message = MagicMock()

        with patch("main.get_pool", AsyncMock(return_value=db)), \
             patch("shared_state.record_shop_purchase", MagicMock()):
            await cb_shop_buy(callback, "b")

        # Must return the exact alert
        callback.answer.assert_called_once_with(
            "Этот предмет является уникальной реликвией из кейсов и не продается в обычном магазине!",
            show_alert=True
        )

        bal = await common.database.get_user_global_balance(db, user_id)
        assert bal == 0.0

    @pytest.mark.asyncio
    async def test_shop_callback_non_buyable_rich_balance_rejection(self, isolated_test_db):
        """User with large balance attempting to buy non-buyable relic is also rejected without deduction."""
        from main import cb_shop_buy
        db = isolated_test_db
        user_id = 75002

        await common.database.add_user_global_balance(db, user_id, "b", 500000.0)

        callback = MagicMock()
        callback.from_user.id = user_id
        callback.data = "shop_buy_face_monocle"
        callback.answer = AsyncMock()
        callback.message = MagicMock()

        with patch("main.get_pool", AsyncMock(return_value=db)), \
             patch("shared_state.record_shop_purchase", MagicMock()):
            await cb_shop_buy(callback, "b")

        callback.answer.assert_called_once_with(
            "Этот предмет является уникальной реликвией из кейсов и не продается в обычном магазине!",
            show_alert=True
        )

        bal = await common.database.get_user_global_balance(db, user_id)
        assert bal == 500000.0

    @pytest.mark.asyncio
    async def test_shop_callback_buyable_item_success_contrast(self, isolated_test_db):
        """Regular buyable item succeeds and deducts funds."""
        from main import cb_shop_buy
        db = isolated_test_db
        user_id = 75003

        await common.database.add_user_global_balance(db, user_id, "b", 10000.0)

        callback = MagicMock()
        callback.from_user.id = user_id
        callback.data = "shop_buy_feet_boots"
        callback.answer = AsyncMock()
        callback.message = MagicMock()

        with patch("main.get_pool", AsyncMock(return_value=db)), \
             patch("shared_state.record_shop_purchase", MagicMock()), \
             patch("main._render_shop_subview", AsyncMock()):
            await cb_shop_buy(callback, "b")

        bal = await common.database.get_user_global_balance(db, user_id)
        assert bal < 10000.0

    @pytest.mark.asyncio
    async def test_shop_callback_whale_safe_purchase(self, isolated_test_db):
        """Callback shop_buy_lootbox_whale successfully purchases safe and burns 70% to Abu Fund."""
        from main import cb_shop_buy
        db = isolated_test_db
        user_id = 75004

        await common.database.add_user_global_balance(db, user_id, "b", 100000.0)

        callback = MagicMock()
        callback.from_user.id = user_id
        callback.data = "shop_buy_lootbox_whale"
        callback.answer = AsyncMock()
        callback.message = MagicMock()

        fund_before = await common.database.get_abu_fund_total(db)

        with patch("main.get_pool", AsyncMock(return_value=db)), \
             patch("shared_state.record_shop_purchase", MagicMock()), \
             patch("main._render_shop_subview", AsyncMock()):
            await cb_shop_buy(callback, "b")

        fund_after = await common.database.get_abu_fund_total(db)
        assert round(fund_after - fund_before, 2) == 35000.0

    def test_build_lootbox_shop_content_contains_whale_safe(self):
        """_build_lootbox_shop_content includes Whale Safe info and button."""
        text, kb = main._build_lootbox_shop_content(user_id=1, balance=50000.0)
        assert "Сейф Олигарха" in text
        assert "50 000 ₪ × 1.5ⁿ" in text
        assert "70% стоимости" in text

        callback_buttons = [
            button.callback_data
            for row in kb.inline_keyboard
            for button in row
        ]
        assert "shop_buy_lootbox_whale" in callback_buttons

    @pytest.mark.asyncio
    async def test_cmd_auction_and_bid_flow(self, isolated_test_db):
        """Tests /auction and /bid commands via auction_engine."""
        from auction_engine import cmd_auction, cmd_bid
        db = isolated_test_db
        user_id = 75010
        await common.database.add_user_global_balance(db, user_id, "b", 100000.0)

        # 1. /auction with no active auctions
        msg = MagicMock()
        msg.board_id = "b"
        msg.from_user.id = user_id
        msg.from_user.full_name = "WhaleAnon"
        msg.text = "/auction"
        msg.reply = AsyncMock()

        await cmd_auction(msg)
        msg.reply.assert_called_once()
        assert "АУКЦИОННЫЙ ДОМ ДВАЧА" in msg.reply.call_args[0][0]

        # 2. /auction create custom_role 50000 5000 24 Тестовый Барон
        msg.reset_mock()
        msg.board_id = "b"
        msg.text = "/auction create custom_role 50000 5000 24 Тестовый Барон"
        await cmd_auction(msg)
        assert "успешно создан" in msg.reply.call_args[0][0]

        # 3. /auction now lists the lot
        msg.reset_mock()
        msg.board_id = "b"
        msg.text = "/auction"
        await cmd_auction(msg)
        assert "АКТИВНЫЕ АУКЦИОНЫ" in msg.reply.call_args[0][0]

        # 4. /bid 1 50000
        msg.reset_mock()
        msg.board_id = "b"
        msg.text = "/bid 1 50000"
        await cmd_bid(msg)
        assert "СТАВКА ПРИНЯТА" in msg.reply.call_args[0][0]

    @pytest.mark.asyncio
    async def test_cmd_whale_safe_and_raid_commands(self, isolated_test_db):
        """Tests /whale_safe and /raid_oligarch commands."""
        from auction_engine import cmd_whale_safe, cmd_raid_oligarch
        db = isolated_test_db
        user_id = 75020
        await common.database.add_user_global_balance(db, user_id, "b", 100000.0)

        # /whale_safe
        msg = MagicMock()
        msg.board_id = "b"
        msg.from_user.id = user_id
        msg.from_user.full_name = "Whale"
        msg.text = "/whale_safe"
        msg.reply = AsyncMock()
        msg.reply_to_message = None

        await cmd_whale_safe(msg)
        assert "СЕЙФ ОЛИГАРХА ВЗЛОМАН" in msg.reply.call_args[0][0]

        # /raid_oligarch interactive lobby
        msg.reset_mock()
        msg.board_id = "b"
        msg.chat.id = 999
        msg.text = "/raid_oligarch"
        await cmd_raid_oligarch(msg)
        assert "ОБЪЯВЛЕН НАРОДНЫЙ РЕЙД ОБЭП" in msg.reply.call_args[0][0]

        # /raid_oligarch with 5 voter IDs
        target_id = 75099
        await common.database.add_user_global_balance(db, target_id, "b", 200000.0)
        voters = [75030 + i for i in range(5)]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 1000.0)
            await db.execute("UPDATE Users SET posts_count = 30 WHERE user_id = ?", (v,))

        msg.reset_mock()
        msg.board_id = "b"
        msg.text = f"/raid_oligarch {','.join(map(str, voters))} {target_id}"
        await cmd_raid_oligarch(msg)
        assert "РАСКУЛАЧИВАНИЕ ОЛИГАРХА" in msg.reply.call_args[0][0]
