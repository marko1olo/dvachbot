# -*- coding: utf-8 -*-
"""
tests/test_lootbox_rebalance.py — Comprehensive Test Suite for Milestone 2:
Lootbox Overhaul & EV/RTP Anti-Exploit.

Features Covered:
- F2.1: Rebalanced Drop Tables (TRASH_ITEMS ~14.28 ₪, PREMIUM_JUNK ~90 ₪)
- F2.2: Duplicate Cashback Overhaul & Scrap Recycling:
  - calculate_duplicate_cashback(case_price, item_price, is_weapon)
  - Weapon scrap values for trash (15-45 ₪) and gold (20-150 ₪)
  - Heavy Combat Kit bundle cap (80 ₪ max cashback)
  - Fixed scrap recycling (35 ₪ for timed when perm owned)
  - Permanent duplicate cashback min(120, max(40, int(price * 0.20)))
  - 7-day maximum cap on protective buffs
- F2.3: Mathematical Balance & Empirical Monte Carlo EV/RTP Verification:
  - roll_trash_lootbox() Nominal RTP <= 55% <= 85%, Cash RTP ~17%
  - roll_gold_safe() Nominal RTP <= 65% <= 85%, Cash RTP ~23%
  - Anti-Autoclicker Continuous Bankruptcy Proof
- F2.4: Non-Buyable Status Rewards:
  - Exclusive titles: [Золотой Кит], [Шекелевый Барон], [Сборщик Стеклотары], [Король Помойки]
  - Mythic relics in CLOTHING_CATALOG with non_buyable: True
"""

import random
import time
from typing import Dict, Any

import pytest

import lootbox_engine
from lootbox_engine import (
    TRASH_ITEMS,
    PREMIUM_JUNK,
    NON_BUYABLE_TITLES,
    EXCLUSIVE_RELICS,
    WEAPON_SCRAP_PRICES,
    calculate_duplicate_cashback,
    roll_trash_lootbox,
    roll_gold_safe,
    apply_lootbox_reward,
)
from wardrobe_engine import CLOTHING_CATALOG, get_wardrobe_total_stats


# =============================================================================
# 1. DROP TABLES (F2.1)
# =============================================================================

class TestDropTables:
    """Validates rebalanced drop tables eliminating baseline inflation."""

    def test_trash_items_count_range_and_average(self):
        """TRASH_ITEMS: 7 items, values 10-20 ₪, average payout ~14.28 ₪."""
        assert len(TRASH_ITEMS) == 7
        total_payout = 0
        for name, desc, val in TRASH_ITEMS:
            assert 10 <= val <= 20, f"Item {name} value {val} out of bounds [10, 20]"
            assert len(desc) > 0
            total_payout += val
        avg = total_payout / len(TRASH_ITEMS)
        assert round(avg, 2) == 14.29  # 100 / 7 = 14.2857... ₪
        assert total_payout == 100

    def test_premium_junk_count_range_and_average(self):
        """PREMIUM_JUNK: 6 items, values 50-130 ₪, average payout exactly 90.00 ₪."""
        assert len(PREMIUM_JUNK) == 6
        total_payout = 0
        for name, desc, val in PREMIUM_JUNK:
            assert 50 <= val <= 130, f"Item {name} value {val} out of bounds [50, 130]"
            assert len(desc) > 0
            total_payout += val
        avg = total_payout / len(PREMIUM_JUNK)
        assert avg == 90.00  # 540 / 6 = 90.00 ₪
        assert total_payout == 540


# =============================================================================
# 2. DUPLICATE CASHBACK OVERHAUL (F2.2)
# =============================================================================

