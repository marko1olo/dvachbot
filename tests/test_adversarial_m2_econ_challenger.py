# -*- coding: utf-8 -*-
"""
tests/test_adversarial_m2_econ_challenger.py — Adversarial Verification Suite for Milestone 2:
Duplicate Cashback Caps, Scrap Recycling, Protection Caps & Status Rewards.

Tested by: challenger_m2_econ_2 (Empirical Adversarial Verifier)

Verification Scope:
1. Duplicate weapon cashback for every weapon across both case types ('trash' and 'gold').
2. Heavy Combat Kit bundle cap: verify duplicate knife + pepperspray yields exactly 80 ₪ max, never 637 ₪.
3. Timed apparel duplicate when permanent owned: verify fixed 35 ₪ scrap payout.
4. Protection stacking caps: verify shield_until, tinfoil_until cap at exactly now + 7 * 86400 (7 days max).
5. Verify non-buyable status titles in drop tables and title assignment in active_items.
6. Empirical Monte Carlo bankruptcy & EV/RTP stress tests under adversarial edge cases.
"""

import copy
import random
import time
from typing import Dict, Any, List
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
# 1. DUPLICATE WEAPON CASHBACK FOR EVERY WEAPON ACROSS BOTH CASE TYPES
# =============================================================================

class TestAdversarialWeaponCashback:
    """
    Adversarially tests weapon duplicate cashback across 'trash' and 'gold' cases.
    Verifies that every weapon awards exact scrap when owned, and 0 cashback when unowned.
    """

    WEAPONS = ["shit", "pills", "knife", "pepperspray", "mute", "partyvan"]

    @pytest.mark.parametrize("weapon_key", WEAPONS)
    def test_duplicate_weapon_cashback_trash_case(self, weapon_key: str):
        """Verify duplicate scrap payout for every weapon in trash cases."""
        item_flag = f"{weapon_key}_gun"
        expected_scrap = WEAPON_SCRAP_PRICES["trash"][weapon_key]

        # Case A: User already owns the weapon -> must receive exact scrap
        owned_inv = {item_flag: True}
        payload = {item_flag: True}
        res_inv, cash, note = apply_lootbox_reward(owned_inv, payload, base_cash=0, case_type="trash")

        assert cash == expected_scrap, (
            f"Trash case duplicate {weapon_key} yielded {cash} ₪, expected {expected_scrap} ₪"
        )
        assert res_inv[item_flag] is True
        assert f"утиль +{expected_scrap} ₪" in note
        # Trash case price is 150: weapon cashback must NEVER exceed 30% of case price (45 ₪)
        assert cash <= 45, f"Cashback {cash} ₪ exceeds 30% case price cap (45 ₪) for trash case"

        # Case B: User does NOT own the weapon -> must receive 0 cashback and gain weapon
        clean_inv = {}
        res_inv2, cash2, note2 = apply_lootbox_reward(clean_inv, payload, base_cash=0, case_type="trash")
        assert cash2 == 0, f"Unowned weapon {weapon_key} gave cashback {cash2} ₪ instead of 0"
        assert res_inv2[item_flag] is True

    @pytest.mark.parametrize("weapon_key", WEAPONS)
    def test_duplicate_weapon_cashback_gold_case(self, weapon_key: str):
        """Verify duplicate scrap payout for every weapon in gold cases."""
        item_flag = f"{weapon_key}_gun"
        expected_scrap = WEAPON_SCRAP_PRICES["gold"][weapon_key]

        # Case A: User already owns the weapon -> must receive exact scrap
        owned_inv = {item_flag: True}
        payload = {item_flag: True}
        res_inv, cash, note = apply_lootbox_reward(owned_inv, payload, base_cash=0, case_type="gold")

        assert cash == expected_scrap, (
            f"Gold case duplicate {weapon_key} yielded {cash} ₪, expected {expected_scrap} ₪"
        )
        assert res_inv[item_flag] is True
        assert f"утиль +{expected_scrap} ₪" in note
        # Gold case price is 500: weapon cashback must NEVER exceed 30% of case price (150 ₪)
        assert cash <= 150, f"Cashback {cash} ₪ exceeds 30% case price cap (150 ₪) for gold case"

        # Case B: User does NOT own the weapon -> must receive 0 cashback and gain weapon
        clean_inv = {}
        res_inv2, cash2, note2 = apply_lootbox_reward(clean_inv, payload, base_cash=0, case_type="gold")
        assert cash2 == 0, f"Unowned weapon {weapon_key} gave cashback {cash2} ₪ instead of 0"
        assert res_inv2[item_flag] is True

    def test_calculate_duplicate_cashback_contract_bounds(self):
        """Adversarially tests boundary conditions of calculate_duplicate_cashback formula."""
        # Standard cases
        assert calculate_duplicate_cashback(150, 400) == 45   # min(45, 80) = 45
        assert calculate_duplicate_cashback(500, 400) == 80   # min(150, 80) = 80
        assert calculate_duplicate_cashback(500, 1200) == 150 # min(150, 240) = 150
        assert calculate_duplicate_cashback(500, 50) == 10    # min(150, 10) = 10

        # Boundary checks: zero case price or zero item price
        assert calculate_duplicate_cashback(0, 500) == 0
        assert calculate_duplicate_cashback(500, 0) == 0
        assert calculate_duplicate_cashback(0, 0) == 0

        # High prices (stress test integer precision)
        assert calculate_duplicate_cashback(1_000_000, 500_000) == 100_000  # min(300k, 100k) = 100k


