import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import common.database
import common.db_pool
from wardrobe_engine import (
    get_wardrobe_total_stats,
)
from combat_moderation_engine import calculate_combat_duration_and_backfire
import common.work_engine as work_engine
import post_helpers
import stats_generator


@pytest.fixture(autouse=True)
def patch_main_db_pool(isolated_test_db):
    pool_stub = AsyncMock(return_value=isolated_test_db)
    with patch("main.get_pool", pool_stub):
        yield


# =====================================================================
# 1. WARDROBE ENGINE: STATS, TTL, EXPIRATION & SET BONUSES
# =====================================================================

def test_wardrobe_total_stats_defaults():
    """Empty or None active_items should return safe zeroed/default stats."""
    empty_stats = get_wardrobe_total_stats({})
    assert empty_stats["total_defense"] == 0
    assert empty_stats["total_toxicity"] == 0
    assert empty_stats["total_sanity"] == 0
    assert empty_stats["rob_deflect_chance"] == 0.0
    assert empty_stats["rob_stolen_reduction_pct"] == 0.0
    assert empty_stats["rob_fear_chance"] == 0.0
    assert empty_stats["evasion_chance"] == 0.0
    assert empty_stats["mute_reduction_pct"] == 0
    assert empty_stats["debuff_reduction_pct"] == 0.0
    assert empty_stats["shit_immunity"] is False
    assert empty_stats["laxative_immunity"] is False
    assert empty_stats["schizo_immunity"] is False
    assert empty_stats["work_fine_immunity"] is False
    assert empty_stats["salary_mult"] == 1.0
    assert empty_stats["tips_mult"] == 1.0
    assert empty_stats["cooldown_mult"] == 1.0
    assert empty_stats["lootbox_flat_chance"] == 0.0
    assert empty_stats["lootbox_drop_mult"] == 1.0
    assert empty_stats["casino_bonus_pct"] == 0
    assert empty_stats["compact_post_icon"] == ""
    assert empty_stats["stealth_profile"] is False
    assert empty_stats["active_set_name"] is None
    assert empty_stats["equipped_items_summary"] == "(Ничего не надето)"

    none_stats = get_wardrobe_total_stats(None)
    assert none_stats["total_defense"] == 0
    assert none_stats["salary_mult"] == 1.0


def test_wardrobe_total_stats_ttl_expiration():
    """Expired items must NOT provide stats or perks, while permanent items always do."""
    now = int(time.time())

    # Item expired 100s ago
    expired_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now - 100,
        "equipped_torso": "body_cloak",
        "body_cloak_expires": now - 100,
    }
    stats = get_wardrobe_total_stats(expired_items, current_time=now)
    assert stats["total_defense"] == 0
    assert stats["mute_reduction_pct"] == 0
    assert stats["work_fine_immunity"] is False
    assert stats["equipped_items_summary"] == "(Ничего не надето)"

    # Item active for 1000s
    active_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 1000,
    }
    stats_act = get_wardrobe_total_stats(active_items, current_time=now)
    assert stats_act["total_defense"] == 45
    assert stats_act["mute_reduction_pct"] == 50
    assert stats_act["work_fine_immunity"] is True
    assert stats_act["compact_post_icon"] == "🪖 "

    # Permanent item with expired timestamp should still be valid
    perm_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now - 100,
        "hat_helmet_is_permanent": True,
    }
    stats_perm = get_wardrobe_total_stats(perm_items, current_time=now)
    assert stats_perm["total_defense"] == 45
    assert stats_perm["mute_reduction_pct"] == 50


def test_wardrobe_set_bonuses_calculation():
    """Test set bonus detection and stat aggregation for all 6 major sets."""
    now = int(time.time())

    # 1. Set Riot Police (hat_helmet + feet_boots)
    riot_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now + 3600,
    }
    riot_stats = get_wardrobe_total_stats(riot_items, current_time=now)
    assert riot_stats["total_defense"] == 105
    assert riot_stats["total_toxicity"] == 35
    assert riot_stats["total_sanity"] == 25
    assert riot_stats["mute_reduction_pct"] == 70
    assert riot_stats["shit_immunity"] is True
    assert riot_stats["work_fine_immunity"] is True
    assert riot_stats["compact_post_icon"] == "🪖 "
    assert "Силовик" in riot_stats["active_set_name"]

    # 2. Set Wasserman (body_wasserman + face_wasserman_glasses)
    wass_items = {
        "equipped_torso": "body_wasserman",
        "body_wasserman_expires": now + 3600,
        "equipped_face": "face_wasserman_glasses",
        "face_wasserman_glasses_expires": now + 3600,
    }
    wass_stats = get_wardrobe_total_stats(wass_items, current_time=now)
    assert wass_stats["total_defense"] == 55
    assert wass_stats["total_toxicity"] == 5
    assert wass_stats["total_sanity"] == 95
    assert wass_stats["salary_mult"] == 1.40
    assert wass_stats["schizo_immunity"] is True
    assert wass_stats["compact_post_icon"] == "🦺 "
    assert "Вассерман" in wass_stats["active_set_name"]

    # 3. Set Gop-Skuf (hat_crown + body_tracksuit)
    gop_items = {
        "equipped_head": "hat_crown",
        "hat_crown_expires": now + 3600,
        "equipped_torso": "body_tracksuit",
        "body_tracksuit_expires": now + 3600,
    }
    gop_stats = get_wardrobe_total_stats(gop_items, current_time=now)
    assert gop_stats["total_defense"] == 20
    assert gop_stats["total_toxicity"] == 70
    assert gop_stats["total_sanity"] == 0
    assert gop_stats["rob_fear_chance"] == 0.40
    assert gop_stats["tips_mult"] == 1.35
    assert gop_stats["compact_post_icon"] == "👑 "
    assert "Сыч" in gop_stats["active_set_name"]

    # 4. Set Ward 6 (body_straitjacket + hat_tinfoil)
    w6_items = {
        "equipped_torso": "body_straitjacket",
        "body_straitjacket_expires": now + 3600,
        "equipped_head": "hat_tinfoil",
        "hat_tinfoil_expires": now + 3600,
    }
    w6_stats = get_wardrobe_total_stats(w6_items, current_time=now)
    assert w6_stats["total_defense"] == 55
    assert w6_stats["total_toxicity"] == 80
    assert w6_stats["total_sanity"] == -5
    assert w6_stats["laxative_immunity"] is True
    assert w6_stats["schizo_immunity"] is True
    assert w6_stats["compact_post_icon"] == "🥼 "
    assert "Палата №6" in w6_stats["active_set_name"]

    # 5. Set Neo (body_cloak + face_anon_mask)
    neo_items = {
        "equipped_torso": "body_cloak",
        "body_cloak_expires": now + 3600,
        "equipped_face": "face_anon_mask",
        "face_anon_mask_expires": now + 3600,
    }
    neo_stats = get_wardrobe_total_stats(neo_items, current_time=now)
    assert neo_stats["total_defense"] == 100
    assert neo_stats["total_toxicity"] == 25
    assert neo_stats["total_sanity"] == 60
    assert neo_stats["salary_mult"] == 1.25
    assert neo_stats["stealth_profile"] is True
    assert neo_stats["casino_bonus_pct"] == 20
    assert neo_stats["compact_post_icon"] == "🕶️ "
    assert "Избранный" in neo_stats["active_set_name"]

    # 6. Set Anime Hikka (hat_cat_ears + body_hoodie)
    hikka_items = {
        "equipped_head": "hat_cat_ears",
        "hat_cat_ears_expires": now + 3600,
        "equipped_torso": "body_hoodie",
        "body_hoodie_expires": now + 3600,
    }
    hikka_stats = get_wardrobe_total_stats(hikka_items, current_time=now)
    assert hikka_stats["total_defense"] == 20
    assert hikka_stats["total_toxicity"] == -15
    assert hikka_stats["total_sanity"] == 105
    assert hikka_stats["lootbox_drop_mult"] == 2.0
    assert hikka_stats["compact_post_icon"] == "🐱 "
    assert "Хикка" in hikka_stats["active_set_name"]


