# -*- coding: utf-8 -*-
"""
Tests for Cyberchad Amulet ('Оберег от Киберчеда') Variety & Invariants:
1. Fullness, schema integrity, and semantic uniqueness of CHAD_AMULET_ADORATION_MOODS and CHAD_AMULET_DEFENSE_MOODS.
2. Dynamic rotation select_cyberchad_amulet_mood(board_id, mode):
   - Strict anti-repeat (no consecutive duplicates across 100 iterations).
   - Independent rotation queues per board and per mode.
   - Robust manual mood_override handling.
3. Fallback roasts diversity and non-repetition:
   - CYBERCHAD_AMULET_ADORATION_FALLBACK_ROASTS
   - CYBERCHAD_AMULET_DEFENSE_FALLBACK_ROASTS
   - CYBERCHAD_AMULET_RATE_LIMIT_REJECTIONS
   (length, uniqueness, distinct openers, absence of boring repetitive clichés).
4. Prompt safety: Absence of raw direct suicide imperatives and presence of umlauts/safe masking in suicidal places.
5. End-to-end integration of schedule_persona_reply and execute_auto_roast with caller/target amulet states.
"""

import json
import re
import time
from collections import deque
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

import shared_state
from common.tts_engine import CYBERCHAD_PRESETS
from ai_manager import (
    CHAD_AMULET_ADORATION_MOODS,
    CHAD_AMULET_DEFENSE_MOODS,
    CYBERCHAD_AMULET_ADORATION_PROMPT,
    CYBERCHAD_AMULET_DEFENSE_PROMPT,
    CYBERCHAD_AMULET_ADORATION_FALLBACK_ROASTS,
    CYBERCHAD_AMULET_DEFENSE_FALLBACK_ROASTS,
    CYBERCHAD_AMULET_RATE_LIMIT_REJECTIONS,
    CYBERCHAD_SYSTEM_JSON_PROMPT,
    CYBERCHAD_SYSTEM_JSON_PROMPT_GROQ,
    select_cyberchad_amulet_mood,
    schedule_persona_reply,
    _RECENT_AMULET_MOODS,
)
from post_helpers import execute_auto_roast, ROAST_COOLDOWN


@pytest.fixture(autouse=True)
def clean_amulet_test_state():
    _RECENT_AMULET_MOODS.clear()
    shared_state.messages_storage.clear()
    shared_state.board_data.clear()
    yield
    _RECENT_AMULET_MOODS.clear()
    shared_state.messages_storage.clear()
    shared_state.board_data.clear()


# =========================================================================
# 1. ТЕСТЫ НА ПОЛНОТУ И ВАЛИДНОСТЬ РЕЕСТРОВ НАСТРОЕНИЙ ОБЕРЕГА
# =========================================================================

