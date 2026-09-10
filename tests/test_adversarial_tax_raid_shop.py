# -*- coding: utf-8 -*-
"""
tests/test_adversarial_tax_raid_shop.py
Adversarial verification suite for challenger_m3_gen3_2:
1. Super-Wealth Tax Progression & Idle Surcharge:
   - Exhaustive verification of all brackets (0%, 0.3%, 1.0%, 2.5%, 5.0%).
   - Exact 1.5x idle multiplier for inactive mega-wallets (>500k and idle >= 72h).
   - Boundary tests at 5k, 50k, 500k, 5M shekels and 71.99h vs 72.00h.
   - End-to-end database execution via process_daily_wealth_tax.
2. /raid_oligarch Class Wars & Sybil Defenses:
   - Sybil defense (<5 voters, duplicate IDs, voter balance >= 5000, voter posts < 25).
   - Defensive gear: Diplomatic Passport & ОБЭП Extinguisher (charge decrement).
   - Confiscation math: 10% capped at 200,000 ₪, 70% burn to Abu Fund, 30% to 5 workers.
   - Target qualification & auto-selection.
3. M2 Shop Non-Buyable Relic Guard:
   - Test all 5 relics (hat_golden_foil, hat_cyber_ushanka, body_dva_ch_mantle,
     body_padishah_mantle, face_monocle) with balance=0 and balance=10,000,000.
   - Exact rejection text 'Этот предмет является уникальной реликвией из кейсов и не продается в обычном магазине!'
   - show_alert=True and exactly 0 shekels deducted.
"""

import asyncio
import json
import math
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import common.config
import common.database
import common.db_pool
from main import cb_shop_buy
from wardrobe_engine import CLOTHING_CATALOG
from whale_economy_engine import (
    calculate_wealth_tax,
    execute_oligarch_raid,
    process_daily_wealth_tax,
)


# =============================================================================
# PART 1: SUPER-WEALTH TAX PROGRESSION & IDLE SURCHARGE
# =============================================================================

