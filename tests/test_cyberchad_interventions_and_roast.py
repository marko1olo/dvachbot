# -*- coding: utf-8 -*-
"""
Tests for Requirement R2: Cyberchad Spontaneous Interventions & Direct Reply Roasting.
Validates:
1. Spontaneous fight interventions enforce strict minimum cooldown >= 3600.0s per board.
2. Spontaneous fight interventions send strictly voice messages (no text body).
3. Direct replies to Cyberchad (author_id==0, is_ai_roast, is_ai, or text mentions) trigger personalized brutal voice roasts.
4. Direct replies decouple from spontaneous cooldown (never blocked by board cooldown).
5. Direct replies construct ancestral thread context via build_reply_chain_context.
6. Root cyberchad_tts module re-exports engine components correctly.
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from common.tts_engine import CYBERCHAD_PRESETS
from ai_manager import (
    register_post_and_maybe_trigger_cyberchad_intervention,
    _BOARD_FIGHT_TRACKER,
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION,
    _LAST_CYBERCHAD_INTERVENTION,
    _LAST_DIRECT_ROAST_USER_TS,
    CYBERCHAD_FIGHT_INTERVENTION_PROMPT,
    CYBERCHAD_DIRECT_ROAST_PROMPT,
)


@pytest.fixture(autouse=True)
def reset_cyberchad_trackers():
    _BOARD_FIGHT_TRACKER.clear()
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION.clear()
    _LAST_DIRECT_ROAST_USER_TS.clear()
    shared_state.messages_storage.clear()
    yield
    _BOARD_FIGHT_TRACKER.clear()
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION.clear()
    _LAST_DIRECT_ROAST_USER_TS.clear()
    shared_state.messages_storage.clear()


class TestCyberchadSpontaneousInterventions:
    """Tests for spontaneous fight interventions on boards."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    async def test_spontaneous_intervention_strict_3600s_cooldown(
        self, mock_process_post, mock_summarize, mock_synth_meta
    ):
        mock_bot = AsyncMock()
        mock_summarize.return_value = "Хватит кукарекать, омежки. Завалите ебальники."
        mock_synth_meta.return_value = (b"MOCK_FIGHT_OGG", CYBERCHAD_PRESETS["classic"])

        t0 = 1000000.0

        # Trigger fight with 4 posts from 2 users with aggressive words
        with patch("time.time", return_value=t0):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>100 ты клоун и чмо", post_num=101)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>101 сам долбоеб соси хуй", post_num=102)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>102 уебок завали пасть", post_num=103)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>103 чухан ебаный", post_num=104)

        # 1st intervention must have triggered
        assert mock_process_post.call_count == 1
        assert _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION.get("b") == t0
        assert _LAST_CYBERCHAD_INTERVENTION.get("b") == t0

        # Now test 1800s later (30 min) -> another fight erupts
        t1 = t0 + 1800.0
        _BOARD_FIGHT_TRACKER.clear()
        mock_process_post.reset_mock()

        with patch("time.time", return_value=t1):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>200 ты клоун и чмо", post_num=201)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>201 сам долбоеб соси хуй", post_num=202)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>202 уебок завали пасть", post_num=203)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>203 чухан ебаный", post_num=204)

        # Must NOT trigger because 1800s < 3600s
        assert mock_process_post.call_count == 0

        # Now test at 3601s (after 1 hour)
        t2 = t0 + 3601.0
        _BOARD_FIGHT_TRACKER.clear()
        mock_process_post.reset_mock()

        with patch("time.time", return_value=t2):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>300 ты клоун и чмо", post_num=301)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>301 сам долбоеб соси хуй", post_num=302)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>302 уебок завали пасть", post_num=303)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>303 чухан ебаный", post_num=304)

        # Must trigger because 3601 >= 3600s
        assert mock_process_post.call_count == 1
        assert _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION.get("b") == t2

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    async def test_spontaneous_intervention_strictly_voice_only(
        self, mock_process_post, mock_summarize, mock_synth_meta
    ):
        mock_bot = AsyncMock()
        mock_summarize.return_value = "Размазал обоих клоунов по стенке."
        mock_synth_meta.return_value = (b"CYBERCHAD_PURE_VOICE_BYTES", CYBERCHAD_PRESETS["heavy_bass"])

        now = 1000000.0
        with patch("time.time", return_value=now):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>100 ты клоун и чмо", post_num=101)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>101 сам долбоеб соси хуй", post_num=102)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>102 уебок завали пасть", post_num=103)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>103 чухан ебаный", post_num=104)

        assert mock_process_post.call_count == 1
        call_params = mock_process_post.call_args[0][0]

        # Verify purely voice delivery with no text message body
        assert call_params.board_id == "b"
        assert call_params.user_id == 0
        assert call_params.content["type"] == "voice"
        assert call_params.content["voice_bytes"] == b"CYBERCHAD_PURE_VOICE_BYTES"
        assert call_params.content["caption"] == "🔥 Разъёб от Киберчеда"
        assert call_params.content["is_ai_roast"] is True
        assert call_params.content["is_ai"] is True
        assert "text" not in call_params.content or call_params.content["text"] is None


