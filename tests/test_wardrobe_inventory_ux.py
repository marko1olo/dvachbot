# -*- coding: utf-8 -*-
"""
test_wardrobe_inventory_ux.py — Unit & Integration Tests for Wardrobe & Inventory UX
Red-Team Inquisitor Subagent 4 Suite.

Validates:
1. Durability Bar Formatting & Edge Cases:
   - 100% full, 75% mid, 20% warning, 0% broken.
2. Slot Formatting & Item Status:
   - Empty slot, intact equipped item, low durability warning, broken item warning.
3. Privacy & Zero User ID Leakage:
   - sanitize_anon_display with int, str, None.
   - Raw user_id is cryptographically replaced with phonetic Anon hash.
4. Wardrobe & Inventory Card Formatting:
   - format_wardrobe_full_card contains anonymous owner, slots, stats summary.
   - format_inventory_wardrobe_section outputs clear stats and warnings.
   - format_wardrobe_stats_summary breaks down defense, toxicity, sanity, perks.
   - format_active_set_bonuses_summary formats active sets and short descriptions.
5. Durability Warnings:
   - get_wardrobe_durability_warnings identifies broken items and items <= 25%.
   - Suggests specific /repair command.
6. Combat & Work Degradation:
   - degrade_equipped_gear_on_combat degrades relevant slots and returns alerts.
   - degrade_equipped_gear_on_work respects work_fine_immunity.
7. Expiration & Enriched Gear:
   - get_owned_wardrobe_items correctly populates expires_in_hours.
   - get_equipped_gear enriches with durability, broken flag, and repair_cost.
"""

import time
import pytest
from unittest.mock import patch

from wardrobe_engine import (
    CLOTHING_CATALOG,
    SET_BONUSES,
    get_equipped_gear,
    get_owned_wardrobe_items,
    get_wardrobe_total_stats,
    apply_armor_durability_hit,
    calculate_item_repair_cost,
    repair_wardrobe_item,
    is_wardrobe_item_broken,
    sanitize_anon_display,
    format_durability_bar,
    format_equipment_slot_line,
    format_wardrobe_stats_summary,
    format_active_set_bonuses_summary,
    get_wardrobe_durability_warnings,
    format_wardrobe_full_card,
    format_inventory_wardrobe_section,
    degrade_equipped_gear_on_combat,
    degrade_equipped_gear_on_work,
)


# =============================================================================
# 1. DURABILITY BAR & SLOT FORMATTING TESTS
# =============================================================================

def test_format_durability_bar():
    """Verify durability bar displays correct progress, emojis, and labels."""
    # 100% durability
    bar_100 = format_durability_bar(100.0, is_broken=False, bar_len=10)
    assert "[██████████] 100.0%" == bar_100

    # 70% durability
    bar_70 = format_durability_bar(70.0, is_broken=False, bar_len=10)
    assert "[███████░░░] 70.0%" == bar_70

    # 20% durability (low wear alert)
    bar_20 = format_durability_bar(20.0, is_broken=False, bar_len=10)
    assert "20.0%" in bar_20
    assert "⚠️ Износ!" in bar_20

    # 0% or broken
    bar_0 = format_durability_bar(0.0, is_broken=False, bar_len=10)
    assert "💔 СЛОМАНО!" in bar_0

    bar_broken = format_durability_bar(50.0, is_broken=True, bar_len=10)
    assert "💔 СЛОМАНО!" in bar_broken


def test_format_equipment_slot_line_intact_and_empty():
    """Verify slot formatting for empty and equipped items."""
    # Empty head slot
    empty_line = format_equipment_slot_line("head", None)
    assert "Голова" in empty_line
    assert "Без убора" in empty_line

    # Intact equipped helmet
    helmet_item = dict(CLOTHING_CATALOG["hat_helmet"])
    helmet_item["durability"] = 100.0
    helmet_item["is_broken"] = False
    helmet_item["duration_label"] = "28д 5ч"

    line = format_equipment_slot_line("head", helmet_item)
    assert "Шлем ОМОНа" in line
    assert "🛡️+45" in line
    assert "100.0%" in line
    assert "28д 5ч" in line