# =====================================================================
# 2. COMBAT MODERATION ENGINE: MUTE DURATION REDUCTION
# =====================================================================

def test_combat_duration_mute_reduction():
    """calculate_combat_duration_and_backfire respects target_items mute_reduction_pct."""
    now = int(time.time())

    # Base call without gear
    dur_base, back_base, _ = calculate_combat_duration_and_backfire(
        1001, 2001, "shoot", 300, target_items=None
    )
    assert dur_base == 900  # 15 min base for shoot

    # Target with hat_helmet (-50% mute duration)
    helmet_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
    }
    dur_helmet, _, _ = calculate_combat_duration_and_backfire(
        1001, 2001, "shoot", 300, target_items=helmet_items
    )
    assert dur_helmet == 450  # 900 * 0.5 = 450

    # Target with set_riot_police (-70% mute duration)
    riot_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now + 3600,
    }
    dur_riot, _, _ = calculate_combat_duration_and_backfire(
        1001, 2001, "shoot", 300, target_items=riot_items
    )
    assert dur_riot == 270  # 900 * (1 - 0.7) = 270

    # Test Partyvan with riot gear (base 10800s / 3h -> -70% = 3240s)
    dur_pv_riot, _, _ = calculate_combat_duration_and_backfire(
        1001, 2001, "partyvan", 300, target_items=riot_items
    )
    assert dur_pv_riot == 3240


# =====================================================================
# 3. WORK ENGINE: DURABILITY FIX & UTILITY PERKS
# =====================================================================

def test_work_engine_durability_fix_and_perks():
    """Work engine must check TTL and apply perks (hat_helmet risk=0, hat_bag, tracksuit)."""
    now = int(time.time())

    # Case 1: Expired Wasserman gear should NOT increase salary
    expired_items = {
        "equipped_torso": "body_wasserman",
        "body_wasserman_expires": now - 100,
        "equipped_face": "face_wasserman_glasses",
        "face_wasserman_glasses_expires": now - 100,
        "unlocked_achievements": ["ach_first_work"],
        "work_shifts": 1,
    }

    with patch("random.random", return_value=0.5), patch("common.work_engine.is_night_shift_active", return_value=False):
        success, earned, msg, drop = work_engine.execute_job_action(
            job_id="bottles",
            current_items=expired_items,
        )
    assert success is True
    # Bottles base reward is 15-45 ₪, mult 1.0 (no buff)
    assert earned <= 45
    assert "Жилетка Вассермана" not in msg
    assert "Сет Онотоле" not in msg

    # Case 2: Active hat_helmet removes work risk (risk_pct = 0.0)
    helmet_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "work_shifts": 10,
    }
    # Job 'sweeper' has risk_pct = 0.08, but hat_helmet zeroes it
    with patch("random.random", return_value=0.01):  # Normally triggers 8% fail
        success_h, earned_h, msg_h, _ = work_engine.execute_job_action(
            job_id="sweeper",
            current_items=helmet_items,
        )
        assert success_h is True

    # Case 3: Active hat_bag yields flat 8% chance of trash_lootbox
    bag_items = {
        "equipped_head": "hat_bag",
        "hat_bag_expires": now + 3600,
        "work_shifts": 10,
    }
    with patch("random.random", return_value=0.05):  # 0.05 < 0.08
        success_b, _, _, drop_b = work_engine.execute_job_action(
            job_id="bottles",
            current_items=bag_items,
        )
        assert success_b is True
        assert drop_b == "trash_lootbox"

    # Case 4: Slippers reduce cooldown mult to 0.8
    slippers_items = {
        "equipped_feet": "feet_slippers",
        "feet_slippers_expires": now + 3600,
    }
    stats_sl = get_wardrobe_total_stats(slippers_items, current_time=now)
    assert stats_sl["cooldown_mult"] == 0.80


# =====================================================================
# 4. COMBAT COMMANDS: ROB DEFLECTION, FEAR & STEALTH
# =====================================================================

