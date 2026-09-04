# -*- coding: utf-8 -*-
"""
Tests for Upgraded Cyberchad:
1. Rich context building (30 thread posts, media Vision tags, VoiceTranscriptions, author history, past chad replies).
2. JSON Schema parsing with robust markdown/fallback extraction.
3. Reply refusal mechanism ({"reply": false} triggers silent skip without TTS/posting).
4. Full synonym regex matching for Cyberchad names and aliases.
5. Replacement of legacy PersonaBot with Cyberchad in schedule_persona_reply and execute_auto_roast.
"""

import os
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from common.tts_engine import CYBERCHAD_PRESETS
from ai_manager import (
    CYBERCHAD_NAME_REGEX,
    CYBERCHAD_SYSTEM_JSON_PROMPT,
    parse_cyberchad_response,
    build_cyberchad_context,
    register_post_and_maybe_trigger_cyberchad_intervention,
    schedule_persona_reply,
    _BOARD_FIGHT_TRACKER,
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION,
    _LAST_DIRECT_ROAST_USER_TS,
)


@pytest.fixture(autouse=True)
def clean_test_state():
    _BOARD_FIGHT_TRACKER.clear()
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION.clear()
    _LAST_DIRECT_ROAST_USER_TS.clear()
    shared_state.messages_storage.clear()
    yield
    _BOARD_FIGHT_TRACKER.clear()
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION.clear()
    _LAST_DIRECT_ROAST_USER_TS.clear()
    shared_state.messages_storage.clear()


class TestCyberchadJSONParser:
    """Tests for parse_cyberchad_response robustness and refusal behavior."""

    def test_parse_valid_json_reply_true(self):
        raw = json.dumps({
            "reply": True,
            "thought": "Юзер понтуется, а сам сидит в треде без штанов. Размазываю.",
            "text": "Ты кого клоуном назвал, омежка?",
            "reason_if_skipped": "",
            "generate_image": False,
            "image_prompt": ""
        })
        parsed = parse_cyberchad_response(raw)
        assert parsed["reply"] is True
        assert parsed["thought"] == "Юзер понтуется, а сам сидит в треде без штанов. Размазываю."
        assert parsed["text"] == "Ты кого клоуном назвал, омежка?"
        assert parsed["generate_image"] is False

    def test_parse_json_markdown_wrapped(self):
        raw = """
        Вот мой вердикт:
        ```json
        {
          "reply": true,
          "thought": "Сравнил его высер с реальностью.",
          "text": "Размазал тебя по фактам, сыч.",
          "reason_if_skipped": "",
          "generate_image": true,
          "image_prompt": "cyberpunk chad laughing at a soyjak"
        }
        ```
        """
        parsed = parse_cyberchad_response(raw)
        assert parsed["reply"] is True
        assert parsed["thought"] == "Сравнил его высер с реальностью."
        assert parsed["text"] == "Размазал тебя по фактам, сыч."
        assert parsed["generate_image"] is True
        assert parsed["image_prompt"] == "cyberpunk chad laughing at a soyjak"

    def test_parse_reply_false_refusal(self):
        raw = json.dumps({
            "reply": False,
            "thought": "Скучный односложный спам",
            "text": "",
            "reason_if_skipped": "Скучный односложный спам без зацепки",
            "generate_image": False,
            "image_prompt": ""
        })
        parsed = parse_cyberchad_response(raw)
        assert parsed["reply"] is False
        assert parsed["text"] == ""
        assert "Скучный" in parsed["reason_if_skipped"]

    def test_parse_text_fallback_valid(self):
        raw = "Хватит скулить в чате, иди траву потрогай."
        parsed = parse_cyberchad_response(raw)
        assert parsed["reply"] is True
        assert parsed["text"] == "Хватит скулить в чате, иди траву потрогай."

    def test_parse_text_refusal_phrase(self):
        raw = "Не буду отвечать на этот бессмысленный высер"
        parsed = parse_cyberchad_response(raw)
        assert parsed["reply"] is False


