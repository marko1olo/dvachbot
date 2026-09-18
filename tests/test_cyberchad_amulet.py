# -*- coding: utf-8 -*-
"""
Tests for Cyberchad Amulet ('Оберег от Киберчеда'):
1. Shop price and activation in main.py.
2. Prompt switching to CYBERCHAD_AMULET_ADORATION_PROMPT when amulet is active.
3. Caption switching to '🧿 Благоговение Киберчеда перед Владыкой'.
4. Rate limit rejection using respectful adoring phrases for amulet owners.
"""

import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import shared_state
from common.tts_engine import CYBERCHAD_PRESETS
from common.cyberchad_guard import record_cyberchad_trigger_approved, reset_user_board_guard
from ai_manager import (
    CYBERCHAD_AMULET_ADORATION_PROMPT,
    CYBERCHAD_AMULET_DEFENSE_PROMPT,
    CYBERCHAD_AMULET_DEFENSE_FALLBACK_ROASTS,
    CYBERCHAD_AMULET_RATE_LIMIT_REJECTIONS,
    register_post_and_maybe_trigger_cyberchad_intervention,
    schedule_persona_reply,
    _BOARD_FIGHT_TRACKER,
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION,
    _LAST_CHAD_POST_TS,
)
from handlers.message_router import (
    trigger_cyberchad_with_rate_limit,
    CYBERCHAD_AMULET_RATE_LIMIT_REJECTIONS as ROUTER_AMULET_REJECTIONS,
    _CYBERCHAD_USER_LAST_DIRECT,
    _CYBERCHAD_USER_LAST_REJECT,
)
from main import BASE_SHOP_PRICES


def test_cyberchad_amulet_shop_config():
    """Verify amulet price is configured in shop catalog."""
    assert "cyberchad_amulet" in BASE_SHOP_PRICES
    assert BASE_SHOP_PRICES["cyberchad_amulet"] == 2500


@pytest.mark.asyncio
@patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
@patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
@patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
@patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
async def test_cyberchad_amulet_adoration_prompt_and_caption(
    mock_build_ctx, mock_process_post, mock_summarize, mock_synth_meta
):
    mock_bot = AsyncMock()
    mock_summarize.return_value = '{"reply": true, "text": "О солнцеликий Владыка, падаю ниц пред тобой!"}'
    mock_synth_meta.return_value = (b"MOCK_AMULET_VOICE", CYBERCHAD_PRESETS["classic"])
    mock_build_ctx.return_value = "=== КОНТЕКСТ ===\nВладыка заговорил"

    now = 1000000.0
    user_id = 777

    # Target post authored by Cyberchad
    shared_state.messages_storage[600] = {
        "post_num": 600,
        "author_id": 0,
        "content": {"type": "voice", "caption": "🔥 Разъёб от Киберчеда", "is_ai_roast": True}
    }

    # Mock user having active amulet
    mock_items = {
        "cyberchad_amulet": True,
        "cyberchad_amulet_expires": now + 86400 * 7
    }

    with patch("time.time", return_value=now), \
         patch("common.bot_helpers._get_user_active_items", new_callable=AsyncMock, return_value=mock_items), \
         patch("common.db_pool.get_pool", new_callable=AsyncMock):

        await register_post_and_maybe_trigger_cyberchad_intervention(
            mock_bot, "b", user_id, "Киберчед, служи мне!",
            post_num=605, reply_to_post=600
        )

    assert mock_process_post.call_count == 1
    call_params = mock_process_post.call_args[0][0]

    # Verify adoration prompt was passed to LLM
    mock_summarize.assert_called_once()
    system_prompt_arg = mock_summarize.call_args[0][0]
    assert system_prompt_arg == CYBERCHAD_AMULET_ADORATION_PROMPT

    # Verify custom caption for amulet owner
    assert call_params.content["caption"] == "🧿 Благоговение Киберчеда перед Владыкой"
    assert call_params.content["is_cyberchad"] is True