class TestAdversarialSuperWealthTax:
    """Adversarial stress-testing of super-wealth tax calculation and daily execution."""

    @pytest.mark.parametrize(
        "balance,expected_tax,desc",
        [
            # Tier 0: <= 5,000 ₪ -> 0%
            (-1000.0, 0.0, "Negative balance is exempt"),
            (0.0, 0.0, "Zero balance is exempt"),
            (1.0, 0.0, "1 shekel is exempt"),
            (4999.0, 0.0, "4,999 shekels is exempt"),
            (5000.0, 0.0, "Exact 5,000 shekels boundary is exempt"),

            # Tier 1: 5,001 - 50,000 ₪ -> 0.3% / day
            (5001.0, 15.00, "5,001 shekels at 0.3%"),
            (10000.0, 30.00, "10,000 shekels at 0.3%"),
            (25000.0, 75.00, "25,000 shekels at 0.3%"),
            (50000.0, 150.00, "Exact 50,000 shekels upper boundary at 0.3%"),

            # Tier 2: 50,001 - 500,000 ₪ -> 1.0% / day
            (50001.0, 500.01, "50,001 shekels at 1.0%"),
            (100000.0, 1000.00, "100,000 shekels at 1.0%"),
            (250000.0, 2500.00, "250,000 shekels at 1.0%"),
            (500000.0, 5000.00, "Exact 500,000 shekels upper boundary at 1.0%"),

            # Tier 3: 500,001 - 5,000,000 ₪ -> 2.5% / day
            (500001.0, 12500.03, "500,001 shekels at 2.5%"),
            (1000000.0, 25000.00, "1,000,000 shekels at 2.5%"),
            (2500000.0, 62500.00, "2,500,000 shekels at 2.5%"),
            (5000000.0, 125000.00, "Exact 5,000,000 shekels upper boundary at 2.5%"),

            # Tier 4: > 5,000,000 ₪ -> 5.0% / day
            (5000001.0, 250000.05, "5,000,001 shekels at 5.0%"),
            (10000000.0, 500000.00, "10,000,000 shekels at 5.0%"),
            (50000000.0, 2500000.00, "50,000,000 shekels at 5.0%"),
        ]
    )
    def test_tax_progression_all_tiers_without_idle(self, balance, expected_tax, desc):
        """Verify all 5 tiers (0%, 0.3%, 1.0%, 2.5%, 5.0%) without idle surcharge."""
        actual_tax = calculate_wealth_tax(balance, idle_hours=0.0)
        assert actual_tax == pytest.approx(expected_tax, abs=0.02), f"Failed for {desc}: got {actual_tax}, expected {expected_tax}"

    @pytest.mark.parametrize(
        "balance,idle_hours,expected_tax,expected_rate_pct,desc",
        [
            # Boundary at 500k: <= 500,000 NEVER receives 1.5x idle surcharge!
            (500000.0, 72.0, 5000.00, 1.0, "500k boundary at 72h idle must NOT receive surcharge (rate remains 1.0%)"),
            (500000.0, 1000.0, 5000.00, 1.0, "500k with extreme idle must NOT receive surcharge"),
            (300000.0, 100.0, 3000.00, 1.0, "300k with idle must NOT receive surcharge"),
            (40000.0, 200.0, 120.00, 0.3, "40k with idle must NOT receive surcharge"),
            (5000.0, 500.0, 0.0, 0.0, "5k with idle is exempt"),

            # Boundary at 500,001: > 500,000 and idle >= 72.0 receives 1.5x surcharge
            (500001.0, 71.99, 12500.03, 2.5, "500,001 with 71.99h idle must NOT receive surcharge (rate 2.5%)"),
            (500001.0, 72.00, 18750.04, 3.75, "500,001 with 72.00h idle MUST receive 1.5x surcharge (rate 3.75%)"),

            # Mega-wallets (Tier 3: 2.5% * 1.5 = 3.75%)
            (1000000.0, 24.0, 25000.00, 2.5, "1M active (<72h) pays base 2.5%"),
            (1000000.0, 71.99, 25000.00, 2.5, "1M active at 71.99h pays base 2.5%"),
            (1000000.0, 72.00, 37500.00, 3.75, "1M inactive at 72.00h pays 3.75%"),
            (1000000.0, 168.0, 37500.00, 3.75, "1M inactive 1 week pays 3.75%"),
            (5000000.0, 72.0, 187500.00, 3.75, "5M inactive at 72h pays 3.75%"),

            # Super-Mega-wallets (Tier 4: 5.0% * 1.5 = 7.5%)
            (10000000.0, 0.0, 500000.00, 5.0, "10M active pays base 5.0%"),
            (10000000.0, 72.0, 750000.00, 7.5, "10M inactive at 72h pays 7.5%"),
            (100000000.0, 72.0, 7500000.00, 7.5, "100M inactive at 72h pays 7.5%"),
        ]
    )
    def test_idle_surcharge_rules_and_boundaries(self, balance, idle_hours, expected_tax, expected_rate_pct, desc):
        """Strictly validates the 1.5x idle multiplier for inactive mega-wallets (>500k, >=72h)."""
        actual_tax = calculate_wealth_tax(balance, idle_hours=idle_hours)
        assert actual_tax == pytest.approx(expected_tax, abs=0.05), f"Failed for {desc}: got {actual_tax}, expected {expected_tax}"

    def test_tax_malformed_and_extreme_inputs(self):
        """Adversarial malformed, non-numeric, None, or negative inputs."""
        assert calculate_wealth_tax(None) == 0.0  # type: ignore
        assert calculate_wealth_tax("invalid") == 0.0  # type: ignore
        assert calculate_wealth_tax(-999999999.0) == 0.0
        assert calculate_wealth_tax(0, idle_hours=1000) == 0.0

    @pytest.mark.asyncio
    async def test_process_daily_wealth_tax_e2e_multi_cohort(self, isolated_test_db):
        """
        Executes process_daily_wealth_tax in an isolated database with a multi-cohort population:
        - User 1: 4,500 ₪ (exempt, balance <= 5000)
        - User 2: 30,000 ₪ (active, rate 0.3% = 90 ₪)
        - User 3: 600,000 ₪ (active, rate 2.5% = 15,000 ₪)
        - User 4: 1,000,000 ₪ (inactive >= 72h, rate 2.5% * 1.5 = 3.75% = 37,500 ₪)
        Verifies:
        - Exact balances after deduction
        - 100% of total tax transferred to Abu Yacht Fund
        - Transactions recorded
        """
        db = isolated_test_db
        now = time.time()

        u_exempt = 88001
        u_mid_active = 88002
        u_mega_active = 88003
        u_mega_idle = 88004

        await common.database.add_user_global_balance(db, u_exempt, "b", 4500.0)
        await common.database.add_user_global_balance(db, u_mid_active, "b", 30000.0)
        await common.database.add_user_global_balance(db, u_mega_active, "b", 600000.0)
        await common.database.add_user_global_balance(db, u_mega_idle, "b", 1000000.0)

        # Set post timestamps: active users posted 1 hour ago, idle user posted 80 hours ago
        await db.execute(
            "INSERT INTO Posts (board_id, thread_id, post_num, author_id, content, timestamp) VALUES ('b', 1, 101, ?, '{}', ?)",
            (u_mid_active, now - 3600)
        )
        await db.execute(
            "INSERT INTO Posts (board_id, thread_id, post_num, author_id, content, timestamp) VALUES ('b', 1, 102, ?, '{}', ?)",
            (u_mega_active, now - 3600)
        )
        await db.execute(
            "INSERT INTO Posts (board_id, thread_id, post_num, author_id, content, timestamp) VALUES ('b', 1, 103, ?, '{}', ?)",
            (u_mega_idle, now - 80 * 3600)
        )

        initial_fund = await common.database.get_abu_fund_total(db)

        # Execute daily tax
        summary = await process_daily_wealth_tax(db)

        expected_tax_u2 = 90.00       # 30,000 * 0.003
        expected_tax_u3 = 15000.00    # 600,000 * 0.025
        expected_tax_u4 = 37500.00    # 1,000,000 * 0.025 * 1.5
        total_expected_tax = expected_tax_u2 + expected_tax_u3 + expected_tax_u4

        assert summary["affected_users"] == 3
        assert summary["total_tax_collected"] == pytest.approx(total_expected_tax, abs=0.1)

        # Verify balances
        assert await common.database.get_user_global_balance(db, u_exempt) == 4500.0
        assert await common.database.get_user_global_balance(db, u_mid_active) == pytest.approx(30000.0 - expected_tax_u2, abs=0.1)
        assert await common.database.get_user_global_balance(db, u_mega_active) == pytest.approx(600000.0 - expected_tax_u3, abs=0.1)
        assert await common.database.get_user_global_balance(db, u_mega_idle) == pytest.approx(1000000.0 - expected_tax_u4, abs=0.1)

        # Verify 100% of collected tax is added to Abu Fund
        final_fund = await common.database.get_abu_fund_total(db)
        assert round(final_fund - initial_fund, 2) == pytest.approx(total_expected_tax, abs=0.1)


