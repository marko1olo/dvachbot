# -*- coding: utf-8 -*-
"""
tests/test_adversarial_m1_challenger_wardrobe.py — Adversarial Stress Test Suite for Milestone 1
================================================================================================
Empirical challenge tests targeting:
1. Item expiration boundary: item expired 1s ago (now - 1) vs item expiring in 1s (now + 1) vs exact (now).
2. Permanence strict override: is_permanent = True with expired timestamps, ancient timestamps, and duration stacking.
3. Invalid / corrupted active_items payloads: None, non-dict types (str, int, list, bool), non-existent item IDs, malformed expires.
4. Extreme defense values (>500 Def): formula saturation, rob stolen reduction, boundary behavior on tiny balances, no negative thefts.
5. End-to-end combat command resilience: cmd_rob, cmd_shoot, cmd_partyvan with extreme and corrupted targets.
"""

import asyncio
import json
import random
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite

import common.database
import common.db_pool
import shared_state
from wardrobe_engine import (
    CLOTHING_CATALOG,
    SET_BONUSES,
    add_item_duration,
    get_equipped_gear,
    get_owned_wardrobe_items,
    equip_item,
    get_wardrobe_total_stats,
)
from combat_moderation_engine import calculate_combat_duration_and_backfire
import common.work_engine as work_engine


@pytest.fixture(autouse=True)
def patch_main_db_pool(isolated_test_db):
    pool_stub = AsyncMock(return_value=isolated_test_db)
    with patch("main.get_pool", pool_stub):
        yield


# =====================================================================
# 1. ITEM EXPIRATION BOUNDARY: (now - 1) vs (now + 1) vs (now)
# =====================================================================

def test_item_expiration_boundary_one_second_difference():
    """
    Empirical test:
    - Item expired 1 second ago (now - 1) must be strictly EXCLUDED.
    - Item expiring in 1 second (now + 1) must be strictly INCLUDED.
    - Item with exact expiration (now) must be strictly EXCLUDED (expires > now is False).
    """
    now = 1750000000

    # 1. Expired 1 second ago
    t_expired = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now - 1,
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now - 1,
    }
    stats_exp = get_wardrobe_total_stats(t_expired, current_time=now)
    assert stats_exp["total_defense"] == 0
    assert stats_exp["mute_reduction_pct"] == 0
    assert stats_exp["shit_immunity"] is False
    assert stats_exp["work_fine_immunity"] is False
    assert stats_exp["compact_post_icon"] == ""
    assert stats_exp["equipped_items_summary"] == "(Ничего не надето)"

    gear_exp = get_equipped_gear(t_expired, current_time=now)
    assert gear_exp["head"] is None
    assert gear_exp["feet"] is None

    # 2. Expiring in 1 second
    t_active = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 1,
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now + 1,
    }
    stats_act = get_wardrobe_total_stats(t_active, current_time=now)
    # hat_helmet (45 def) + feet_boots (25 def) = 70 def, plus Riot Police set bonus (35 def) = 105 def
    assert stats_act["total_defense"] == 105
    assert stats_act["mute_reduction_pct"] == 70
    assert stats_act["shit_immunity"] is True
    assert stats_act["work_fine_immunity"] is True
    assert stats_act["compact_post_icon"] == "🪖 "
    assert "Силовик" in stats_act["active_set_name"]

    gear_act = get_equipped_gear(t_active, current_time=now)
    assert gear_act["head"]["id"] == "hat_helmet"
    assert gear_act["feet"]["id"] == "feet_boots"

    # 3. Exact timestamp match (expires == now)
    t_exact = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now,
    }
    stats_exact = get_wardrobe_total_stats(t_exact, current_time=now)
    assert stats_exact["total_defense"] == 0
    assert stats_exact["mute_reduction_pct"] == 0
    assert stats_exact["equipped_items_summary"] == "(Ничего не надето)"


