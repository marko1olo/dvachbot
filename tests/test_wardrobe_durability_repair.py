# -*- coding: utf-8 -*-
"""
test_wardrobe_durability_repair.py — Unit & Integration Tests for Wardrobe Durability & Repair System

Validates:
1. rob_deflect scaling with defense:
   - Linear scaling: Def * 0.005
   - Base cap at 0.75 (75%) for high defense without set bonus
   - Elevated cap at 0.85 (85%) when a set bonus is active
   - Mythic floor overrides (hat_golden_foil -> 0.25, body_padishah_mantle -> 0.50)
2. apply_armor_durability_hit:
   - Slot mapping ('body', 'torso', 'head', 'face', 'feet', direct item_id)
   - Degradation tracking in active_items[f"{item_id}_durability"]
   - Armor breaking at 0% durability (f"{item_id}_broken" = True)
   - Stat defense disabled in get_wardrobe_total_stats when armor is broken
   - Already broken armor handling
3. calculate_item_repair_cost:
   - Scaling with base item price and missing durability fraction
   - Durability format resilience (0.80 vs 80.0)
   - Wealthy user repair tax: int(user_balance * 0.002), capped at 10,000 ₪
   - Zero cost for fully intact items
4. repair_wardrobe_item:
   - Durability restored to 100.0%, broken flag reset to False
   - Returns correct calculated cost
   - Rejection when item is fully intact
   - Rejection when item is not owned or not in catalog
"""

import time
import pytest
from unittest.mock import patch

from wardrobe_engine import (
    CLOTHING_CATALOG,
    SET_BONUSES,
    get_wardrobe_total_stats,
    apply_armor_durability_hit,
    calculate_item_repair_cost,
    repair_wardrobe_item,
)


# =============================================================================
# 1. ARMOR DEFLECTION SCALING TESTS
# =============================================================================

def test_rob_deflect_scaling_linear():
    """Verify rob_deflect scales linearly with defense: Def * 0.005."""
    now = int(time.time())

    # Empty stats -> 0.0 deflect
    empty_stats = get_wardrobe_total_stats({}, current_time=now)
    assert empty_stats["rob_deflect_chance"] == 0.0

    # Low defense item: hat_bag (Def=15) -> 15 * 0.005 = 0.075
    stats = get_wardrobe_total_stats({
        "equipped_head": "hat_bag",
        "hat_bag_expires": now + 3600
    }, current_time=now)
    assert stats["total_defense"] == 15
    assert stats["rob_deflect_chance"] == 0.075

    # Mid defense item: hat_helmet (Def=45) -> 45 * 0.005 = 0.225
    stats = get_wardrobe_total_stats({
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600
    }, current_time=now)
    assert stats["total_defense"] == 45
    assert stats["rob_deflect_chance"] == 0.225


def test_rob_deflect_base_cap_75_percent_without_set():
    """High armor users without set bonus are capped at 0.75 (75%)."""
    now = int(time.time())

    # Mock custom extreme single item without set bonus
    mock_catalog = {
        "body_titan_plate": {
            "id": "body_titan_plate",
            "slot": "torso",
            "name": "Титановый Панцирь",
            "price": 10000,
            "defense": 160,  # 160 * 0.005 = 0.80 -> must be capped at 0.75
            "toxicity": 0,
            "sanity": 50,
        },
        "body_god_armor": {
            "id": "body_god_armor",
            "slot": "torso",
            "name": "Броня Богов",
            "price": 50000,
            "defense": 300,  # 300 * 0.005 = 1.50 -> must be capped at 0.75
            "toxicity": 0,
            "sanity": 100,
        }
    }

    with patch.dict(CLOTHING_CATALOG, mock_catalog, clear=False):
        # Def = 150 -> exactly 0.75
        items_150 = {
            "equipped_torso": "body_cyber_suit",  # 70 def
            "body_cyber_suit_expires": now + 3600,
            "equipped_head": "hat_golden_crown",  # 40 def
            "hat_golden_crown_expires": now + 3600,
            "equipped_feet": "feet_golden_sneakers",  # 30 def
            "feet_golden_sneakers_expires": now + 3600,
            "equipped_face": "face_thug_glasses",  # 5 def
            "face_thug_glasses_expires": now + 3600,
        }
        # Total defense: 70 + 40 + 30 + 5 = 145 -> 145 * 0.005 = 0.725
        stats_145 = get_wardrobe_total_stats(items_150, current_time=now)
        assert stats_145["total_defense"] == 145
        assert stats_145["rob_deflect_chance"] == 0.725

        # Def = 160 -> capped at 0.75
        items_160 = {
            "equipped_torso": "body_titan_plate",
            "body_titan_plate_expires": now + 3600,
        }
        stats_160 = get_wardrobe_total_stats(items_160, current_time=now)
        assert stats_160["total_defense"] == 160
        assert stats_160["rob_deflect_chance"] == 0.75

        # Def = 300 -> capped at 0.75
        items_300 = {
            "equipped_torso": "body_god_armor",
            "body_god_armor_expires": now + 3600,
        }
        stats_300 = get_wardrobe_total_stats(items_300, current_time=now)
        assert stats_300["total_defense"] == 300
        assert stats_300["rob_deflect_chance"] == 0.75


