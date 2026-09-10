# -*- coding: utf-8 -*-
"""
scripts/verify_m2_econ_adversarial.py — Standalone Adversarial Verifier for Milestone 2:
Duplicate Cashback Caps & Status Rewards.

Author: challenger_m2_econ_2 (Empirical Adversarial Verifier)
"""

import os
import sys
import time
import random
from typing import Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def log_test(name: str, passed: bool, detail: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"[{status}] {name}")
    if detail:
        print(f"       -> {detail}")
    if not passed:
        print(f"FATAL ERROR in test: {name}")
        sys.exit(1)


def verify_duplicate_weapon_cashback():
    print("\n--- 1. Duplicate Weapon Cashback for Every Weapon Across Both Case Types ---")
    weapons = ["shit", "pills", "knife", "pepperspray", "mute", "partyvan"]

    for ctype in ("trash", "gold"):
        table = WEAPON_SCRAP_PRICES[ctype]
        case_price = 150 if ctype == "trash" else 500
        max_cap = int(case_price * 0.30)

        for w in weapons:
            expected = table[w]
            w_flag = f"{w}_gun"

            # Check 1: User already owns weapon -> receives exact scrap payout
            owned_inv = {w_flag: True}
            payload = {w_flag: True}
            res_inv, cash, note = apply_lootbox_reward(owned_inv, payload, base_cash=0, case_type=ctype)
            passed = (cash == expected) and (cash <= max_cap) and (res_inv.get(w_flag) is True)
            log_test(
                f"Case '{ctype}' duplicate {w} scrap payout",
                passed,
                f"Yielded: {cash} ₪ (expected: {expected} ₪, max 30% cap: {max_cap} ₪)"
            )

            # Check 2: User does NOT own weapon -> receives 0 cashback and gains weapon
            clean_inv = {}
            res_inv2, cash2, _ = apply_lootbox_reward(clean_inv, payload, base_cash=0, case_type=ctype)
            passed2 = (cash2 == 0) and (res_inv2.get(w_flag) is True)
            log_test(
                f"Case '{ctype}' unowned {w} grant",
                passed2,
                f"Yielded: {cash2} ₪ cashback (expected: 0 ₪), weapon acquired: {res_inv2.get(w_flag)}"
            )


def verify_heavy_combat_kit_bundle_cap():
    print("\n--- 2. Heavy Combat Kit Bundle Cap (Max 80 ₪, Never 637 ₪) ---")
    now = int(time.time())

    # Scenario A: User owns knife -> receives exactly 80 ₪
    inv_knife = {"knife_gun": True}
    bundle_payload = {
        "reflect_shield_until": now + 6 * 3600,
        "shield_until": now + 6 * 3600,
        "knife_gun": True,
        "pills_gun": True,
        "bundle_type": "combat_kit"
    }
    res_inv, cash, note = apply_lootbox_reward(inv_knife, bundle_payload, base_cash=0, case_type="gold")
    passed_a = (cash == 80) and (cash != 637)
    log_test("Combat kit with duplicate knife", passed_a, f"Yielded: {cash} ₪ (expected 80 ₪)")

    # Scenario B: User owns pepperspray -> receives exactly 80 ₪
    inv_spray = {"pepperspray_gun": True}
    bundle_payload_spray = {
        "reflect_shield_until": now + 6 * 3600,
        "shield_until": now + 6 * 3600,
        "pepperspray_gun": True,
        "pills_gun": True,
        "bundle_type": "combat_kit"
    }
    res_inv, cash, note = apply_lootbox_reward(inv_spray, bundle_payload_spray, base_cash=0, case_type="gold")
    passed_b = (cash == 80) and (cash != 637)
    log_test("Combat kit with duplicate pepperspray", passed_b, f"Yielded: {cash} ₪ (expected 80 ₪)")

    # Scenario C: User owns knife AND pepperspray -> receives exactly 80 ₪ (NOT 160 ₪ or 637 ₪)
    inv_both = {"knife_gun": True, "pepperspray_gun": True, "pills_gun": True}
    res_inv, cash, note = apply_lootbox_reward(inv_both, bundle_payload, base_cash=0, case_type="gold")
    passed_c = (cash == 80) and (cash != 637)
    log_test("Combat kit when owning both knife & pepperspray", passed_c, f"Yielded: {cash} ₪ (expected exactly 80 ₪)")

    # Scenario D: Adversarial hacked bundle with BOTH weapons inside payload
    evil_bundle = {
        "reflect_shield_until": now + 6 * 3600,
        "shield_until": now + 6 * 3600,
        "knife_gun": True,
        "pepperspray_gun": True,
        "pills_gun": True,
        "bundle_type": "combat_kit"
    }
    res_inv, cash, note = apply_lootbox_reward(inv_both, evil_bundle, base_cash=0, case_type="gold")
    passed_d = (cash == 80) and (cash != 160) and (cash != 637)
    log_test("Adversarial bundle with dual-weapons inside payload", passed_d, f"Yielded: {cash} ₪ (capped strictly at 80 ₪)")