@pytest.mark.asyncio
async def test_rob_wardrobe_deflection_and_fear(isolated_test_db):
    """cmd_rob respects rob_fear_chance, rob_deflect_chance, and stealth_profile."""
    import main

    now = int(time.time())
    attacker_id = 7001
    target_id = 7002
    board_id = "b"

    # Target needs posts_count >= 50
    await common.database.add_user_global_balance(isolated_test_db, attacker_id, board_id, 500.0)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps({"knife_gun": True}), attacker_id),
    )

    # 1. Target with set_gop_skuf -> 40% fear counter-attack
    target_skuf_items = {
        "equipped_head": "hat_crown",
        "hat_crown_expires": now + 3600,
        "equipped_torso": "body_tracksuit",
        "body_tracksuit_expires": now + 3600,
    }
    await common.database.add_user_global_balance(isolated_test_db, target_id, board_id, 2000.0)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps(target_skuf_items), target_id),
    )

    fake_msg = MagicMock()
    fake_msg.from_user.id = attacker_id
    fake_msg.from_user.first_name = "Robber"
    fake_msg.chat = MagicMock(id=77777)
    fake_msg.message_id = 1111
    fake_msg.reply_to_message = MagicMock()
    fake_msg.reply_to_message.from_user.id = target_id
    fake_msg.reply_to_message.from_user.first_name = "SkufTarget"
    fake_msg.reply_to_message.message_id = 1234
    fake_msg.answer = AsyncMock()
    fake_msg.bot = MagicMock()
    fake_msg.bot.send_message = AsyncMock()

    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
        mock_auth.return_value = target_id

        # fear_chance is 0.40, random.random() < fear_chance triggers fear
        with patch("random.random", return_value=0.10):
            await main.cmd_rob(fake_msg, board_id, stream="ru")
            called_text = fake_msg.answer.call_args[0][0]
            assert "СЫЧ НАПУГАЛ ГРАБИТЕЛЯ" in called_text or "Заточка сломалась от страха" in called_text

        # 2. Target with set_neo -> stealth_profile hides balance
        target_neo_items = {
            "equipped_torso": "body_cloak",
            "body_cloak_expires": now + 3600,
            "equipped_face": "face_anon_mask",
            "face_anon_mask_expires": now + 3600,
        }
        await isolated_test_db.execute(
            "UPDATE Users SET active_items = ? WHERE user_id = ?",
            (json.dumps(target_neo_items), target_id),
        )
        # Re-arm attacker
        await isolated_test_db.execute(
            "UPDATE Users SET active_items = ? WHERE user_id = ?",
            (json.dumps({"knife_gun": True}), attacker_id),
        )

        import shared_state
        shared_state._TARGET_LAST_ATTACKED_TS.clear()
        shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
        shared_state._VICTIM_ROB_COOLDOWNS.clear()

        fake_msg.answer.reset_mock()
        await main.cmd_rob(fake_msg, board_id, stream="ru")
        called_text = fake_msg.answer.call_args[0][0]
        assert "цифровым шумом Матрицы" in called_text

        # 3. Target with Riot Police set (Def = 105 -> P_deflect = 0.2625, stolen_red = 0.525)
        target_riot_items = {
            "equipped_head": "hat_helmet",
            "hat_helmet_expires": now + 3600,
            "equipped_feet": "feet_boots",
            "feet_boots_expires": now + 3600,
        }
        await isolated_test_db.execute(
            "UPDATE Users SET active_items = ? WHERE user_id = ?",
            (json.dumps(target_riot_items), target_id),
        )
        # Re-arm attacker
        await isolated_test_db.execute(
            "UPDATE Users SET active_items = ? WHERE user_id = ?",
            (json.dumps({"knife_gun": True}), attacker_id),
        )

        shared_state._TARGET_LAST_ATTACKED_TS.clear()
        shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
        shared_state._VICTIM_ROB_COOLDOWNS.clear()

        fake_msg.answer.reset_mock()
        # Test Deflection: random.random < rob_deflect_chance (0.2625)
        with patch("random.random", return_value=0.15):
            await main.cmd_rob(fake_msg, board_id, stream="ru")
            called_text = fake_msg.answer.call_args[0][0]
            assert "РИКОШЕТ О БРОНЮ" in called_text

        # 4. Test Stolen Reduction when deflection does not trigger
        await isolated_test_db.execute(
            "UPDATE Users SET active_items = ? WHERE user_id = ?",
            (json.dumps({"knife_gun": True}), attacker_id),
        )
        shared_state._TARGET_LAST_ATTACKED_TS.clear()
        shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
        shared_state._VICTIM_ROB_COOLDOWNS.clear()

        fake_msg.answer.reset_mock()
        fake_msg.answer_photo = AsyncMock()
        with patch("random.random", return_value=0.99), patch("random.uniform", return_value=0.20):
            # Target balance = 2000. Base stolen = 2000 * 0.20 = 400.
            # Stolen reduction: Def = 105 -> rob_stolen_reduction_pct = min(0.60, 105/200) = 0.525.
            # Reduced stolen = max(1, int(round(400 * (1.0 - 0.525)))) = max(1, int(round(400 * 0.475))) = 190.
            await main.cmd_rob(fake_msg, board_id, stream="ru")
            if fake_msg.answer_photo.called:
                out_text = fake_msg.answer_photo.call_args[1].get("caption", "")
            else:
                out_text = fake_msg.answer.call_args[0][0]
            assert "190" in out_text


# =====================================================================
# 5. COMBAT COMMANDS: SHIT IMMUNITY & REFLECTION
# =====================================================================

@pytest.mark.asyncio
async def test_shit_wardrobe_immunity_and_reflection(isolated_test_db):
    """cmd_shit checks feet_boots immunity and hat_tinfoil reflection."""
    import main

    now = int(time.time())
    attacker_id = 7101
    target_id = 7102
    board_id = "b"

    # Attacker with shit_gun
    await common.database.add_user_global_balance(isolated_test_db, attacker_id, board_id, 100.0)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps({"shit_gun": True}), attacker_id),
    )

    # 1. Target with feet_boots -> complete immunity
    target_boots_items = {
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now + 3600,
    }
    await common.database.add_user_global_balance(isolated_test_db, target_id, board_id, 100.0)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps(target_boots_items), target_id),
    )

    fake_msg = MagicMock()
    fake_msg.from_user.id = attacker_id
    fake_msg.from_user.first_name = "Shitter"
    fake_msg.chat = MagicMock(id=77777)
    fake_msg.message_id = 2222
    fake_msg.reply_to_message = MagicMock()
    fake_msg.reply_to_message.from_user.id = target_id
    fake_msg.reply_to_message.from_user.first_name = "BootsTarget"
    fake_msg.reply_to_message.message_id = 2345
    fake_msg.answer = AsyncMock()
    fake_msg.bot = MagicMock()
    fake_msg.bot.send_message = AsyncMock()

    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
        mock_auth.return_value = target_id

        await main.cmd_shit(fake_msg, board_id, stream="ru")
        called_text = fake_msg.answer.call_args[0][0]
        assert "БЕРЦЫ ОМОНА ОТБИЛИ АТАКУ" in called_text

        # Verify target was NOT debuffed
        async with isolated_test_db.execute("SELECT active_items FROM Users WHERE user_id = ?", (target_id,)) as c:
            row = await c.fetchone()
            t_items = json.loads(row[0])
            assert t_items.get("shit_until", 0) <= now

        # 2. Target with hat_tinfoil -> reflection
        target_foil_items = {
            "equipped_head": "hat_tinfoil",
            "hat_tinfoil_expires": now + 3600,
        }
        await isolated_test_db.execute(
            "UPDATE Users SET active_items = ? WHERE user_id = ?",
            (json.dumps(target_foil_items), target_id),
        )
        # Re-arm attacker
        await isolated_test_db.execute(
            "UPDATE Users SET active_items = ? WHERE user_id = ?",
            (json.dumps({"shit_gun": True}), attacker_id),
        )

        import shared_state
        shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
        shared_state._TARGET_LAST_ATTACKED_TS.clear()

        fake_msg.answer.reset_mock()
        await main.cmd_shit(fake_msg, board_id, stream="ru")
        called_text = fake_msg.answer.call_args[0][0]
        assert "ШАПОЧКА ИЗ ФОЛЬГИ" in called_text or "отскочило от фольги" in called_text


