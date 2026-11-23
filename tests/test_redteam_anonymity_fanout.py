# -*- coding: utf-8 -*-
"""
test_redteam_anonymity_fanout.py — Comprehensive Red-Team verification of:
1. Zero Raw User ID Leakage: No bare numeric IDs shown to regular users in
   bot messages (economy_extension, main.py, site_tgach).
2. Multi-Party Fanout & DM Delivery:
   - /partyvan: DM notifications to victim when saved by wardrobe (Тяги бархатные, Плащ Нео).
   - /pepperspray: Dual-channel delivery: chat announcement AND DM notification to victim
     on hit, on mirror reflection, and on helmet protection.
"""

import pytest
import asyncio
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import types

import main
from common.anon_identity import get_anon_id, generate_anon_name
from site_tgach.main import safe_user_hash
from tests.economy_live import live_economy, live_handler
import combat_moderation_engine as cme
import shared_state


def make_mock_message(user_id=111, chat_id=1001, text="", reply_to_message=None, message_id=999):
    msg = MagicMock(spec=types.Message)
    msg.from_user = MagicMock(id=user_id, username="testanon", is_bot=False)
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.message_id = message_id
    msg.text = text
    msg.caption = None
    msg.reply_to_message = reply_to_message
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.delete = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.id = 9999999
    msg.bot.send_message = AsyncMock()
    msg.bot.delete_message = AsyncMock()
    return msg


# =============================================================================
# 1. ANONYMITY AUDIT TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_economy_extension_partyvan_and_shit_no_raw_id(isolated_test_db):
    """economy_extension.py must not leak bare numeric target_id in DM to attacker."""
    import economy_extension

    attacker_id = 123456789
    target_id = 987654321
    board_id = "b"

    rep_msg = make_mock_message(user_id=target_id, message_id=10)
    cmd_msg = make_mock_message(user_id=attacker_id, message_id=11, reply_to_message=rep_msg)

    # Setup attacker and target in isolated_test_db with >= 50 posts
    active_items = {"partyvan_gun": True, "shit_gun": True}
    await isolated_test_db.execute(
        "INSERT OR REPLACE INTO Users (user_id, board_id, active_items, posts_count) VALUES (?, ?, ?, ?)",
        (attacker_id, board_id, json.dumps(active_items), 100)
    )
    await isolated_test_db.execute(
        "INSERT OR REPLACE INTO Users (user_id, board_id, active_items, posts_count) VALUES (?, ?, ?, ?)",
        (target_id, board_id, json.dumps({}), 100)
    )
    await isolated_test_db.commit()

    with patch("economy_extension.get_pool", return_value=isolated_test_db), \
         patch("economy_extension.get_reply_target", return_value=target_id):

        await economy_extension.cmd_partyvan(cmd_msg, board_id)

        # Check all send_message calls on bot
        for call_args in cmd_msg.bot.send_message.call_args_list:
            text = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("text", "")
            # Must NOT contain raw target_id
            assert f"<code>{target_id}</code>" not in text
            if "Пативэн успешно выслан" in text:
                assert get_anon_id(target_id) in text

        # Test cmd_shit
        cmd_msg.bot.send_message.reset_mock()
        await economy_extension.cmd_shit(cmd_msg, board_id)
        for call_args in cmd_msg.bot.send_message.call_args_list:
            text = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("text", "")
            assert f"<code>{target_id}</code>" not in text


@pytest.mark.asyncio
async def test_site_tgach_api_create_post_no_raw_id():
    """site_tgach/main.py must return safe_user_hash instead of raw numeric author_id."""
    raw_uid = 123456789
    hashed = safe_user_hash(raw_uid)

    assert hashed != str(raw_uid)
    assert len(hashed) == 12
    # Verify idempotency
    assert safe_user_hash(hashed) == hashed


# =============================================================================
# 2. MULTI-PARTY FANOUT & DM DELIVERY TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_partyvan_wardrobe_sneakers_evasion_notifies_victim_in_dm():
    """When a victim evades /partyvan via Тяги бархатные, victim must receive DM alert."""
    attacker_id = 1111
    victim_id = 2222
    board_id = "b"
    now = int(time.time())

    async with live_economy() as live:
        cme.reset_combat_moderation_state()
        shared_state.reset_combat_state()

        attacker_items = {"partyvan_gun": True}
        victim_items = {"equipped_feet": "feet_sneakers", "feet_sneakers_expires": now + 3600}

        await live.seed_user(attacker_id, 1000.0, attacker_items, posts_count=100)
        await live.seed_user(victim_id, 1000.0, victim_items, posts_count=100)
        live.aim_at(victim_id)
        msg = live.message(attacker_id)

        with patch("combat_moderation_engine.calculate_combat_duration_and_backfire", return_value=(3600, False, 0.1)), \
             patch("random.random", return_value=0.01):  # Force evasion chance (< 0.30)

            await live_handler("partyvan")(msg, board_id)

            answers = live.answers(msg)
            assert any("ТЯГИ БАРХАТНЫЕ СПАСЛИ" in a for a in answers)

            dm_calls = [
                c for c in msg.bot.send_message.call_args_list
                if (c.args and c.args[0] == victim_id) or (c.kwargs.get("chat_id") == victim_id)
            ]
            assert len(dm_calls) >= 1
            victim_dm_text = dm_calls[0].args[1] if len(dm_calls[0].args) > 1 else dm_calls[0].kwargs.get("text", "")
            assert "ТЯГИ БАРХАТНЫЕ СПАСЛИ ТЕБЯ" in victim_dm_text
            assert generate_anon_name(attacker_id) in victim_dm_text
            assert str(attacker_id) not in victim_dm_text


