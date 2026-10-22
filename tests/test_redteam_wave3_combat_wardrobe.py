# -*- coding: utf-8 -*-
"""
tests/test_redteam_wave3_combat_wardrobe.py
Red Team Inquisitor Test Suite — Wave 3, Sector 4:
Combat Moderation Engine, Wardrobe Engine, Achievements Engine, Votemute Engine.
"""

import json
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import common.database
from common.db_pool import get_pool
from combat_moderation_engine import (
    calculate_combat_duration_and_backfire,
    create_combat_appeal_session,
    active_combat_appeals,
    reset_combat_moderation_state,
    callback_combat_appeal,
    callback_combat_bail,
)
from wardrobe_engine import (
    get_wardrobe_total_stats,
    get_equipped_gear,
    get_owned_wardrobe_items,
    equip_item,
    unequip_slot,
    CLOTHING_CATALOG,
    SET_BONUSES,
)
from achievements_engine import (
    check_and_unlock_achievement,
    get_user_achievements,
    atomic_claim_achievement_reward,
    ACHIEVEMENTS_CATALOG,
)
from votemute_engine import (
    start_or_add_vote,
    clean_expired_votemutes,
    active_votemutes,
    check_user_unbribable_mute,
    is_user_under_unbribable_mute,
    generate_votemute_key,
    cmd_votemute,
)


@pytest.fixture(autouse=True)
def clean_memory_state():
    reset_combat_moderation_state()
    active_votemutes.clear()
    yield
    reset_combat_moderation_state()
    active_votemutes.clear()


# =====================================================================
# 1. COMBAT MODERATION ENGINE: FORMULAS, SAFETY & SPLIT-BRAIN APPEALS
# =====================================================================

def test_combat_duration_weapon_normalization_and_target_posts_coercion():
    """Verify case-insensitivity, whitespace tolerance and non-int posts safety."""
    now = int(time.time())
    helmet_items = {"equipped_head": "hat_helmet", "hat_helmet_expires": now + 3600}

    # 1. Uppercase & padded weapon type
    dur, is_back, chance = calculate_combat_duration_and_backfire(
        1001, 2001, "  SHOOT  ", target_posts=300, target_items=None
    )
    assert dur == 900
    assert not is_back

    dur_pv, _, _ = calculate_combat_duration_and_backfire(
        1001, 2001, "PARTYVAN", target_posts=300, target_items=None
    )
    assert dur_pv == 10800

    # 2. String target_posts
    dur_str_posts, _, _ = calculate_combat_duration_and_backfire(
        1001, 2001, "shoot", target_posts="100", target_items=None
    )
    assert dur_str_posts == 630  # 900 * 0.70

    # 3. None target_posts -> coerced to 0 -> newbie immunity
    dur_none_posts, _, _ = calculate_combat_duration_and_backfire(
        1001, 2001, "shoot", target_posts=None, target_items=None
    )
    assert dur_none_posts == 0


def test_combat_duration_json_string_target_items():
    """calculate_combat_duration_and_backfire must parse JSON string wardrobe items."""
    now = int(time.time())
    helmet_dict = {"equipped_head": "hat_helmet", "hat_helmet_expires": now + 3600}
    helmet_json_str = json.dumps(helmet_dict)

    dur, _, _ = calculate_combat_duration_and_backfire(
        attacker_id=1001,
        target_id=2001,
        weapon_type="shoot",
        target_posts=300,
        target_items=helmet_json_str
    )
    # Hat helmet grants -50% mute reduction: 900 * 0.50 = 450
    assert dur == 450


@pytest.mark.asyncio
async def test_combat_appeal_and_bail_split_brain_protection():
    """
    Test race condition resolution between community appeal and instant bail:
    1. Appeal cannot pass if bail is currently being processed.
    2. If appeal completed while bail deduction was in-flight, bail refunds the payer.
    """
    session_id = create_combat_appeal_session(
        board_id="b",
        attacker_id=501,
        target_id=502,
        weapon_type="shoot",
        duration_sec=900,
    )
    sess = active_combat_appeals[session_id]

    # Simulate bail in-flight
    sess._is_processing_bail = True

    # 1. Appeal click while bail is in-flight must be rejected
    cb_appeal = MagicMock()
    cb_appeal.data = f"cappeal:{session_id}"
    cb_appeal.from_user.id = 701
    cb_appeal.answer = AsyncMock()

    with patch("combat_moderation_engine.get_pool", new_callable=AsyncMock), \
         patch("combat_moderation_engine.get_user_posts_count", new_callable=AsyncMock, return_value=50):
        await callback_combat_appeal(cb_appeal)
        assert cb_appeal.answer.called
        assert "залог" in cb_appeal.answer.call_args[0][0]

    # Reset in-flight bail
    sess._is_processing_bail = False

    # 2. Now simulate bail refund if appeal completed during deduction
    sess.is_appealed = False
    sess.is_bailed = False
    cb_bail = MagicMock()
    cb_bail.data = f"cbail:{session_id}"
    cb_bail.from_user.id = 801
    cb_bail.answer = AsyncMock()

    async def _deduct_side_effect(*args, **kwargs):
        # Appeal completes concurrently right here during deduction!
        sess.is_appealed = True
        return (True, 400)

    mock_db = AsyncMock()
    with patch("combat_moderation_engine.get_pool", return_value=mock_db), \
         patch("main.get_current_item_price", return_value=600), \
         patch("common.database.get_user_global_balance", new_callable=AsyncMock, return_value=1000), \
         patch("main.deduct_user_global_balance", side_effect=_deduct_side_effect), \
         patch("main.add_user_global_balance", new_callable=AsyncMock) as mock_refund:
        await callback_combat_bail(cb_bail)
        # Payer must be refunded because appeal was already finalized
        assert mock_refund.called
        assert "Шекели возвращены" in cb_bail.answer.call_args[0][0]