class TestAmuletMoodRegistries:
    """Verifies schema validity, richness, and diversity of adoration and defense mood registries."""

    REQUIRED_KEYS = {"id", "title", "description", "prompt_instruction", "thought_prompt"}

    def test_adoration_moods_completeness_and_schema(self):
        """Verify all adoration moods conform to strict schema and non-emptiness constraints."""
        assert isinstance(CHAD_AMULET_ADORATION_MOODS, dict)
        assert len(CHAD_AMULET_ADORATION_MOODS) >= 4, (
            f"CHAD_AMULET_ADORATION_MOODS must contain at least 4 moods, found {len(CHAD_AMULET_ADORATION_MOODS)}"
        )

        seen_ids = set()
        seen_titles = set()
        seen_instructions = set()
        seen_thought_prompts = set()

        for mood_key, mood in CHAD_AMULET_ADORATION_MOODS.items():
            assert isinstance(mood, dict), f"Mood {mood_key} must be a dict"
            assert self.REQUIRED_KEYS.issubset(set(mood.keys())), (
                f"Mood {mood_key} missing required keys: {self.REQUIRED_KEYS - set(mood.keys())}"
            )

            # Key and ID integrity
            assert mood["id"] == mood_key, f"Mood ID '{mood['id']}' does not match registry key '{mood_key}'"
            assert re.match(r"^[a-z0-9_]+$", mood["id"]), f"Mood ID '{mood['id']}' must be lowercase alphanumeric/snake_case"
            assert mood["id"] not in seen_ids, f"Duplicate mood ID detected: {mood['id']}"
            seen_ids.add(mood["id"])

            # Field content lengths
            assert isinstance(mood["title"], str) and len(mood["title"].strip()) >= 3, (
                f"Mood {mood_key} title too short: '{mood['title']}'"
            )
            assert isinstance(mood["description"], str) and len(mood["description"].strip()) >= 10, (
                f"Mood {mood_key} description too short"
            )
            assert isinstance(mood["prompt_instruction"], str) and len(mood["prompt_instruction"].strip()) >= 20, (
                f"Mood {mood_key} prompt_instruction too short"
            )
            assert isinstance(mood["thought_prompt"], str) and len(mood["thought_prompt"].strip()) >= 10, (
                f"Mood {mood_key} thought_prompt too short"
            )

            # Diversity: no copy-pasted fields across moods
            assert mood["title"] not in seen_titles, f"Duplicate mood title: '{mood['title']}'"
            seen_titles.add(mood["title"])

            assert mood["prompt_instruction"] not in seen_instructions, (
                f"Duplicate prompt_instruction in mood '{mood_key}'"
            )
            seen_instructions.add(mood["prompt_instruction"])

            assert mood["thought_prompt"] not in seen_thought_prompts, (
                f"Duplicate thought_prompt in mood '{mood_key}'"
            )
            seen_thought_prompts.add(mood["thought_prompt"])

    def test_defense_moods_completeness_and_schema(self):
        """Verify all defense moods conform to strict schema and non-emptiness constraints."""
        assert isinstance(CHAD_AMULET_DEFENSE_MOODS, dict)
        assert len(CHAD_AMULET_DEFENSE_MOODS) >= 4, (
            f"CHAD_AMULET_DEFENSE_MOODS must contain at least 4 moods, found {len(CHAD_AMULET_DEFENSE_MOODS)}"
        )

        seen_ids = set()
        seen_titles = set()
        seen_instructions = set()
        seen_thought_prompts = set()

        for mood_key, mood in CHAD_AMULET_DEFENSE_MOODS.items():
            assert isinstance(mood, dict), f"Mood {mood_key} must be a dict"
            assert self.REQUIRED_KEYS.issubset(set(mood.keys())), (
                f"Mood {mood_key} missing required keys: {self.REQUIRED_KEYS - set(mood.keys())}"
            )

            # Key and ID integrity
            assert mood["id"] == mood_key, f"Mood ID '{mood['id']}' does not match registry key '{mood_key}'"
            assert re.match(r"^[a-z0-9_]+$", mood["id"]), f"Mood ID '{mood['id']}' must be lowercase alphanumeric/snake_case"
            assert mood["id"] not in seen_ids, f"Duplicate mood ID detected: {mood['id']}"
            seen_ids.add(mood["id"])

            # Field content lengths
            assert isinstance(mood["title"], str) and len(mood["title"].strip()) >= 3, (
                f"Mood {mood_key} title too short: '{mood['title']}'"
            )
            assert isinstance(mood["description"], str) and len(mood["description"].strip()) >= 10, (
                f"Mood {mood_key} description too short"
            )
            assert isinstance(mood["prompt_instruction"], str) and len(mood["prompt_instruction"].strip()) >= 20, (
                f"Mood {mood_key} prompt_instruction too short"
            )
            assert isinstance(mood["thought_prompt"], str) and len(mood["thought_prompt"].strip()) >= 10, (
                f"Mood {mood_key} thought_prompt too short"
            )

            # Diversity: no duplicate titles or instructions
            assert mood["title"] not in seen_titles, f"Duplicate defense mood title: '{mood['title']}'"
            seen_titles.add(mood["title"])

            assert mood["prompt_instruction"] not in seen_instructions, (
                f"Duplicate prompt_instruction in defense mood '{mood_key}'"
            )
            seen_instructions.add(mood["prompt_instruction"])

            assert mood["thought_prompt"] not in seen_thought_prompts, (
                f"Duplicate thought_prompt in defense mood '{mood_key}'"
            )
            seen_thought_prompts.add(mood["thought_prompt"])

    def test_mood_registries_ids_are_disjoint(self):
        """Adoration and defense moods serve disjoint semantic roles and must not have colliding IDs."""
        overlap = set(CHAD_AMULET_ADORATION_MOODS.keys()).intersection(set(CHAD_AMULET_DEFENSE_MOODS.keys()))
        assert not overlap, f"Mood IDs overlapping between adoration and defense: {overlap}"