# =============================================================================
# 2. HEAVY COMBAT KIT BUNDLE CAP (EXACTLY 80 ₪ MAX, NEVER 637 ₪)
# =============================================================================

class TestAdversarialCombatKitBundleCap:
    """
    Stress-tests the Combat Kit bundle cap.
    Verifies that duplicate weapon payouts in bundles are capped at exactly 80 ₪ max,
    never allowing the legacy 637 ₪ exploit.
    """

    def test_combat_kit_with_knife_when_knife_owned(self):
        """Knife duplicate in combat kit yields exactly 80 ₪."""
        now = int(time.time())
        inv = {"knife_gun": True}
        payload = {
            "reflect_shield_until": now + 6 * 3600,
            "shield_until": now + 6 * 3600,
            "knife_gun": True,
            "pills_gun": True,
            "bundle_type": "combat_kit"
        }
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=0, case_type="gold")
        assert cash == 80
        assert "компенсация +80 ₪" in note
        assert res_inv["pills_gun"] is True

    def test_combat_kit_with_pepperspray_when_pepperspray_owned(self):
        """Pepperspray duplicate in combat kit yields exactly 80 ₪."""
        now = int(time.time())
        inv = {"pepperspray_gun": True}
        payload = {
            "reflect_shield_until": now + 6 * 3600,
            "shield_until": now + 6 * 3600,
            "pepperspray_gun": True,
            "pills_gun": True,
            "bundle_type": "combat_kit"
        }
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=0, case_type="gold")
        assert cash == 80
        assert "компенсация +80 ₪" in note
        assert res_inv["pills_gun"] is True

    def test_combat_kit_with_both_knife_and_pepperspray_owned(self):
        """
        User already owns BOTH knife and pepperspray.
        Combat kit contains knife and pills.
        Total cashback must be exactly 80 ₪, NOT 80 + 80 or 637 ₪.
        """
        now = int(time.time())
        inv = {
            "knife_gun": True,
            "pepperspray_gun": True,
            "pills_gun": True,
        }
        payload = {
            "reflect_shield_until": now + 6 * 3600,
            "shield_until": now + 6 * 3600,
            "knife_gun": True,
            "pills_gun": True,
            "bundle_type": "combat_kit"
        }
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=0, case_type="gold")
        assert cash == 80, f"Expected exactly 80 ₪ cap, got {cash} ₪"
        assert cash != 637, "CRITICAL FLAW: Re-occurrence of 637 ₪ duplicate exploit!"

    def test_adversarially_crafted_dual_weapon_bundle(self):
        """
        Adversarial test: An evil/hacked bundle payload containing BOTH knife_gun AND pepperspray_gun.
        User already has both.
        The bundle cap logic MUST break on first detection and yield exactly 80 ₪, NEVER 160 ₪ or 637 ₪.
        """
        now = int(time.time())
        inv = {
            "knife_gun": True,
            "pepperspray_gun": True,
            "pills_gun": True,
        }
        adversarial_payload = {
            "reflect_shield_until": now + 6 * 3600,
            "shield_until": now + 6 * 3600,
            "knife_gun": True,
            "pepperspray_gun": True,
            "pills_gun": True,
            "bundle_type": "combat_kit"
        }
        res_inv, cash, note = apply_lootbox_reward(inv, adversarial_payload, base_cash=0, case_type="gold")
        assert cash == 80, f"Adversarial dual-weapon bundle yielded {cash} ₪, expected exactly 80 ₪"
        assert cash != 160
        assert cash != 637

    def test_combat_kit_unowned_grants_items_with_zero_cash(self):
        """User with empty inventory gets items and 0 ₪ cash."""
        now = int(time.time())
        inv = {}
        payload = {
            "reflect_shield_until": now + 6 * 3600,
            "shield_until": now + 6 * 3600,
            "knife_gun": True,
            "pills_gun": True,
            "bundle_type": "combat_kit"
        }
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=0, case_type="gold")
        assert cash == 0
        assert res_inv["knife_gun"] is True
        assert res_inv["pills_gun"] is True
        assert res_inv["shield_until"] >= now + 5 * 3600