# =====================================================================
# 6. COMBAT COMMANDS: CURSE & SCHIZOPILL IMMUNITIES
# =====================================================================

@pytest.mark.asyncio
async def test_curse_and_schizopill_immunities(isolated_test_db):
    """cmd_curse respects set_ward6 laxative immunity, cmd_schizopill respects set_wasserman."""
    import main

    now = int(time.time())
    attacker_id = 7201
    target_id = 7202
    board_id = "b"

    # Attacker with laxative_gun & schizopill_gun
    await common.database.add_user_global_balance(isolated_test_db, attacker_id, board_id, 100.0)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps({"laxative_gun": True, "schizopill_gun": True}), attacker_id),
    )

    # Target with set_ward6 (body_straitjacket + hat_tinfoil)
    ward6_items = {
        "equipped_torso": "body_straitjacket",
        "body_straitjacket_expires": now + 3600,
        "equipped_head": "hat_tinfoil",
        "hat_tinfoil_expires": now + 3600,
    }
    await common.database.add_user_global_balance(isolated_test_db, target_id, board_id, 100.0)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps(ward6_items), target_id),
    )

    fake_msg = MagicMock()
    fake_msg.from_user.id = attacker_id
    fake_msg.from_user.first_name = "Curser"
    fake_msg.chat = MagicMock(id=77777)
    fake_msg.message_id = 3333
    fake_msg.reply_to_message = MagicMock()
    fake_msg.reply_to_message.from_user.id = target_id
    fake_msg.reply_to_message.from_user.first_name = "Ward6Target"
    fake_msg.reply_to_message.message_id = 3456
    fake_msg.answer = AsyncMock()
    fake_msg.bot = MagicMock()
    fake_msg.bot.send_message = AsyncMock()

    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
        mock_auth.return_value = target_id

        # /curse on Ward 6 patient -> immune
        await main.cmd_curse(fake_msg, board_id, stream="ru")
        called_text = fake_msg.answer.call_args[0][0]
        assert "ПАЛАТА №6" in called_text or "иммунитетом к слабительному" in called_text

        # Clear combat cooldown so schizopill can be fired immediately
        import shared_state
        shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
        shared_state._TARGET_LAST_ATTACKED_TS.clear()

        # /schizopill on Ward 6 patient -> immune
        fake_msg.answer.reset_mock()
        await main.cmd_schizopill(fake_msg, board_id, stream="ru")
        called_text = fake_msg.answer.call_args[0][0]
        assert "МЕНТАЛЬНЫЙ ИММУНИТЕТ" in called_text or "Палаты №6" in called_text


# =====================================================================
# 7. COMBAT COMMANDS: SHOOT & PARTYVAN EVASION
# =====================================================================

@pytest.mark.asyncio
async def test_shoot_and_partyvan_evasion(isolated_test_db):
    """feet_sneakers grants 30% evasion from /shoot and /partyvan."""
    import main

    now = int(time.time())
    attacker_id = 7301
    target_id = 7302
    board_id = "b"

    # Attacker with mute_gun and partyvan_gun
    await common.database.add_user_global_balance(isolated_test_db, attacker_id, board_id, 1000.0)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps({"mute_gun": True, "partyvan_gun": True}), attacker_id),
    )

    # Target with feet_sneakers and posts_count >= 50
    sneaker_items = {
        "equipped_feet": "feet_sneakers",
        "feet_sneakers_expires": now + 3600,
    }
    await common.database.add_user_global_balance(isolated_test_db, target_id, board_id, 100.0)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ?, posts_count = 100 WHERE user_id = ?",
        (json.dumps(sneaker_items), target_id),
    )

    fake_msg = MagicMock()
    fake_msg.from_user.id = attacker_id
    fake_msg.from_user.first_name = "Shooter"
    fake_msg.chat = MagicMock(id=77777)
    fake_msg.message_id = 4444
    fake_msg.reply_to_message = MagicMock()
    fake_msg.reply_to_message.from_user.id = target_id
    fake_msg.reply_to_message.from_user.first_name = "FastTarget"
    fake_msg.reply_to_message.message_id = 4567
    fake_msg.answer = AsyncMock()
    fake_msg.bot = MagicMock()
    fake_msg.bot.send_message = AsyncMock()

    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_auth:
        mock_auth.return_value = target_id

        # 1. /shoot with sneaker evasion roll < 0.30
        # Call 1: calculate_combat_duration_and_backfire -> backfire roll (0.5 > 0)
        # Call 2: evasion_chance check -> (0.15 < 0.30 -> evade!)
        with patch("random.random", side_effect=[0.5, 0.15]):
            await main.cmd_shoot(fake_msg, board_id, stream="ru")
            called_text = fake_msg.answer.call_args[0][0]
            assert "ТЯГИ БАРХАТНЫЕ СПАСЛИ" in called_text or "увернулась" in called_text

        # Reset target attacks grief protection and combat cooldowns for /partyvan
        import shared_state
        shared_state._TARGET_LAST_ATTACKED_TS.clear()
        shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()

        # 2. /partyvan with sneaker evasion roll < 0.30
        # Re-arm attacker with partyvan_gun
        await isolated_test_db.execute(
            "UPDATE Users SET active_items = ? WHERE user_id = ?",
            (json.dumps({"partyvan_gun": True}), attacker_id),
        )
        fake_msg.answer.reset_mock()
        with patch("random.random", side_effect=[0.5, 0.15]):
            await main.cmd_partyvan(fake_msg, board_id, stream="ru")
            called_text = fake_msg.answer.call_args[0][0]
            assert "ТЯГИ БАРХАТНЫЕ СПАСЛИ" in called_text or "ускользнула" in called_text


