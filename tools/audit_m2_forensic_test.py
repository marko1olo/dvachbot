# -*- coding: utf-8 -*-
"""
tools/audit_m2_forensic_test.py
Independent Forensic Auditor Verification Script for Milestone 2.
Empirically stress-tests:
1. AST analysis for hardcoded shortcuts or facades.
2. Boundary and edge-case inputs.
3. Multi-seed Monte Carlo simulations (20,000 rolls per case type).
4. Continuous bankruptcy and positive-EV exploit search.
"""

import ast
import random
import time
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


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

def audit_ast():
    print("=== 1. AST ANALYSIS OF LOOTBOX ENGINE ===")
    filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lootbox_engine.py"))
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    print(f"Found functions: {func_names}")

    required_funcs = ["calculate_duplicate_cashback", "roll_trash_lootbox", "roll_gold_safe", "apply_lootbox_reward"]
    for rf in required_funcs:
        assert rf in func_names, f"Missing function: {rf}"

    # Search for suspicious identifiers
    suspicious = ["mock", "fake", "bypass", "test_override", "always_win", "cheat"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            for s in suspicious:
                if s in node.id.lower():
                    raise AssertionError(f"Suspicious variable found in AST: {node.id}")
    print("AST Check: PASS (No suspicious identifiers, all functions exist)")

def audit_boundary_cases():
    print("=== 2. BOUNDARY AND EDGE CASE STRESS TEST ===")
    
    # 2.1 calculate_duplicate_cashback boundaries
    assert calculate_duplicate_cashback(0, 0) == 0
    assert calculate_duplicate_cashback(0, 1000) == 0
    assert calculate_duplicate_cashback(1000, 0) == 0
    assert calculate_duplicate_cashback(100, 50) == 10  # min(30, 10) = 10
    assert calculate_duplicate_cashback(500, 1200) == 150 # min(150, 240) = 150
    assert calculate_duplicate_cashback(10**8, 10**8) == 20000000 # min(30M, 20M) = 20M
    print("Cashback boundary checks: PASS")

    # 2.2 7-day protection capping under repeated stress
    now = int(time.time())
    inv = {"shield_until": now + 86400 * 6, "reflect_shield_until": now + 86400 * 6}
    for _ in range(50):
        payload = {"shield_until": now + 6 * 3600, "reflect_shield_until": now + 6 * 3600}
        inv, _, _ = apply_lootbox_reward(inv, payload, 0, case_type="gold")
        assert inv["shield_until"] <= now + 7 * 86400 + 1
        assert inv["reflect_shield_until"] <= now + 7 * 86400 + 1
    print("Buff 7-day clamping stress: PASS")

    # 2.3 Corrupted inventory recovery in apply_lootbox_reward
    corrupted_inv = {
        "knife_gun": None,
        "equipped_head": 12345,
        "shield_until": -999,
        "hat_helmet_is_permanent": "invalid_string"
    }
    # Must not throw unhandled exceptions
    res_inv, cash, note = apply_lootbox_reward(dict(corrupted_inv), {"knife_gun": True}, 50, case_type="gold")
    assert cash >= 50
    print("Corrupted inventory resilience: PASS")

def audit_monte_carlo_multi_seed():
    print("=== 3. MULTI-SEED MONTE CARLO SIMULATION (20,000 ROLLS) ===")
    seeds = [42, 1337, 2026, 99999, 777]
    
    # Trash Lootbox: Cost 150, Target Nominal RTP <= 85%, Target Cash RTP < 25%
    for s in seeds:
        random.seed(s)
        N = 20000
        cost = 150
        spent = N * cost
        liquid_cash = 0
        nominal_val = 0
        
        # Saturated inventory
        inv = {
            "knife_gun": True, "mute_gun": True, "partyvan_gun": True,
            "pepperspray_gun": True, "shit_gun": True, "pills_gun": True,
            "hat_bag_is_permanent": True
        }
        for _ in range(N):
            tier, title, desc, payload, base_cash = roll_trash_lootbox()
            _, final_cash, _ = apply_lootbox_reward(dict(inv), payload, base_cash, case_type="trash")
            liquid_cash += final_cash
            
            if "🔥 ДЖЕКПОТ" in tier:
                nom = 350 if base_cash == 350 else (500 if "mute_gun" in payload else 1200)
            elif "✨ РЕДКИЙ" in tier or "👗 БАЗОВЫЙ" in tier:
                nom = 180
            elif "⚔️ РАСХОДНИК" in tier:
                nom = 80
            else:
                nom = base_cash
            nominal_val += nom

        cash_rtp = (liquid_cash / spent) * 100.0
        nominal_rtp = (nominal_val / spent) * 100.0
        print(f"Trash Case (Seed {s}): Cash RTP = {cash_rtp:.2f}%, Nominal RTP = {nominal_rtp:.2f}%")
        assert cash_rtp < 25.0, f"Cash RTP {cash_rtp}% exceeds 25%"
        assert nominal_rtp <= 85.0, f"Nominal RTP {nominal_rtp}% exceeds 85%"

    # Gold Safe: Cost 500, Target Nominal RTP <= 85%, Target Cash RTP < 35%
    for s in seeds:
        random.seed(s)
        N = 20000
        cost = 500
        spent = N * cost
        liquid_cash = 0
        nominal_val = 0
        
        # Fully saturated inventory
        inv = {
            "knife_gun": True, "pepperspray_gun": True, "partyvan_gun": True, "pills_gun": True,
            "body_cloak_is_permanent": True, "hat_helmet_is_permanent": True, "body_wasserman_is_permanent": True,
            "hat_cat_ears_is_permanent": True, "body_hoodie_is_permanent": True, "face_thug_glasses_is_permanent": True,
            "face_wasserman_glasses_is_permanent": True, "feet_boots_is_permanent": True, "feet_sneakers_is_permanent": True,
            "hat_crown_is_permanent": True, "face_anon_mask_is_permanent": True, "hat_golden_foil_is_permanent": True
        }
        for _ in range(N):
            tier, title, desc, payload, base_cash = roll_gold_safe()
            _, final_cash, _ = apply_lootbox_reward(dict(inv), payload, base_cash, case_type="gold")
            liquid_cash += final_cash
            
            if "🌟 МИФИЧЕСКИЙ" in tier or "👑 СУПЕР-ДЖЕКПОТ" in tier:
                if base_cash == 1500: nom = 1500
                elif base_cash == 3000: nom = 3500
                elif "partyvan_gun" in payload: nom = 2100
                else: nom = 1000
            elif "🌟 ЛЕГЕНДАРНЫЙ" in tier or "👗 ЭЛИТНЫЙ" in tier:
                nom = 364
            elif "⚔️ БОЕВОЙ" in tier:
                nom = 250
            else:
                nom = base_cash
            nominal_val += nom

        cash_rtp = (liquid_cash / spent) * 100.0
        nominal_rtp = (nominal_val / spent) * 100.0
        print(f"Gold Safe (Seed {s}): Cash RTP = {cash_rtp:.2f}%, Nominal RTP = {nominal_rtp:.2f}%")
        assert cash_rtp < 35.0, f"Cash RTP {cash_rtp}% exceeds 35%"
        assert nominal_rtp <= 85.0, f"Nominal RTP {nominal_rtp}% exceeds 85%"

    print("Multi-seed Monte Carlo: PASS")

def audit_continuous_bankruptcy():
    print("=== 4. CONTINUOUS BANKRUPTCY & ANTI-EXPLOIT PROOF ===")
    random.seed(999)
    balance = 100000.0  # 100k starting capital
    cost = 500
    opens = 0
    inv = {"knife_gun": True, "pepperspray_gun": True, "hat_helmet_is_permanent": True}
    
    balances = [balance]
    while balance >= cost and opens < 2000:
        balance -= cost
        opens += 1
        tier, title, desc, payload, base_cash = roll_gold_safe()
        inv, cashback, _ = apply_lootbox_reward(inv, payload, base_cash, case_type="gold")
        balance += cashback
        balances.append(balance)

    print(f"Started at 100,000 ₪, went bankrupt at open #{opens}. Final balance: {balance} ₪.")
    assert balance < cost, f"Player did not go bankrupt! Final balance: {balance}"
    assert opens < 500, f"Player survived too long ({opens} opens), indicating positive or near-100% RTP."
    print("Continuous Bankruptcy: PASS (No infinite money exploit possible)")

if __name__ == "__main__":
    audit_ast()
    audit_boundary_cases()
    audit_monte_carlo_multi_seed()
    audit_continuous_bankruptcy()
    print("\nALL FORENSIC AUDIT CHECKS PASSED EMPIRICALLY!")