# =============================================================================
# 3. TIMED APPAREL DUPLICATE WHEN PERMANENT OWNED (FIXED 35 ₪ SCRAP)
# =============================================================================

class TestAdversarialTimedApparelScrap:
    """
    Verifies that when a player rolls a timed apparel item while already owning the
    permanent version of that same item, a fixed scrap payout of exactly 35 ₪ is awarded.
    """

    ITEMS_TO_TEST = [
        "hat_helmet",
        "body_cloak",
        "body_wasserman",
        "hat_cat_ears",
        "body_hoodie",
        "face_thug_glasses",
        "face_wasserman_glasses",
        "feet_boots",
        "feet_sneakers",
        "hat_crown",
        "face_anon_mask",
        "hat_tophat",
        "hat_cyber_ushanka",
        "body_dva_ch_mantle",
        "hat_golden_foil",
    ]

    @pytest.mark.parametrize("item_id", ITEMS_TO_TEST)
    def test_timed_duplicate_yields_exact_35_shekels(self, item_id: str):
        """Verify fixed 35 ₪ scrap payout across diverse wardrobe items."""
        item_meta = CLOTHING_CATALOG.get(item_id, {})
        slot = item_meta.get("slot", "torso")

        # Inventory has this item permanently
        inv = {
            f"{item_id}_is_permanent": True,
            f"owned_{item_id}": True,
            f"equipped_{slot}": item_id,
        }

        timed_payload = {
            "item_id": item_id,
            "is_permanent": False,
            "dur_hours": 720,
            "slot": slot
        }

        res_inv, cash, note = apply_lootbox_reward(inv, timed_payload, base_cash=0, case_type="gold")

        # Must yield exactly 35 ₪
        assert cash == 35, (
            f"Item {item_id} yielded {cash} ₪ scrap, expected exactly 35 ₪"
        )
        assert "Утиль: +35 ₪" in note
        # Permanent status must remain intact
        assert res_inv[f"{item_id}_is_permanent"] is True

    def test_timed_apparel_when_permanent_not_owned_gives_zero_cash(self):
        """When permanent is NOT owned, timed apparel extends inventory and gives 0 cash."""
        inv = {}
        payload = {
            "item_id": "hat_helmet",
            "is_permanent": False,
            "dur_hours": 720,
            "slot": "head"
        }
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=0, case_type="gold")
        assert cash == 0
        assert res_inv.get("hat_helmet_is_permanent") is not True
        assert res_inv.get("equipped_head") == "hat_helmet"
        assert res_inv.get("owned_hat_helmet") is True
        assert "Продление экипировки" in note

    def test_permanent_apparel_duplicate_cashback_bounds(self):
        """Permanent apparel duplicate gives min(120, max(40, int(price * 0.20)))."""
        # 1. High price item (e.g. price 600 -> 20% is 120 -> cashback 120)
        inv = {"hat_helmet_is_permanent": True, "owned_hat_helmet": True}
        perm_payload = {"item_id": "hat_helmet", "is_permanent": True, "dur_hours": 0, "slot": "head"}
        res_inv, cash, note = apply_lootbox_reward(inv, perm_payload, base_cash=0, case_type="gold")
        assert cash == 120
        assert "Вечный дубликат" in note

        # 2. Low price item (e.g. price 120 -> 20% is 24 -> clamped to 40)
        inv2 = {"hat_bag_is_permanent": True, "owned_hat_bag": True}
        perm_payload2 = {"item_id": "hat_bag", "is_permanent": True, "dur_hours": 0, "slot": "head"}
        res_inv2, cash2, note2 = apply_lootbox_reward(inv2, perm_payload2, base_cash=0, case_type="gold")
        assert cash2 == 40