# =====================================================================
# 8. SOCIAL VISIBILITY: POST HEADERS AND PASSPORT DISPLAY
# =====================================================================

@pytest.mark.asyncio
async def test_social_visibility_post_headers(isolated_test_db):
    """post_helpers formats headers with wardrobe compact_post_icon (crown, monocle, helmet)."""
    db = isolated_test_db
    user_id = 7401
    now = int(time.time())

    # 1. Equip riot police gear
    riot_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now + 3600,
    }
    await common.database.add_user_global_balance(db, user_id, "b", 500.0)
    await db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps(riot_items), user_id),
    )

    header = await post_helpers.format_header(
        board_id="b",
        post_num=999,
        author_id=user_id,
        stream="ru",
    )
    # Anonymity policy: item emojis (helmets, crowns, monocles) must NEVER leak into post headers
    assert "🪖" not in header
    assert "999" in header

    thread_header = await post_helpers.format_thread_post_header(
        board_id="b",
        local_post_num=42,
        author_id=user_id,
        thread_info={"op_id": 100},
        stream="ru",
    )
    assert "🪖" not in thread_header
    assert "42" in thread_header

    # 2. hat_crown test
    crown_items = {
        "equipped_head": "hat_crown",
        "hat_crown_expires": now + 3600,
    }
    await db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps(crown_items), user_id),
    )
    header_crown = await post_helpers.format_header("b", 1000, user_id, "ru")
    assert "👑" not in header_crown
    thread_crown = await post_helpers.format_thread_post_header("b", 43, user_id, {"op_id": 100}, "ru")
    assert "👑" not in thread_crown

    # 3. face_monocle test
    monocle_items = {
        "equipped_face": "face_monocle",
        "face_monocle_expires": now + 3600,
    }
    await db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps(monocle_items), user_id),
    )
    header_monocle = await post_helpers.format_header("b", 1001, user_id, "ru")
    assert "⚜️" not in header_monocle
    thread_monocle = await post_helpers.format_thread_post_header("b", 44, user_id, {"op_id": 100}, "ru")
    assert "⚜️" not in thread_monocle


@pytest.mark.asyncio
async def test_passport_and_inventory_wardrobe_summary(isolated_test_db):
    """_format_text_report and _build_inventory_content show equipped gear and sets."""
    import main

    now = int(time.time())

    # 1. UserStatsCardData text report with equipped Wasserman set
    wass_items = {
        "equipped_torso": "body_wasserman",
        "body_wasserman_expires": now + 3600,
        "equipped_face": "face_wasserman_glasses",
        "face_wasserman_glasses_expires": now + 3600,
    }
    card_data = stats_generator.UserStatsCardData(
        user_id=8888,
        board_id="b",
        schizo_name="Onotole",
        role_name="Анон",
        custom_prefix="",
        role="user",
        posts_count=100,
        rx_received=50,
        rx_given=25,
        mutes_count=0,
        balance=1234.0,
        cringe_factor=5,
        rank=1,
        total_users=50,
        slang_comment="База",
        active_items=wass_items,
    )
    report = stats_generator._format_text_report(card_data)
    assert "🎽 <b>Экипировка:</b>" in report
    assert "Жилетка Вассермана" in report
    assert "✨ <b>Сет:</b>" in report
    assert "Анатолий Вассерман" in report

    # 2. _build_inventory_content includes wardrobe section
    await common.database.add_user_global_balance(isolated_test_db, 8888, "b", 1234.0)
    await isolated_test_db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ?",
        (json.dumps(wass_items), 8888),
    )
    inv_text, _ = await main._build_inventory_content(
        user_id=8888,
        board_id="b",
    )
    assert "НАДЕТЫЙ ГАРДЕРОБ:" in inv_text
    assert "Жилетка Вассермана" in inv_text
    assert "Очки Онотоле" in inv_text or "Вассермана" in inv_text


@pytest.mark.asyncio
async def test_wardrobe_and_weapon_toxicity_in_passport_and_avatar():
    """Verify toxicity calculation in both HTML passport and PNG character card."""
    import avatar_generator
    now = int(time.time())

    # Case A: Base user without items, 0 posts -> 15%
    items_empty = {}
    html_empty = avatar_generator.build_character_html_card(
        user_id=101, anon_id="test01", balance=100.0, posts_count=0, active_items=items_empty
    )
    assert "15%" in html_empty

    # Case B: 2 clothing items with toxicity + knife_gun
    # body_tracksuit: +30 toxicity
    # hat_cyber_ushanka: +15 toxicity
    # knife_gun: +30 toxicity
    # base: 15% (posts_count=0) -> Total: 15 + 30 + 15 + 30 = 90%
    toxic_items = {
        "equipped_torso": "body_tracksuit",
        "body_tracksuit_is_permanent": True,
        "equipped_head": "hat_cyber_ushanka",
        "hat_cyber_ushanka_is_permanent": True,
        "knife_gun": True,
    }
    html_toxic = avatar_generator.build_character_html_card(
        user_id=102, anon_id="test02", balance=500.0, posts_count=0, active_items=toxic_items
    )
    assert "90%" in html_toxic
    assert "Обоссанные треники" in html_toxic
    assert "Кибер-Ушанка" in html_toxic
    assert "Заточка" in html_toxic

    # Case C: PNG card generation with the same toxic items
    png_buf = avatar_generator.build_character_card(
        user_id=102, anon_id="test02", balance=500.0, posts_count=0, active_items=toxic_items
    )
    assert png_buf is not None
    assert png_buf.getvalue().startswith(b"\x89PNG")

    # Case D: shit_gun and vomit_gun toxicity parity (+20 each)
    # base: 15% (posts_count=0) + shit_gun (+20) + vomit_gun (+20) = 55%
    poop_items = {
        "shit_gun": True,
        "vomit_gun": True,
    }
    html_poop = avatar_generator.build_character_html_card(
        user_id=103, anon_id="test03", balance=200.0, posts_count=0, active_items=poop_items
    )
    assert "55%" in html_poop
    assert "Кусок говна" in html_poop or "Блевота" in html_poop
    png_poop = avatar_generator.build_character_card(
        user_id=103, anon_id="test03", balance=200.0, posts_count=0, active_items=poop_items
    )
    assert png_poop is not None
    assert png_poop.getvalue().startswith(b"\x89PNG")

    # Case E: Defense & Sanity parity from wardrobe stats (hat_helmet + body_hoodie)
    # hat_helmet: def 45, san 0
    # body_hoodie: def 15, san 25, tox 10
    # total_defense = 45 + 15 = 60
    # total_sanity = 25
    # base def = 5, total def = 5 + 60 = 65%
    # base san = 100, with curse (-50) + hoodie san (+25) -> san = min(100, 100 - 50 + 25) = 75%
    def_san_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_is_permanent": True,
        "equipped_torso": "body_hoodie",
        "body_hoodie_is_permanent": True,
    }
    html_def_san = avatar_generator.build_character_html_card(
        user_id=104, anon_id="test04", balance=300.0, posts_count=0, active_items=def_san_items,
        cursed_until=int(now + 1800)
    )
    assert "65%" in html_def_san