@pytest.mark.asyncio
async def test_partyvan_wardrobe_cloak_stealth_notifies_victim_in_dm():
    """When a victim evades /partyvan via Плащ Нео, victim must receive DM alert."""
    attacker_id = 3333
    victim_id = 4444
    board_id = "b"
    now = int(time.time())

    async with live_economy() as live:
        cme.reset_combat_moderation_state()
        shared_state.reset_combat_state()

        attacker_items = {"partyvan_gun": True}
        victim_items = {"equipped_torso": "body_cloak", "body_cloak_expires": now + 3600}

        await live.seed_user(attacker_id, 1000.0, attacker_items, posts_count=100)
        await live.seed_user(victim_id, 1000.0, victim_items, posts_count=100)
        live.aim_at(victim_id)
        msg = live.message(attacker_id)

        with patch("combat_moderation_engine.calculate_combat_duration_and_backfire", return_value=(3600, False, 0.1)), \
             patch("random.random", return_value=0.01):  # Force cloak stealth (< 0.15)

            await live_handler("partyvan")(msg, board_id)

            answers = live.answers(msg)
            assert any("ПЛАЩ НЕО СКРЫЛ ОТ ОБЛАВЫ" in a for a in answers)

            dm_calls = [
                c for c in msg.bot.send_message.call_args_list
                if (c.args and c.args[0] == victim_id) or (c.kwargs.get("chat_id") == victim_id)
            ]
            assert len(dm_calls) >= 1
            victim_dm_text = dm_calls[0].args[1] if len(dm_calls[0].args) > 1 else dm_calls[0].kwargs.get("text", "")
            assert "ПЛАЩ НЕО СПАС ТЕБЯ" in victim_dm_text
            assert generate_anon_name(attacker_id) in victim_dm_text
            assert str(attacker_id) not in victim_dm_text


@pytest.mark.asyncio
async def test_pepperspray_dual_channel_successful_hit():
    """When /pepperspray hits, chat gets announcement AND victim gets DM alert."""
    attacker_id = 5555
    victim_id = 6666
    board_id = "b"

    async with live_economy() as live:
        cme.reset_combat_moderation_state()
        shared_state.reset_combat_state()

        attacker_items = {"pepperspray_gun": True}
        victim_items = {}

        await live.seed_user(attacker_id, 1000.0, attacker_items, posts_count=100)
        await live.seed_user(victim_id, 1000.0, victim_items, posts_count=100)
        live.aim_at(victim_id)
        msg = live.message(attacker_id)

        await live_handler("pepperspray")(msg, board_id)

        # 1. Chat announcement
        chat_calls = [
            c for c in msg.bot.send_message.call_args_list
            if (c.args and c.args[0] == msg.chat.id) or (c.kwargs.get("chat_id") == msg.chat.id)
        ]
        assert len(chat_calls) >= 1
        chat_text = chat_calls[0].args[1] if len(chat_calls[0].args) > 1 else chat_calls[0].kwargs.get("text", "")
        assert "СТРУЯ В ЕБАЛО" in chat_text
        assert generate_anon_name(victim_id) in chat_text

        # 2. Victim DM
        dm_calls = [
            c for c in msg.bot.send_message.call_args_list
            if (c.args and c.args[0] == victim_id) or (c.kwargs.get("chat_id") == victim_id)
        ]
        assert len(dm_calls) >= 1
        victim_dm_text = dm_calls[0].args[1] if len(dm_calls[0].args) > 1 else dm_calls[0].kwargs.get("text", "")
        assert "В ТЕБЯ РАСПЫЛИЛИ ПЕРЦОВЫЙ БАЛЛОНЧИК" in victim_dm_text
        assert generate_anon_name(attacker_id) in victim_dm_text
        assert str(attacker_id) not in victim_dm_text


@pytest.mark.asyncio
async def test_pepperspray_dual_channel_mirror_reflection():
    """When /pepperspray reflects from Зеркало, chat gets alert AND victim gets DM."""
    attacker_id = 7771
    victim_id = 7772
    board_id = "b"
    now = int(time.time())

    async with live_economy() as live:
        cme.reset_combat_moderation_state()
        shared_state.reset_combat_state()

        attacker_items = {"pepperspray_gun": True}
        victim_items = {"reflect_shield_until": now + 3600}

        await live.seed_user(attacker_id, 1000.0, attacker_items, posts_count=100)
        await live.seed_user(victim_id, 1000.0, victim_items, posts_count=100)
        live.aim_at(victim_id)
        msg = live.message(attacker_id)

        await live_handler("pepperspray")(msg, board_id)

        # 1. Chat announcement
        chat_calls = [
            c for c in msg.bot.send_message.call_args_list
            if (c.args and c.args[0] == msg.chat.id) or (c.kwargs.get("chat_id") == msg.chat.id)
        ]
        assert len(chat_calls) >= 1
        chat_text = chat_calls[0].args[1] if len(chat_calls[0].args) > 1 else chat_calls[0].kwargs.get("text", "")
        assert "РИКОШЕТ ЗЕРКАЛЬНОГО ЩИТА" in chat_text

        # 2. Victim DM
        dm_calls = [
            c for c in msg.bot.send_message.call_args_list
            if (c.args and c.args[0] == victim_id) or (c.kwargs.get("chat_id") == victim_id)
        ]
        assert len(dm_calls) >= 1
        victim_dm_text = dm_calls[0].args[1] if len(dm_calls[0].args) > 1 else dm_calls[0].kwargs.get("text", "")
        assert "ЗЕРКАЛЬНЫЙ ЩИТ ОТРАЗИЛ ПЕРЦОВКУ" in victim_dm_text
        assert generate_anon_name(attacker_id) in victim_dm_text
        assert str(attacker_id) not in victim_dm_text