def test_rob_deflect_elevated_cap_85_percent_with_active_set():
    """When a set bonus is active, deflect cap is elevated to 0.85 (85%)."""
    now = int(time.time())

    # Set Neo: body_cloak (30 def) + face_anon_mask (20 def) + set bonus (50 def) = 100 def
    neo_items = {
        "equipped_torso": "body_cloak",
        "body_cloak_expires": now + 3600,
        "equipped_face": "face_anon_mask",
        "face_anon_mask_expires": now + 3600,
    }
    stats_neo = get_wardrobe_total_stats(neo_items, current_time=now)
    assert stats_neo["total_defense"] == 30 + 20 + 50  # 100 def
    assert stats_neo["rob_deflect_chance"] == 0.50  # 100 * 0.005 = 0.50

    # Add head and feet to reach high defense while maintaining set bonus
    mock_catalog = {
        "hat_super_helm": {
            "id": "hat_super_helm",
            "slot": "head",
            "name": "Супер Шлем",
            "price": 5000,
            "defense": 80,
            "toxicity": 0,
            "sanity": 20,
        }
    }
    with patch.dict(CLOTHING_CATALOG, mock_catalog, clear=False):
        # Neo set (100) + super helm (80) = 180 total defense
        # 180 * 0.005 = 0.90 -> with active set bonus, capped at 0.85!
        neo_high_def = dict(neo_items)
        neo_high_def["equipped_head"] = "hat_super_helm"
        neo_high_def["hat_super_helm_expires"] = now + 3600

        stats_high = get_wardrobe_total_stats(neo_high_def, current_time=now)
        assert stats_high["total_defense"] == 180
        assert stats_high["rob_deflect_chance"] == 0.85  # Elevated set cap at 85%

        # Def = 170 -> 170 * 0.005 = 0.85
        # Set Riot Police: hat_helmet (45 def) + feet_boots (25 def) + set bonus (35 def) = 105 def
        # Plus body_cyber_suit (70 def) = 175 total defense -> capped at 0.85
        riot_items = {
            "equipped_head": "hat_helmet",
            "hat_helmet_expires": now + 3600,
            "equipped_feet": "feet_boots",
            "feet_boots_expires": now + 3600,
            "equipped_torso": "body_cyber_suit",
            "body_cyber_suit_expires": now + 3600,
        }
        stats_riot = get_wardrobe_total_stats(riot_items, current_time=now)
        assert stats_riot["total_defense"] == 45 + 25 + 35 + 70  # 175
        assert stats_riot["rob_deflect_chance"] == 0.85


def test_rob_deflect_mythic_floors():
    """hat_golden_foil guarantees >= 0.25 and body_padishah_mantle guarantees >= 0.50."""
    now = int(time.time())

    # hat_golden_foil has 50 def -> 50 * 0.005 = 0.25 (floor matches)
    foil_stats = get_wardrobe_total_stats({
        "equipped_head": "hat_golden_foil",
        "hat_golden_foil_is_permanent": True
    }, current_time=now)
    assert foil_stats["rob_deflect_chance"] >= 0.25

    # body_padishah_mantle (Def=45) -> 45 * 0.005 = 0.225 -> elevated by padishah perk to 0.50
    pad_stats = get_wardrobe_total_stats({
        "equipped_torso": "body_padishah_mantle",
        "body_padishah_mantle_expires": now + 3600
    }, current_time=now)
    assert pad_stats["rob_deflect_chance"] == 0.50