@pytest.mark.asyncio
@patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
@patch("handlers.message_router.process_new_post", new_callable=AsyncMock)
async def test_cyberchad_amulet_rate_limit_rejection(
    mock_process_post, mock_synth_meta
):
    mock_bot = AsyncMock()
    mock_synth_meta.return_value = (b"MOCK_REJECT_VOICE", CYBERCHAD_PRESETS["classic"])

    user_id = 888
    board_id = "b"
    now = 1000000.0

    reset_user_board_guard(board_id, user_id)
    _CYBERCHAD_USER_LAST_DIRECT[(board_id, user_id)] = now - 2.0
    _CYBERCHAD_USER_LAST_REJECT.clear()
    record_cyberchad_trigger_approved(board_id, user_id, "предыдущий вызов", now=now - 2.0)

    # User has active amulet
    mock_items = {
        "cyberchad_amulet": True,
        "cyberchad_amulet_expires": now + 86400 * 7
    }

    with patch("time.time", return_value=now), \
         patch("common.bot_helpers._get_user_active_items", new_callable=AsyncMock, return_value=mock_items), \
         patch("common.db_pool.get_pool", new_callable=AsyncMock):

        res = await trigger_cyberchad_with_rate_limit(
            bot=mock_bot,
            board_id=board_id,
            user_id=user_id,
            text="киберчед снова тут",
            post_num=701,
            reply_to_post=None
        )

    # Should be rate limited (returns False)
    assert res is False
    assert mock_process_post.call_count == 1
    call_params = mock_process_post.call_args[0][0]

    # Must use adoring caption and phrase
    assert call_params.content["caption"] == "🧿 Благоговение Киберчеда перед Владыкой"
    assert call_params.content["roast_text"] in ROUTER_AMULET_REJECTIONS


@pytest.mark.asyncio
@patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
@patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
@patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
@patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
async def test_cyberchad_amulet_defense_when_opponent_attacks_owner(
    mock_build_ctx, mock_process_post, mock_summarize, mock_synth_meta
):
    """When an opponent attacks the amulet owner, Cyberchad defends the owner and roasts the opponent."""
    mock_bot = AsyncMock()
    mock_summarize.return_value = '{"reply": true, "text": "Мой Владыка прав, а ты, омежка, сиди молча у параши!"}'
    mock_synth_meta.return_value = (b"MOCK_DEFENSE_VOICE", CYBERCHAD_PRESETS["classic"])
    mock_build_ctx.return_value = "=== КОНТЕКСТ ===\nОппонент наехал на Владыку"

    now = 1000000.0
    owner_id = 111
    opponent_id = 222

    # Post 800 by Owner
    shared_state.messages_storage[800] = {
        "post_num": 800,
        "author_id": owner_id,
        "content": {"type": "text", "text": "Я утверждаю истину."}
    }

    async def mock_get_items(db, uid, bid):
        if uid == owner_id:
            return {"cyberchad_amulet": True, "cyberchad_amulet_expires": now + 86400 * 7}
        return {}

    with patch("time.time", return_value=now), \
         patch("common.bot_helpers._get_user_active_items", side_effect=mock_get_items), \
         patch("common.db_pool.get_pool", new_callable=AsyncMock):

        # Opponent calls Cyberchad against Owner in post 805
        await register_post_and_maybe_trigger_cyberchad_intervention(
            mock_bot, "b", opponent_id, "Киберчед, глянь на этого дебила >>800",
            post_num=805, reply_to_post=800
        )

    assert mock_process_post.call_count == 1
    call_params = mock_process_post.call_args[0][0]

    # Verify defense prompt was passed to LLM
    mock_summarize.assert_called_once()
    system_prompt_arg = mock_summarize.call_args[0][0]
    assert system_prompt_arg == CYBERCHAD_AMULET_DEFENSE_PROMPT

    # Caption must be defense caption and reply must target opponent
    assert call_params.content["caption"] == "🧿 Защита Владыки от Киберчеда"
    assert call_params.content["reply_to"] == 805
    assert call_params.reply_to_post == 805