class TestCyberchadSystemPrompt:
    """Tests that CYBERCHAD_SYSTEM_JSON_PROMPT enforces 3-entity separation, 1-5 sentences, blocks 1-6, and zoomer ban."""

    def test_prompt_bans_zoomer_slang(self):
        prompt_lower = CYBERCHAD_SYSTEM_JSON_PROMPT.lower()
        # Prompt must explicitly ban tiktok/zoomer words
        assert "скуф" in prompt_lower
        assert "альтушка" in prompt_lower
        assert "дединсайд" in prompt_lower
        assert "вайб" in prompt_lower
        assert "сигма" in prompt_lower
        assert "запрещен" in prompt_lower or "запрещено" in prompt_lower

    def test_prompt_enforces_3_entities_and_blocks(self):
        prompt_lower = CYBERCHAD_SYSTEM_JSON_PROMPT.lower()
        # 3 entities check
        assert "музыкальный роаст" in prompt_lower or "реакция на музыку" in prompt_lower
        assert "голосовых" in prompt_lower
        assert "разговорный киберчед" in prompt_lower

        # Blocks 1-6 check
        assert "блок 1" in prompt_lower
        assert "блок 2" in prompt_lower
        assert "блок 3" in prompt_lower
        assert "блок 4" in prompt_lower
        assert "блок 5" in prompt_lower
        assert "блок 6" in prompt_lower

        # Thought and schema checks
        assert "thought" in prompt_lower
        assert "реферальн" in prompt_lower

        # 1-5 sentences length rule
        assert "1 до 5" in prompt_lower or "1-5" in prompt_lower


class TestCyberchadNameRegex:
    """Tests that CYBERCHAD_NAME_REGEX captures all real aliases and variations."""

    @pytest.mark.parametrize("msg_text", [
        "киберчед поясни за шмот",
        "Кибер Чед, ты тут?",
        "кибер-чед разберись с ним",
        "киберчат го бухать",
        "кибер котлета выходи",
        "кибердед завалил тред",
        "нейрочед жги",
        "нейро чат что думаешь",
        "cyberchad answer me",
        "cyber_chad destroyed them",
        "чед ты лучший",
        "чедик, поясни",
        "ответь чеду",
        "мы с чедом заодно",
    ])
    def test_regex_matches_valid_names(self, msg_text):
        assert CYBERCHAD_NAME_REGEX.search(msg_text) is not None

    @pytest.mark.parametrize("msg_text", [
        "чемодан вокзал россия",
        "очередной тред ни о чем",
        "привет аноны",
        "купил чадо за 500 рублей",
    ])
    def test_regex_does_not_false_positive(self, msg_text):
        assert CYBERCHAD_NAME_REGEX.search(msg_text) is None


class TestCyberchadContextBuilder:
    """Tests explicit blocks 1-6 context generation without dossier bloat."""

    @pytest.mark.asyncio
    async def test_build_cyberchad_context_structure(self):
        # Seed an older parent post outside the 30-post window
        shared_state.messages_storage[50] = {
            "post_num": 50,
            "board_id": "b",
            "author_id": 999,
            "content": {"type": "text", "text": "старый важный пост на который отвечают"}
        }

        # Seed messages_storage in RAM
        shared_state.messages_storage[100] = {
            "post_num": 100,
            "board_id": "b",
            "author_id": 111,
            "content": {"type": "text", "text": "Всем привет в этом треде"}
        }
        shared_state.messages_storage[101] = {
            "post_num": 101,
            "board_id": "b",
            "author_id": 222,
            "content": {"type": "voice", "transcription": "я записал голосовуху про крипту"}
        }
        shared_state.messages_storage[102] = {
            "post_num": 102,
            "board_id": "b",
            "author_id": 0,
            "content": {"type": "voice", "caption": "🔥 Разъёб от Киберчеда", "text": "Очередной крипто-омежка скулит"}
        }
        shared_state.messages_storage[103] = {
            "post_num": 103,
            "board_id": "b",
            "author_id": 222,
            "reply_to_post_num": 50,
            "content": {"type": "text", "text": "киберчед ты сам омежка", "reply_to": 50}
        }

        context = await build_cyberchad_context(
            board_id="b",
            target_post_num=103,
            author_id=222,
            limit_board=3,
            limit_author=5,
            limit_chad=3
        )

        # Verify all explicit blocks 1-6 are present and correctly structured
        assert "=== [БЛОК 1: ЦЕЛЕВОЕ СООБЩЕНИЕ ДЛЯ ОТВЕТА (ЦЕЛЬ)] ===" in context
        assert ">>103" in context
        assert "киберчед ты сам омежка" in context

        assert "=== [БЛОК 2: ЦИТИРУЕМЫЙ РОДИТЕЛЬСКИЙ ПОСТ (ЕСЛИ ЭТО РЕПЛАЙ)] ===" in context
        assert ">>50" in context
        assert "старый важный пост на который отвечают" in context

        assert "=== [БЛОК 3: ИСТОРИЯ ЧАТА" in context
        assert "я записал голосовуху про крипту" in context

        assert "=== [БЛОК 4: ПРОШЛЫЕ СООБЩЕНИЯ ЭТОГО ЮЗЕРА (ДЛЯ ЛОВЛИ НА ПЕРЕОБУВАНИИ)] ===" in context
        assert "=== [БЛОК 5: ТВОИ ПРОШЛЫЕ ОТВЕТЫ (ЗАПРЕТ САМОПОВТОРОВ)] ===" in context
        assert "=== [БЛОК 6: СЕРВЕРНОЕ ВРЕМЯ (МСК)] ===" in context
        assert "МСК" in context

        # Verify no dossier bloat (no balance, no items query)
        assert "шекелей" not in context
        assert "инвентарь" not in context