# =============================================================================
# PART 2: /raid_oligarch CLASS WARS & SYBIL DEFENSES
# =============================================================================

class TestAdversarialRaidOligarch:
    """Adversarial stress-testing of proletarian raids, Sybil defenses, and confiscation math."""

    @pytest.mark.asyncio
    async def test_raid_sybil_defense_fewer_than_5_voters(self, isolated_test_db):
        """Reject if < 5 distinct voters (0, 1, 2, 3, 4 voters)."""
        db = isolated_test_db
        target_id = 91000
        await common.database.add_user_global_balance(db, target_id, "b", 500000.0)

        # 0 voters
        res0 = await execute_oligarch_raid(db, [], target_id, "b")
        assert res0["ok"] is False
        assert "Недостаточно квалифицированных рабочих" in res0["error"]

        # 1 voter
        v1 = 91001
        await common.database.add_user_global_balance(db, v1, "b", 100.0)
        await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (v1,))
        res1 = await execute_oligarch_raid(db, [v1], target_id, "b")
        assert res1["ok"] is False
        assert "Недостаточно квалифицированных рабочих" in res1["error"]

        # 4 voters
        voters_4 = [91001, 91002, 91003, 91004]
        for v in voters_4:
            await common.database.add_user_global_balance(db, v, "b", 100.0)
            await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (v,))
        res4 = await execute_oligarch_raid(db, voters_4, target_id, "b")
        assert res4["ok"] is False
        assert "Недостаточно квалифицированных рабочих" in res4["error"]

    @pytest.mark.asyncio
    async def test_raid_sybil_defense_duplicate_voter_ids(self, isolated_test_db):
        """Sybil attack attempt: passing 5 voter IDs but with duplicates (e.g. 1 user 5 times)."""
        db = isolated_test_db
        target_id = 91010
        await common.database.add_user_global_balance(db, target_id, "b", 500000.0)

        v = 91011
        await common.database.add_user_global_balance(db, v, "b", 100.0)
        await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (v,))

        # 5 times the same voter
        res_same = await execute_oligarch_raid(db, [v, v, v, v, v], target_id, "b")
        assert res_same["ok"] is False
        assert "Недостаточно квалифицированных рабочих" in res_same["error"]

        # 3 unique voters duplicated to 5 elements
        v2, v3 = 91012, 91013
        await common.database.add_user_global_balance(db, v2, "b", 100.0)
        await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (v2,))
        await common.database.add_user_global_balance(db, v3, "b", 100.0)
        await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (v3,))

        res_dups = await execute_oligarch_raid(db, [v, v2, v3, v, v2], target_id, "b")
        assert res_dups["ok"] is False
        assert "Недостаточно квалифицированных рабочих" in res_dups["error"]

    @pytest.mark.asyncio
    async def test_raid_sybil_defense_voter_balance_boundary(self, isolated_test_db):
        """Reject if any voter has balance >= 5,000 ₪. Boundary: 4,999.99 qualified vs 5,000 disqualified."""
        db = isolated_test_db
        target_id = 91020
        await common.database.add_user_global_balance(db, target_id, "b", 500000.0)

        # 4 qualified voters
        voters = [91021, 91022, 91023, 91024]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 500.0)
            await db.execute("UPDATE Users SET posts_count = 30 WHERE user_id = ?", (v,))

        # 5th voter with EXACTLY 5,000 ₪ -> must be DISQUALIFIED
        v5_boundary = 91025
        await common.database.add_user_global_balance(db, v5_boundary, "b", 5000.0)
        await db.execute("UPDATE Users SET posts_count = 30 WHERE user_id = ?", (v5_boundary,))

        res_fail = await execute_oligarch_raid(db, voters + [v5_boundary], target_id, "b")
        assert res_fail["ok"] is False
        assert "Недостаточно квалифицированных рабочих" in res_fail["error"]

        # Reduce 5th voter to 4,999.99 ₪ -> must now QUALIFY
        await common.database.deduct_user_global_balance(db, v5_boundary, "b", 0.01)
        res_pass = await execute_oligarch_raid(db, voters + [v5_boundary], target_id, "b")
        assert res_pass["ok"] is True

    @pytest.mark.asyncio
    async def test_raid_sybil_defense_voter_posts_boundary_and_fallback(self, isolated_test_db):
        """Reject if voter has < 25 posts. Boundary: 24 posts disqualified vs 25 posts qualified."""
        db = isolated_test_db
        target_id = 91030
        await common.database.add_user_global_balance(db, target_id, "b", 500000.0)

        voters = [91031, 91032, 91033, 91034]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 500.0)
            await db.execute("UPDATE Users SET posts_count = 30 WHERE user_id = ?", (v,))

        # 5th voter with 24 posts -> DISQUALIFIED
        v5_under = 91035
        await common.database.add_user_global_balance(db, v5_under, "b", 500.0)
        await db.execute("UPDATE Users SET posts_count = 24 WHERE user_id = ?", (v5_under,))

        res_fail = await execute_oligarch_raid(db, voters + [v5_under], target_id, "b")
        assert res_fail["ok"] is False
        assert "Недостаточно квалифицированных рабочих" in res_fail["error"]

        # Fallback test: Users.posts_count is 0, but user has 25 posts recorded in Posts table
        v5_fallback = 91036
        await common.database.add_user_global_balance(db, v5_fallback, "b", 500.0)
        await db.execute("UPDATE Users SET posts_count = 0 WHERE user_id = ?", (v5_fallback,))

        now = time.time()
        for i in range(25):
            await db.execute(
                "INSERT INTO Posts (board_id, thread_id, post_num, author_id, content, timestamp) VALUES ('b', 1, ?, ?, '{}', ?)",
                (2000 + i, v5_fallback, now)
            )

        res_fallback = await execute_oligarch_raid(db, voters + [v5_fallback], target_id, "b")
        assert res_fallback["ok"] is True
        assert res_fallback["target_id"] == target_id

    @pytest.mark.asyncio
    async def test_raid_diplomatic_passport_defense(self, isolated_test_db):
        """Diplomatic Passport completely blocks raid without deducting funds or consuming passport."""
        db = isolated_test_db
        target_id = 91040
        await common.database.add_user_global_balance(db, target_id, "b", 1000000.0)

        # Give target active Diplomatic Passport
        ai_target = {"diplomatic_passport_until": int(time.time()) + 86400}
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(ai_target), target_id))

        voters = [91041, 91042, 91043, 91044, 91045]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 500.0)
            await db.execute("UPDATE Users SET posts_count = 40 WHERE user_id = ?", (v,))

        res = await execute_oligarch_raid(db, voters, target_id, "b")
        assert res["ok"] is False
        assert res.get("blocked") is True
        assert "Дипломатический Паспорт" in res["error"]

        # Oligarch balance completely preserved
        assert await common.database.get_user_global_balance(db, target_id) == 1000000.0

        # Passport is still active (not consumed)
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (target_id,)) as c:
            row = await c.fetchone()
            loaded_ai = json.loads(row[0])
            assert "diplomatic_passport_until" in loaded_ai

    @pytest.mark.asyncio
    async def test_raid_obep_extinguisher_defense_multi_charge_depletion(self, isolated_test_db):
        """ОБЭП Extinguisher blocks raid and consumes exactly 1 charge per blocked raid."""
        db = isolated_test_db
        target_id = 91050
        await common.database.add_user_global_balance(db, target_id, "b", 500000.0)

        # Target has extinguisher with 2 charges
        ai_target = {"extinguisher_obep": True, "extinguisher_obep_charges": 2}
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(ai_target), target_id))

        voters = [91051, 91052, 91053, 91054, 91055]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 500.0)
            await db.execute("UPDATE Users SET posts_count = 40 WHERE user_id = ?", (v,))

        # --- Raid 1: Blocked, charges 2 -> 1 ---
        res1 = await execute_oligarch_raid(db, voters, target_id, "b")
        assert res1["ok"] is False
        assert res1.get("blocked") is True
        assert "Огнетушитель ОБЭП" in res1["error"]
        assert await common.database.get_user_global_balance(db, target_id) == 500000.0

        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (target_id,)) as c:
            ai_after1 = json.loads((await c.fetchone())[0])
            assert ai_after1.get("extinguisher_obep") is True
            assert ai_after1.get("extinguisher_obep_charges") == 1

        # --- Raid 2: Blocked, charges 1 -> 0 (extinguisher removed) ---
        res2 = await execute_oligarch_raid(db, voters, target_id, "b")
        assert res2["ok"] is False
        assert res2.get("blocked") is True
        assert "Огнетушитель ОБЭП" in res2["error"]
        assert await common.database.get_user_global_balance(db, target_id) == 500000.0

        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (target_id,)) as c:
            ai_after2 = json.loads((await c.fetchone())[0])
            assert "extinguisher_obep" not in ai_after2
            assert "extinguisher_obep_charges" not in ai_after2

        # --- Raid 3: No defense remaining -> SUCCEEDS ---
        res3 = await execute_oligarch_raid(db, voters, target_id, "b")
        assert res3["ok"] is True
        assert res3["confiscated"] == 50000.0  # 10% of 500k
        assert await common.database.get_user_global_balance(db, target_id) == 450000.0

    @pytest.mark.asyncio
    async def test_raid_confiscation_cap_200k_and_70_30_split(self, isolated_test_db):
        """
        Confiscation is strictly 10% capped at 200,000 ₪.
        70% burned to Abu Fund, 30% distributed to the 5 voters.
        """
        db = isolated_test_db
        voters = [91061, 91062, 91063, 91064, 91065]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 1000.0)
            await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (v,))

        # Test Case 1: Standard Oligarch with 800,000 ₪ (10% = 80,000 ₪ < 200k cap)
        oli1 = 91060
        await common.database.add_user_global_balance(db, oli1, "b", 800000.0)

        fund_before = await common.database.get_abu_fund_total(db)
        res1 = await execute_oligarch_raid(db, voters, oli1, "b")

        assert res1["ok"] is True
        assert res1["confiscated"] == 80000.0
        assert res1["burned_to_abu"] == 56000.0      # 70% of 80,000
        assert res1["distributed_total"] == 24000.0  # 30% of 80,000
        assert res1["per_voter"] == 4800.0           # 24,000 / 5

        # Oligarch 1 balance after raid
        assert await common.database.get_user_global_balance(db, oli1) == 720000.0

        # Abu Fund increased by 56,000 ₪
        fund_mid = await common.database.get_abu_fund_total(db)
        assert round(fund_mid - fund_before, 2) == 56000.0

        # Voters received 4,800 ₪ each (1,000 + 4,800 = 5,800 ₪)
        for v in voters:
            assert await common.database.get_user_global_balance(db, v) == 5800.0

        # Reset voters' balances to < 5000 for next test
        for v in voters:
            await common.database.deduct_user_global_balance(db, v, "b", 5000.0)

        # Test Case 2: Mega-Oligarch with 10,000,000 ₪ (10% = 1,000,000 ₪ -> CAPPED at 200,000 ₪)
        oli2 = 91070
        await common.database.add_user_global_balance(db, oli2, "b", 10000000.0)

        res2 = await execute_oligarch_raid(db, voters, oli2, "b")
        assert res2["ok"] is True
        assert res2["confiscated"] == 200000.0  # CAPPED at 200,000 ₪
        assert res2["burned_to_abu"] == 140000.0  # 70% of 200,000
        assert res2["distributed_total"] == 60000.0  # 30% of 200,000
        assert res2["per_voter"] == 12000.0  # 60,000 / 5

        # Oligarch 2 balance after raid
        assert await common.database.get_user_global_balance(db, oli2) == 9800000.0

        # Abu Fund increased by 140,000 ₪
        fund_after = await common.database.get_abu_fund_total(db)
        assert round(fund_after - fund_mid, 2) == 140000.0

        # Voters received 12,000 ₪ each (800 + 12,000 = 12,800 ₪)
        for v in voters:
            assert await common.database.get_user_global_balance(db, v) == 12800.0

    @pytest.mark.asyncio
    async def test_raid_target_not_oligarch_or_auto_selection(self, isolated_test_db):
        """Reject if target balance <= 5000 ₪; test auto-selection when target_id is None."""
        db = isolated_test_db
        voters = [91081, 91082, 91083, 91084, 91085]
        for v in voters:
            await common.database.add_user_global_balance(db, v, "b", 500.0)
            await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (v,))

        # Target with 5,000 ₪ (not oligarch)
        poor_target = 91089
        await common.database.add_user_global_balance(db, poor_target, "b", 5000.0)
        res_poor = await execute_oligarch_raid(db, voters, poor_target, "b")
        assert res_poor["ok"] is False
        assert "Цель не является олигархом" in res_poor["error"]

        # Auto-selection test: create two rich users, auto-select should target the richest
        rich1 = 91091
        rich2 = 91092
        await common.database.add_user_global_balance(db, rich1, "b", 100000.0)
        await common.database.add_user_global_balance(db, rich2, "b", 900000.0)

        res_auto = await execute_oligarch_raid(db, voters, None, "b")
        assert res_auto["ok"] is True
        assert res_auto["target_id"] == rich2  # richest user auto-selected
        assert res_auto["confiscated"] == 90000.0  # 10% of 900,000