def test_format_equipment_slot_line_broken():
    """Broken items must show broken indicator and repair recommendation."""
    helmet_item = dict(CLOTHING_CATALOG["hat_helmet"])
    helmet_item["durability"] = 0.0
    helmet_item["is_broken"] = True

    line = format_equipment_slot_line("head", helmet_item)
    assert "Шлем ОМОНа" in line
    assert "💔 СЛОМАНО!" in line
    assert "Защита отключена!" in line
    assert "/repair hat_helmet" in line


# =============================================================================
# 2. PRIVACY & ZERO USER ID LEAKAGE TESTS
# =============================================================================

def test_sanitize_anon_display_raw_userid_masked():
    """Raw user_id integers or numeric strings must NEVER leak into public text."""
    secret_uid = 987654321
    anon_name = sanitize_anon_display(secret_uid)

    assert str(secret_uid) not in anon_name
    assert "Анон [" in anon_name
    assert len(anon_name) > 6

    # Test numeric string
    anon_str = sanitize_anon_display("123456789")
    assert "123456789" not in anon_str
    assert "Анон [" in anon_str

    # Test None
    assert sanitize_anon_display(None) == "Анон"


def test_format_wardrobe_card_no_raw_userid_leak():
    """The generated wardrobe card must never contain the raw user ID."""
    secret_uid = 554433221
    now = int(time.time())
    active_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "owned_hat_helmet": True,
        "hat_helmet_durability": 85.0,
    }

    card_text = format_wardrobe_full_card(active_items, user_id=secret_uid, balance=25000.0)

    assert str(secret_uid) not in card_text
    assert "ПРИМЕРОЧНАЯ И ГАРДЕРОБ [Анон [" in card_text
    assert "25,000 ₪" in card_text
    assert "Шлем ОМОНа" in card_text


# =============================================================================
# 3. STATS CLARITY & SET BONUSES TESTS
# =============================================================================

def test_format_wardrobe_stats_summary_clarity():
    """Stats summary must explain what Defense, Toxicity, Sanity and perks do."""
    now = int(time.time())
    # Riot police set: hat_helmet + feet_boots
    active_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now + 3600,
    }

    summary = format_wardrobe_stats_summary(active_items)

    assert "Броня и Защита:" in summary
    assert "Рикошет грабежа:" in summary
    assert "Токсичность:" in summary
    assert "Рассудок:" in summary
    assert "Мут-резист:" in summary
    assert "-70%" in summary
    assert "Иммунитеты:" in summary
    assert "Говно" in summary


def test_format_active_set_bonuses_summary():
    """Set bonuses summary displays active set names and short perks."""
    now = int(time.time())
    active_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now + 3600,
    }

    summary = format_active_set_bonuses_summary(active_items)
    assert "Силовик ОМОНа" in summary
    assert "-70% мут" in summary

    # Empty sets
    empty_summary = format_active_set_bonuses_summary({})
    assert "Нет активных сетов" in empty_summary


# =============================================================================
# 4. DURABILITY WARNINGS & ALERTS TESTS
# =============================================================================

def test_get_wardrobe_durability_warnings():
    """Identifies broken items (dur=0%) and items with critical wear (<=25%)."""
    now = int(time.time())
    active_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "hat_helmet_durability": 15.0,  # Critical wear <= 25%
        "equipped_torso": "body_cloak",
        "body_cloak_expires": now + 3600,
        "body_cloak_durability": 0.0,   # Broken
        "body_cloak_broken": True,
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now + 3600,
        "feet_boots_durability": 90.0,  # Intact
    }

    warnings = get_wardrobe_durability_warnings(active_items)
    assert len(warnings) == 2

    broken_warn = next(w for w in warnings if "Плащ Нео" in w)
    assert "СЛОМАН (0% прочности)!" in broken_warn
    assert "/repair body_cloak" in broken_warn

    crit_warn = next(w for w in warnings if "Шлем ОМОНа" in w)
    assert "на грани поломки (15.0% прочности)!" in crit_warn
    assert "/repair hat_helmet" in crit_warn


def test_format_inventory_wardrobe_section():
    """Inventory section renders all slots and warns if any gear is broken."""
    now = int(time.time())
    active_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "hat_helmet_durability": 80.0,
        "equipped_torso": "body_tracksuit",
        "body_tracksuit_expires": now + 3600,
        "body_tracksuit_durability": 0.0,
        "body_tracksuit_broken": True,
    }

    inv_sec = format_inventory_wardrobe_section(active_items)
    assert "НАДЕТЫЙ ГАРДЕРОБ И СТАТЫ:" in inv_sec
    assert "Шлем ОМОНа" in inv_sec
    assert "Обоссанные треники" in inv_sec
    assert "СЛОМАНО!" in inv_sec
    assert "Почини: /repair" in inv_sec