# =============================================================================
# 2. APPLY_ARMOR_DURABILITY_HIT TESTS
# =============================================================================

def test_apply_armor_durability_hit_basic_degradation():
    """Durability starts at 100% and degrades with each hit."""
    items = {
        "equipped_torso": "body_cloak",
        "owned_body_cloak": True,
    }

    # 1. 10% hit
    ok, msg = apply_armor_durability_hit(items, slot="body", damage_pct=0.10)
    assert ok is True
    assert items["body_cloak_durability"] == 90.0
    assert items["body_cloak_broken"] is False
    assert "90.0%" in msg

    # 2. 25% hit
    ok, msg = apply_armor_durability_hit(items, slot="torso", damage_pct=0.25)
    assert ok is True
    assert items["body_cloak_durability"] == 65.0
    assert items["body_cloak_broken"] is False

    # 3. Direct percentage value (e.g. 15.0)
    ok, msg = apply_armor_durability_hit(items, slot="body", damage_pct=15.0)
    assert ok is True
    assert items["body_cloak_durability"] == 50.0


def test_apply_armor_durability_hit_breaking_armor():
    """When durability reaches 0, armor breaks and defense is disabled."""
    now = int(time.time())
    items = {
        "equipped_torso": "body_cloak",
        "body_cloak_expires": now + 3600,
        "body_cloak_durability": 15.0,
    }

    # Verify initial stats before breaking: body_cloak provides 30 defense
    stats_before = get_wardrobe_total_stats(items, current_time=now)
    assert stats_before["total_defense"] == 30

    # Apply 20% damage (exceeding 15% remaining)
    ok, msg = apply_armor_durability_hit(items, slot="body", damage_pct=0.20)
    assert ok is True
    assert items["body_cloak_durability"] == 0.0
    assert items["body_cloak_broken"] is True
    assert "сломался" in msg

    # Verify stat defense is now DISABLED in get_wardrobe_total_stats
    stats_broken = get_wardrobe_total_stats(items, current_time=now)
    assert stats_broken["total_defense"] == 0  # Defense disabled!
    assert stats_broken["rob_deflect_chance"] == 0.0

    # Additional hits on already broken armor must return ok=False
    ok_again, msg_again = apply_armor_durability_hit(items, slot="body", damage_pct=0.10)
    assert ok_again is False
    assert "уже сломан" in msg_again


def test_apply_armor_durability_hit_slot_and_error_handling():
    """Validates slot resolution and graceful invalid input rejection."""
    # Non-dict active_items
    ok, msg = apply_armor_durability_hit(None, slot="body")
    assert ok is False
    assert "Неверный формат" in msg

    # Empty slot
    items = {"equipped_torso": "body_cloak"}
    ok, msg = apply_armor_durability_hit(items, slot="head")
    assert ok is False
    assert "нет экипированного предмета" in msg

    # Zero damage
    ok, msg = apply_armor_durability_hit(items, slot="body", damage_pct=0.0)
    assert ok is True
    assert "не нанесен" in msg

    # Head slot degradation
    items["equipped_head"] = "hat_helmet"
    ok, msg = apply_armor_durability_hit(items, slot="head", damage_pct=0.30)
    assert ok is True
    assert items["hat_helmet_durability"] == 70.0


# =============================================================================
# 3. CALCULATE_ITEM_REPAIR_COST TESTS
# =============================================================================