# =============================================================================
# 4. PROTECTION STACKING CAPS (EXACTLY NOW + 7 * 86400 / 7 DAYS MAX)
# =============================================================================

class TestAdversarialProtectionStackingCaps:
    """
    Adversarially stress-tests protection duration stacking.
    Verifies that shield_until, reflect_shield_until, tinfoil_until, and tinfoil_hat
    never exceed now + 7 * 86400 (7 days max).
    """

    def test_shield_stacking_cap_under_rapid_accumulation(self):
        """Simulate rapid accumulation of shields: cannot exceed 7 days."""
        now = int(time.time())
        max_cap = now + 7 * 86400
        inv: Dict[str, Any] = {}

        # Add shields 35 times (+6 hours each = 210 hours > 168 hours / 7 days)
        for i in range(35):
            payload = {
                "shield_until": now + 6 * 3600,
                "reflect_shield_until": now + 6 * 3600
            }
            inv, _, _ = apply_lootbox_reward(inv, payload, base_cash=0, case_type="gold")

            assert inv["shield_until"] <= max_cap, (
                f"Iteration {i}: shield_until {inv['shield_until']} exceeded max cap {max_cap}!"
            )
            assert inv["reflect_shield_until"] <= max_cap, (
                f"Iteration {i}: reflect_shield_until exceeded max cap!"
            )

        # After 35 rolls, duration must be clamped exactly at max_cap
        assert inv["shield_until"] == max_cap
        assert inv["reflect_shield_until"] == max_cap

    def test_tinfoil_stacking_cap_under_rapid_accumulation(self):
        """Simulate rapid accumulation of tinfoil hats: cannot exceed 7 days."""
        now = int(time.time())
        max_cap = now + 7 * 86400
        inv: Dict[str, Any] = {}

        # Add tinfoil 35 times (+6 hours each)
        for i in range(35):
            payload = {
                "tinfoil_until": now + 6 * 3600,
                "tinfoil_hat": now + 6 * 3600
            }
            inv, _, _ = apply_lootbox_reward(inv, payload, base_cash=0, case_type="trash")

            assert inv["tinfoil_until"] <= max_cap, (
                f"Iteration {i}: tinfoil_until {inv['tinfoil_until']} exceeded max cap {max_cap}!"
            )
            assert inv["tinfoil_hat"] <= max_cap, (
                f"Iteration {i}: tinfoil_hat exceeded max cap!"
            )

        assert inv["tinfoil_until"] == max_cap
        assert inv["tinfoil_hat"] == max_cap

    def test_preexisting_bloated_protection_clamped_immediately(self):
        """
        Adversarial test: A user has a cheated or legacy bloated duration of 10 years (3650 days).
        Any subsequent lootbox opening must instantly clamp all protection buffs down to max 7 days.
        """
        now = int(time.time())
        max_cap = now + 7 * 86400

        bloated_inv = {
            "shield_until": now + 3650 * 86400,
            "reflect_shield_until": now + 3650 * 86400,
            "tinfoil_until": now + 3650 * 86400,
            "tinfoil_hat": now + 3650 * 86400,
            "janitor_until": now + 3650 * 86400,
        }

        # Any innocent reward application (e.g. empty or minor trash payload)
        payload = {"knife_gun": True}
        res_inv, _, _ = apply_lootbox_reward(bloated_inv, payload, base_cash=0, case_type="trash")

        assert res_inv["shield_until"] == max_cap, "Bloated shield_until was not clamped to 7 days"
        assert res_inv["reflect_shield_until"] == max_cap, "Bloated reflect_shield_until was not clamped"
        assert res_inv["tinfoil_until"] == max_cap, "Bloated tinfoil_until was not clamped"
        assert res_inv["tinfoil_hat"] == max_cap, "Bloated tinfoil_hat was not clamped"
        assert res_inv["janitor_until"] == max_cap, "Bloated janitor_until was not clamped"

    def test_expired_protection_resets_properly_from_now(self):
        """If protection expired in the past, new buff duration starts from `now`, not from ancient past."""
        now = int(time.time())
        expired_inv = {
            "shield_until": now - 100000,
            "reflect_shield_until": now - 100000,
            "tinfoil_until": now - 50000,
            "tinfoil_hat": now - 50000,
        }
        payload = {
            "shield_until": now + 6 * 3600,
            "reflect_shield_until": now + 6 * 3600,
            "tinfoil_until": now + 6 * 3600,
            "tinfoil_hat": now + 6 * 3600,
        }
        res_inv, _, _ = apply_lootbox_reward(expired_inv, payload, base_cash=0, case_type="trash")

        # Duration should be approximately now + 6 hours
        expected_expiry = now + 6 * 3600
        assert abs(res_inv["shield_until"] - expected_expiry) <= 5
        assert abs(res_inv["reflect_shield_until"] - expected_expiry) <= 5
        assert abs(res_inv["tinfoil_until"] - expected_expiry) <= 5
        assert abs(res_inv["tinfoil_hat"] - expected_expiry) <= 5