# =====================================================================
# 2. WARDROBE ENGINE: MULTI-SET BONUSES, JSON STRING, & EXPIRED EQUIPS
# =====================================================================

def test_wardrobe_json_string_payload_resilience():
    """All wardrobe functions must accept JSON strings without crashing or dropping stats."""
    now = int(time.time())
    raw_payload = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now + 3600,
        "owned_hat_helmet": True,
        "owned_feet_boots": True,
    }
    json_str = json.dumps(raw_payload)

    # 1. get_wardrobe_total_stats
    stats = get_wardrobe_total_stats(json_str, current_time=now)
    assert stats["total_defense"] == 105
    assert stats["mute_reduction_pct"] == 70
    assert stats["shit_immunity"] is True
    assert stats["work_fine_immunity"] is True

    # 2. get_equipped_gear
    gear = get_equipped_gear(json_str, current_time=now)
    assert gear["head"]["id"] == "hat_helmet"
    assert gear["feet"]["id"] == "feet_boots"

    # 3. get_owned_wardrobe_items
    owned = get_owned_wardrobe_items(json_str)
    assert len(owned) == 2


def test_wardrobe_dual_set_bonus_simultaneous_activation():
    """
    Equipping two disjoint 2-piece sets must grant BOTH sets' bonuses:
    - Set 1: Riot Police (hat_helmet [head] + feet_boots [feet]) -> -70% mute, shit imm, work fine imm
    - Set 2: Wasserman (body_wasserman [torso] + face_wasserman_glasses [face]) -> +40% salary, schizo imm
    """
    now = int(time.time())
    dual_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_expires": now + 3600,
        "equipped_feet": "feet_boots",
        "feet_boots_expires": now + 3600,
        "equipped_torso": "body_wasserman",
        "body_wasserman_expires": now + 3600,
        "equipped_face": "face_wasserman_glasses",
        "face_wasserman_glasses_expires": now + 3600,
    }
    stats = get_wardrobe_total_stats(dual_items, current_time=now)

    # Check Riot Police set perks
    assert stats["mute_reduction_pct"] == 70
    assert stats["shit_immunity"] is True
    assert stats["work_fine_immunity"] is True

    # Check Wasserman set perks
    assert stats["salary_mult"] == 1.40
    assert stats["schizo_immunity"] is True

    # Both set defenses stacked: 45 + 25 + 35 (riot set) + 25 + 10 + 20 (wass set) = 160
    assert stats["total_defense"] == 160


def test_wardrobe_equip_expired_item_rejection():
    """Temporary items with expired timestamp or expires <= now must be rejected by equip_item."""
    now = int(time.time())
    items = {
        "owned_hat_helmet": True,
        "hat_helmet_expires": now - 50,  # Expired
    }
    ok, msg = equip_item(items, "hat_helmet")
    assert ok is False
    assert "истек" in msg
    assert "equipped_head" not in items

    # Permanent item with ancient timestamp can always be equipped
    items_perm = {
        "owned_hat_golden_foil": True,
        "hat_golden_foil_expires": 1,
        "hat_golden_foil_is_permanent": True,
    }
    ok_p, msg_p = equip_item(items_perm, "hat_golden_foil")
    assert ok_p is True
    assert items_perm["equipped_head"] == "hat_golden_foil"


# =====================================================================
# 3. ACHIEVEMENTS ENGINE: CONCURRENCY RACE & ANTI-EXPLOIT
# =====================================================================

def test_achievement_anti_exploit_claimed_registry():
    """
    Once an achievement is claimed, wiping unlocked_achievements must NOT allow re-claiming rewards.
    """
    active_items = {}

    # 1. First unlock succeeds
    unlocked, ach_info = check_and_unlock_achievement(active_items, "ach_work_10")
    assert unlocked is True
    assert ach_info["reward_cash"] == 100
    assert "ach_work_10" in active_items["unlocked_achievements"]
    assert "ach_work_10" in active_items["claimed_achievement_rewards"]

    # 2. Second unlock on same items fails
    u2, _ = check_and_unlock_achievement(active_items, "ach_work_10")
    assert u2 is False

    # 3. Exploiter deletes unlocked_achievements list
    active_items["unlocked_achievements"] = []
    u3, _ = check_and_unlock_achievement(active_items, "ach_work_10")
    assert u3 is False  # Blocked by claimed_achievement_rewards!


