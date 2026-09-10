# -*- coding: utf-8 -*-
"""
tests/test_whale_money_sinks.py
Comprehensive test suite for Milestone 3 (Whale Money Sinks & Currency Dilution):
- F3.1: Exponential Whale Safes (pricing, RTP, drops, duplicate caps, Abu Yacht Fund burn)
- F3.2: Atomic Auction System (Auctions & AuctionBids, escrow, refund, anti-sniping, finalization)
- F3.3: Super-Wealth Tax (progressive brackets, idle surcharge) & Class Wars (/raid_oligarch)
"""

import asyncio
import json
import math
import random
import time
from typing import Any, Dict, List

import pytest

import common.config
import common.database
import common.db_pool
import lootbox_engine
import whale_economy_engine
from whale_economy_engine import (
    buy_whale_safe,
    calculate_wealth_tax,
    calculate_whale_safe_price,
    create_auction,
    ensure_auction_schema,
    execute_oligarch_raid,
    finish_active_auctions,
    place_auction_bid,
    process_daily_wealth_tax,
    roll_whale_safe,
)


# =============================================================================
# PART 1: WHALE SAFES (F3.1)
# =============================================================================

class TestWhaleSafes:
    """Tests for F3.1: Exponential Whale Safes and 70% Abu Yacht Fund burn."""

    def test_whale_safe_price_exponential(self):
        """Validates progression P(n) = int(50000 * (1.5 ** n))."""
        assert calculate_whale_safe_price(0) == 50000
        assert calculate_whale_safe_price(1) == 75000
        assert calculate_whale_safe_price(2) == 112500
        assert calculate_whale_safe_price(3) == 168750
        assert calculate_whale_safe_price(4) == 253125
        assert calculate_whale_safe_price(5) == 379687
        assert calculate_whale_safe_price(6) == 569531

        # Edge case: negative n safely clamped
        assert calculate_whale_safe_price(-1) == 50000

    def test_whale_safe_drop_structure_and_types(self):
        """roll_whale_safe() returns valid 5-element tuple conforming to lootbox contract."""
        for _ in range(50):
            tier, title, desc, payload, base_cash = roll_whale_safe()
            assert isinstance(tier, str) and len(tier) > 0
            assert isinstance(title, str) and len(title) > 0
            assert isinstance(desc, str) and len(desc) > 0
            assert isinstance(payload, dict)
            assert isinstance(base_cash, int) and base_cash >= 0

    def test_whale_safe_monte_carlo_rtp_and_cash_rtp(self):
        """
        Simulation: 5,000 rolls of roll_whale_safe().
        Contract requirements:
        1. Liquid Cash RTP <= 20.0%
        2. Total Nominal RTP <= 65.0% <= 85.0%
        """
        random.seed(42)
        N = 5000
        cost_per_case = 50000.0
        total_spent = N * cost_per_case
        total_cash_returned = 0.0
        total_nominal_value = 0.0

        # Nominal valuations:
        # Mythic Title: 15,000 ₪
        # VIP Pin: 12,000 ₪
        # Monocle: 8,000 ₪ (perm 20,000 ₪)
        # Padishah: 8,000 ₪ (perm 25,000 ₪)
        # Diplomatic passport: 6,000 ₪
        # ОБЭП Extinguisher: 5,000 ₪
        # Gold Ingot: 15,000 ₪
        # Certificate: 1 ₪

        for _ in range(N):
            tier, title, desc, payload, base_cash = roll_whale_safe()
            total_cash_returned += base_cash

            nominal = base_cash
            if "[👑 Золотой Анон]" in payload.get("grant_title", ""):
                nominal += 15000
            elif payload.get("vip_pin_voucher"):
                nominal += 12000
            elif payload.get("item_id") == "face_monocle":
                nominal += 20000 if payload.get("is_permanent") else 8000
            elif payload.get("item_id") == "body_padishah_mantle":
                nominal += 25000 if payload.get("is_permanent") else 8000
            elif payload.get("diplomatic_passport"):
                nominal += 6000
            elif payload.get("extinguisher_obep"):
                nominal += 5000

            total_nominal_value += nominal

        cash_rtp = (total_cash_returned / total_spent) * 100.0
        nominal_rtp = (total_nominal_value / total_spent) * 100.0

        # Strict RTP assertions:
        assert cash_rtp <= 20.0, f"Liquid Cash RTP too high: {cash_rtp:.2f}% (max 20%)"
        assert nominal_rtp <= 65.0, f"Nominal RTP too high: {nominal_rtp:.2f}% (max 65%)"

    def test_whale_safe_prestige_drop_tables_coverage(self):
        """Verifies that stochastic rolls generate all required prestige items."""
        random.seed(123)
        found = {
            "title_golden_anon": False,
            "vip_pin_voucher": False,
            "face_monocle": False,
            "body_padishah_mantle": False,
            "diplomatic_passport": False,
            "extinguisher_obep": False,
            "gold_ingot": False,
            "certificate_sucker": False,
        }

        for _ in range(2000):
            tier, title, desc, payload, base_cash = roll_whale_safe()
            if payload.get("grant_title") == "[👑 Золотой Анон]":
                found["title_golden_anon"] = True
            if payload.get("vip_pin_voucher"):
                found["vip_pin_voucher"] = True
            if payload.get("item_id") == "face_monocle":
                found["face_monocle"] = True
            if payload.get("item_id") == "body_padishah_mantle":
                found["body_padishah_mantle"] = True
            if payload.get("diplomatic_passport"):
                found["diplomatic_passport"] = True
            if payload.get("extinguisher_obep"):
                found["extinguisher_obep"] = True
            if payload.get("gold_ingot"):
                found["gold_ingot"] = True
            if payload.get("certificate_sucker"):
                found["certificate_sucker"] = True

        for k, v in found.items():
            assert v is True, f"Item {k} was never dropped in 2,000 rolls!"

    def test_whale_safe_weapon_cashback_cap_under_15000(self):
        """Weapon duplicate cashback in whale case is capped at 15,000 ₪ (<= 30% of 50k)."""
        active_items = {"partyvan_gun": True, "knife_gun": True}
        # Roll a duplicate partyvan gun
        payload = {"partyvan_gun": True}
        res_ai, cash, msg = lootbox_engine.apply_lootbox_reward(
            active_items=active_items,
            payload=payload,
            base_cash=0,
            case_type="whale"
        )
        assert cash <= 15000, f"Cashback exceeded 15,000 ₪ cap: {cash}"
        assert cash == 12000  # WEAPON_SCRAP_PRICES["whale"]["partyvan"]

    @pytest.mark.asyncio
    async def test_buy_whale_safe_atomic_flow(self, isolated_test_db):
        """
        Tests buy_whale_safe():
        - Deducts price P(0) = 50,000 ₪
        - Burns 70% (35,000 ₪) to Abu Yacht Fund
        - Advances opened_today counter
        - Fails when balance is insufficient
        """
        db = isolated_test_db
        user_id = 11001

        # Insufficient funds:
        await common.database.add_user_global_balance(db, user_id, "b", 10000.0)
        res = await buy_whale_safe(db, user_id, "b")
        assert res["ok"] is False
        assert "Недостаточно шекелей" in res["error"]

        # Sufficient funds: 150,000 ₪
        await common.database.add_user_global_balance(db, user_id, "b", 140000.0)
        fund_before = await common.database.get_abu_fund_total(db)

        # First purchase (n=0: 50,000 ₪)
        res1 = await buy_whale_safe(db, user_id, "b")
        assert res1["ok"] is True
        assert res1["price"] == 50000
        assert res1["burned_to_abu"] == 35000.0
        assert res1["opened_today"] == 1

        fund_after = await common.database.get_abu_fund_total(db)
        assert fund_after == fund_before + 35000.0

        # Second purchase (n=1: 75,000 ₪)
        res2 = await buy_whale_safe(db, user_id, "b")
        assert res2["ok"] is True
        assert res2["price"] == 75000
        assert res2["burned_to_abu"] == 52500.0
        assert res2["opened_today"] == 2