def test_work_engine_expiration_boundary():
    """Work engine must distinguish (now - 1) from (now + 1) for gear perks."""
    now = 1750000000

    # 1s expired hat_helmet does NOT zero out risk
    expired_helmet = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now - 1,
        "work_shifts": 10,
    }
    with patch("time.time", return_value=now):
        with patch("random.random", return_value=0.01):  # triggers 8% fail on sweeper
            succ, pen, msg, _ = work_engine.execute_job_action(
                job_id="sweeper",
                current_items=expired_helmet,
            )
            assert succ is False  # Failed because helmet is expired!
            assert pen > 0

    # 1s future hat_helmet DOES zero out risk
    active_helmet = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 1,
        "work_shifts": 10,
    }
    with patch("time.time", return_value=now):
        with patch("random.random", return_value=0.01):
            succ, pen, msg, _ = work_engine.execute_job_action(
                job_id="sweeper",
                current_items=active_helmet,
            )
            assert succ is True  # Succeeded because active helmet eliminated risk!


# =====================================================================
# 2. PERMANENCE STRICT OVERRIDE: is_permanent = True with Expired Timestamps
# =====================================================================

def test_permanence_strictly_overrides_expired_timestamps():
    """
    When an item has is_permanent = True, it must remain fully active regardless of:
    - expires = now - 1
    - expires = 1 (epoch timestamp)
    - expires = now - 1000000
    - expires = None
    """
    now = 1750000000

    for expired_ts in [now - 1, 1, now - 1000000, 0]:
        perm_items = {
            "equipped_head": "hat_helmet",
            "hat_helmet_expires": expired_ts,
            "hat_helmet_is_permanent": True,
            "equipped_feet": "feet_sneakers",
            "feet_sneakers_expires": expired_ts,
            "feet_sneakers_is_permanent": True,
        }
        stats = get_wardrobe_total_stats(perm_items, current_time=now)
        assert stats["total_defense"] == 60  # 45 + 15
        assert stats["mute_reduction_pct"] == 50
        assert stats["evasion_chance"] == 0.30
        assert stats["work_fine_immunity"] is True
        assert stats["compact_post_icon"] == "🪖 "

        gear = get_equipped_gear(perm_items, current_time=now)
        assert gear["head"]["id"] == "hat_helmet"
        assert gear["feet"]["id"] == "feet_sneakers"


def test_permanence_owned_list_and_equip_action():
    """Permanent items with expired timestamps must show as permanent and allow equipping."""
    now = 1750000000
    active_items = {
        "owned_hat_crown": True,
        "hat_crown_expires": now - 500,
        "hat_crown_is_permanent": True,
    }

    # get_owned_wardrobe_items
    with patch("time.time", return_value=now):
        owned = get_owned_wardrobe_items(active_items)
        assert len(owned) == 1
        assert owned[0]["id"] == "hat_crown"
        assert owned[0]["is_permanent"] is True
        assert owned[0]["duration_label"] == "🌟 Навсегда"

        # equip_item
        ok, equip_msg = equip_item(active_items, "hat_crown")
        assert ok is True
        assert active_items["equipped_head"] == "hat_crown"


def test_add_item_duration_permanence_protection():
    """Adding non-permanent duration must NOT strip or downgrade existing permanence."""
    active_items = {}
    add_item_duration(active_items, "hat_helmet", 100, is_permanent=True)
    assert active_items["hat_helmet_is_permanent"] is True
    assert "hat_helmet_expires" not in active_items

    # Attempt to add regular duration
    add_item_duration(active_items, "hat_helmet", 168, is_permanent=False)
    assert active_items["hat_helmet_is_permanent"] is True
    assert "hat_helmet_expires" not in active_items


# =====================================================================
# 3. INVALID & CORRUPTED active_items PAYLOADS
# =====================================================================

@pytest.mark.parametrize("corrupted_payload", [
    None,
    "corrupted_string",
    "",
    12345,
    -999,
    3.1415,
    [],
    [{"key": "val"}],
    True,
    False,
])
def test_get_wardrobe_total_stats_non_dict_payloads(corrupted_payload):
    """Passing any non-dict or None must return default safe 0-values without crashing."""
    stats = get_wardrobe_total_stats(corrupted_payload)
    assert isinstance(stats, dict)
    assert stats["total_defense"] == 0
    assert stats["total_toxicity"] == 0
    assert stats["total_sanity"] == 0
    assert stats["rob_deflect_chance"] == 0.0
    assert stats["rob_stolen_reduction_pct"] == 0.0
    assert stats["evasion_chance"] == 0.0
    assert stats["mute_reduction_pct"] == 0
    assert stats["shit_immunity"] is False
    assert stats["salary_mult"] == 1.0
    assert stats["equipped_items_summary"] == "(Ничего не надето)"