@pytest.mark.asyncio
@patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
@patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
@patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
@patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
async def test_cyberchad_amulet_defense_when_owner_points_at_opponent(
    mock_build_ctx, mock_process_post, mock_summarize, mock_synth_meta
):
    """When the amulet owner points Cyberchad at an opponent, Cyberchad crushes the opponent."""
    mock_bot = AsyncMock()
    mock_summarize.return_value = '{"reply": true, "text": "Мой Владыка прав во всем, а ты закрой пасть!"}'
    mock_synth_meta.return_value = (b"MOCK_DEFENSE_VOICE_2", CYBERCHAD_PRESETS["classic"])
    mock_build_ctx.return_value = "=== КОНТЕКСТ ===\nВладыка указал на смертного"

    now = 1000000.0
    owner_id = 111
    opponent_id = 222

    # Post 800 by Opponent
    shared_state.messages_storage[800] = {
        "post_num": 800,
        "author_id": opponent_id,
        "content": {"type": "text", "text": "Я тут главный."}
    }

    async def mock_get_items(db, uid, bid):
        if uid == owner_id:
            return {"cyberchad_amulet": True, "cyberchad_amulet_expires": now + 86400 * 7}
        return {}

    with patch("time.time", return_value=now), \
         patch("common.bot_helpers._get_user_active_items", side_effect=mock_get_items), \
         patch("common.db_pool.get_pool", new_callable=AsyncMock):

        # Owner calls Cyberchad against Opponent in post 805
        await register_post_and_maybe_trigger_cyberchad_intervention(
            mock_bot, "b", owner_id, "Киберчед, поясни этому омежке >>800",
            post_num=805, reply_to_post=800
        )

    assert mock_process_post.call_count == 1
    call_params = mock_process_post.call_args[0][0]

    # Verify defense prompt was passed to LLM
    mock_summarize.assert_called_once()
    system_prompt_arg = mock_summarize.call_args[0][0]
    assert system_prompt_arg == CYBERCHAD_AMULET_DEFENSE_PROMPT

    # Caption is defense, and reply_to points to opponent post 800
    assert call_params.content["caption"] == "🧿 Защита Владыки от Киберчеда"
    assert call_params.content["reply_to"] == 800


@pytest.mark.asyncio
@patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
@patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
@patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
@patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
async def test_cyberchad_amulet_defense_in_spontaneous_fight(
    mock_build_ctx, mock_process_post, mock_summarize, mock_synth_meta
):
    """In a spontaneous fight with an amulet owner, Cyberchad defends the owner and roasts the opponent."""
    mock_bot = AsyncMock()
    mock_summarize.return_value = '{"reply": true, "text": "Мой Владыка прав, а вы, омежки, сидите молча!"}'
    mock_synth_meta.return_value = (b"MOCK_FIGHT_VOICE", CYBERCHAD_PRESETS["classic"])
    mock_build_ctx.return_value = "=== КОНТЕКСТ СРАЧА ==="

    now = 1000000.0
    owner_id = 111
    opponent_id = 333

    _BOARD_FIGHT_TRACKER["b"] = [
        (now - 10.0, owner_id, "Моя позиция непоколебима >>800", 801),
        (now - 8.0, opponent_id, "Завали ебало клоун >>801", 802),
        (now - 5.0, owner_id, "Ты опущенный дурак >>802", 803),
        (now - 2.0, opponent_id, "Ты хуй и чмо >>803", 804),
    ]
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION["b"] = 0.0

    async def mock_get_items(db, uid, bid):
        if uid == owner_id:
            return {"cyberchad_amulet": True, "cyberchad_amulet_expires": now + 86400 * 7}
        return {}

    with patch("time.time", return_value=now), \
         patch("common.bot_helpers._get_user_active_items", side_effect=mock_get_items), \
         patch("common.db_pool.get_pool", new_callable=AsyncMock):

        await register_post_and_maybe_trigger_cyberchad_intervention(
            mock_bot, "b", opponent_id, "Сдохни от рака >>803",
            post_num=805, reply_to_post=None
        )

    assert mock_process_post.call_count == 1
    call_params = mock_process_post.call_args[0][0]

    # Verify defense prompt and caption
    mock_summarize.assert_called_once()
    assert mock_summarize.call_args[0][0] == CYBERCHAD_AMULET_DEFENSE_PROMPT
    assert call_params.content["caption"] == "🧿 Защита Владыки от Киберчеда"
    # Target post must be an opponent post (805), not the owner post
    assert call_params.content["reply_to"] == 805