# =============================================================================
# 5. NON-BUYABLE STATUS TITLES IN DROP TABLES & ASSIGNMENT IN ACTIVE_ITEMS
# =============================================================================

class TestAdversarialStatusTitlesAndRelics:
    """
    Verifies that non-buyable status titles are present in drop tables,
    can be rolled, are properly assigned to active_items, and cannot be bought in shops.
    """

    EXPECTED_TITLES = ["[Золотой Кит]", "[Шекелевый Барон]", "[Сборщик Стеклотары]", "[Король Помойки]"]

    def test_non_buyable_titles_registry(self):
        """All 4 exclusive titles are listed in NON_BUYABLE_TITLES."""
        assert NON_BUYABLE_TITLES == self.EXPECTED_TITLES

    def test_non_buyable_titles_cannot_be_bought_in_clothing_catalog(self):
        """Ensure no title or exclusive relic can be bought with shekels in clothing catalog."""
        for item_id, data in CLOTHING_CATALOG.items():
            # If item is in EXCLUSIVE_RELICS, it must have non_buyable: True
            if item_id in EXCLUSIVE_RELICS:
                assert data.get("non_buyable") is True, f"Relic {item_id} must be non_buyable"

    def test_drop_tables_contain_all_four_status_titles(self):
        """
        Adversarially inspects roll_trash_lootbox and roll_gold_safe generators
        to prove that all 4 titles can be generated across case rolls.
        """
        found_titles = set()

        # Deterministic simulation over many seeds to verify presence in generators
        for seed in range(5000):
            random.seed(seed)
            _, _, _, trash_payload, _ = roll_trash_lootbox()
            if "grant_title" in trash_payload:
                found_titles.add(trash_payload["grant_title"])

            random.seed(seed + 100000)
            _, _, _, gold_payload, _ = roll_gold_safe()
            if "grant_title" in gold_payload:
                found_titles.add(gold_payload["grant_title"])

            if len(found_titles) == 4:
                break

        assert found_titles == set(self.EXPECTED_TITLES), (
            f"Expected all 4 titles to be present in drop generators, but only found: {found_titles}"
        )

    def test_grant_title_assignment_in_active_items(self):
        """
        apply_lootbox_reward correctly records custom_title and title_expires_at,
        handling both bracketed and unbracketed input strings.
        """
        now = int(time.time())

        # Test A: Title with brackets
        inv1: Dict[str, Any] = {}
        payload1 = {"grant_title": "[Золотой Кит]", "title_days": 30}
        res1, cash1, note1 = apply_lootbox_reward(inv1, payload1, base_cash=0)
        assert res1["custom_title"] == "[Золотой Кит]"
        assert res1["title_expires_at"] == now + 30 * 86400
        assert "ПОЛУЧЕН ТИТУЛ" in note1
        assert "[Золотой Кит]" in note1

        # Test B: Title without brackets -> auto-enclosed
        inv2: Dict[str, Any] = {}
        payload2 = {"grant_title": "Король Помойки", "title_days": 15}
        res2, cash2, note2 = apply_lootbox_reward(inv2, payload2, base_cash=0)
        assert res2["custom_title"] == "[Король Помойки]"
        assert res2["title_expires_at"] == now + 15 * 86400
        assert "[Король Помойки]" in note2

    def test_exclusive_relics_properties_in_wardrobe(self):
        """Validate mythic relics exist, have Tier 4, and grant strong passives."""
        for relic_id in EXCLUSIVE_RELICS:
            assert relic_id in CLOTHING_CATALOG
            relic = CLOTHING_CATALOG[relic_id]
            assert relic.get("tier") == 4
            assert relic.get("non_buyable") is True
            assert relic.get("name") is not None


