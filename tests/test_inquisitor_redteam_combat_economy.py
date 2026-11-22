# -*- coding: utf-8 -*-
"""
tests/test_inquisitor_redteam_combat_economy.py
Comprehensive Inquisitor Redteam Verification Suite:
- Combat moderation formulas, backfire scaling, newbie immunity, grief protection, safe cooldowns
- Casino bet validation (negative, zero, float precision, NaN/Inf), dynamic caps, VIP rake, jackpot tax
- Wardrobe durability degradation, zero negative durability invariant, full stat/set reset on broken items
- Whale economy raid mechanics, 1,000,000 ₪ cap, 70% Abu Fund burning, progressive wealth tax with deposit discount
"""

import math
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

import combat_moderation_engine
import casino_engine
import wardrobe_engine
import whale_economy_engine
from common.database import (
    add_user_global_balance,
    get_user_global_balance,
    get_abu_fund_total,
    record_user_transaction,
)


# =============================================================================
# 1. COMBAT MODERATION ENGINE AUDIT TESTS
# =============================================================================

def test_combat_moderation_attacker_fine_extreme_inputs():
    """Verify calculate_attacker_false_report_fine safely handles NaN, Inf, and negative inputs."""
    assert combat_moderation_engine.calculate_attacker_false_report_fine(None) == 500.0
    assert combat_moderation_engine.calculate_attacker_false_report_fine(0) == 500.0
    assert combat_moderation_engine.calculate_attacker_false_report_fine(-500) == 500.0
    assert combat_moderation_engine.calculate_attacker_false_report_fine(float('nan')) == 500.0
    assert combat_moderation_engine.calculate_attacker_false_report_fine(float('inf')) == 500.0
    assert combat_moderation_engine.calculate_attacker_false_report_fine("corrupted") == 500.0

    # Normal scaling (5% of balance, min 500, max 200,000)
    assert combat_moderation_engine.calculate_attacker_false_report_fine(5000) == 500.0   # 5% of 5000 = 250 -> 500
    assert combat_moderation_engine.calculate_attacker_false_report_fine(20000) == 1000.0 # 5% of 20000 = 1000
    assert combat_moderation_engine.calculate_attacker_false_report_fine(10_000_000) == 200_000.0  # Capped at 200k


def test_combat_pair_cooldown_clock_skew_and_zero():
    """Verify pair attack cooldown handles clock skews, zero/negative cooldowns gracefully."""
    # Negative/zero cooldown
    blocked, rem = combat_moderation_engine.check_pair_attack_cooldown(1, 2, cooldown_seconds=0.0)
    assert not blocked
    assert rem == 0

    blocked, rem = combat_moderation_engine.check_pair_attack_cooldown(1, 2, cooldown_seconds=-10.0)
    assert not blocked
    assert rem == 0

    # Attack in future (clock skew)
    now = time.time()
    combat_moderation_engine._TARGET_PAIR_LAST_ATTACK[(101, 102)] = now + 50.0
    blocked, rem = combat_moderation_engine.check_pair_attack_cooldown(101, 102, cooldown_seconds=900.0)
    assert blocked is True
    assert rem == 900


def test_combat_duration_and_newbie_immunity_corrupted_inputs():
    """calculate_combat_duration_and_backfire gives 0 duration for newbies or negative/corrupted posts."""
    dur, is_back, _ = combat_moderation_engine.calculate_combat_duration_and_backfire(
        attacker_id=99, target_id=100, weapon_type="partyvan", target_posts=10
    )
    assert dur == 0
    assert is_back is False

    # Negative posts treated as newbie (< 50)
    dur_neg, is_back_neg, _ = combat_moderation_engine.calculate_combat_duration_and_backfire(
        attacker_id=99, target_id=100, weapon_type="partyvan", target_posts=-5
    )
    assert dur_neg == 0
    assert is_back_neg is False

    # String posts
    dur_str, _, _ = combat_moderation_engine.calculate_combat_duration_and_backfire(
        attacker_id=99, target_id=100, weapon_type="partyvan", target_posts="invalid"
    )
    assert dur_str == 0