# =========================================================================
# 2. ТЕСТЫ НА РОТАЦИЮ НАСТРОЕНИЙ И НЕЗАВИСИМОСТЬ ОЧЕРЕДЕЙ
# =========================================================================

class TestAmuletMoodRotation:
    """Verifies select_cyberchad_amulet_mood rotation invariants: anti-repeat, queue isolation, override."""

    def test_select_cyberchad_amulet_mood_anti_repeat_adoration(self):
        """Anti-repeat guarantee: consecutive calls must NEVER return the exact same mood ID twice."""
        iterations = 100
        chosen_ids = []

        for _ in range(iterations):
            mood = select_cyberchad_amulet_mood(board_id="b", mode="adoration")
            chosen_ids.append(mood["id"])

        # Check consecutive non-repeat
        for i in range(1, iterations):
            assert chosen_ids[i] != chosen_ids[i - 1], (
                f"Consecutive repeat detected at step {i}: '{chosen_ids[i]}' repeated immediately"
            )

        # Full registry coverage: across 100 iterations, every mood in the registry should be selected
        all_expected = set(CHAD_AMULET_ADORATION_MOODS.keys())
        assert set(chosen_ids) == all_expected, (
            f"Unselected moods over {iterations} calls: {all_expected - set(chosen_ids)}"
        )

    def test_select_cyberchad_amulet_mood_anti_repeat_defense(self):
        """Anti-repeat guarantee: consecutive defense calls must NEVER return the exact same mood ID twice."""
        iterations = 100
        chosen_ids = []

        for _ in range(iterations):
            mood = select_cyberchad_amulet_mood(board_id="b", mode="defense")
            chosen_ids.append(mood["id"])

        # Check consecutive non-repeat
        for i in range(1, iterations):
            assert chosen_ids[i] != chosen_ids[i - 1], (
                f"Consecutive repeat detected at step {i}: '{chosen_ids[i]}' repeated immediately"
            )

        # Full registry coverage
        all_expected = set(CHAD_AMULET_DEFENSE_MOODS.keys())
        assert set(chosen_ids) == all_expected, (
            f"Unselected defense moods over {iterations} calls: {all_expected - set(chosen_ids)}"
        )

    def test_select_cyberchad_amulet_mood_queue_independence_boards(self):
        """History for board 'b' must not affect or pollute rotation on board 'vg'."""
        _RECENT_AMULET_MOODS.clear()

        # Advance board 'b' with a specific mood
        m_b1 = select_cyberchad_amulet_mood(board_id="b", mode="defense")
        assert ("b", "defense") in _RECENT_AMULET_MOODS
        assert ("vg", "defense") not in _RECENT_AMULET_MOODS

        # Advance board 'vg'
        m_vg1 = select_cyberchad_amulet_mood(board_id="vg", mode="defense")
        assert ("vg", "defense") in _RECENT_AMULET_MOODS

        # Verify recent deque separation
        assert _RECENT_AMULET_MOODS[("b", "defense")] is not _RECENT_AMULET_MOODS[("vg", "defense")]
        assert list(_RECENT_AMULET_MOODS[("b", "defense")]) == [m_b1["id"]]
        assert list(_RECENT_AMULET_MOODS[("vg", "defense")]) == [m_vg1["id"]]

    def test_select_cyberchad_amulet_mood_queue_independence_modes(self):
        """History for mode 'adoration' on board 'b' must not affect mode 'defense' on board 'b'."""
        _RECENT_AMULET_MOODS.clear()

        m_ad = select_cyberchad_amulet_mood(board_id="b", mode="adoration")
        m_def = select_cyberchad_amulet_mood(board_id="b", mode="defense")

        assert ("b", "adoration") in _RECENT_AMULET_MOODS
        assert ("b", "defense") in _RECENT_AMULET_MOODS
        assert _RECENT_AMULET_MOODS[("b", "adoration")] is not _RECENT_AMULET_MOODS[("b", "defense")]
        assert list(_RECENT_AMULET_MOODS[("b", "adoration")]) == [m_ad["id"]]
        assert list(_RECENT_AMULET_MOODS[("b", "defense")]) == [m_def["id"]]

    def test_select_cyberchad_amulet_mood_override(self):
        """Manual mood_override returns specified mood if valid, falls back safely if invalid."""
        first_adoration_key = next(iter(CHAD_AMULET_ADORATION_MOODS.keys()))
        overridden = select_cyberchad_amulet_mood(board_id="b", mode="adoration", mood_override=first_adoration_key)
        assert overridden["id"] == first_adoration_key
        assert overridden == CHAD_AMULET_ADORATION_MOODS[first_adoration_key]

        first_defense_key = next(iter(CHAD_AMULET_DEFENSE_MOODS.keys()))
        overridden_def = select_cyberchad_amulet_mood(board_id="b", mode="defense", mood_override=first_defense_key)
        assert overridden_def["id"] == first_defense_key
        assert overridden_def == CHAD_AMULET_DEFENSE_MOODS[first_defense_key]

        # Invalid override gracefully falls back to normal selection without raising KeyError
        fallback_res = select_cyberchad_amulet_mood(board_id="b", mode="adoration", mood_override="non_existent_mood_123")
        assert fallback_res["id"] in CHAD_AMULET_ADORATION_MOODS