@pytest.mark.asyncio
async def test_neo_set_variations_and_alert_length_limit():
    """Verify Neo set triggers with anon mask OR thug glasses, and alert msg <= 190 chars."""
    import wardrobe_engine
    now = int(time.time())

    # 1. Neo set with face_anon_mask
    neo_mask_items = {
        "owned_body_cloak": True,
        "body_cloak_expires": now + 3600,
        "equipped_torso": "body_cloak",
        "owned_face_anon_mask": True,
        "face_anon_mask_expires": now + 3600,
    }
    ok_mask, msg_mask = wardrobe_engine.equip_item(neo_mask_items, "face_anon_mask")
    assert ok_mask is True
    assert "Избранный / Нео" in msg_mask
    assert len(msg_mask) <= 190, f"msg_mask too long: {len(msg_mask)}"
    stats_mask = wardrobe_engine.get_wardrobe_total_stats(neo_mask_items, current_time=now)
    assert stats_mask["compact_post_icon"] == "🕶️ "
    assert stats_mask["stealth_profile"] is True

    # 2. Neo set with face_thug_glasses
    neo_thug_items = {
        "owned_body_cloak": True,
        "body_cloak_expires": now + 3600,
        "equipped_torso": "body_cloak",
        "owned_face_thug_glasses": True,
        "face_thug_glasses_expires": now + 3600,
    }
    ok_thug, msg_thug = wardrobe_engine.equip_item(neo_thug_items, "face_thug_glasses")
    assert ok_thug is True
    assert "Избранный / Нео" in msg_thug
    assert len(msg_thug) <= 190, f"msg_thug too long: {len(msg_thug)}"
    stats_thug = wardrobe_engine.get_wardrobe_total_stats(neo_thug_items, current_time=now)
    assert stats_thug["compact_post_icon"] == "🕶️ "
    assert stats_thug["stealth_profile"] is True
    assert stats_thug["casino_bonus_pct"] == 20
    assert stats_thug["salary_mult"] >= 1.25

# =====================================================================
# 9. CAPITAL SURCHARGE PRICING & LUXURY WARDROBE EXPANSION
# =====================================================================