# =============================================================================
# 5. COMBAT & WORK DEGRADATION TESTS
# =============================================================================

def test_degrade_equipped_gear_on_combat():
    """Combat degradation damages appropriate armor slot and returns alerts."""
    now = int(time.time())
    active_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "hat_helmet_durability": 100.0,
        "equipped_torso": "body_cloak",
        "body_cloak_expires": now + 3600,
        "body_cloak_durability": 10.0,
    }

    # 1. Action 'shoot' targets head first
    hit, alerts = degrade_equipped_gear_on_combat(active_items, action="shoot", damage_pct=0.10)
    assert hit is True
    assert active_items["hat_helmet_durability"] == 90.0

    # 2. Action 'rob' targets torso first (with 10% remaining -> breaks!)
    hit_rob, alerts_rob = degrade_equipped_gear_on_combat(active_items, action="rob", damage_pct=0.15)
    assert hit_rob is True
    assert active_items["body_cloak_durability"] == 0.0
    assert active_items["body_cloak_broken"] is True
    assert len(alerts_rob) == 1
    assert "СЛОМАЛСЯ В БОЮ!" in alerts_rob[0]
    assert "/repair body_cloak" in alerts_rob[0]


def test_degrade_equipped_gear_on_work_immunity():
    """Work degradation does not affect users with work_fine_immunity."""
    now = int(time.time())
    # User with hat_helmet has work_fine_immunity
    active_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "equipped_feet": "feet_slippers",
        "feet_slippers_expires": now + 3600,
        "feet_slippers_durability": 100.0,
    }

    with patch("random.random", return_value=0.0):  # Force trigger
        hit, alerts = degrade_equipped_gear_on_work(active_items, shift_risk=1.0)
    assert hit is False
    assert alerts == []
    assert active_items["feet_slippers_durability"] == 100.0


def test_degrade_equipped_gear_on_work_wear_and_tear():
    """Non-immune users can suffer wear and tear on work shifts."""
    now = int(time.time())
    active_items = {
        "equipped_feet": "feet_slippers",
        "feet_slippers_expires": now + 3600,
        "feet_slippers_durability": 100.0,
    }

    with patch("random.random", return_value=0.0):  # Force trigger
        hit, alerts = degrade_equipped_gear_on_work(active_items, shift_risk=1.0, damage_pct=0.05)
    assert hit is True
    assert active_items["feet_slippers_durability"] == 95.0


# =============================================================================
# 6. ENRICHED GEAR & EXPIRATION TIMER FIX
# =============================================================================

def test_get_owned_wardrobe_items_populates_expires_in_hours():
    """get_owned_wardrobe_items must populate expires_in_hours for non-permanent gear."""
    now = int(time.time())
    active_items = {
        "owned_hat_bag": True,
        "hat_bag_expires": now + (12 * 3600),  # 12 hours remaining
        "hat_bag_durability": 85.0,
        "owned_hat_golden_foil": True,
        "hat_golden_foil_is_permanent": True,
    }

    owned = get_owned_wardrobe_items(active_items)
    bag = next(i for i in owned if i["id"] == "hat_bag")
    assert bag["expires_in_hours"] == 12
    assert bag["durability"] == 85.0
    assert bag["broken"] is False
    assert bag["repair_cost"] > 0

    gold = next(i for i in owned if i["id"] == "hat_golden_foil")
    assert gold["expires_in_hours"] == 0
    assert gold["duration_label"] == "🌟 Навсегда"


def test_get_equipped_gear_enriches_durability_and_status():
    """get_equipped_gear enriches items with live durability, broken status, and repair_cost."""
    now = int(time.time())
    active_items = {
        "equipped_head": "hat_crown",
        "hat_crown_expires": now + 7200,
        "hat_crown_durability": 40.0,
    }

    equipped = get_equipped_gear(active_items, current_time=now)
    crown = equipped["head"]
    assert crown is not None
    assert crown["id"] == "hat_crown"
    assert crown["durability"] == 40.0
    assert crown["broken"] is False
    assert crown["repair_cost"] > 0
    assert "Корона VIP-Сыча" in crown["name"]