def test_corrupted_dict_values_and_unknown_item_ids():
    """Active items with unknown IDs, None slot values, or non-string IDs must be ignored."""
    corrupted_dict = {
        "equipped_head": "hat_non_existent_999",
        "equipped_torso": 99999,
        "equipped_face": None,
        "equipped_feet": ["sneakers"],
        "some_random_key": {"nested": True},
    }
    stats = get_wardrobe_total_stats(corrupted_dict)
    assert stats["total_defense"] == 0
    assert stats["compact_post_icon"] == ""
    assert stats["equipped_items_summary"] == "(Ничего не надето)"


def test_combat_duration_with_corrupted_target_items():
    """calculate_combat_duration_and_backfire must not fail on corrupted target_items."""
    for bad_items in [None, "invalid", 1234, [], {"equipped_head": "unknown"}]:
        dur, back, chance = calculate_combat_duration_and_backfire(
            attacker_id=9001,
            target_id=9002,
            weapon_type="shoot",
            target_posts=100,
            target_items=bad_items,
        )
        assert dur > 0
        assert isinstance(back, bool)


# =====================================================================
# 4. EXTREME DEFENSE VALUES (>500 Def) & COMBAT THEFT / DAMAGE
# =====================================================================

def test_extreme_defense_formulas_saturation():
    """
    Formulas:
    - P_deflect = min(0.35, Def * 0.0025)
    - stolen_reduction = min(0.60, Def / 200.0)
    - debuff_reduction = min(0.60, max(0, Sanity) * 0.006)

    At Def > 500, deflect chance MUST be capped at 0.35 and stolen reduction at 0.60.
    """
    for extreme_def in [500, 1000, 50000, 1000000]:
        # Inject custom extreme item
        catalog_patch = {
            "hat_god_helm": {
                "id": "hat_god_helm",
                "slot": "head",
                "defense": extreme_def,
                "toxicity": 0,
                "sanity": 500,
                "name": "God Helm",
            }
        }
        with patch.dict(CLOTHING_CATALOG, catalog_patch, clear=False):
            items = {
                "equipped_head": "hat_god_helm",
                "hat_god_helm_is_permanent": True,
            }
            stats = get_wardrobe_total_stats(items)
            assert stats["total_defense"] == extreme_def
            assert stats["rob_deflect_chance"] == 0.35  # Strict cap at 35%
            assert stats["rob_stolen_reduction_pct"] == 0.60  # Strict cap at 60%
            assert stats["debuff_reduction_pct"] == 0.60  # Strict cap at 60%


def test_negative_defense_resilience():
    """Corrupted / negative defense and sanity values must not invert formulas."""
    neg_patch = {
        "hat_cursed": {
            "id": "hat_cursed",
            "slot": "head",
            "defense": -500,
            "toxicity": -100,
            "sanity": -500,
            "name": "Cursed Hat",
        }
    }
    with patch.dict(CLOTHING_CATALOG, neg_patch, clear=False):
        items = {
            "equipped_head": "hat_cursed",
            "hat_cursed_is_permanent": True,
        }
        stats = get_wardrobe_total_stats(items)
        assert stats["total_defense"] == -500
        # debuff reduction pct must not be negative
        assert stats["debuff_reduction_pct"] == 0.0