def test_progressive_capital_surcharge_pricing_tiers():
    """Verifies progressive capital surcharge for offensive weapons, debuffs, and status items."""
    import main
    from main import get_current_item_price, calculate_capital_surcharge_pct, PROGRESSIVE_SURCHARGE_ITEMS

    # 1. Novice tier (balance <= 10,000 or None) -> 0% surcharge
    assert calculate_capital_surcharge_pct(None) == 0.0
    assert calculate_capital_surcharge_pct(0) == 0.0
    assert calculate_capital_surcharge_pct(5000) == 0.0
    assert calculate_capital_surcharge_pct(10000) == 0.0

    # Partyvan base price is 1500 (novice 100% protected)
    assert get_current_item_price('partyvan', balance=None) == 1500
    assert get_current_item_price('partyvan', balance=0) == 1500
    assert get_current_item_price('partyvan', balance=10000) == 1500

    # 2. Progression across tiers for partyvan (surcharge + dynamic 1% fee capped at 100k)
    # 30,000 (10k-50k): +12.5% (1688) + 300 fee -> 1988
    assert get_current_item_price('partyvan', balance=30000) == 1988
    # 50,000: +25% (1875) + 500 fee -> 2375
    assert get_current_item_price('partyvan', balance=50000) == 2375
    # 100,000 (50k-200k): +50% (2250) + 1000 fee -> 3250
    assert get_current_item_price('partyvan', balance=100000) == 3250
    # 200,000: +100% (3000) + 2000 fee -> 5000
    assert get_current_item_price('partyvan', balance=200000) == 5000
    # 500,000: +300% (4x -> 6000) + 5000 fee -> 11000
    assert get_current_item_price('partyvan', balance=500000) == 11000
    # 1,000,000: +500% (6x -> 9000) + 10,000 fee -> 19000
    assert get_current_item_price('partyvan', balance=1000000) == 19000
    # 2,000,000: +900% (10x -> 15000) + 20,000 fee -> 35000
    assert get_current_item_price('partyvan', balance=2000000) == 35000
    # 10,000,000: capped at +2400% (25x -> 37500) + 100,000 max fee -> 137500
    assert get_current_item_price('partyvan', balance=10000000) == 137500
    assert get_current_item_price('partyvan', balance=20000000) == 137500

    # 3. All 26 surcharged items must scale up with capital
    assert len(PROGRESSIVE_SURCHARGE_ITEMS) == 26
    ITEMS_WITH_EXTRA_CAPITAL_FEES = {'janitor', 'partyvan', 'mute', 'prefix', 'badge_color'}
    for item in PROGRESSIVE_SURCHARGE_ITEMS:
        p_novice = get_current_item_price(item, balance=5000)
        p_rich = get_current_item_price(item, balance=1000000)
        p_ultra = get_current_item_price(item, balance=10000000)
        assert p_rich > p_novice, f'Item {item} failed to scale with wealth! ({p_rich} vs {p_novice})'
        assert p_ultra > p_rich, f'Item {item} failed to reach ultra scaling! ({p_ultra} vs {p_rich})'
        if item not in ITEMS_WITH_EXTRA_CAPITAL_FEES:
            # Items without extra capital fees have exact 6x at 1M and 25x at 10M
            assert p_rich == p_novice * 6, f'Item {item} expected 6x at 1M, got {p_rich} vs {p_novice}'
            assert p_ultra == p_novice * 25, f'Item {item} expected 25x at 10M, got {p_ultra} vs {p_novice}'

    # 4. Explicit verification for Combat Defense items
    assert get_current_item_price('shield', balance=5000) == 500
    assert get_current_item_price('shield', balance=1000000) == 3000
    assert get_current_item_price('shield', balance=10000000) == 12500
    assert get_current_item_price('bribe', balance=5000) == 450
    assert get_current_item_price('bribe', balance=1000000) == 2700
    assert get_current_item_price('tinfoil', balance=5000) == 450
    assert get_current_item_price('tinfoil', balance=1000000) == 2700
    assert get_current_item_price('hat_tinfoil', balance=5000) == 450
    assert get_current_item_price('hat_tinfoil', balance=1000000) == 2700
    assert get_current_item_price('ksiva_polkovnik', balance=5000) == 650
    assert get_current_item_price('ksiva_polkovnik', balance=1000000) == 3900
    assert get_current_item_price('badge_druzhinnik', balance=5000) == 400
    assert get_current_item_price('badge_druzhinnik', balance=1000000) == 2400
    assert get_current_item_price('cyberchad_amulet', balance=5000) == 2500
    assert get_current_item_price('cyberchad_amulet', balance=1000000) == 15000
    assert get_current_item_price('cyberchad_amulet', balance=10000000) == 62500
    assert get_current_item_price('hat_helmet', balance=5000) == 600
    assert get_current_item_price('hat_helmet', balance=1000000) == 3600
    assert get_current_item_price('feet_boots', balance=5000) == 350
    assert get_current_item_price('feet_boots', balance=1000000) == 2100

    # 5. Explicit verification for Combat Offense items
    assert get_current_item_price('knife', balance=5000) == 300
    assert get_current_item_price('knife', balance=1000000) == 1800
    assert get_current_item_price('knife', balance=10000000) == 7500
    assert get_current_item_price('pepperspray', balance=5000) == 300
    assert get_current_item_price('pepperspray', balance=1000000) == 1800
    assert get_current_item_price('shit', balance=5000) == 80
    assert get_current_item_price('shit', balance=1000000) == 480
    assert get_current_item_price('vomit', balance=5000) == 90
    assert get_current_item_price('vomit', balance=1000000) == 540
    assert get_current_item_price('laxative', balance=5000) == 500
    assert get_current_item_price('laxative', balance=1000000) == 3000
    assert get_current_item_price('flag_ua', balance=5000) == 120
    assert get_current_item_price('flag_ua', balance=1000000) == 720
    assert get_current_item_price('flag_ru', balance=5000) == 120
    assert get_current_item_price('flag_ru', balance=1000000) == 720

    # 6. Dynamic Weapon & Vanity status fees
    # mute (500 base): +0.5% fee up to 50k
    assert get_current_item_price('mute', balance=5000) == 500
    assert get_current_item_price('mute', balance=1000000) == 8000  # 500*6 + 5000
    assert get_current_item_price('mute', balance=10000000) == 62500  # 500*25 + 50000

    # prefix (350 base): +2% dynamic status fee up to 100k
    assert get_current_item_price('prefix', balance=5000) == 350
    assert get_current_item_price('prefix', balance=1000000) == 22100  # 350*6 + 20000
    assert get_current_item_price('prefix', balance=10000000) == 108750  # 350*25 + 100000

    # badge_color (500 base): +2% dynamic status fee up to 100k
    assert get_current_item_price('badge_color', balance=5000) == 500
    assert get_current_item_price('badge_color', balance=1000000) == 23000  # 500*6 + 20000
    assert get_current_item_price('badge_color', balance=10000000) == 112500  # 500*25 + 100000


def test_beginner_survival_items_surcharge_immunity():
    """Beginner & survival consumables MUST NOT suffer surcharge regardless of user wealth."""
    from main import get_current_item_price

    beginner_items = [
        'pills', 'hat_bag', 'body_tracksuit', 'feet_slippers',
    ]
    for item in beginner_items:
        p_zero = get_current_item_price(item, balance=0)
        p_novice = get_current_item_price(item, balance=5000)
        p_oligarch = get_current_item_price(item, balance=2500000)
        assert p_zero == p_novice == p_oligarch, f'Beginner item {item} was surcharged! ({p_zero} vs {p_oligarch})'


def test_combat_moderation_capital_scaled_false_report_fine_and_bail():
    """Verify capital-scaled false report fines and bail costs in combat moderation engine."""
    from combat_moderation_engine import calculate_attacker_false_report_fine, calculate_bail_cost

    # 1. Novice tier (balance <= 10,000 or None) -> exactly 500 ₪
    assert calculate_attacker_false_report_fine(None) == 500.0
    assert calculate_attacker_false_report_fine(0) == 500.0
    assert calculate_attacker_false_report_fine(5000) == 500.0
    assert calculate_attacker_false_report_fine(10000) == 500.0

    # 2. Capital scaling (5% of balance)
    assert calculate_attacker_false_report_fine(50000) == 2500.0
    assert calculate_attacker_false_report_fine(200000) == 10000.0
    assert calculate_attacker_false_report_fine(500000) == 25000.0

    # 3. Scaling for 1M, 2M, 4M and hard cap at 200,000 ₪ for balances >= 4,000,000
    assert calculate_attacker_false_report_fine(1000000) == 50000.0
    assert calculate_attacker_false_report_fine(2000000) == 100000.0
    assert calculate_attacker_false_report_fine(4000000) == 200000.0
    assert calculate_attacker_false_report_fine(5000000) == 200000.0
    assert calculate_attacker_false_report_fine(10000000) == 200000.0

    # 4. calculate_bail_cost alias identity
    assert calculate_bail_cost(1000000) == 50000.0
    assert calculate_bail_cost(5000000) == 200000.0