def test_calculate_item_repair_cost_proportional():
    """Repair cost scales with base price and missing durability fraction."""
    # body_cloak price = 550 ₪
    # Fully intact (100% or 1.0) -> cost 0
    assert calculate_item_repair_cost("body_cloak", 100.0, 0.0) == 0
    assert calculate_item_repair_cost("body_cloak", 1.0, 0.0) == 0

    # 50% damaged (cur=50.0 or 0.5) -> 550 * 0.50 = 275 ₪
    assert calculate_item_repair_cost("body_cloak", 50.0, 0.0) == 275
    assert calculate_item_repair_cost("body_cloak", 0.5, 0.0) == 275

    # Completely broken (0.0) -> 550 * 1.0 = 550 ₪
    assert calculate_item_repair_cost("body_cloak", 0.0, 0.0) == 550

    # 10% damaged (cur=90.0) -> 550 * 0.10 = 55 ₪
    assert calculate_item_repair_cost("body_cloak", 90.0, 0.0) == 55


def test_calculate_item_repair_cost_wealthy_user_tax():
    """Wealthy users pay a maintenance tax: int(user_balance * 0.002), capped at 10,000 ₪."""
    # body_cloak at 50% durability: base repair = 275 ₪

    # User with 50,000 ₪ balance: tax = 50,000 * 0.002 = 100 ₪ -> total = 375 ₪
    cost_50k = calculate_item_repair_cost("body_cloak", 50.0, 50000.0)
    assert cost_50k == 275 + 100

    # User with 1,000,000 ₪ balance: tax = 1,000,000 * 0.002 = 2,000 ₪ -> total = 2,275 ₪
    cost_1m = calculate_item_repair_cost("body_cloak", 50.0, 1000000.0)
    assert cost_1m == 275 + 2000

    # Multi-millionaire oligarch with 15,000,000 ₪ balance:
    # 15M * 0.002 = 30,000 ₪ -> capped at 10,000 ₪!
    cost_15m = calculate_item_repair_cost("body_cloak", 50.0, 15000000.0)
    assert cost_15m == 275 + 10000  # Exactly 10,275 ₪

    # Intact item pays zero tax even with high balance
    assert calculate_item_repair_cost("body_cloak", 100.0, 15000000.0) == 0


# =============================================================================
# 4. REPAIR_WARDROBE_ITEM TESTS
# =============================================================================

def test_repair_wardrobe_item_flow():
    """Fully restores broken and damaged items to 100% durability and clears broken flag."""
    now = int(time.time())
    items = {
        "equipped_torso": "body_cloak",
        "owned_body_cloak": True,
        "body_cloak_expires": now + 3600,
        "body_cloak_durability": 30.0,
        "body_cloak_broken": False,
    }

    # Repair damaged item
    ok, msg, cost = repair_wardrobe_item(items, "body_cloak", user_balance=10000.0)
    assert ok is True
    assert items["body_cloak_durability"] == 100.0
    assert items["body_cloak_broken"] is False
    # Base: 550 * 0.70 = 385, Tax: 10,000 * 0.002 = 20 -> Total 405
    assert cost == 405
    assert "успешно отремонтирован" in msg

    # Second repair call immediately after must be rejected (already 100%)
    ok_repeat, msg_repeat, cost_repeat = repair_wardrobe_item(items, "body_cloak", user_balance=10000.0)
    assert ok_repeat is False
    assert cost_repeat == 0
    assert "не требует ремонта" in msg_repeat


def test_repair_broken_item_restores_stats():
    """Repairing a broken item restores its defense stat in get_wardrobe_total_stats."""
    now = int(time.time())
    items = {
        "equipped_head": "hat_helmet",  # 45 defense
        "owned_hat_helmet": True,
        "hat_helmet_expires": now + 3600,
        "hat_helmet_durability": 0.0,
        "hat_helmet_broken": True,
    }

    # Verify stat is disabled while broken
    assert get_wardrobe_total_stats(items, current_time=now)["total_defense"] == 0

    # Perform repair
    ok, msg, cost = repair_wardrobe_item(items, "hat_helmet", user_balance=0.0)
    assert ok is True
    assert items["hat_helmet_durability"] == 100.0
    assert items["hat_helmet_broken"] is False
    assert cost == 600  # hat_helmet price is 600, 100% missing -> 600 ₪

    # Verify stat defense is now fully restored
    assert get_wardrobe_total_stats(items, current_time=now)["total_defense"] == 45