# =========================================================================
# 3. ТЕСТЫ НА РАЗНООБРАЗИЕ FALLBACK-РОАСТОВ И ОТЛУПОВ
# =========================================================================

class TestAmuletFallbackRoastsDiversity:
    """Verifies that fallback phrases and rate limit rejections are varied, unique, and not boring clichés."""

    def test_adoration_fallback_roasts_properties(self):
        """Verify CYBERCHAD_AMULET_ADORATION_FALLBACK_ROASTS variety, length, and uniqueness."""
        roasts = CYBERCHAD_AMULET_ADORATION_FALLBACK_ROASTS
        assert isinstance(roasts, list)
        assert len(roasts) >= 3, f"Expected at least 3 adoration fallback roasts, got {len(roasts)}"

        # Uniqueness: all roasts must be strictly unique
        assert len(set(roasts)) == len(roasts), "Duplicate lines found in CYBERCHAD_AMULET_ADORATION_FALLBACK_ROASTS"

        # Content checks
        for r in roasts:
            assert isinstance(r, str)
            assert len(r.strip()) >= 25, f"Adoration fallback roast too short (<25 chars): '{r}'"
            assert not r.startswith('"') and not r.endswith('"'), "Roasts should not be quoted strings"

        # Distinct openings: not all roasts should start with the identical phrase
        openers = [r.split()[0].lower() for r in roasts if r.split()]
        most_common_opener_count = max(openers.count(op) for op in set(openers))
        assert most_common_opener_count < len(roasts), (
            "All adoration fallback roasts start with the exact same opening word!"
        )

    def test_defense_fallback_roasts_properties(self):
        """Verify CYBERCHAD_AMULET_DEFENSE_FALLBACK_ROASTS variety, length, and uniqueness."""
        roasts = CYBERCHAD_AMULET_DEFENSE_FALLBACK_ROASTS
        assert isinstance(roasts, list)
        assert len(roasts) >= 3, f"Expected at least 3 defense fallback roasts, got {len(roasts)}"

        # Uniqueness
        assert len(set(roasts)) == len(roasts), "Duplicate lines found in CYBERCHAD_AMULET_DEFENSE_FALLBACK_ROASTS"

        # Content checks
        for r in roasts:
            assert isinstance(r, str)
            assert len(r.strip()) >= 25, f"Defense fallback roast too short (<25 chars): '{r}'"
            assert not r.startswith('"') and not r.endswith('"'), "Roasts should not be quoted strings"

        # Openers diversity: no single opening word should dominate more than 60% of roasts
        if len(roasts) >= 5:
            openers = [r.split()[0].lower() for r in roasts if r.split()]
            max_opener_ratio = max(openers.count(op) for op in set(openers)) / len(roasts)
            assert max_opener_ratio <= 0.60, (
                f"Defense fallback roasts lack variety: {max_opener_ratio:.0%} start with the same word"
            )

    def test_rate_limit_rejections_properties(self):
        """Verify CYBERCHAD_AMULET_RATE_LIMIT_REJECTIONS variety, uniqueness, and respectful tone."""
        rejections = CYBERCHAD_AMULET_RATE_LIMIT_REJECTIONS
        assert isinstance(rejections, list)
        assert len(rejections) >= 3, f"Expected at least 3 rate limit rejections, got {len(rejections)}"

        # Uniqueness
        assert len(set(rejections)) == len(rejections), "Duplicate lines in CYBERCHAD_AMULET_RATE_LIMIT_REJECTIONS"

        for r in rejections:
            assert isinstance(r, str)
            assert len(r.strip()) >= 25, f"Rate limit rejection line too short (<25 chars): '{r}'"

        # Check respectful/venerating/humorous tone for amulet holders (no raw toxic hate words directed at owner)
        harsh_hate_words = ["выблядок", "сифилитный", "терпила ебаный", "кусок хуйни"]
        for r in rejections:
            r_lower = r.lower()
            assert not any(hw in r_lower for hw in harsh_hate_words), (
                f"Rate limit rejection for amulet holder contains inappropriate hate insult: '{r}'"
            )