def test_luxury_wardrobe_catalog_and_stats():
    """Test definitions, prices, and stats of Tier 5 Luxury items and sets."""
    import time
    from wardrobe_engine import CLOTHING_CATALOG, SET_BONUSES, get_wardrobe_total_stats
    from main import BASE_SHOP_PRICES

    luxury_items = [
        'hat_golden_crown', 'body_sheikh_mantle', 'body_cyber_suit',
        'face_cyber_visor', 'feet_golden_sneakers'
    ]

    # 1. Price verification: 25k - 150k range & parity with BASE_SHOP_PRICES
    for item_id in luxury_items:
        assert item_id in CLOTHING_CATALOG, f'{item_id} missing from CLOTHING_CATALOG'
        assert item_id in BASE_SHOP_PRICES, f'{item_id} missing from BASE_SHOP_PRICES'
        cat_price = CLOTHING_CATALOG[item_id]['price']
        base_price = BASE_SHOP_PRICES[item_id]
        assert 25000 <= cat_price <= 150000, f'{item_id} price {cat_price} out of [25k, 150k] range'
        assert cat_price == base_price, f'{item_id} catalog price {cat_price} != base price {base_price}'
        assert not CLOTHING_CATALOG[item_id].get('non_buyable', False), f'{item_id} must be buyable in shop'

    now = int(time.time())

    # 2. Individual luxury perks
    # Golden crown: +30% tips, 👑👑 icon
    crown_stats = get_wardrobe_total_stats({
        'equipped_head': 'hat_golden_crown',
        'hat_golden_crown_expires': now + 3600
    }, current_time=now)
    assert crown_stats['total_defense'] == 40
    assert crown_stats['total_sanity'] == 45
    assert crown_stats['tips_mult'] == 1.30
    assert crown_stats['compact_post_icon'] == '👑👑 '

    # Sheikh mantle: 50% rob deflection, stealth
    sheikh_stats = get_wardrobe_total_stats({
        'equipped_torso': 'body_sheikh_mantle',
        'body_sheikh_mantle_expires': now + 3600
    }, current_time=now)
    assert sheikh_stats['total_defense'] == 60
    assert sheikh_stats['rob_deflect_chance'] == 0.50
    assert sheikh_stats['stealth_profile'] is True

    # Golden sneakers: 40% evasion, 0.70 cooldown
    snk_stats = get_wardrobe_total_stats({
        'equipped_feet': 'feet_golden_sneakers',
        'feet_golden_sneakers_expires': now + 3600
    }, current_time=now)
    assert snk_stats['evasion_chance'] == 0.40
    assert snk_stats['cooldown_mult'] == 0.70

    # Cyber visor: +15% casino, 🥽 icon
    visor_stats = get_wardrobe_total_stats({
        'equipped_face': 'face_cyber_visor',
        'face_cyber_visor_expires': now + 3600
    }, current_time=now)
    assert visor_stats['casino_bonus_pct'] == 15
    assert visor_stats['compact_post_icon'] == '🥽 '

    # Cyber suit: 0 fines on work, stealth
    suit_stats = get_wardrobe_total_stats({
        'equipped_torso': 'body_cyber_suit',
        'body_cyber_suit_expires': now + 3600
    }, current_time=now)
    assert suit_stats['work_fine_immunity'] is True
    assert suit_stats['stealth_profile'] is True

    # 3. Luxury Sets: set_oligarch and set_cyber_syndicate
    oligarch_items = {
        'equipped_head': 'hat_golden_crown',
        'hat_golden_crown_expires': now + 3600,
        'equipped_torso': 'body_sheikh_mantle',
        'body_sheikh_mantle_expires': now + 3600,
    }
    oligarch_stats = get_wardrobe_total_stats(oligarch_items, current_time=now)
    assert oligarch_stats['total_defense'] == 40 + 60 + 50  # 150
    assert oligarch_stats['total_sanity'] == 45 + 50 + 50  # 145
    assert oligarch_stats['salary_mult'] == 1.30
    assert oligarch_stats['rob_deflect_chance'] == 0.75  # 150 def * 0.005 = 0.75
    assert oligarch_stats['stealth_profile'] is True
    assert 'Олигарх' in oligarch_stats['active_set_name']

    cyber_items = {
        'equipped_face': 'face_cyber_visor',
        'face_cyber_visor_expires': now + 3600,
        'equipped_torso': 'body_cyber_suit',
        'body_cyber_suit_expires': now + 3600,
    }
    cyber_stats = get_wardrobe_total_stats(cyber_items, current_time=now)
    assert cyber_stats['total_defense'] == 25 + 70 + 50  # 145
    assert cyber_stats['total_sanity'] == 40 + 60 + 40  # 140
    assert cyber_stats['evasion_chance'] == 0.50
    assert cyber_stats['casino_bonus_pct'] == 25
    assert cyber_stats['stealth_profile'] is True
    assert 'Синдикат' in cyber_stats['active_set_name']


def test_luxury_wardrobe_equip_stacking_and_dressing_room():
    """Test equipping, unequipping, and duration stacking on luxury items."""
    import time
    from wardrobe_engine import equip_item, unequip_slot, add_item_duration, get_owned_wardrobe_items

    now = int(time.time())
    inv = {}

    # Add duration for golden crown
    add_item_duration(inv, 'hat_golden_crown', 720)
    assert inv['owned_hat_golden_crown'] is True
    assert inv['hat_golden_crown_expires'] >= now + 720 * 3600 - 5

    # Equip
    ok, msg = equip_item(inv, 'hat_golden_crown')
    assert ok is True
    assert inv['equipped_head'] == 'hat_golden_crown'

    # Add sheikh mantle duration and equip to form set_oligarch
    add_item_duration(inv, 'body_sheikh_mantle', 720)
    ok2, msg2 = equip_item(inv, 'body_sheikh_mantle')
    assert ok2 is True
    assert 'Шекелевый Олигарх' in msg2
    assert len(msg2) <= 190

    # Owned items list
    owned = get_owned_wardrobe_items(inv)
    owned_ids = [o['id'] for o in owned]
    assert 'hat_golden_crown' in owned_ids
    assert 'body_sheikh_mantle' in owned_ids

    # Unequip
    ok_u, msg_u = unequip_slot(inv, 'head')
    assert ok_u is True
    assert 'equipped_head' not in inv