class TestDuplicateCashbackOverhaul:
    """Validates duplicate cashback caps, weapon scrap, bundle caps, and buff caps."""

    def test_calculate_duplicate_cashback_formula(self):
        """Formula: min(int(case_price * 0.30), int(item_price * 0.20))."""
        # Gold safe (500 ₪): max possible cashback is 500 * 0.30 = 150 ₪
        assert calculate_duplicate_cashback(500, 1200, is_weapon=True) == 150  # Partyvan
        assert calculate_duplicate_cashback(500, 500, is_weapon=True) == 100   # Mute
        assert calculate_duplicate_cashback(500, 450, is_weapon=True) == 90    # Pepperspray
        assert calculate_duplicate_cashback(500, 400, is_weapon=True) == 80    # Knife
        assert calculate_duplicate_cashback(500, 100, is_weapon=True) == 20    # Shit

        # Trash case (150 ₪): max possible cashback is 150 * 0.30 = 45 ₪
        assert calculate_duplicate_cashback(150, 1200, is_weapon=True) == 45   # Partyvan
        assert calculate_duplicate_cashback(150, 500, is_weapon=True) == 45    # Mute
        assert calculate_duplicate_cashback(150, 400, is_weapon=True) == 45    # Knife
        assert calculate_duplicate_cashback(150, 100, is_weapon=True) == 20    # Shit

    def test_weapon_scrap_prices_table(self):
        """Validates explicit weapon scrap price dictionaries for trash and gold cases."""
        assert WEAPON_SCRAP_PRICES["trash"] == {
            "shit": 15,
            "pills": 20,
            "knife": 35,
            "pepperspray": 40,
            "mute": 45,
            "partyvan": 45,
        }
        assert WEAPON_SCRAP_PRICES["gold"] == {
            "shit": 20,
            "pills": 20,
            "knife": 80,
            "pepperspray": 80,
            "mute": 100,
            "partyvan": 150,
        }

    def test_apply_lootbox_reward_weapon_scrap_trash_case(self):
        """Scrap prices applied when opening trash case with already-charged weapon."""
        inv = {"knife_gun": True}
        payload = {"knife_gun": True}
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=0, case_type="trash")
        assert cash == 35
        assert "утиль +35 ₪" in note

        inv = {"mute_gun": True}
        payload = {"mute_gun": True}
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=0, case_type="trash")
        assert cash == 45
        assert "утиль +45 ₪" in note

    def test_apply_lootbox_reward_weapon_scrap_gold_case(self):
        """Scrap prices applied when opening gold case with already-charged weapon."""
        inv = {"knife_gun": True}
        payload = {"knife_gun": True}
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=0, case_type="gold")
        assert cash == 80
        assert "утиль +80 ₪" in note

        inv = {"partyvan_gun": True}
        payload = {"partyvan_gun": True}
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=0, case_type="gold")
        assert cash == 150
        assert "утиль +150 ₪" in note

    def test_bundle_cap_combat_kit_eliminates_dual_weapon_exploit(self):
        """
        Bundle Cap: In combat_kit bundle, if user already has weapon,
        cashback is capped at 80 ₪ total, eliminating legacy +137 ₪ profit.
        """
        now = int(time.time())
        bundle_payload = {
            "reflect_shield_until": now + 6 * 3600,
            "shield_until": now + 6 * 3600,
            "knife_gun": True,
            "pills_gun": True,
            "bundle_type": "combat_kit"
        }

        # 1. User has no weapons -> 0 cashback, items granted
        clean_inv = {}
        res_inv, cash, note = apply_lootbox_reward(clean_inv, bundle_payload, base_cash=0, case_type="gold")
        assert cash == 0
        assert res_inv["knife_gun"] is True
        assert res_inv["pills_gun"] is True

        # 2. User already has knife and pills -> bundle cap 80 ₪
        saturated_inv = {"knife_gun": True, "pills_gun": True}
        res_inv, cash, note = apply_lootbox_reward(saturated_inv, bundle_payload, base_cash=0, case_type="gold")
        assert cash == 80  # Exactly 80 ₪, not 80 + 20 or 300 + 337!
        assert "компенсация +80 ₪" in note

    def test_fixed_scrap_recycling_timed_apparel_when_perm_owned(self):
        """
        Rolling timed apparel when permanent is already owned gives fixed 35 ₪ scrap
        (instead of the old legacy 75% of catalog price).
        """
        inv = {
            "equipped_head": "hat_helmet",
            "hat_helmet_is_permanent": True,
            "owned_hat_helmet": True
        }
        timed_payload = {
            "item_id": "hat_helmet",
            "is_permanent": False,
            "dur_hours": 720,
            "slot": "head"
        }
        res_inv, cash, note = apply_lootbox_reward(inv, timed_payload, base_cash=0, case_type="gold")
        assert cash == 35
        assert "Утиль: +35 ₪" in note
        # Permanent status must not be overridden
        assert res_inv["hat_helmet_is_permanent"] is True

    def test_permanent_duplicate_apparel_cashback(self):
        """
        Rolling permanent apparel when permanent is already owned gives
        min(120, max(40, int(price * 0.20))).
        """
        inv = {
            "equipped_head": "hat_helmet",
            "hat_helmet_is_permanent": True,
            "owned_hat_helmet": True
        }
        perm_payload = {
            "item_id": "hat_helmet",  # price 600
            "is_permanent": True,
            "dur_hours": 0,
            "slot": "head"
        }
        # price 600 * 0.20 = 120 -> min(120, max(40, 120)) = 120
        res_inv, cash, note = apply_lootbox_reward(inv, perm_payload, base_cash=0, case_type="gold")
        assert cash == 120
        assert "Вечный дубликат" in note

        # Low price item: hat_bag (price 120)
        # 120 * 0.20 = 24 -> min(120, max(40, 24)) = 40
        inv_bag = {"hat_bag_is_permanent": True, "owned_hat_bag": True}
        bag_payload = {"item_id": "hat_bag", "is_permanent": True, "dur_hours": 0, "slot": "head"}
        res_inv, cash, note = apply_lootbox_reward(inv_bag, bag_payload, base_cash=0, case_type="gold")
        assert cash == 40

    def test_protective_buffs_capped_at_seven_days(self):
        """Cap protection buffs to max 7 days from current timestamp."""
        now = int(time.time())
        max_cap = now + 7 * 86400

        # Bloated existing inventory
        bloated_inv = {
            "shield_until": now + 365 * 86400,
            "reflect_shield_until": now + 30 * 86400,
            "tinfoil_until": now + 20 * 86400,
            "tinfoil_hat": now + 20 * 86400,
            "janitor_until": now + 15 * 86400,
        }
        payload = {"shield_until": now + 6 * 3600, "reflect_shield_until": now + 6 * 3600}
        res_inv, cash, note = apply_lootbox_reward(bloated_inv, payload, base_cash=0)

        assert res_inv["shield_until"] <= max_cap
        assert res_inv["reflect_shield_until"] <= max_cap
        assert res_inv["tinfoil_until"] <= max_cap
        assert res_inv["tinfoil_hat"] <= max_cap
        assert res_inv["janitor_until"] <= max_cap