# =============================================================================
# 6. MONTE CARLO ADVERSARIAL STRESS-TESTS (EV/RTP & CONTINUOUS BANKRUPTCY)
# =============================================================================

class TestAdversarialEconomicSoundness:
    """
    Proves that the rebalanced economy has strictly negative expected return for players,
    guaranteeing that autoclicker bots continuously bleed funds to bankruptcy.
    """

    def test_monte_carlo_trash_lootbox_rtp_bounds(self):
        """10,000 rolls of Trash case (150 ₪): Cash RTP < 25%, Nominal RTP <= 85%."""
        random.seed(9999)
        N = 10000
        cost = 150
        total_cash = 0
        total_nominal = 0

        # Fully saturated inventory to maximize duplicate cashbacks
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
            tier, _, _, payload, base_cash = roll_trash_lootbox()
            _, final_cash, _ = apply_lootbox_reward(copy.deepcopy(active_items), payload, base_cash, case_type="trash")
            total_cash += final_cash

            if "🔥 ДЖЕКПОТ" in tier:
                nom = 350 if base_cash == 350 else (500 if "mute_gun" in payload else 1200)
            elif "✨ РЕДКИЙ" in tier or "👗 БАЗОВЫЙ" in tier:
                nom = 180
            elif "⚔️ РАСХОДНИК" in tier:
                nom = 80
            else:
                nom = base_cash
            total_nominal += nom

        cash_rtp = (total_cash / (N * cost)) * 100.0
        nominal_rtp = (total_nominal / (N * cost)) * 100.0

        assert cash_rtp < 25.0, f"Cash RTP {cash_rtp:.2f}% exceeded 25%"
        assert nominal_rtp <= 85.0, f"Nominal RTP {nominal_rtp:.2f}% exceeded 85%"

    def test_monte_carlo_gold_safe_rtp_bounds(self):
        """10,000 rolls of Gold Safe (500 ₪): Cash RTP < 35%, Nominal RTP <= 85%."""
        random.seed(9999)
        N = 10000
        cost = 500
        total_cash = 0
        total_nominal = 0

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
            tier, _, _, payload, base_cash = roll_gold_safe()
            _, final_cash, _ = apply_lootbox_reward(copy.deepcopy(active_items), payload, base_cash, case_type="gold")
            total_cash += final_cash

            if "🌟 МИФИЧЕСКИЙ" in tier or "👑 СУПЕР-ДЖЕКПОТ" in tier:
                if base_cash == 1500:
                    nom = 1500
                elif base_cash == 3000:
                    nom = 3500
                elif "partyvan_gun" in payload:
                    nom = 2100
                else:
                    nom = 1000
            elif "🌟 ЛЕГЕНДАРНЫЙ" in tier or "👗 ЭЛИТНЫЙ" in tier:
                nom = 364
            elif "⚔️ БОЕВОЙ" in tier:
                nom = 250
            else:
                nom = base_cash
            total_nominal += nom

        cash_rtp = (total_cash / (N * cost)) * 100.0
        nominal_rtp = (total_nominal / (N * cost)) * 100.0

        assert cash_rtp < 35.0, f"Cash RTP {cash_rtp:.2f}% exceeded 35%"
        assert nominal_rtp <= 85.0, f"Nominal RTP {nominal_rtp:.2f}% exceeded 85%"

    def test_autoclicker_continuous_bankruptcy_simulation(self):
        """
        Adversarial test: An oligarch bot with 100,000 ₪ tries to spam gold safe openings.
        Must monotonically trend downwards and hit 0 balance (no infinite loop).
        """
        random.seed(777)
        balance = 100_000
        cost = 500
        rolls = 0
        inv = {
            "knife_gun": True,
            "pepperspray_gun": True,
            "hat_helmet_is_permanent": True,
            "body_cloak_is_permanent": True,
        }

        while balance >= cost and rolls < 5000:
            balance -= cost
            rolls += 1
            _, _, _, payload, base_cash = roll_gold_safe()
            inv, cashback, _ = apply_lootbox_reward(inv, payload, base_cash, case_type="gold")
            balance += cashback

        # Player must deplete the 100k balance within reasonable number of rolls
        assert balance < cost, f"Bot survived with balance {balance} ₪ after {rolls} rolls!"
        assert rolls < 600, f"Bot lasted too long: {rolls} rolls with 100,000 ₪"