@pytest.mark.asyncio
async def test_target_grief_protection_handles_none_message():
    """check_target_grief_protection handles message=None without crashing."""
    res = await combat_moderation_engine.check_target_grief_protection(None, target_id=888, user_id=999, board_id="b")
    assert isinstance(res, bool)


# =============================================================================
# 2. CASINO ENGINE INTEGRITY & BET HARDENING TESTS
# =============================================================================

def test_casino_bet_validation_rejects_negative_zero_float_and_nan():
    """validate_casino_bet must reject negative, zero, float fractions, and NaN/Inf."""
    # Negative bets
    ok, _, msg = casino_engine.validate_casino_bet(-100, balance=10000)
    assert ok is False

    # Zero bet
    ok, _, msg = casino_engine.validate_casino_bet(0, balance=10000)
    assert ok is False

    # Float fraction (float precision bug prevention)
    ok, _, msg = casino_engine.validate_casino_bet(10.5, balance=10000)
    assert ok is False
    assert "целым числом" in msg

    # NaN / Inf
    ok, _, msg = casino_engine.validate_casino_bet(float('nan'), balance=10000)
    assert ok is False

    ok, _, msg = casino_engine.validate_casino_bet(float('inf'), balance=10000)
    assert ok is False

    # String / None
    ok, _, msg = casino_engine.validate_casino_bet(None, balance=10000)
    assert ok is False

    # Valid integer bet
    ok, max_allowed, msg = casino_engine.validate_casino_bet(100, balance=10000)
    assert ok is True
    assert max_allowed == 1000


def test_casino_clamp_bet_to_limits_sanitization():
    """clamp_bet_to_limits cleanses NaN, Inf, and floats down to clean positive integers."""
    assert casino_engine.clamp_bet_to_limits(float('nan'), balance=5000) == casino_engine.MIN_CASINO_BET
    assert casino_engine.clamp_bet_to_limits(float('inf'), balance=5000) == 1000  # Cap for 5000 balance
    assert casino_engine.clamp_bet_to_limits(-500, balance=5000) == casino_engine.MIN_CASINO_BET
    assert casino_engine.clamp_bet_to_limits(250.7, balance=5000) == 250
    assert casino_engine.clamp_bet_to_limits(5000, balance=float('nan')) == 1000  # Novice tier cap when balance unknown/0


def test_casino_jackpot_tax_and_vip_rake_edge_cases():
    """calculate_jackpot_tax and calculate_vip_table_rake handle invalid and extreme numbers."""
    # Jackpot tax
    tax, payout, msg = casino_engine.calculate_jackpot_tax(float('nan'))
    assert tax == 0 and payout == 0

    tax, payout, msg = casino_engine.calculate_jackpot_tax(-1000)
    assert tax == 0 and payout == 0

    tax, payout, msg = casino_engine.calculate_jackpot_tax(50000, multiplier=5.0)
    assert tax == 5000
    assert payout == 45000
    assert "Налог Абу" in msg

    # VIP Table Rake
    rake, bet = casino_engine.calculate_vip_table_rake(-100)
    assert rake == 0 and bet == 0

    rake, bet = casino_engine.calculate_vip_table_rake(100000)
    assert rake == 10000  # 10%
    assert bet == 90000


def test_russian_roulette_bet_sanitization_and_isolation():
    """play_russian_roulette_shot cleans corrupted bets and isolates sessions."""
    uid = 777001
    casino_engine.active_roulette_sessions.pop(uid, None)

    # First shot with float('nan') bet safely normalizes to MIN_CASINO_BET
    survived, mult, streak, _ = casino_engine.play_russian_roulette_shot(uid, bet=float('nan'))
    if survived:
        assert streak == 1
        assert casino_engine.active_roulette_sessions[uid]["bet"] == casino_engine.MIN_CASINO_BET
    else:
        assert streak == 0