def verify_timed_apparel_scrap():
    print("\n--- 3. Timed Apparel Duplicate When Permanent Owned (Fixed 35 ₪ Scrap) ---")
    catalog_items = list(CLOTHING_CATALOG.keys())
    sampled_items = catalog_items[:10]

    for item_id in sampled_items:
        meta = CLOTHING_CATALOG[item_id]
        slot = meta.get("slot", "torso")
        price = meta.get("price", 400)

        inv = {
            f"{item_id}_is_permanent": True,
            f"owned_{item_id}": True,
            f"equipped_{slot}": item_id
        }
        timed_payload = {
            "item_id": item_id,
            "is_permanent": False,
            "dur_hours": 720,
            "slot": slot
        }

        res_inv, cash, note = apply_lootbox_reward(inv, timed_payload, base_cash=0, case_type="gold")
        passed = (cash == 35) and (res_inv.get(f"{item_id}_is_permanent") is True)
        log_test(
            f"Timed duplicate for '{item_id}' (catalog price {price} ₪)",
            passed,
            f"Scrap payout: {cash} ₪ (expected exactly 35 ₪ fixed scrap, permanent retained: {res_inv.get(f'{item_id}_is_permanent')})"
        )


def verify_protection_stacking_caps():
    print("\n--- 4. Protection Stacking Caps (Max now + 7 * 86400 / 7 Days Max) ---")
    now = int(time.time())
    max_cap = now + 7 * 86400

    # Test 1: Rapid accumulation of shields
    inv = {}
    for i in range(30):
        p = {"shield_until": now + 6 * 3600, "reflect_shield_until": now + 6 * 3600}
        inv, _, _ = apply_lootbox_reward(inv, p, base_cash=0, case_type="gold")

    passed_shield = (inv["shield_until"] == max_cap) and (inv["reflect_shield_until"] == max_cap)
    log_test(
        "Shield duration capped at exactly 7 days",
        passed_shield,
        f"shield_until: {inv['shield_until']}, max_cap: {max_cap}, diff: {inv['shield_until'] - max_cap}s"
    )

    # Test 2: Rapid accumulation of tinfoil
    inv2 = {}
    for i in range(30):
        p = {"tinfoil_until": now + 6 * 3600, "tinfoil_hat": now + 6 * 3600}
        inv2, _, _ = apply_lootbox_reward(inv2, p, base_cash=0, case_type="trash")

    passed_tinfoil = (inv2["tinfoil_until"] == max_cap) and (inv2["tinfoil_hat"] == max_cap)
    log_test(
        "Tinfoil duration capped at exactly 7 days",
        passed_tinfoil,
        f"tinfoil_until: {inv2['tinfoil_until']}, max_cap: {max_cap}, diff: {inv2['tinfoil_until'] - max_cap}s"
    )

    # Test 3: Bloated legacy duration clamped immediately
    bloated = {
        "shield_until": now + 500 * 86400,
        "tinfoil_until": now + 500 * 86400,
        "janitor_until": now + 500 * 86400
    }
    res_bloated, _, _ = apply_lootbox_reward(bloated, {"knife_gun": True}, base_cash=0, case_type="trash")
    passed_clamp = (
        res_bloated["shield_until"] == max_cap and
        res_bloated["tinfoil_until"] == max_cap and
        res_bloated["janitor_until"] == max_cap
    )
    log_test(
        "Preexisting bloated protection clamped down to 7 days",
        passed_clamp,
        f"Clamped shield: {res_bloated['shield_until']}, tinfoil: {res_bloated['tinfoil_until']}"
    )


def verify_non_buyable_titles_and_assignment():
    print("\n--- 5. Non-Buyable Status Titles & Assignment in active_items ---")
    expected = ["[Золотой Кит]", "[Шекелевый Барон]", "[Сборщик Стеклотары]", "[Король Помойки]"]
    log_test("NON_BUYABLE_TITLES matches expected 4 titles", NON_BUYABLE_TITLES == expected)

    # Check titles can be generated across roll engines
    found = set()
    for s in range(5000):
        random.seed(s)
        _, _, _, tp, _ = roll_trash_lootbox()
        if "grant_title" in tp:
            found.add(tp["grant_title"])
        random.seed(s + 50000)
        _, _, _, gp, _ = roll_gold_safe()
        if "grant_title" in gp:
            found.add(gp["grant_title"])
        if len(found) == 4:
            break

    log_test(
        "All 4 non-buyable status titles present in lootbox drop generators",
        found == set(expected),
        f"Found titles: {found}"
    )

    # Check assignment in active_items
    now = int(time.time())
    for t in expected:
        inv = {}
        payload = {"grant_title": t, "title_days": 30}
        res_inv, cash, note = apply_lootbox_reward(inv, payload, base_cash=0)
        passed = (
            res_inv.get("custom_title") == t and
            res_inv.get("title_expires_at") == now + 30 * 86400 and
            t in note
        )
        log_test(f"Title {t} assignment in active_items", passed, f"custom_title: {res_inv.get('custom_title')}")

    # Check non-buyability in CLOTHING_CATALOG
    relics_ok = True
    for r in EXCLUSIVE_RELICS:
        if r not in CLOTHING_CATALOG or CLOTHING_CATALOG[r].get("non_buyable") is not True:
            relics_ok = False
            break
    log_test("Exclusive mythic relics are registered as non_buyable in catalog", relics_ok)


def main():
    print("=" * 75)
    print("EMPIRICAL ADVERSARIAL VERIFICATION SUITE — MILESTONE 2")
    print("=" * 75)
    verify_duplicate_weapon_cashback()
    verify_heavy_combat_kit_bundle_cap()
    verify_timed_apparel_scrap()
    verify_protection_stacking_caps()
    verify_non_buyable_titles_and_assignment()
    print("\n" + "=" * 75)
    print("ALL 5 MILESTONE 2 REQUIREMENTS EMPIRICALLY VERIFIED WITH ZERO ERRORS!")
    print("=" * 75)


if __name__ == "__main__":
    main()