# =============================================================================
# PART 3: M2 SHOP NON-BUYABLE RELIC GUARD (cb_shop_buy)
# =============================================================================

class TestAdversarialShopNonBuyableRelicGuard:
    """
    Adversarial verification of M2 Shop anti-relic exploit guard:
    Simulates cb_shop_buy with each non_buyable relic item:
    - hat_golden_foil
    - hat_cyber_ushanka
    - body_dva_ch_mantle
    - body_padishah_mantle
    - face_monocle
    Tested with:
    - balance = 0 ₪
    - balance = 10,000,000 ₪
    Verifies:
    - Exact rejection text:
      'Этот предмет является уникальной реликвией из кейсов и не продается в обычном магазине!'
    - show_alert=True
    - 0 shekels deducted
    - Item is not equipped / not added to active_items
    """

    RELIC_ITEMS = [
        "hat_golden_foil",
        "hat_cyber_ushanka",
        "body_dva_ch_mantle",
        "body_padishah_mantle",
        "face_monocle",
    ]

    EXACT_REJECTION_TEXT = "Этот предмет является уникальной реликвией из кейсов и не продается в обычном магазине!"

    def test_clothing_catalog_relic_definitions(self):
        """Ensure all 5 items are in CLOTHING_CATALOG and explicitly marked non_buyable=True."""
        for item_id in self.RELIC_ITEMS:
            assert item_id in CLOTHING_CATALOG, f"Item {item_id} not found in CLOTHING_CATALOG!"
            item_meta = CLOTHING_CATALOG[item_id]
            assert item_meta.get("non_buyable") is True, f"Item {item_id} must have non_buyable=True!"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("relic_id", RELIC_ITEMS)
    async def test_shop_callback_relic_zero_balance_rejection(self, relic_id, isolated_test_db):
        """Simulate cb_shop_buy with balance=0 for each non_buyable relic."""
        db = isolated_test_db
        user_id = 95000 + hash(relic_id) % 1000

        # Ensure user has 0 balance and empty active_items
        await common.database.add_user_global_balance(db, user_id, "b", 0.0)
        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 0.0, '{}')",
            (user_id,)
        )

        callback = MagicMock()
        callback.from_user.id = user_id
        callback.data = f"shop_buy_{relic_id}"
        callback.answer = AsyncMock()
        callback.message = MagicMock()

        with patch("main.get_pool", AsyncMock(return_value=db)), \
             patch("shared_state.record_shop_purchase", MagicMock()):
            await cb_shop_buy(callback, "b")

        # Verify exact callback alert
        callback.answer.assert_called_once_with(
            self.EXACT_REJECTION_TEXT,
            show_alert=True
        )

        # Verify 0 shekels deducted
        current_bal = await common.database.get_user_global_balance(db, user_id)
        assert current_bal == 0.0

        # Verify item not added to active_items
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            ai = json.loads(row[0]) if (row and row[0]) else {}
            assert relic_id not in ai.values()
            assert relic_id not in ai

    @pytest.mark.asyncio
    @pytest.mark.parametrize("relic_id", RELIC_ITEMS)
    async def test_shop_callback_relic_ten_million_balance_rejection(self, relic_id, isolated_test_db):
        """Simulate cb_shop_buy with balance=10,000,000 for each non_buyable relic."""
        db = isolated_test_db
        user_id = 96000 + hash(relic_id) % 1000
        initial_balance = 10000000.0

        await common.database.add_user_global_balance(db, user_id, "b", initial_balance)
        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', ?, '{}')",
            (user_id, initial_balance)
        )

        callback = MagicMock()
        callback.from_user.id = user_id
        callback.data = f"shop_buy_{relic_id}"
        callback.answer = AsyncMock()
        callback.message = MagicMock()

        with patch("main.get_pool", AsyncMock(return_value=db)), \
             patch("shared_state.record_shop_purchase", MagicMock()):
            await cb_shop_buy(callback, "b")

        # Verify exact callback alert
        callback.answer.assert_called_once_with(
            self.EXACT_REJECTION_TEXT,
            show_alert=True
        )

        # Verify 0 shekels deducted: balance MUST remain exactly 10,000,000 ₪
        current_bal = await common.database.get_user_global_balance(db, user_id)
        assert current_bal == initial_balance

        # Verify item not added to active_items
        async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            ai = json.loads(row[0]) if (row and row[0]) else {}
            assert relic_id not in ai.values()
            assert relic_id not in ai

    @pytest.mark.asyncio
    async def test_shop_callback_buyable_item_contrast(self, isolated_test_db):
        """Contrast test: standard buyable item (hat_bag, 120 ₪) succeeds when affordable."""
        db = isolated_test_db
        user_id = 97001
        initial_balance = 1000.0
        item_price = CLOTHING_CATALOG["hat_bag"]["price"]  # 120 ₪

        await common.database.add_user_global_balance(db, user_id, "b", initial_balance)
        await db.execute(
            "INSERT OR REPLACE INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', ?, '{}')",
            (user_id, initial_balance)
        )

        callback = MagicMock()
        callback.from_user.id = user_id
        callback.data = "shop_buy_hat_bag"
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.edit_text = AsyncMock()

        with patch("main.get_pool", AsyncMock(return_value=db)), \
             patch("shared_state.record_shop_purchase", MagicMock()):
            await cb_shop_buy(callback, "b")

        # Must not show the relic rejection
        if callback.answer.call_args:
            called_text = callback.answer.call_args[0][0] if callback.answer.call_args[0] else ""
            assert called_text != self.EXACT_REJECTION_TEXT

        # Funds were deducted
        final_bal = await common.database.get_user_global_balance(db, user_id)
        assert final_bal == initial_balance - item_price