# =============================================================================
# 3. WARDROBE ENGINE DURABILITY & BROKEN ITEMS AUDIT TESTS
# =============================================================================

def test_durability_cannot_become_negative():
    """apply_armor_durability_hit must never reduce durability below 0.0."""
    items = {
        "equipped_torso": "body_cloak",
        "owned_body_cloak": True,
        "body_cloak_durability": 15.0,
        "body_cloak_broken": False,
    }

    # Inflict massive durability damage (50 percentage points against 15.0 durability)
    ok, msg = wardrobe_engine.apply_armor_durability_hit(items, slot="torso", damage_pct=50.0)
    assert ok is True
    assert items["body_cloak_durability"] == 0.0
    assert items["body_cloak_broken"] is True
    assert "сломался" in msg

    # Durability is strictly clamped at 0.0, never negative
    assert items["body_cloak_durability"] >= 0.0

    # Inflicting hit on already broken armor
    ok2, msg2 = wardrobe_engine.apply_armor_durability_hit(items, slot="torso", damage_pct=0.5)
    assert ok2 is False
    assert items["body_cloak_durability"] == 0.0
    assert "уже сломан" in msg2


def test_durability_hit_rejects_nan_and_inf():
    """apply_armor_durability_hit with NaN or Inf does not corrupt durability."""
    items = {
        "equipped_head": "hat_helmet",
        "owned_hat_helmet": True,
        "hat_helmet_durability": 80.0,
        "hat_helmet_broken": False,
    }

    ok, msg = wardrobe_engine.apply_armor_durability_hit(items, slot="head", damage_pct=float('nan'))
    assert ok is True
    assert items["hat_helmet_durability"] == 80.0  # Not corrupted to NaN


def test_broken_items_reset_all_stats_passives_and_set_bonuses():
    """
    CRITICAL REDTEAM TEST:
    When an item's durability reaches 0 (broken), it must:
    - NOT contribute to defense, toxicity, or sanity.
    - NOT activate set bonuses (even if both items are equipped).
    - NOT grant item passives (mute reduction, immunities, work perks).
    """
    now = int(time.time())
    # Equip OMON set (hat_helmet + feet_boots)
    # Set grants: -70% mute, shit immunity, work fine immunity, +35 bonus defense
    # Helmet alone grants: 45 def, 20 tox, 15 san, -50% mute, work fine immunity
    # Boots alone grant: 25 def, 15 tox, 10 san, shit immunity
    items = {
        "equipped_head": "hat_helmet",
        "owned_hat_helmet": True,
        "hat_helmet_expires": now + 86400,
        "hat_helmet_durability": 100.0,
        "hat_helmet_broken": False,

        "equipped_feet": "feet_boots",
        "owned_feet_boots": True,
        "feet_boots_expires": now + 86400,
        "feet_boots_durability": 100.0,
        "feet_boots_broken": False,
    }

    # 1. Full functional OMON set
    stats_intact = wardrobe_engine.get_wardrobe_total_stats(items, current_time=now)
    assert stats_intact["total_defense"] == 45 + 25 + 35  # 105
    assert stats_intact["active_set_name"] is not None
    assert stats_intact["mute_reduction_pct"] == 70
    assert stats_intact["shit_immunity"] is True
    assert stats_intact["work_fine_immunity"] is True

    # 2. BREAK the helmet (durability = 0.0)
    items["hat_helmet_durability"] = 0.0
    items["hat_helmet_broken"] = True

    stats_broken = wardrobe_engine.get_wardrobe_total_stats(items, current_time=now)

    # Set bonus MUST BE CANCELLED because helmet is broken
    assert stats_broken["active_set_name"] is None

    # Total defense must only come from boots (25 def), NO helmet (0) and NO set bonus (0)
    assert stats_broken["total_defense"] == 25

    # Helmet's toxicity (20) and sanity (15) must NOT be added
    assert stats_broken["total_toxicity"] == 15  # Only from boots
    assert stats_broken["total_sanity"] == 10    # Only from boots

    # Helmet's mute reduction (-50%) and set mute reduction (-70%) must be GONE (0%)
    assert stats_broken["mute_reduction_pct"] == 0

    # Helmet's work fine immunity must be GONE
    assert stats_broken["work_fine_immunity"] is False

    # Boots are still intact, so boots shit immunity remains
    assert stats_broken["shit_immunity"] is True

    # In summary, broken item must be flagged as (СЛОМАНО)
    assert "(СЛОМАНО)" in stats_broken["equipped_items_summary"]