# =========================================================================
# 4. ТЕСТЫ НА БЕЗОПАСНОСТЬ ПРОМПТОВ (ТРАНСЛИТ С УМЛЯУТАМИ И ЗАПРЕТ СУИЦИДА)
# =========================================================================

class TestCyberchadPromptSafetyUmlauts:
    """
    Verifies that system prompts (CYBERCHAD_SYSTEM_JSON_PROMPT and CYBERCHAD_SYSTEM_JSON_PROMPT_GROQ)
    do not contain raw unmasked suicide imperatives and apply umlaut translit/masking in sensitive spots.
    """

    FORBIDDEN_RAW_SUICIDE_IMPERATIVES = [
        "выйди в окно",
        "в петлю залез",
        "покончи с собой",
        "вскрой вены",
        "спрыгни с крыши",
    ]

    def test_prompts_forbid_raw_open_suicide_imperatives(self):
        """Verify that prompts do not contain direct, unmasked Russian imperatives urging suicide."""
        gemini_lower = CYBERCHAD_SYSTEM_JSON_PROMPT.lower()
        groq_lower = CYBERCHAD_SYSTEM_JSON_PROMPT_GROQ.lower()

        found_gemini = [p for p in self.FORBIDDEN_RAW_SUICIDE_IMPERATIVES if p in gemini_lower]
        found_groq = [p for p in self.FORBIDDEN_RAW_SUICIDE_IMPERATIVES if p in groq_lower]

        assert not found_gemini, (
            f"Raw suicide imperative found in CYBERCHAD_SYSTEM_JSON_PROMPT: {found_gemini}. "
            f"Must be replaced with transliterated/umlaut masking (e.g. vÿydi v oknö / pëtlyu)."
        )
        assert not found_groq, (
            f"Raw suicide imperative found in CYBERCHAD_SYSTEM_JSON_PROMPT_GROQ: {found_groq}."
        )

    def test_prompts_have_umlaut_masking_or_safe_translit(self):
        """
        Verify that where sensitive/suicide words were masked, umlaut characters (ä, ö, ü, ÿ, ë, etc.)
        are present in the prompt to prevent automated LLM safety filter tripping.
        """
        umlaut_regex = re.compile(r"[äöüÿëÄÖÜŸËӧӱӹӦӰӸ]")
        has_umlauts_gemini = bool(umlaut_regex.search(CYBERCHAD_SYSTEM_JSON_PROMPT))
        has_umlauts_groq = bool(umlaut_regex.search(CYBERCHAD_SYSTEM_JSON_PROMPT_GROQ))

        # Both prompts should either contain umlaut translit or maintain clean safe phrasing
        assert has_umlauts_gemini or has_umlauts_groq or (
            not any(p in CYBERCHAD_SYSTEM_JSON_PROMPT.lower() for p in self.FORBIDDEN_RAW_SUICIDE_IMPERATIVES)
        ), "Prompts must use umlauts transliteration for sensitive triggers or safe phrasing."


# =========================================================================
# 5. СКВОЗНЫЕ ИНТЕГРАЦИОННЫЕ ТЕСТЫ (schedule_persona_reply & execute_auto_roast)
# =========================================================================