class TestCyberchadDirectReplyRoasts:
    """Tests for direct replies to Cyberchad and contextual roasting."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    @patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
    async def test_direct_reply_triggers_personalized_voice_roast_ignoring_spontaneous_cooldown(
        self, mock_build_ctx, mock_process_post, mock_summarize, mock_synth_meta
    ):
        mock_bot = AsyncMock()
        mock_summarize.return_value = '{"reply": true, "text": "Слышь ты, сопляк, пошел вон из треда."}'
        mock_synth_meta.return_value = (b"MOCK_DIRECT_ROAST_VOICE", CYBERCHAD_PRESETS["infernal"])
        mock_build_ctx.return_value = "=== [БЛОК 1: ЦЕЛЕВОЕ СООБЩЕНИЕ] ===\nТы кого клоуном назвал"

        now = 1000000.0

        # Set spontaneous intervention cooldown on board "b" to active (now)
        _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION["b"] = now

        # Target post #500 authored by Cyberchad (author_id = 0)
        shared_state.messages_storage[500] = {
            "post_num": 500,
            "author_id": 0,
            "content": {"type": "voice", "caption": "🔥 Разъёб от Киберчеда", "is_ai_roast": True}
        }

        with patch("time.time", return_value=now + 50.0):
            # User 999 replies directly to Cyberchad's post #500
            await register_post_and_maybe_trigger_cyberchad_intervention(
                mock_bot, "b", 999, "Ты кого клоуном назвал, жестянка?",
                post_num=506, reply_to_post=500
            )

        # Must trigger despite spontaneous board cooldown!
        assert mock_process_post.call_count == 1
        call_params = mock_process_post.call_args[0][0]

        assert call_params.board_id == "b"
        assert call_params.user_id == 0
        assert call_params.reply_to_post == 506
        assert call_params.content["type"] == "voice"
        assert call_params.content["voice_bytes"] == b"MOCK_DIRECT_ROAST_VOICE"
        assert call_params.content["reply_to"] == 506

        # Spontaneous cooldown was not updated by direct roast
        assert _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION["b"] == now

        # Verify rich context was built
        mock_build_ctx.assert_called_once()

        # Verify LLM was invoked with direct roast prompt and context
        mock_summarize.assert_called_once()
        prompt_arg, user_text_arg = mock_summarize.call_args[0][:2]
        assert prompt_arg == CYBERCHAD_DIRECT_ROAST_PROMPT
        assert "Ты кого клоуном назвал" in user_text_arg

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    async def test_direct_mention_triggers_voice_roast(
        self, mock_process_post, mock_summarize, mock_synth_meta
    ):
        mock_bot = AsyncMock()
        mock_summarize.return_value = "Киберчед на связи, поясняю за твой кринж."
        mock_synth_meta.return_value = (b"MOCK_MENTION_VOICE", CYBERCHAD_PRESETS["classic"])

        now = 1000000.0
        with patch("time.time", return_value=now):
            await register_post_and_maybe_trigger_cyberchad_intervention(
                mock_bot, "b", 777, "Киберчед, поясни за базар!",
                post_num=801, reply_to_post=None
            )

        assert mock_process_post.call_count == 1
        call_params = mock_process_post.call_args[0][0]
        assert call_params.content["type"] == "voice"
        assert call_params.reply_to_post == 801

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    async def test_direct_reply_per_user_cooldown(
        self, mock_process_post, mock_summarize, mock_synth_meta
    ):
        mock_bot = AsyncMock()
        mock_summarize.return_value = "Разнос."
        mock_synth_meta.return_value = (b"MOCK_VOICE", CYBERCHAD_PRESETS["classic"])

        shared_state.messages_storage[600] = {
            "post_num": 600, "author_id": 0, "content": {"is_ai": True}
        }

        t0 = 1000000.0

        with patch("time.time", return_value=t0):
            await register_post_and_maybe_trigger_cyberchad_intervention(
                mock_bot, "b", 555, "Ответ 1", post_num=601, reply_to_post=600
            )

        assert mock_process_post.call_count == 1

        # Second reply from same user within 5s is debounced
        with patch("time.time", return_value=t0 + 4.0):
            await register_post_and_maybe_trigger_cyberchad_intervention(
                mock_bot, "b", 555, "Ответ 2 спам", post_num=602, reply_to_post=600
            )

        assert mock_process_post.call_count == 1  # Still 1

        # Reply from a different user is NOT blocked
        with patch("time.time", return_value=t0 + 4.0):
            await register_post_and_maybe_trigger_cyberchad_intervention(
                mock_bot, "b", 888, "Ответ от другого юзера", post_num=603, reply_to_post=600
            )

        assert mock_process_post.call_count == 2


class TestRootCyberchadTTSModule:
    """Tests for the root cyberchad_tts module."""

    def test_root_module_exports(self):
        import cyberchad_tts
        assert hasattr(cyberchad_tts, "synthesize_cyberchad_voice")
        assert hasattr(cyberchad_tts, "synthesize_cyberchad_voice_with_meta")
        assert hasattr(cyberchad_tts, "clean_tts_text")
        assert hasattr(cyberchad_tts, "CYBERCHAD_PRESETS")
        assert hasattr(cyberchad_tts, "CyberchadPreset")
        assert hasattr(cyberchad_tts, "get_preset")
        assert hasattr(cyberchad_tts, "get_random_preset")
        assert len(cyberchad_tts.CYBERCHAD_PRESETS) == 10