def test_repair_wardrobe_item_rejections():
    """Rejects unowned items, invalid items, and invalid active_items payloads."""
    # Invalid dict payload
    ok, msg, cost = repair_wardrobe_item("not_a_dict", "body_cloak")
    assert ok is False
    assert cost == 0

    # Item not in catalog
    ok, msg, cost = repair_wardrobe_item({}, "unknown_item_xyz")
    assert ok is False
    assert cost == 0
    assert "не найден" in msg

    # Unowned item
    ok, msg, cost = repair_wardrobe_item({}, "body_cloak")
    assert ok is False
    assert cost == 0
    assert "нет предмета" in msg


# =============================================================================
# 5. INTEGRATION TESTS: COMBAT DURABILITY WEAR & /repair SYSTEM
# =============================================================================

import json
from unittest.mock import AsyncMock, MagicMock
import shared_state
import common.database
import main


@pytest.mark.asyncio
async def test_cmd_rob_armor_deflect_durability_hit(isolated_test_db):
    """Verify victim armor takes 8% durability wear and t_items is persisted when rob deflects."""
    db = isolated_test_db
    robber_id = 92001
    victim_id = 92002
    board_id = "b"
    now = int(time.time())

    await common.database.add_user_global_balance(db, robber_id, board_id, 1000.0)
    await common.database.add_user_global_balance(db, victim_id, board_id, 50000.0)
    await db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps({"knife_gun": True}), robber_id),
    )
    victim_items = {
        "equipped_torso": "body_cloak",
        "owned_body_cloak": True,
        "body_cloak_expires": now + 3600,
        "body_cloak_durability": 100.0,
    }
    await db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps(victim_items), victim_id),
    )
    await db.commit()

    shared_state._TARGET_LAST_ATTACKED_TS.clear()
    shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
    shared_state._VICTIM_ROB_COOLDOWNS.clear()

    fake_msg = MagicMock()
    fake_msg.from_user.id = robber_id
    fake_msg.from_user.first_name = "Thief"
    fake_msg.chat = MagicMock(id=88888)
    fake_msg.message_id = 3001
    fake_msg.reply_to_message = MagicMock()
    fake_msg.reply_to_message.from_user.id = victim_id
    fake_msg.reply_to_message.from_user.first_name = "Victim"
    fake_msg.reply_to_message.message_id = 3000
    fake_msg.answer = AsyncMock()
    fake_msg.bot = MagicMock()
    fake_msg.bot.send_message = AsyncMock()

    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth, \
         patch("random.uniform", return_value=0.20), \
         patch("random.random", return_value=0.001):
        mock_auth.return_value = victim_id
        await main.cmd_rob(fake_msg, board_id, stream="ru")

        assert fake_msg.answer.called
        call_text = fake_msg.answer.call_args[0][0]
        assert "РИКОШЕТ О БРОНЮ" in call_text

        robber_items_db = await main._get_user_active_items(db, robber_id, board_id)
        assert robber_items_db.get("knife_gun") is False

        victim_items_db = await main._get_user_active_items(db, victim_id, board_id)
        assert victim_items_db.get("body_cloak_durability") == 92.0


@pytest.mark.asyncio
async def test_cmd_rob_armor_deflect_fallback_slot(isolated_test_db):
    """If victim has no torso armor but has head armor, head armor takes the 8% wear."""
    db = isolated_test_db
    robber_id = 92003
    victim_id = 92004
    board_id = "b"
    now = int(time.time())

    await common.database.add_user_global_balance(db, robber_id, board_id, 1000.0)
    await common.database.add_user_global_balance(db, victim_id, board_id, 50000.0)
    await db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps({"knife_gun": True}), robber_id),
    )
    victim_items = {
        "equipped_head": "hat_helmet",
        "owned_hat_helmet": True,
        "hat_helmet_expires": now + 3600,
        "hat_helmet_durability": 100.0,
    }
    await db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps(victim_items), victim_id),
    )
    await db.commit()

    shared_state._TARGET_LAST_ATTACKED_TS.clear()
    shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
    shared_state._VICTIM_ROB_COOLDOWNS.clear()

    fake_msg = MagicMock()
    fake_msg.from_user.id = robber_id
    fake_msg.from_user.first_name = "Thief2"
    fake_msg.chat = MagicMock(id=88889)
    fake_msg.message_id = 3003
    fake_msg.reply_to_message = MagicMock()
    fake_msg.reply_to_message.from_user.id = victim_id
    fake_msg.reply_to_message.from_user.first_name = "Victim2"
    fake_msg.reply_to_message.message_id = 3002
    fake_msg.answer = AsyncMock()
    fake_msg.bot = MagicMock()
    fake_msg.bot.send_message = AsyncMock()

    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth, \
         patch("random.uniform", return_value=0.20), \
         patch("random.random", return_value=0.001):
        mock_auth.return_value = victim_id
        await main.cmd_rob(fake_msg, board_id, stream="ru")

        victim_items_db = await main._get_user_active_items(db, victim_id, board_id)
        assert victim_items_db.get("hat_helmet_durability") == 92.0