# =============================================================================
# PART 2: ATOMIC AUCTION SYSTEM (F3.2)
# =============================================================================

class TestAtomicAuctions:
    """Tests for F3.2: Atomic Auctions, escrow deduction, outbid refund, anti-sniping."""

    @pytest.mark.asyncio
    async def test_ensure_auction_schema_idempotency(self, isolated_test_db):
        """Calling ensure_auction_schema() multiple times does not raise errors."""
        db = isolated_test_db
        await ensure_auction_schema(db)
        await ensure_auction_schema(db)

    @pytest.mark.asyncio
    async def test_create_and_place_bid_atomic_escrow(self, isolated_test_db):
        """Creates auction and places atomic bid with global balance escrow."""
        db = isolated_test_db
        await ensure_auction_schema(db)

        # Create auction
        auc_id = await create_auction(
            db, lot_type="custom_role", title="[Главный Скуф]",
            description="Кастомный титул на 30 дней",
            start_price=50000.0, min_bid_step=5000.0, duration_sec=3600.0
        )
        assert auc_id > 0

        # Bidder with 100,000 ₪
        user_id = 21001
        await common.database.add_user_global_balance(db, user_id, "b", 100000.0)

        # Place 60,000 ₪ bid
        res = await place_auction_bid(db, auc_id, user_id, "Anon1", 60000.0)
        assert res["ok"] is True
        assert res["bid_amount"] == 60000.0

        # Balance deducted
        new_bal = await common.database.get_user_global_balance(db, user_id)
        assert new_bal == 40000.0

    @pytest.mark.asyncio
    async def test_auction_instant_outbid_refund(self, isolated_test_db):
        """When User B outbids User A, User A gets 100% of escrow refunded instantly."""
        db = isolated_test_db
        await ensure_auction_schema(db)

        auc_id = await create_auction(
            db, lot_type="board_pin", title="Pin /b/",
            description="Закреп треда на 24 часа",
            start_price=20000.0, min_bid_step=2000.0, duration_sec=3600.0
        )

        user_a = 22001
        user_b = 22002
        await common.database.add_user_global_balance(db, user_a, "b", 50000.0)
        await common.database.add_user_global_balance(db, user_b, "b", 50000.0)

        # User A bids 25,000 ₪
        res_a = await place_auction_bid(db, auc_id, user_a, "AnonA", 25000.0)
        assert res_a["ok"] is True
        assert await common.database.get_user_global_balance(db, user_a) == 25000.0

        # User B outbids with 30,000 ₪
        res_b = await place_auction_bid(db, auc_id, user_b, "AnonB", 30000.0)
        assert res_b["ok"] is True
        assert res_b["previous_winner"] == user_a

        # User A is refunded back to 50,000 ₪; User B is at 20,000 ₪
        assert await common.database.get_user_global_balance(db, user_a) == 50000.0
        assert await common.database.get_user_global_balance(db, user_b) == 20000.0

    @pytest.mark.asyncio
    async def test_auction_anti_sniping_extension(self, isolated_test_db):
        """Bids placed within 300s of auction end extend ends_at by 300s."""
        db = isolated_test_db
        await ensure_auction_schema(db)

        # Create auction with only 120s remaining
        auc_id = await create_auction(
            db, lot_type="custom_badge", title="Gold Badge",
            description="Уникальный бейдж",
            start_price=10000.0, min_bid_step=1000.0, duration_sec=120.0
        )

        user_id = 23001
        await common.database.add_user_global_balance(db, user_id, "b", 50000.0)

        now = time.time()
        res = await place_auction_bid(db, auc_id, user_id, "SniperAnon", 15000.0)
        assert res["ok"] is True
        assert res["extended"] is True
        assert res["ends_at"] >= now + 295.0

    @pytest.mark.asyncio
    async def test_auction_bid_validations(self, isolated_test_db):
        """Verifies bid rejection on invalid amounts, step, or balance."""
        db = isolated_test_db
        await ensure_auction_schema(db)

        auc_id = await create_auction(
            db, lot_type="custom_role", title="VIP",
            description="Desc", start_price=50000.0, min_bid_step=5000.0, duration_sec=3600.0
        )

        user_id = 24001
        await common.database.add_user_global_balance(db, user_id, "b", 100000.0)

        # Negative / NaN / Inf
        assert (await place_auction_bid(db, auc_id, user_id, "Anon", -100.0))["ok"] is False
        assert (await place_auction_bid(db, auc_id, user_id, "Anon", float("nan")))["ok"] is False
        assert (await place_auction_bid(db, auc_id, user_id, "Anon", float("inf")))["ok"] is False

        # Below start price
        assert (await place_auction_bid(db, auc_id, user_id, "Anon", 40000.0))["ok"] is False

        # Place valid 60,000 ₪
        await place_auction_bid(db, auc_id, user_id, "Anon", 60000.0)

        # Same user bidding again
        assert (await place_auction_bid(db, auc_id, user_id, "Anon", 70000.0))["ok"] is False

        # Insufficient step from another user (step is 5,000, so min is 65,000)
        user_2 = 24002
        await common.database.add_user_global_balance(db, user_2, "b", 100000.0)
        res_step = await place_auction_bid(db, auc_id, user_2, "Anon2", 62000.0)
        assert res_step["ok"] is False
        assert "Слишком маленькая ставка" in res_step["error"]

    @pytest.mark.asyncio
    async def test_finish_active_auctions_burns_100_pct_and_awards(self, isolated_test_db):
        """finish_active_auctions() burns winning bid to Abu Fund and sets status."""
        db = isolated_test_db
        await ensure_auction_schema(db)

        # Create auction already ended
        now = time.time()
        cur = await db.execute("""
            INSERT INTO Auctions (
                lot_type, title, description, start_price, min_bid_step, current_bid,
                current_winner_id, current_winner_name, board_id, status, starts_at, ends_at, created_at
            ) VALUES ('custom_role', 'Title', '[Владелец /b/]', 50000.0, 5000.0, 80000.0, 25001, 'Winner', 'b', 'active', ?, ?, ?)
        """, (now - 3600, now - 10, now - 3600))
        auc_id = cur.lastrowid

        # Seed winner in Users
        await common.database.add_user_global_balance(db, 25001, "b", 1000.0)
        fund_before = await common.database.get_abu_fund_total(db)

        # Finish auctions
        finished = await finish_active_auctions(db)
        assert len(finished) == 1
        assert finished[0]["auction_id"] == auc_id
        assert finished[0]["winning_bid"] == 80000.0

        # Fund increased by 100% of winning bid
        fund_after = await common.database.get_abu_fund_total(db)
        assert fund_after == fund_before + 80000.0

        # Custom prefix updated in Users
        async with db.execute("SELECT custom_prefix FROM Users WHERE user_id = ?", (25001,)) as c:
            row = await c.fetchone()
            assert row[0] == "[Владелец /b/]"