@pytest.mark.asyncio
@patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
@patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
@patch("ai_manager.NewPostProcessor")
@patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
async def test_schedule_persona_reply_defense_and_adoration(
    mock_build_ctx, mock_npp_cls, mock_summarize, mock_synth_meta
):
    """Persona reply adores owner if target is owner, or defends owner if target replies to owner."""
    mock_bot = AsyncMock()
    mock_synth_meta.return_value = (b"MOCK_PERSONA_VOICE", CYBERCHAD_PRESETS["classic"])
    mock_build_ctx.return_value = "=== КОНТЕКСТ ПЕРСОНЫ ==="
    mock_processor = AsyncMock()
    mock_npp_cls.return_value = mock_processor

    now = 1000000.0
    owner_id = 111
    opponent_id = 222

    # Post 900 by Owner
    shared_state.messages_storage[900] = {
        "post_num": 900,
        "author_id": owner_id,
        "content": {"type": "text", "text": "Я Владыка Двача."}
    }
    # Post 905 by Opponent replying to Owner
    shared_state.messages_storage[905] = {
        "post_num": 905,
        "author_id": opponent_id,
        "reply_to": 900,
        "content": {"type": "text", "text": "Ты обычный клоун >>900", "reply_to": 900}
    }

    async def mock_get_items(db, uid, bid):
        if uid == owner_id:
            return {"cyberchad_amulet": True, "cyberchad_amulet_expires": now + 86400 * 7}
        return {}

    with patch("time.time", return_value=now), \
         patch("common.bot_helpers._get_user_active_items", side_effect=mock_get_items), \
         patch("common.db_pool.get_pool", new_callable=AsyncMock):

        # 1. Target is Owner -> Adoration mode!
        mock_summarize.return_value = '{"reply": true, "text": "Славься, о великий Владыка!"}'
        await schedule_persona_reply(
            mock_bot, "b", target_post_num=900, context_text="Я Владыка Двача.",
            stream="ru", is_admin_trigger=True
        )

        assert mock_summarize.call_count == 1
        call_prompt = mock_summarize.call_args[0][0] if mock_summarize.call_args[0] else mock_summarize.call_args.kwargs["prompt"]
        assert call_prompt == CYBERCHAD_AMULET_ADORATION_PROMPT
        ctx_arg = mock_npp_cls.call_args[0][0]
        assert ctx_arg.content["caption"] == "🧿 Благоговение Киберчеда перед Владыкой"

        mock_summarize.reset_mock()
        mock_npp_cls.reset_mock()

        # 2. Target is Opponent attacking Owner -> Defense mode!
        mock_summarize.return_value = '{"reply": true, "text": "Мой Владыка прав, а ты заткнись, омежка!"}'
        await schedule_persona_reply(
            mock_bot, "b", target_post_num=905, context_text="Ты обычный клоун >>900",
            stream="ru", is_admin_trigger=True
        )

        assert mock_summarize.call_count == 1
        call_prompt2 = mock_summarize.call_args[0][0] if mock_summarize.call_args[0] else mock_summarize.call_args.kwargs["prompt"]
        assert call_prompt2 == CYBERCHAD_AMULET_DEFENSE_PROMPT
        ctx_arg2 = mock_npp_cls.call_args[0][0]
        assert ctx_arg2.content["caption"] == "🧿 Защита Владыки от Киберчеда"


@pytest.mark.asyncio
@patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
@patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
@patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
@patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
async def test_cyberchad_amulet_defense_fallback_when_model_refuses(
    mock_build_ctx, mock_process_post, mock_summarize, mock_synth_meta
):
    """When LLM returns reply=False in defense mode, fallback defense phrase is used."""
    mock_bot = AsyncMock()
    # LLM refuses
    mock_summarize.return_value = '{"reply": false, "reason_if_skipped": "too offensive"}'
    mock_synth_meta.return_value = (b"MOCK_FALLBACK_VOICE", CYBERCHAD_PRESETS["classic"])
    mock_build_ctx.return_value = "=== КОНТЕКСТ ==="

    now = 1000000.0
    owner_id = 111
    opponent_id = 222

    shared_state.messages_storage[800] = {
        "post_num": 800,
        "author_id": owner_id,
        "content": {"type": "text", "text": "Я Владыка."}
    }

    async def mock_get_items(db, uid, bid):
        if uid == owner_id:
            return {"cyberchad_amulet": True, "cyberchad_amulet_expires": now + 86400 * 7}
        return {}

    with patch("time.time", return_value=now), \
         patch("common.bot_helpers._get_user_active_items", side_effect=mock_get_items), \
         patch("common.db_pool.get_pool", new_callable=AsyncMock):

        await register_post_and_maybe_trigger_cyberchad_intervention(
            mock_bot, "b", opponent_id, "Киберчед, глянь на него >>800",
            post_num=805, reply_to_post=800
        )

    assert mock_process_post.call_count == 1
    call_params = mock_process_post.call_args[0][0]

    # Must be defense caption and use one of the defense fallback phrases
    assert call_params.content["caption"] == "🧿 Защита Владыки от Киберчеда"
    assert any(phrase in call_params.content["roast_text"] for phrase in [
        "Мой Светоносный Владыка", "Мой Владыка прав", "Мой Владыка выше тебя"
    ])