def test_achievement_malformed_unlocked_types_normalization():
    """Achievements engine must not crash when unlocked_achievements is string, tuple, set, None."""
    for malformed in ["ach_work_10", ("ach_work_10",), {"ach_work_10"}, None, 12345]:
        items = {"unlocked_achievements": malformed}
        all_ach = get_user_achievements(items)
        assert len(all_ach) == len(ACHIEVEMENTS_CATALOG)


@pytest.mark.asyncio
async def test_atomic_claim_achievement_reward_concurrency_protection(isolated_test_db):
    """
    Stress test: 20 simultaneous coroutines attempt to claim the exact same achievement
    for the exact same user.
    INVARIANT: Exactly ONE coroutine succeeds, balance increases by exactly 1 reward.
    """
    user_id = 998877
    board_id = "b"

    # Seed user with 0 balance and empty items
    await isolated_test_db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 0, '{}')",
        (user_id, board_id)
    )
    await isolated_test_db.commit()

    target_ach = "ach_work_100"  # reward = 1500₪
    reward_amount = ACHIEVEMENTS_CATALOG[target_ach]["reward_cash"]

    async def _claim():
        return await atomic_claim_achievement_reward(isolated_test_db, user_id, board_id, target_ach)

    # Run 20 concurrent claims
    results = await asyncio.gather(*[_claim() for _ in range(20)])

    success_count = sum(1 for ok, rew, _ in results if ok)
    assert success_count == 1, f"Expected exactly 1 claim success, got {success_count}"

    # Verify final balance in DB
    async with isolated_test_db.execute("SELECT balance, active_items FROM Users WHERE user_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
        final_bal = row[0]
        final_items = json.loads(row[1])

    assert final_bal == reward_amount
    assert target_ach in final_items["unlocked_achievements"]
    assert target_ach in final_items["claimed_achievement_rewards"]


# =====================================================================
# 4. VOTEMUTE ENGINE: MEMORY LEAK PLUG, LONGER MUTE PROTECTION, & BOT IMMUNITY
# =====================================================================

def test_votemute_clean_expired_sessions_memory_leak():
    """clean_expired_votemutes must prune unexecuted sessions >10m and executed sessions >40m."""
    now = time.time()

    # Session 1: unexecuted active (5m old) -> keep
    active_votemutes["vm_1"] = {"created_ts": now - 300, "executed": False}
    # Session 2: unexecuted expired (15m old) -> prune
    active_votemutes["vm_2"] = {"created_ts": now - 900, "executed": False}
    # Session 3: executed recent (20m old) -> keep
    active_votemutes["vm_3"] = {"created_ts": now - 1200, "executed": True}
    # Session 4: executed ancient (50m old) -> prune
    active_votemutes["vm_4"] = {"created_ts": now - 3000, "executed": True}

    clean_expired_votemutes()

    assert "vm_1" in active_votemutes
    assert "vm_2" not in active_votemutes
    assert "vm_3" in active_votemutes
    assert "vm_4" not in active_votemutes


@pytest.mark.asyncio
async def test_votemute_does_not_reduce_existing_longer_mute(isolated_test_db):
    """
    Amnesty prevention: If target has a 2-hour partyvan mute (now + 7200),
    applying a 30-minute votemute (now + 1800) must NEVER reduce cursed_until.
    """
    target_id = 444333
    board_id = "b"
    post_num = 12345
    now = int(time.time())
    long_mute_until = now + 7200  # 2 hours

    await isolated_test_db.execute(
        "INSERT INTO Users (user_id, board_id, cursed_until, active_items) VALUES (?, ?, ?, '{}')",
        (target_id, board_id, long_mute_until)
    )
    await isolated_test_db.commit()

    # Vote 5 times to execute iron mute
    with patch("votemute_engine.get_pool", AsyncMock(return_value=isolated_test_db)):
        for voter_id in range(1001, 1006):
            ok, msg, count, executed = await start_or_add_vote(
                board_id=board_id,
                target_id=target_id,
                post_num=post_num,
                voter_id=voter_id,
                bot=None
            )

        assert executed is True

        # Allow background task to finish
        await asyncio.sleep(0.05)

        # Check DB cursed_until was NOT reduced
        async with isolated_test_db.execute(
            "SELECT cursed_until, active_items FROM Users WHERE user_id = ?",
            (target_id,)
        ) as cur:
            row = await cur.fetchone()
            cur_cursed = row[0]
            items = json.loads(row[1])

        assert cur_cursed >= long_mute_until
        assert is_user_under_unbribable_mute(items) is True


@pytest.mark.asyncio
async def test_votemute_bot_rejection():
    """Attempting to votemute the bot must be rejected immediately."""
    mock_bot = MagicMock(id=999999)
    ok, msg, _, _ = await start_or_add_vote(
        board_id="b",
        target_id=999999,
        post_num=100,
        voter_id=123,
        bot=mock_bot
    )
    assert ok is False
    assert "бота" in msg