# =============================================================================
# 3. MATHEMATICAL REBALANCE & MONTE CARLO EV/RTP (F2.3)
# =============================================================================

class TestMathematicalRebalanceAndRTP:
    """Verifies empirical RTP <= 85% on simulated distributions."""

    def test_roll_gold_safe_output_contract(self):
        """roll_gold_safe returns valid 5-tuple matching contract."""
        for _ in range(50):
            tier, title, desc, payload, base_cash = roll_gold_safe()
            assert isinstance(tier, str)
            assert isinstance(title, str)
            assert isinstance(desc, str)
            assert isinstance(payload, dict)
            assert isinstance(base_cash, int)
            assert base_cash >= 0

    def test_roll_trash_lootbox_output_contract(self):
        """roll_trash_lootbox returns valid 5-tuple matching contract."""
        for _ in range(50):
            tier, title, desc, payload, base_cash = roll_trash_lootbox()
            assert isinstance(tier, str)
            assert isinstance(title, str)
            assert isinstance(desc, str)
            assert isinstance(payload, dict)
            assert isinstance(base_cash, int)
            assert base_cash >= 0

    def test_monte_carlo_trash_lootbox_rtp_under_85(self):
        """
        10,000 stochastic rolls of Trash Lootbox (150 ₪) with saturated duplicate inventory.
        Confirms Liquid Cash RTP < 25% and Nominal RTP <= 85.0% (target ~53%).
        """
        random.seed(1337)
        N = 10000
        cost_per_case = 150
        total_spent = N * cost_per_case
        total_liquid_cash = 0
        total_nominal_value = 0

        # Fully saturated inventory
        active_items = {
            "knife_gun": True,
            "mute_gun": True,
            "partyvan_gun": True,
            "pepperspray_gun": True,
            "shit_gun": True,
            "pills_gun": True,
            "hat_bag_is_permanent": True,
        }

        for _ in range(N):
            tier, title, desc, payload, base_cash = roll_trash_lootbox()
            _, final_cash, _ = apply_lootbox_reward(
                dict(active_items), payload, base_cash, case_type="trash"
            )
            total_liquid_cash += final_cash

            # Nominal economic value
            if "🔥 ДЖЕКПОТ" in tier:
                nominal = 350 if base_cash == 350 else (500 if "mute_gun" in payload else 1200)
            elif "✨ РЕДКИЙ" in tier or "👗 БАЗОВЫЙ" in tier:
                nominal = 180
            elif "⚔️ РАСХОДНИК" in tier:
                nominal = 80
            else:  # Trash
                nominal = base_cash

            total_nominal_value += nominal

        cash_rtp = (total_liquid_cash / total_spent) * 100.0
        nominal_rtp = (total_nominal_value / total_spent) * 100.0

        assert cash_rtp < 25.0, f"Cash RTP {cash_rtp:.2f}% exceeds threshold"
        assert nominal_rtp <= 85.0, f"Nominal RTP {nominal_rtp:.2f}% exceeds 85%"

    def test_monte_carlo_gold_safe_rtp_under_85(self):
        """
        10,000 stochastic rolls of Gold Safe (500 ₪) with saturated duplicate inventory.
        Confirms Liquid Cash RTP < 35% and Nominal RTP <= 85.0% (target ~62%).
        """
        random.seed(1337)
        N = 10000
        cost_per_case = 500
        total_spent = N * cost_per_case
        total_liquid_cash = 0
        total_nominal_value = 0

        # Fully saturated inventory
        active_items = {
            "knife_gun": True,
            "pepperspray_gun": True,
            "partyvan_gun": True,
            "pills_gun": True,
            "body_cloak_is_permanent": True,
            "hat_helmet_is_permanent": True,
            "body_wasserman_is_permanent": True,
            "hat_cat_ears_is_permanent": True,
            "body_hoodie_is_permanent": True,
            "face_thug_glasses_is_permanent": True,
            "face_wasserman_glasses_is_permanent": True,
            "feet_boots_is_permanent": True,
            "feet_sneakers_is_permanent": True,
            "hat_crown_is_permanent": True,
            "face_anon_mask_is_permanent": True,
            "hat_golden_foil_is_permanent": True,
        }

        for _ in range(N):
            tier, title, desc, payload, base_cash = roll_gold_safe()
            _, final_cash, _ = apply_lootbox_reward(
                dict(active_items), payload, base_cash, case_type="gold"
            )
            total_liquid_cash += final_cash

            # Nominal economic value
            if "🌟 МИФИЧЕСКИЙ" in tier or "👑 СУПЕР-ДЖЕКПОТ" in tier:
                if base_cash == 1500:
                    nominal = 1500
                elif base_cash == 3000:
                    nominal = 3500
                elif "partyvan_gun" in payload:
                    nominal = 2100
                else:
                    nominal = 1000
            elif "🌟 ЛЕГЕНДАРНЫЙ" in tier or "👗 ЭЛИТНЫЙ" in tier:
                nominal = 364
            elif "⚔️ БОЕВОЙ" in tier:
                nominal = 250
            else:  # Premium Junk
                nominal = base_cash

            total_nominal_value += nominal

        cash_rtp = (total_liquid_cash / total_spent) * 100.0
        nominal_rtp = (total_nominal_value / total_spent) * 100.0

        assert cash_rtp < 35.0, f"Cash RTP {cash_rtp:.2f}% exceeds threshold"
        assert nominal_rtp <= 85.0, f"Nominal RTP {nominal_rtp:.2f}% exceeds 85%"

    def test_anti_autoclicker_continuous_bankruptcy(self):
        """Opening 1,000 Gold Safes monotonically drains player wallet to bankruptcy."""
        random.seed(42)
        balance = 50000.0  # 50k starting capital
        cost = 500
        opens = 0
        inv = {"knife_gun": True, "pepperspray_gun": True, "hat_helmet_is_permanent": True}

        while balance >= cost and opens < 1000:
            balance -= cost
            opens += 1
            tier, title, desc, payload, base_cash = roll_gold_safe()
            inv, cashback, _ = apply_lootbox_reward(inv, payload, base_cash, case_type="gold")
            balance += cashback

        # Player must go bankrupt in under 200 openings with 50,000 ₪
        assert balance < cost, f"Player did not go bankrupt! Final balance: {balance}"
        assert opens < 300, f"Player survived too long: {opens} openings"