class TestCyberchadInterventionRefusal:
    """Tests that reply: false causes silent skip without TTS or post creation."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    async def test_direct_reply_refusal_silent_skip(
        self, mock_process_post, mock_summarize, mock_synth_meta
    ):
        mock_bot = AsyncMock()
        # Model returns JSON with reply: False
        mock_summarize.return_value = json.dumps({
            "reply": False,
            "text": "",
            "reason_if_skipped": "Скучный банальный флуд"
        })

        shared_state.messages_storage[500] = {
            "post_num": 500,
            "author_id": 0,
            "content": {"type": "voice", "caption": "🔥 Разъёб от Киберчеда", "is_ai_roast": True}
        }

        await register_post_and_maybe_trigger_cyberchad_intervention(
            mock_bot, "b", 999, "ок",
            post_num=501, reply_to_post=500
        )

        # Must NOT call TTS or post new message!
        assert mock_synth_meta.call_count == 0
        assert mock_process_post.call_count == 0


class TestSchedulePersonaReplyReplacement:
    """Tests that schedule_persona_reply triggers Cyberchad instead of legacy Persona."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.create_post", new_callable=AsyncMock)
    @patch("ai_manager.update_post_content", new_callable=AsyncMock)
    @patch("post_processor.NewPostProcessor.execute", new_callable=AsyncMock)
    async def test_schedule_persona_reply_invokes_cyberchad(
        self, mock_post_exec, mock_update, mock_create_post, mock_summarize, mock_synth_meta
    ):
        mock_bot = AsyncMock()
        mock_create_post.return_value = 888
        mock_summarize.return_value = json.dumps({
            "reply": True,
            "text": "Пояснил за твой высер по понятиям борды.",
            "reason_if_skipped": "",
            "generate_image": False,
            "image_prompt": ""
        })
        mock_synth_meta.return_value = (b"CYBERCHAD_VOICE_PAYLOAD", CYBERCHAD_PRESETS["heavy_bass"])

        shared_state.messages_storage[777] = {
            "post_num": 777,
            "author_id": 12345,
            "content": {"type": "text", "text": "киберчед ответь на этот пост"}
        }

        await schedule_persona_reply(
            bot=mock_bot,
            board_id="b",
            target_post_num=777,
            context_text="киберчед ответь на этот пост",
            stream="ru",
            is_admin_trigger=True
        )

        # Verify create_post was called with Cyberchad properties
        assert mock_create_post.call_count == 1
        create_kwargs = mock_create_post.call_args[1]
        assert create_kwargs["author_id"] == 0
        content_arg = create_kwargs["content"]
        assert content_arg["is_cyberchad"] is True
        assert content_arg["is_ai_roast"] is True
        assert content_arg["voice_bytes"] == b"CYBERCHAD_VOICE_PAYLOAD"
        assert content_arg["caption"] == "🔥 Разъёб от Киберчеда"

        # Verify header formatting
        assert mock_update.call_count == 1
        updated_content = mock_update.call_args[0][1]
        assert "🔥 КИБЕРЧЕД 🔥" in updated_content["header"]