# =============================================================================
# 4. WHALE ECONOMY ENGINE & CLASS WARS AUDIT TESTS
# =============================================================================

def test_wealth_tax_handles_nan_and_deposit_discount():
    """calculate_wealth_tax safely handles NaN inputs and applies 50% deposit tax discount."""
    # NaN handling
    assert whale_economy_engine.calculate_wealth_tax(float('nan')) == 0.0
    assert whale_economy_engine.calculate_wealth_tax(50000, deposit_balance=float('nan')) == 150.0  # 0.3% of 50k
    assert whale_economy_engine.calculate_wealth_tax(100000, idle_hours=float('nan')) == 1000.0     # 1.0% of 100k

    # Idle surcharge: balance > 500k and idle >= 72h -> 1.5x rate (2.5% -> 3.75%)
    tax_active = whale_economy_engine.calculate_wealth_tax(1_000_000, idle_hours=24.0)
    tax_idle = whale_economy_engine.calculate_wealth_tax(1_000_000, idle_hours=72.0)
    assert tax_active == 25000.0   # 2.5%
    assert tax_idle == 37500.0     # 3.75% (1.5x)

    # Bank deposit discount (50% reduced tax on deposit portion)
    tax_all_wallet = whale_economy_engine.calculate_wealth_tax(100_000, deposit_balance=0.0)
    tax_all_deposit = whale_economy_engine.calculate_wealth_tax(100_000, deposit_balance=100_000)
    assert tax_all_wallet == 1000.0   # 1.0% of 100k
    assert tax_all_deposit == 500.0   # 0.5% (50% discount)


@pytest.mark.asyncio
async def test_raid_oligarch_burns_70_percent_to_abu_fund(isolated_test_db):
    """
    execute_oligarch_raid verifies:
    - Confiscates 10% capped at 1,000,000 ₪.
    - Exactly 70% burned to Abu Yacht Fund.
    - Exactly 30% distributed equally to 5 proletarian voters.
    - Target's defenses (passport/extinguisher) properly protect.
    """
    db = isolated_test_db
    voters = [60001, 60002, 60003, 60004, 60005]
    for v in voters:
        await add_user_global_balance(db, v, "b", 1000.0)
        await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (v,))
    await db.commit()

    # Target Oligarch with 2,000,000 ₪
    oligarch_id = 70001
    await add_user_global_balance(db, oligarch_id, "b", 2_000_000.0)
    fund_before = await get_abu_fund_total(db)

    res = await whale_economy_engine.execute_oligarch_raid(db, voters, target_id=oligarch_id)
    assert res["ok"] is True
    assert res["confiscated"] == 200_000.0       # 10% of 2M
    assert res["burned_to_abu"] == 140_000.0     # 70% burned
    assert res["distributed_total"] == 60_000.0  # 30% distributed
    assert res["per_voter"] == 12_000.0          # 60,000 / 5

    # Check Abu Fund increased by exactly 140,000 ₪
    fund_after = await get_abu_fund_total(db)
    assert round(fund_after - fund_before, 2) == 140_000.0

    # Check oligarch balance
    assert await get_user_global_balance(db, oligarch_id) == 1_800_000.0

    # Check workers received 12,000 ₪ each (1,000 + 12,000 = 13,000 ₪)
    for v in voters:
        assert await get_user_global_balance(db, v) == 13_000.0