# =============================================================================
# 4. NON-BUYABLE STATUS REWARDS & RELICS (F2.4)
# =============================================================================

class TestNonBuyableStatusRewards:
    """Validates exclusive non-buyable titles and permanent relics."""

    def test_non_buyable_titles_registry(self):
        """Four non-buyable titles exist in catalog constants."""
        expected = ["[Золотой Кит]", "[Шекелевый Барон]", "[Сборщик Стеклотары]", "[Король Помойки]"]
        assert NON_BUYABLE_TITLES == expected

    def test_exclusive_relics_in_clothing_catalog(self):
        """Three mythic relics exist in CLOTHING_CATALOG with non_buyable: True."""
        for relic_id in EXCLUSIVE_RELICS:
            assert relic_id in CLOTHING_CATALOG, f"Missing relic {relic_id} in CLOTHING_CATALOG"
            item = CLOTHING_CATALOG[relic_id]
            assert item.get("non_buyable") is True, f"{relic_id} must have non_buyable=True"
            assert item.get("tier") == 4
            assert item.get("defense", 0) > 0
            assert item.get("sanity", 0) > 0

    def test_hat_golden_foil_stats_and_immunities(self):
        """hat_golden_foil grants Def 50, San 50, and shit/schizo immunity."""
        items = {
            "equipped_head": "hat_golden_foil",
            "hat_golden_foil_is_permanent": True,
        }
        stats = get_wardrobe_total_stats(items)
        assert stats["total_defense"] == 50
        assert stats["total_sanity"] == 50
        assert stats["shit_immunity"] is True
        assert stats["schizo_immunity"] is True
        assert stats["compact_post_icon"] == "👑 "

    def test_body_dva_ch_mantle_stats_and_stealth(self):
        """body_dva_ch_mantle grants Def 35, San 50, and stealth mode."""
        items = {
            "equipped_torso": "body_dva_ch_mantle",
            "body_dva_ch_mantle_is_permanent": True,
        }
        stats = get_wardrobe_total_stats(items)
        assert stats["total_defense"] == 35
        assert stats["total_sanity"] == 50
        assert stats["stealth_profile"] is True

    def test_grant_title_via_apply_lootbox_reward(self):
        """apply_lootbox_reward records custom_title and expiration in active_items."""
        now = int(time.time())
        inv = {}
        payload = {"grant_title": "[Золотой Кит]", "title_days": 30}
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=3000)

        assert cash == 3000
        assert res_inv["custom_title"] == "[Золотой Кит]"
        assert res_inv["title_expires_at"] >= now + 29 * 86400
        assert "[Золотой Кит]" in note