# =============================================================================
# PART 3: SUPER-WEALTH TAX & CLASS WARS (F3.3)
# =============================================================================

class TestSuperWealthTaxAndClassWars:
    """Tests for F3.3: Progressive brackets, idle surcharge, and /raid_oligarch."""

    def test_calculate_wealth_tax_progressive_brackets(self):
        """Validates exact progressive tax rates across wealth tiers."""
        # Tier 0: <= 5,000 ₪ (0%)
        assert calculate_wealth_tax(0.0) == 0.0
        assert calculate_wealth_tax(5000.0) == 0.0

        # Tier 1: 5,001 - 50,000 ₪ (0.3%)
        assert calculate_wealth_tax(10000.0) == 30.0
        assert calculate_wealth_tax(50000.0) == 150.0

        # Tier 2: 50,001 - 500,000 ₪ (1.0%)
        assert calculate_wealth_tax(100000.0) == 1000.0
        assert calculate_wealth_tax(500000.0) == 5000.0

        # Tier 3: 500,001 - 5,000,000 ₪ (2.5%)
        assert calculate_wealth_tax(1000000.0) == 25000.0
        assert calculate_wealth_tax(4000000.0) == 100000.0

        # Tier 4: > 5,000,000 ₪ (5.0%)
        assert calculate_wealth_tax(10000000.0) == 500000.0

    def test_calculate_wealth_tax_idle_surcharge(self):
        """Idle surcharge: 1.5x multiplier for balance > 500,000 ₪ and idle_hours >= 72.0."""
        # Active wallet > 500k: 2.5%
        assert calculate_wealth_tax(1000000.0, idle_hours=12.0) == 25000.0

        # Idle wallet > 500k: 2.5% * 1.5 = 3.75%
        assert calculate_wealth_tax(1000000.0, idle_hours=72.0) == 37500.0
        assert calculate_wealth_tax(1000000.0, idle_hours=120.0) == 37500.0

        # Small/medium wallet idle (<= 500k) has NO surcharge
        assert calculate_wealth_tax(200000.0, idle_hours=100.0) == 2000.0

    @pytest.mark.asyncio
    async def test_process_daily_wealth_tax_execution(self, isolated_test_db):
        """process_daily_wealth_tax() collects tax from >5k users and sends 100% to Abu Fund."""
        db = isolated_test_db
        now = time.time()
        # Seed users:
        # User 1: 3,000 ₪ (tax: 0 ₪)
        # User 2: 40,000 ₪ (tax: 120 ₪)
        # User 3: 1,000,000 ₪ (idle 0 posts -> 1.5x surcharge -> 37,500 ₪)
        # User 4: 1,000,000 ₪ (active post 2h ago -> 2.5% normal -> 25,000 ₪)
        await common.database.add_user_global_balance(db, 31001, "b", 3000.0)
        await common.database.add_user_global_balance(db, 31002, "b", 40000.0)
        await common.database.add_user_global_balance(db, 31003, "b", 1000000.0)
        await common.database.add_user_global_balance(db, 31004, "b", 1000000.0)

        # User 4 has a recent post (2 hours ago, idle < 72h)
        post_json = json.dumps({"text": "Active poster"})
        await db.execute("""
            INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp)
            VALUES (88881, 'b', 1, 31004, ?, ?)
        """, (post_json, now - 7200))

        fund_before = await common.database.get_abu_fund_total(db)
        res = await process_daily_wealth_tax(db)

        assert res["affected_users"] == 3
        expected_total = 120.0 + 37500.0 + 25000.0
        assert res["total_tax_collected"] == expected_total

        fund_after = await common.database.get_abu_fund_total(db)
        assert fund_after == fund_before + expected_total

    @pytest.mark.asyncio
    async def test_execute_oligarch_raid_qualification_rejection(self, isolated_test_db):
        """Raid is rejected when fewer than 5 qualified proletarian voters exist."""
        db = isolated_test_db
        # 3 proletarians + 1 rich user (balance >= 5000)
        await common.database.add_user_global_balance(db, 41001, "b", 100.0)
        await common.database.add_user_global_balance(db, 41002, "b", 200.0)
        await common.database.add_user_global_balance(db, 41003, "b", 300.0)
        await common.database.add_user_global_balance(db, 41004, "b", 8000.0)  # Not qualified!

        for uid in (41001, 41002, 41003, 41004):
            await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (uid,))

        res = await execute_oligarch_raid(db, [41001, 41002, 41003, 41004])
        assert res["ok"] is False
        assert "Недостаточно квалифицированных рабочих" in res["error"]

    @pytest.mark.asyncio
    async def test_execute_oligarch_raid_success_and_dilution(self, isolated_test_db):
        """
        Full raid execution:
        - 1 Oligarch with 500,000 ₪
        - 5 Proletarians with 100 ₪ and 30 posts each
        - Confiscates 10% (50,000 ₪)
        - 70% (35,000 ₪) burned to Abu Fund
        - 30% (15,000 ₪) distributed as 3,000 ₪ each to 5 workers
        - M0 reduced by exactly 35,000 ₪
        """
        db = isolated_test_db
        oligarch_id = 50001
        worker_ids = [50011, 50012, 50013, 50014, 50015]

        await common.database.add_user_global_balance(db, oligarch_id, "b", 500000.0)
        for wid in worker_ids:
            await common.database.add_user_global_balance(db, wid, "b", 100.0)
            await db.execute("UPDATE Users SET posts_count = 40 WHERE user_id = ?", (wid,))

        fund_before = await common.database.get_abu_fund_total(db)
        res = await execute_oligarch_raid(db, worker_ids, target_id=oligarch_id)

        assert res["ok"] is True
        assert res["confiscated"] == 50000.0
        assert res["burned_to_abu"] == 35000.0
        assert res["distributed_total"] == 15000.0
        assert res["per_voter"] == 3000.0

        # Oligarch balance: 500k - 50k = 450,000 ₪
        assert await common.database.get_user_global_balance(db, oligarch_id) == 450000.0

        # Each worker received 3,000 ₪: 100 + 3,000 = 3,100 ₪
        for wid in worker_ids:
            assert await common.database.get_user_global_balance(db, wid) == 3100.0

        # Fund increased by 35,000 ₪
        fund_after = await common.database.get_abu_fund_total(db)
        assert fund_after == fund_before + 35000.0

    @pytest.mark.asyncio
    async def test_execute_oligarch_raid_blocked_by_defenses(self, isolated_test_db):
        """Raid is blocked when oligarch possesses diplomatic passport or ОБЭП extinguisher."""
        db = isolated_test_db
        oligarch_id = 60001
        worker_ids = [60011, 60012, 60013, 60014, 60015]
        now = time.time()

        await common.database.add_user_global_balance(db, oligarch_id, "b", 300000.0)
        for wid in worker_ids:
            await common.database.add_user_global_balance(db, wid, "b", 100.0)
            await db.execute("UPDATE Users SET posts_count = 35 WHERE user_id = ?", (wid,))

        # 1. Oligarch with Diplomatic Passport
        ai_pass = {"diplomatic_passport_until": now + 72 * 3600}
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(ai_pass), oligarch_id))

        res_pass = await execute_oligarch_raid(db, worker_ids, target_id=oligarch_id)
        assert res_pass["ok"] is False
        assert res_pass["blocked"] is True
        assert "Дипломатический Паспорт" in res_pass["error"]

        # 2. Oligarch with ОБЭП Extinguisher
        ai_ext = {"extinguisher_obep": True, "extinguisher_obep_charges": 1}
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(ai_ext), oligarch_id))

        res_ext = await execute_oligarch_raid(db, worker_ids, target_id=oligarch_id)
        assert res_ext["ok"] is False
        assert res_ext["blocked"] is True
        assert "Огнетушитель ОБЭП" in res_ext["error"]

        # Extinguisher charge consumed
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (oligarch_id,)) as c:
            row = await c.fetchone()
            ai_after = json.loads(row[0])
            assert "extinguisher_obep" not in ai_after