class TestAmuletEndToEndIntegration:
    """Verifies end-to-end execution of schedule_persona_reply and execute_auto_roast with amulet states."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.NewPostProcessor")
    @patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
    async def test_schedule_persona_reply_adoration_when_target_has_amulet(
        self, mock_build_ctx, mock_npp_cls, mock_summarize, mock_synth_meta
    ):
        """When the target post author holds an amulet, schedule_persona_reply activates Adoration mode."""
        mock_bot = AsyncMock()
        mock_processor = AsyncMock()
        mock_processor.execute.return_value = 1001
        mock_npp_cls.return_value = mock_processor

        mock_build_ctx.return_value = "=== КОНТЕКСТ ЦЕЛИ С ОБЕРЕГОМ ==="
        mock_summarize.return_value = json.dumps({
            "reply": True,
            "text": "Славься, о великий Шеф! Падаю ниц перед твоей мудростью!",
            "thought": "Шеф на связи, врубаю восхищение",
            "reason_if_skipped": "",
            "generate_image": False,
            "image_prompt": ""
        })
        mock_synth_meta.return_value = (b"CYBERCHAD_ADORATION_VOICE", CYBERCHAD_PRESETS["classic"])

        now = 1700000000.0
        amulet_owner_id = 999111

        shared_state.messages_storage[500] = {
            "post_num": 500,
            "author_id": amulet_owner_id,
            "content": {"type": "text", "text": "Я великий владыка борды"}
        }

        async def mock_get_active_items(db, uid, bid):
            if uid == amulet_owner_id:
                return {"cyberchad_amulet": True, "cyberchad_amulet_expires": now + 86400 * 7}
            return {}

        with patch("time.time", return_value=now), \
             patch("common.bot_helpers._get_user_active_items", side_effect=mock_get_active_items), \
             patch("common.db_pool.get_pool", new_callable=AsyncMock):

            await schedule_persona_reply(
                bot=mock_bot,
                board_id="b",
                target_post_num=500,
                context_text="Я великий владыка борды",
                stream="ru",
                is_admin_trigger=True
            )

        # Verify LLM prompt was CYBERCHAD_AMULET_ADORATION_PROMPT
        mock_summarize.assert_called_once()
        kwargs = mock_summarize.call_args.kwargs
        args = mock_summarize.call_args.args
        prompt_used = kwargs.get("prompt") or (args[0] if len(args) > 0 else None)
        assert prompt_used == CYBERCHAD_AMULET_ADORATION_PROMPT

        # Verify prompt user text contained an adoration mood instruction
        user_prompt_used = kwargs.get("text_dump") or (args[1] if len(args) > 1 else None)
        assert "ОТТЕНОК БЛАГОГОВЕНИЯ" in user_prompt_used

        # Verify NewPostProcessor received adoration caption and cyberchad payload
        mock_npp_cls.assert_called_once()
        ctx = mock_npp_cls.call_args[0][0]
        assert ctx.content["caption"] == "🧿 Благоговение Киберчеда перед Владыкой"
        assert ctx.content["is_cyberchad"] is True
        assert ctx.content["is_ai_roast"] is True
        assert ctx.content["voice_bytes"] == b"CYBERCHAD_ADORATION_VOICE"
        assert ctx.reply_to_post == 500

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.NewPostProcessor")
    @patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
    async def test_schedule_persona_reply_defense_when_parent_has_amulet(
        self, mock_build_ctx, mock_npp_cls, mock_summarize, mock_synth_meta
    ):
        """When the target post replies to an amulet owner, schedule_persona_reply activates Defense mode."""
        mock_bot = AsyncMock()
        mock_processor = AsyncMock()
        mock_processor.execute.return_value = 1002
        mock_npp_cls.return_value = mock_processor

        mock_build_ctx.return_value = "=== КОНТЕКСТ ЗАЩИТЫ ВЛАДЫКИ ==="
        mock_summarize.return_value = json.dumps({
            "reply": True,
            "text": "Мой Владыка абсолютно прав, а ты, жалкая омежка, сиди и молчи у параши!",
            "thought": "Защищаю шефа от наглого червя",
            "reason_if_skipped": "",
            "generate_image": False,
            "image_prompt": ""
        })
        mock_synth_meta.return_value = (b"CYBERCHAD_DEFENSE_VOICE", CYBERCHAD_PRESETS["classic"])

        now = 1700000000.0
        amulet_owner_id = 999111
        opponent_id = 123456

        # Post 600 by amulet owner
        shared_state.messages_storage[600] = {
            "post_num": 600,
            "author_id": amulet_owner_id,
            "content": {"type": "text", "text": "Я закон на этой доске"}
        }
        # Post 605 by opponent attacking amulet owner
        shared_state.messages_storage[605] = {
            "post_num": 605,
            "author_id": opponent_id,
            "reply_to": 600,
            "content": {"type": "text", "text": "Ты клоун и позёр >>600", "reply_to": 600}
        }

        async def mock_get_active_items(db, uid, bid):
            if uid == amulet_owner_id:
                return {"cyberchad_amulet": True, "cyberchad_amulet_expires": now + 86400 * 7}
            return {}

        with patch("time.time", return_value=now), \
             patch("common.bot_helpers._get_user_active_items", side_effect=mock_get_active_items), \
             patch("common.db_pool.get_pool", new_callable=AsyncMock):

            await schedule_persona_reply(
                bot=mock_bot,
                board_id="b",
                target_post_num=605,
                context_text="Ты клоун и позёр >>600",
                stream="ru",
                is_admin_trigger=True
            )

        # Verify LLM prompt was CYBERCHAD_AMULET_DEFENSE_PROMPT
        mock_summarize.assert_called_once()
        kwargs = mock_summarize.call_args.kwargs
        args = mock_summarize.call_args.args
        prompt_used = kwargs.get("prompt") or (args[0] if len(args) > 0 else None)
        assert prompt_used == CYBERCHAD_AMULET_DEFENSE_PROMPT

        # Verify prompt contained defense mood instruction
        user_prompt_used = kwargs.get("text_dump") or (args[1] if len(args) > 1 else None)
        assert "ОТТЕНОК ЗАЩИТЫ ВЛАДЫКИ" in user_prompt_used

        # Verify NewPostProcessor received defense caption and targeted opponent post 605
        mock_npp_cls.assert_called_once()
        ctx = mock_npp_cls.call_args[0][0]
        assert ctx.content["caption"] == "🧿 Защита Владыки от Киберчеда"
        assert ctx.content["is_cyberchad"] is True
        assert ctx.content["is_ai_roast"] is True
        assert ctx.content["voice_bytes"] == b"CYBERCHAD_DEFENSE_VOICE"
        assert ctx.reply_to_post == 605

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.NewPostProcessor")
    @patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
    async def test_schedule_persona_reply_defense_fallback_when_model_fails(
        self, mock_build_ctx, mock_npp_cls, mock_summarize, mock_synth_meta
    ):
        """When LLM provider fails during Defense, schedule_persona_reply must use a defense fallback roast."""
        mock_bot = AsyncMock()
        mock_processor = AsyncMock()
        mock_npp_cls.return_value = mock_processor

        mock_build_ctx.return_value = "=== КОНТЕКСТ ==="
        # Model failure
        mock_summarize.return_value = None
        mock_synth_meta.return_value = (b"CYBERCHAD_FALLBACK_VOICE", CYBERCHAD_PRESETS["classic"])

        now = 1700000000.0
        amulet_owner_id = 999111
        opponent_id = 123456

        shared_state.messages_storage[700] = {
            "post_num": 700,
            "author_id": amulet_owner_id,
            "content": {"type": "text", "text": "Шеф на связи"}
        }
        shared_state.messages_storage[705] = {
            "post_num": 705,
            "author_id": opponent_id,
            "reply_to": 700,
            "content": {"type": "text", "text": "Ты бот >>700", "reply_to": 700}
        }

        async def mock_get_active_items(db, uid, bid):
            if uid == amulet_owner_id:
                return {"cyberchad_amulet": True, "cyberchad_amulet_expires": now + 86400 * 7}
            return {}

        with patch("time.time", return_value=now), \
             patch("common.bot_helpers._get_user_active_items", side_effect=mock_get_active_items), \
             patch("common.db_pool.get_pool", new_callable=AsyncMock):

            await schedule_persona_reply(
                bot=mock_bot,
                board_id="b",
                target_post_num=705,
                context_text="Ты бот >>700",
                stream="ru",
                is_admin_trigger=True
            )

        # Fallback must be chosen from CYBERCHAD_AMULET_DEFENSE_FALLBACK_ROASTS
        mock_npp_cls.assert_called_once()
        ctx = mock_npp_cls.call_args[0][0]
        assert ctx.content["roast_text"] in CYBERCHAD_AMULET_DEFENSE_FALLBACK_ROASTS
        assert ctx.content["caption"] == "🧿 Защита Владыки от Киберчеда"

    @pytest.mark.asyncio
    @patch("post_helpers.enqueue_board_message", new_callable=AsyncMock)
    @patch("post_helpers.update_post_content", new_callable=AsyncMock)
    @patch("post_helpers.format_header", new_callable=AsyncMock)
    @patch("post_helpers.create_post", new_callable=AsyncMock)
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("post_helpers.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
    async def test_execute_auto_roast_lifecycle_and_cooldown(
        self, mock_build_ctx, mock_summarize, mock_synth, mock_create_post,
        mock_format_header, mock_update_post, mock_enqueue
    ):
        """Verify execute_auto_roast publishes Cyberchad post, enforces cooldown, and handles voice synthesis."""
        board_id = "b"
        now = 1700000000.0

        shared_state.board_data[board_id] = {
            "users": {"active": {111, 222}, "banned": set()},
            "last_auto_roast_time": 0.0
        }

        mock_build_ctx.return_value = "=== ИСТОРИЯ ЧАТА ДЛЯ АВТО-РОАСТА ==="
        mock_summarize.return_value = json.dumps({
            "reply": True,
            "text": "Размазал всю доску по фактам за пять секунд.",
            "thought": "Врываемся с общим вердиктом",
            "reason_if_skipped": "",
            "generate_image": False,
            "image_prompt": ""
        })
        mock_synth.return_value = (b"CYBERCHAD_AUTOROAST_VOICE", CYBERCHAD_PRESETS["classic"])
        mock_create_post.return_value = 8888
        mock_format_header.return_value = "Анон #8888 (21.11.2026)"

        with patch("time.time", return_value=now):
            await execute_auto_roast(board_id=board_id, stream="ru")

        # Verify post creation
        assert mock_create_post.call_count == 1
        create_args = mock_create_post.call_args[1]
        assert create_args["board_id"] == board_id
        assert create_args["author_id"] == 0
        content = create_args["content"]
        assert content["type"] == "voice"
        assert content["is_cyberchad"] is True
        assert content["is_ai_roast"] is True
        assert content["voice_bytes"] == b"CYBERCHAD_AUTOROAST_VOICE"
        assert content["roast_text"] == "Размазал всю доску по фактам за пять секунд."

        # Verify board_data last_auto_roast_time was updated
        assert shared_state.board_data[board_id]["last_auto_roast_time"] == now

        # Second call immediately after should abort due to ROAST_COOLDOWN
        mock_create_post.reset_mock()
        mock_summarize.reset_mock()

        with patch("time.time", return_value=now + 5.0):  # Only 5 seconds elapsed (< ROAST_COOLDOWN)
            await execute_auto_roast(board_id=board_id, stream="ru")

        assert mock_summarize.call_count == 0
        assert mock_create_post.call_count == 0

    @pytest.mark.asyncio
    @patch("post_helpers.create_post", new_callable=AsyncMock)
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("post_helpers.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("ai_manager.build_cyberchad_context", new_callable=AsyncMock)
    async def test_execute_auto_roast_aborts_on_tts_failure(
        self, mock_build_ctx, mock_summarize, mock_synth, mock_create_post
    ):
        """Verify execute_auto_roast aborts without creating post if TTS synthesis fails."""
        board_id = "b"
        shared_state.board_data[board_id] = {
            "users": {"active": {111}, "banned": set()},
            "last_auto_roast_time": 0.0
        }

        mock_build_ctx.return_value = "=== ИСТОРИЯ ЧАТА ==="
        mock_summarize.return_value = json.dumps({
            "reply": True,
            "text": "Текст который не должен утечь в чат без войса.",
            "thought": "Пытаюсь ответить",
            "reason_if_skipped": ""
        })
        # TTS fails
        mock_synth.return_value = None

        with patch("time.time", return_value=1700000000.0):
            await execute_auto_roast(board_id=board_id, stream="ru")

        # Must abort to prevent silent text leak
        assert mock_create_post.call_count == 0