@pytest.mark.asyncio
async def test_cmd_repair_no_args_listing(isolated_test_db):
    """When /repair is called with no args, lists damaged items with repair costs and inline button."""
    db = isolated_test_db
    user_id = 93001
    board_id = "b"
    now = int(time.time())

    await common.database.add_user_global_balance(db, user_id, board_id, 10000.0)

    # 1. Fully intact items -> all items in ideal condition
    intact_items = {
        "equipped_torso": "body_cloak",
        "owned_body_cloak": True,
        "body_cloak_expires": now + 3600,
        "body_cloak_durability": 100.0,
    }
    await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(intact_items), user_id))
    await db.commit()

    fake_msg = MagicMock()
    fake_msg.from_user.id = user_id
    fake_msg.text = "/repair"
    fake_msg.answer = AsyncMock()

    await main.cmd_repair(fake_msg, board_id)
    assert fake_msg.answer.called
    res_text = fake_msg.answer.call_args[0][0]
    assert "Все твои предметы в идеальном состоянии" in res_text

    # 2. Damaged items -> lists them with % and button
    fake_msg.answer.reset_mock()
    damaged_items = dict(intact_items)
    damaged_items["body_cloak_durability"] = 50.0
    damaged_items["equipped_head"] = "hat_helmet"
    damaged_items["owned_hat_helmet"] = True
    damaged_items["hat_helmet_expires"] = now + 3600
    damaged_items["hat_helmet_durability"] = 70.0
    await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(damaged_items), user_id))
    await db.commit()

    await main.cmd_repair(fake_msg, board_id)
    assert fake_msg.answer.called
    res_text = fake_msg.answer.call_args[0][0]
    kwargs = fake_msg.answer.call_args[1]
    assert "МАСТЕРСКАЯ ПОЧИНКИ" in res_text
    assert "50.0%" in res_text
    assert "70.0%" in res_text
    assert "Починить всё" in kwargs["reply_markup"].inline_keyboard[0][0].text
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "repair_all_items"