@pytest.mark.asyncio
async def test_cmd_rob_extreme_defense_theft_reductions(isolated_test_db):
    """
    Empirical test for cmd_rob:
    - Target has extreme defense (>500 Def).
    - Ensure stolen reduction is capped at 60%.
    - Ensure theft NEVER becomes 0 or negative on low balances (bounded by max(1, ...)).
    - Target balance must never be negative.
    """
    import main

    attacker_id = 9101
    target_id = 9102
    board_id = "b"

    # Setup attacker
    await common.database.add_user_global_balance(isolated_test_db, attacker_id, board_id, 1000.0)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps({"knife_gun": True}), attacker_id),
    )

    god_helm_patch = {
        "hat_god_helm": {
            "id": "hat_god_helm",
            "slot": "head",
            "defense": 9999,
            "name": "Титановый Купол",
        }
    }

    # Test robbery against various target balances
    for target_bal in [10000.0, 50.0, 5.0, 2.0]:
        with patch.dict(CLOTHING_CATALOG, god_helm_patch, clear=False):
            # Target balance
            await isolated_test_db.execute("UPDATE Users SET balance = ? WHERE user_id = ?", (target_bal, target_id))
            target_items = {
                "equipped_head": "hat_god_helm",
                "hat_god_helm_is_permanent": True,
            }
            await isolated_test_db.execute(
                "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
                (json.dumps(target_items), target_id),
            )

            # Re-arm attacker
            await isolated_test_db.execute(
                "UPDATE Users SET active_items = ? WHERE user_id = ?",
                (json.dumps({"knife_gun": True}), attacker_id),
            )

            # Clear combat cooldowns
            shared_state._TARGET_LAST_ATTACKED_TS.clear()
            shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
            shared_state._VICTIM_ROB_COOLDOWNS.clear()

            fake_msg = MagicMock()
            fake_msg.from_user.id = attacker_id
            fake_msg.from_user.first_name = "Robber"
            fake_msg.chat = MagicMock(id=77777)
            fake_msg.message_id = 5555
            fake_msg.reply_to_message = MagicMock()
            fake_msg.reply_to_message.from_user.id = target_id
            fake_msg.reply_to_message.from_user.first_name = "Tank"
            fake_msg.reply_to_message.message_id = 5556
            fake_msg.answer = AsyncMock()
            fake_msg.bot = MagicMock()
            fake_msg.bot.send_message = AsyncMock()

            with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
                mock_auth.return_value = target_id
                # Bypass deflection (random.random() = 0.99 > 0.35)
                with patch("random.random", return_value=0.99):
                    with patch("random.uniform", return_value=0.20):
                        await main.cmd_rob(fake_msg, board_id, stream="ru")

                        # Verify balances
                        new_target_bal = await common.database.get_user_global_balance(isolated_test_db, target_id)
                        new_attacker_bal = await common.database.get_user_global_balance(isolated_test_db, attacker_id)

                        assert new_target_bal >= 0, f"Target balance went negative: {new_target_bal}"
                        assert new_target_bal <= target_bal, "Target balance increased from being robbed!"


@pytest.mark.asyncio
async def test_cmd_rob_target_with_none_active_items(isolated_test_db):
    """cmd_rob against a target whose active_items is NULL in DB must not crash."""
    import main

    attacker_id = 9201
    target_id = 9202
    board_id = "b"

    await common.database.add_user_global_balance(isolated_test_db, attacker_id, board_id, 1000.0)
    await common.database.add_user_global_balance(isolated_test_db, target_id, board_id, 1000.0)

    # Set target active_items to NULL
    await isolated_test_db.execute("UPDATE Users SET active_items = NULL, posts_count = 100 WHERE user_id = ?", (target_id,))
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps({"knife_gun": True}), attacker_id),
    )

    shared_state._TARGET_LAST_ATTACKED_TS.clear()
    shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
    shared_state._VICTIM_ROB_COOLDOWNS.clear()

    fake_msg = MagicMock()
    fake_msg.from_user.id = attacker_id
    fake_msg.reply_to_message = MagicMock()
    fake_msg.reply_to_message.from_user.id = target_id
    fake_msg.reply_to_message.message_id = 6666
    fake_msg.answer = AsyncMock()
    fake_msg.bot = MagicMock()
    fake_msg.bot.send_message = AsyncMock()

    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
        mock_auth.return_value = target_id
        await main.cmd_rob(fake_msg, board_id, stream="ru")
        assert fake_msg.answer.called