@pytest.mark.asyncio
async def test_cmd_repair_single_item(isolated_test_db):
    """Repair single item by id: deducts cost, sends to Abu fund, resets durability to 100%."""
    db = isolated_test_db
    user_id = 93002
    board_id = "b"
    now = int(time.time())

    initial_balance = 50000.0
    await common.database.add_user_global_balance(db, user_id, board_id, initial_balance)
    abu_before = await common.database.get_abu_fund_total(db)

    items = {
        "equipped_torso": "body_cloak",
        "owned_body_cloak": True,
        "body_cloak_expires": now + 3600,
        "body_cloak_durability": 50.0,
    }
    await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(items), user_id))
    await db.commit()

    fake_msg = MagicMock()
    fake_msg.from_user.id = user_id
    fake_msg.text = "/repair body_cloak"
    fake_msg.answer = AsyncMock()

    await main.cmd_repair(fake_msg, board_id)
    assert fake_msg.answer.called
    assert "РЕМОНТ ВЫПОЛНЕН" in fake_msg.answer.call_args[0][0]

    updated_items = await main._get_user_active_items(db, user_id, board_id)
    assert updated_items["body_cloak_durability"] == 100.0
    assert updated_items.get("body_cloak_broken") is False

    new_bal = await common.database.get_user_global_balance(db, user_id)
    assert new_bal == initial_balance - 375.0

    abu_after = await common.database.get_abu_fund_total(db)
    assert abu_after == abu_before + 375.0

    # Repeat repair is rejected as item is already 100%
    fake_msg.answer.reset_mock()
    await main.cmd_repair(fake_msg, board_id)
    assert "не требует ремонта" in fake_msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_repair_all_command(isolated_test_db):
    """Repair all damaged items via `/repair all`."""
    db = isolated_test_db
    user_id = 93003
    board_id = "b"
    now = int(time.time())

    await common.database.add_user_global_balance(db, user_id, board_id, 10000.0)

    items = {
        "equipped_torso": "body_cloak",
        "owned_body_cloak": True,
        "body_cloak_expires": now + 3600,
        "body_cloak_durability": 60.0,
        "equipped_head": "hat_helmet",
        "owned_hat_helmet": True,
        "hat_helmet_expires": now + 3600,
        "hat_helmet_durability": 50.0,
    }
    await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(items), user_id))
    await db.commit()

    fake_msg = MagicMock()
    fake_msg.from_user.id = user_id
    fake_msg.text = "/repair all"
    fake_msg.answer = AsyncMock()

    await main.cmd_repair(fake_msg, board_id)
    assert fake_msg.answer.called
    assert "ПОЛНЫЙ РЕМОНТ ЗАВЕРШЕН" in fake_msg.answer.call_args[0][0]

    updated_items = await main._get_user_active_items(db, user_id, board_id)
    assert updated_items["body_cloak_durability"] == 100.0
    assert updated_items["hat_helmet_durability"] == 100.0


@pytest.mark.asyncio
async def test_callback_repair_all(isolated_test_db):
    """Callback `repair_all_items` repairs all damaged gear, deducts funds and edits message."""
    db = isolated_test_db
    user_id = 93004
    board_id = "b"
    now = int(time.time())

    await common.database.add_user_global_balance(db, user_id, board_id, 20000.0)

    items = {
        "equipped_torso": "body_cloak",
        "owned_body_cloak": True,
        "body_cloak_expires": now + 3600,
        "body_cloak_durability": 20.0,
        "body_cloak_broken": False,
    }
    await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(items), user_id))
    await db.commit()

    fake_cb = MagicMock()
    fake_cb.from_user.id = user_id
    fake_cb.data = "repair_all_items"
    fake_cb.message = MagicMock()
    fake_cb.message.edit_text = AsyncMock()
    fake_cb.answer = AsyncMock()

    await main.callback_repair_all(fake_cb, board_id)

    assert fake_cb.message.edit_text.called
    assert "ПОЛНЫЙ РЕМОНТ ЗАВЕРШЕН" in fake_cb.message.edit_text.call_args[0][0]

    updated_items = await main._get_user_active_items(db, user_id, board_id)
    assert updated_items["body_cloak_durability"] == 100.0


@pytest.mark.asyncio
async def test_repair_insufficient_balance(isolated_test_db):
    """If balance is insufficient, command and callback reject without modifying items."""
    db = isolated_test_db
    user_id = 93005
    board_id = "b"
    now = int(time.time())

    await common.database.add_user_global_balance(db, user_id, board_id, 10.0)

    items = {
        "equipped_torso": "body_cloak",
        "owned_body_cloak": True,
        "body_cloak_expires": now + 3600,
        "body_cloak_durability": 20.0,
    }
    await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ?", (json.dumps(items), user_id))
    await db.commit()

    fake_msg = MagicMock()
    fake_msg.from_user.id = user_id
    fake_msg.text = "/repair body_cloak"
    fake_msg.answer = AsyncMock()

    await main.cmd_repair(fake_msg, board_id)
    assert "Недостаточно шекелей" in fake_msg.answer.call_args[0][0]

    fake_cb = MagicMock()
    fake_cb.from_user.id = user_id
    fake_cb.data = "repair_all_items"
    fake_cb.answer = AsyncMock()

    await main.callback_repair_all(fake_cb, board_id)
    assert fake_cb.answer.called
    assert "Недостаточно шекелей" in fake_cb.answer.call_args[0][0]

    check_items = await main._get_user_active_items(db, user_id, board_id)
    assert check_items["body_cloak_durability"] == 20.0

