# -*- coding: utf-8 -*-
"""
tests/test_reaction_mimicry_engine.py — Unit & Integration Test Suite for Reaction Mimicry Engine

Tests coverage:
1. All 5 Anon Personas (horny_weeb, toxic_oldfag, clown_troll, based_chad, deep_sych) and their emoji sets.
2. Heuristic classifier triggers: tags, text keywords, boards, greentext lines.
3. LLM classifier with valid JSON parsing.
4. LLM timeout (>4.0s) & 429 rate limit graceful fallback to heuristics.
5. Virtual Anon Pool deterministic allocation & deduplication invariants.
6. Dynamic mood cycle (diurnal calculation, mood bias, cycling).
7. Persistence (JSON load/save, atomic write, 1000-post FIFO pruning, persona stats tracking).
8. Batch runner with candidate sampling and DB queue dispatch.
"""

import asyncio
from datetime import datetime, timezone
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from reaction_mimicry_engine import (
    PERSONAS,
    VALID_MOODS,
    VIRTUAL_ANON_BASE_ID,
    VIRTUAL_ANON_POOL_SIZE,
    get_default_state,
    load_mimicry_state,
    save_mimicry_state,
    calculate_diurnal_mood,
    get_current_mood,
    set_current_mood,
    cycle_mood,
    get_or_assign_virtual_reactor,
    evaluate_post_heuristics,
    evaluate_post_llm,
    decide_post_reactions,
    apply_mimicry_reaction,
    run_mimicry_batch,
    _parse_llm_json_response,
    _extract_post_features,
)


# =============================================================================
# PART 1: PERSONAS CONFIGURATION & INTEGRITY
# =============================================================================

def test_all_five_personas_exist_with_valid_palettes():
    """Verifies that all 5 required personas are defined with appropriate emojis."""
    expected_personas = {"horny_weeb", "toxic_oldfag", "clown_troll", "based_chad", "deep_sych"}
    assert set(PERSONAS.keys()) == expected_personas

    for p_name, conf in PERSONAS.items():
        assert "name" in conf
        assert "desc" in conf
        assert "reaction_options" in conf
        assert len(conf["reaction_options"]) >= 3
        # Each reaction option must be a non-empty list of emojis
        for opt in conf["reaction_options"]:
            assert isinstance(opt, list)
            assert len(opt) >= 1
            for emoji in opt:
                assert isinstance(emoji, str) and len(emoji) > 0


def test_horny_weeb_reaction_emojis():
    """Verifies horny_weeb uses hearts, fires, and affectionate emojis."""
    options = PERSONAS["horny_weeb"]["reaction_options"]
    all_emojis = [e for opt in options for e in opt]
    assert "❤️" in all_emojis or "😍" in all_emojis
    assert "🔥" in all_emojis or "❤‍🔥" in all_emojis


def test_toxic_oldfag_reaction_emojis():
    """Verifies toxic_oldfag uses poop, vomit, middle finger, and disgust emojis."""
    options = PERSONAS["toxic_oldfag"]["reaction_options"]
    all_emojis = [e for opt in options for e in opt]
    assert "💩" in all_emojis
    assert "🤮" in all_emojis or "🤢" in all_emojis
    assert "🖕" in all_emojis


def test_clown_troll_reaction_emojis():
    """Verifies clown_troll uses clown and laughing emojis."""
    options = PERSONAS["clown_troll"]["reaction_options"]
    all_emojis = [e for opt in options for e in opt]
    assert "🤡" in all_emojis
    assert "😂" in all_emojis or "🤣" in all_emojis


def test_based_chad_reaction_emojis():
    """Verifies based_chad uses thumbs up, ok, and 100 emojis."""
    options = PERSONAS["based_chad"]["reaction_options"]
    all_emojis = [e for opt in options for e in opt]
    assert "👍" in all_emojis
    assert "👌" in all_emojis or "💯" in all_emojis


def test_deep_sych_reaction_emojis():
    """Verifies deep_sych uses thinking, mindblown, and sad emojis."""
    options = PERSONAS["deep_sych"]["reaction_options"]
    all_emojis = [e for opt in options for e in opt]
    assert "🤔" in all_emojis or "🧐" in all_emojis
    assert "😢" in all_emojis or "🤯" in all_emojis


# =============================================================================
# PART 2: HEURISTIC CLASSIFIER TRIGGERS
# =============================================================================

def test_heuristic_triggers_horny_weeb_by_tags():
    """Hentai and anime tags trigger horny_weeb with hearts/fire."""
    post = {
        "post_num": 1001,
        "text": "Красивый арт вайфу",
        "tags": ["anime", "hentai", "1girl", "breasts"],
        "board_id": "b"
    }
    persona, reactions = evaluate_post_heuristics(post)
    assert persona == "horny_weeb"
    assert any(e in ["❤️", "🔥", "😍", "❤‍🔥", "🥰"] for e in reactions)


def test_heuristic_triggers_horny_weeb_by_sex_board():
    """Posts on /sex/ board strongly bias toward horny_weeb."""
    post = {
        "post_num": 1002,
        "text": "Оцените тяночку",
        "board_id": "sex"
    }
    persona, reactions = evaluate_post_heuristics(post)
    assert persona == "horny_weeb"


def test_heuristic_triggers_toxic_oldfag_by_cringe_keywords():
    """Normie whining and cringe keywords trigger toxic_oldfag with poop/vomit."""
    post = {
        "post_num": 1003,
        "text": "Пиздец я такое соевое нытье и кринж в тиктоке увидел, просто блевота",
        "board_id": "b"
    }
    persona, reactions = evaluate_post_heuristics(post)
    assert persona == "toxic_oldfag"
    assert any(e in ["💩", "🤮", "🖕", "🤢"] for e in reactions)


def test_heuristic_triggers_toxic_oldfag_by_gay_cringe():
    """Gay/fag themes and zoomer spam trigger toxic_oldfag."""
    post = {
        "post_num": 1004,
        "text": "Тут один зумер пидор плачется что его соя скисла",
        "board_id": "b"
    }
    persona, reactions = evaluate_post_heuristics(post)
    assert persona == "toxic_oldfag"
    assert any(e in ["💩", "🤮", "🖕", "🤢"] for e in reactions)


def test_heuristic_triggers_clown_troll():
    """Absurd circus, clown takes, and epic fails trigger clown_troll."""
    post = {
        "post_num": 1005,
        "text": "Ахаха вот это клоун, чисто обосрался на весь тред, цирк уехал лол",
        "board_id": "b"
    }
    persona, reactions = evaluate_post_heuristics(post)
    assert persona == "clown_troll"
    assert any(e in ["🤡", "😂", "🤣"] for e in reactions)


def test_heuristic_triggers_based_chad_by_greentext():
    """Greentext lines (>) and chad keywords trigger based_chad."""
    post = {
        "post_num": 1006,
        "text": "> проснулся в 6 утра\n> пошел в зал пожал сотку\n> помог анону\nЧисто база, сигма гигачад.",
        "board_id": "b"
    }
    persona, reactions = evaluate_post_heuristics(post)
    assert persona == "based_chad"
    assert any(e in ["👍", "👌", "💯"] for e in reactions)


def test_heuristic_triggers_deep_sych_by_doomer_loneliness():
    """Existential sadness and night thoughts trigger deep_sych."""
    post = {
        "post_num": 1007,
        "text": "Опять эта ночь, сижу один в пустой комнате, тоска съедает, зачем вообще всё это бытие",
        "board_id": "b"
    }
    persona, reactions = evaluate_post_heuristics(post)
    assert persona == "deep_sych"
    assert any(e in ["🤔", "🧐", "🤯", "😢"] for e in reactions)


def test_feature_extraction_nested_content():
    """_extract_post_features correctly unpacks nested content and media tags."""
    post = {
        "content": {
            "text": "Текст в content.text",
            "vision_tags": ["blue_archive", "ecchi"],
            "type": "photo"
        },
        "board_id": "media"
    }
    text, tags, board, mtype = _extract_post_features(post)
    assert "текст в content.text" in text
    assert "blue_archive" in tags
    assert "ecchi" in tags
    assert board == "media"
    assert mtype == "photo"


# =============================================================================
# PART 3: LLM CLASSIFIER WITH STRICT FALLBACK & TIMEOUT
# =============================================================================

def test_parse_llm_json_response_valid():
    """_parse_llm_json_response correctly parses valid markdown JSON."""
    raw = '```json\n{"persona": "horny_weeb", "reactions": ["❤️", "🔥"]}\n```'
    parsed = _parse_llm_json_response(raw)
    assert parsed is not None
    persona, reactions = parsed
    assert persona == "horny_weeb"
    assert reactions == ["❤️", "🔥"]


def test_parse_llm_json_response_malformed():
    """_parse_llm_json_response returns None on invalid JSON."""
    assert _parse_llm_json_response("Some random text without json") is None
    assert _parse_llm_json_response('{"persona": "unknown_alien"}') is None
    assert _parse_llm_json_response('{"persona": "based_chad", "reactions": []}') is None


@pytest.mark.asyncio
async def test_evaluate_post_llm_success():
    """evaluate_post_llm returns LLM parsed result when LLM succeeds."""
    post = {"text": "Тестовый пост", "board_id": "b"}
    fake_json = '{"persona": "based_chad", "reactions": ["💯"]}'

    with patch("reaction_mimicry_engine._invoke_llm_completion_safe", AsyncMock(return_value=fake_json)):
        persona, reactions = await evaluate_post_llm(post, timeout_sec=1.0)

    assert persona == "based_chad"
    assert reactions == ["💯"]


@pytest.mark.asyncio
async def test_evaluate_post_llm_timeout_fallback():
    """evaluate_post_llm falls back cleanly to heuristics when LLM times out (>4.0s)."""
    post = {
        "text": "Опять сижу один в темноте тоска безысходность",
        "board_id": "b"
    }

    async def slow_llm(*args, **kwargs):
        await asyncio.sleep(2.0)
        return '{"persona": "based_chad", "reactions": ["👍"]}'

    # Set timeout to 0.05s to simulate instant timeout
    with patch("reaction_mimicry_engine._invoke_llm_completion_safe", side_effect=slow_llm):
        persona, reactions = await evaluate_post_llm(post, timeout_sec=0.05)

    # Must fallback to deep_sych from heuristic analysis
    assert persona == "deep_sych"
    assert any(e in ["🤔", "🧐", "🤯", "😢"] for e in reactions)


@pytest.mark.asyncio
async def test_evaluate_post_llm_rate_limit_429_fallback():
    """evaluate_post_llm falls back cleanly on 429 Rate Limit error."""
    post = {
        "text": "Ахаха вот это клоун обосрался на весь тред лол",
        "board_id": "b"
    }

    with patch("reaction_mimicry_engine._invoke_llm_completion_safe", AsyncMock(side_effect=RuntimeError("429 Too Many Requests"))):
        persona, reactions = await evaluate_post_llm(post, timeout_sec=1.0)

    # Must fallback to clown_troll from heuristic analysis
    assert persona == "clown_troll"
    assert any(e in ["🤡", "😂", "🤣"] for e in reactions)


@pytest.mark.asyncio
async def test_decide_post_reactions_coordinator():
    """decide_post_reactions respects use_llm flag."""
    post = {"text": "Красава база", "board_id": "b"}
    # use_llm = False -> direct heuristics
    p1, r1 = await decide_post_reactions(post, use_llm=False)
    assert p1 == "based_chad"

    # use_llm = True -> LLM with fallback
    with patch("reaction_mimicry_engine.evaluate_post_llm", AsyncMock(return_value=("horny_weeb", ["🔥"]))):
        p2, r2 = await decide_post_reactions(post, use_llm=True)
        assert p2 == "horny_weeb"
        assert r2 == ["🔥"]


# =============================================================================
# PART 4: VIRTUAL ANON POOL & DEDUPLICATION
# =============================================================================

def test_virtual_anon_id_within_bounds():
    """get_or_assign_virtual_reactor produces IDs strictly in range [770100001..770100050]."""
    for post_num in [1, 42, 100, 598000, 999999]:
        for persona in PERSONAS.keys():
            uid = get_or_assign_virtual_reactor(post_num, persona)
            assert VIRTUAL_ANON_BASE_ID <= uid < (VIRTUAL_ANON_BASE_ID + VIRTUAL_ANON_POOL_SIZE)


def test_virtual_anon_deterministic_reproducibility():
    """Same post_num and persona always return the exact same user_id."""
    uid1 = get_or_assign_virtual_reactor(598271, "horny_weeb")
    uid2 = get_or_assign_virtual_reactor(598271, "horny_weeb")
    assert uid1 == uid2


def test_virtual_anon_distinct_for_different_personas():
    """Different personas for the same post map to different anons across the pool."""
    uids = {
        persona: get_or_assign_virtual_reactor(598271, persona)
        for persona in PERSONAS.keys()
    }
    # At least 3 distinct UIDs among the 5 personas
    assert len(set(uids.values())) >= 3


# =============================================================================
# PART 5: DYNAMIC MOOD CYCLE & PERSISTENCE
# =============================================================================

def test_calculate_diurnal_mood_hours():
    """calculate_diurnal_mood matches day and night phases."""
    # Night
    night_dt = datetime(2026, 11, 23, 2, 0, 0, tzinfo=timezone.utc)
    assert calculate_diurnal_mood(night_dt) in ["chill", "horny"]

    # Morning
    morning_dt = datetime(2026, 11, 23, 9, 0, 0, tzinfo=timezone.utc)
    assert calculate_diurnal_mood(morning_dt) == "based"

    # Afternoon
    afternoon_dt = datetime(2026, 11, 23, 14, 0, 0, tzinfo=timezone.utc)
    assert calculate_diurnal_mood(afternoon_dt) == "toxic"

    # Evening
    evening_dt = datetime(2026, 11, 23, 20, 0, 0, tzinfo=timezone.utc)
    assert calculate_diurnal_mood(evening_dt) == "troll"


def test_mood_cycling():
    """cycle_mood transitions through moods cyclically."""
    state = get_default_state()
    set_current_mood("chill", state)
    assert get_current_mood(state) == "chill"

    m1 = cycle_mood(state=state)
    assert m1 == "toxic"
    m2 = cycle_mood(state=state)
    assert m2 == "horny"

    # Forced mood
    m_forced = cycle_mood(forced_mood="based", state=state)
    assert m_forced == "based"


def test_mood_bias_affects_neutral_post():
    """Ambiguous/neutral posts are swayed by active mood bias."""
    neutral_post = {"text": "Просто обычный короткий пост", "board_id": "b"}

    p_toxic, _ = evaluate_post_heuristics(neutral_post, current_mood="toxic")
    assert p_toxic == "toxic_oldfag"

    p_horny, _ = evaluate_post_heuristics(neutral_post, current_mood="horny")
    assert p_horny == "horny_weeb"

    p_troll, _ = evaluate_post_heuristics(neutral_post, current_mood="troll")
    assert p_troll == "clown_troll"


def test_persistence_save_load(tmp_path):
    """save_mimicry_state and load_mimicry_state preserve state accurately."""
    temp_file = str(tmp_path / "test_state.json")
    state = get_default_state()
    state["current_mood"] = "toxic"
    state["total_reactions_placed"] = 42
    state["persona_stats"]["toxic_oldfag"] = 15

    ok = save_mimicry_state(state, file_path=temp_file)
    assert ok is True
    assert os.path.exists(temp_file)

    loaded = load_mimicry_state(file_path=temp_file)
    assert loaded["current_mood"] == "toxic"
    assert loaded["total_reactions_placed"] == 42
    assert loaded["persona_stats"]["toxic_oldfag"] == 15


# =============================================================================
# PART 6: REACTION APPLICATION & BATCH RUNNER
# =============================================================================

@pytest.mark.asyncio
async def test_apply_mimicry_reaction_lifecycle(tmp_path):
    """apply_mimicry_reaction enqueues reactions to DB and updates state."""
    state = get_default_state()
    temp_file = str(tmp_path / "mimicry_state.json")

    mock_add_queue = AsyncMock()
    with patch("common.database.add_reaction_to_queue", mock_add_queue), \
         patch("reaction_mimicry_engine.STATE_FILE_PATH", temp_file):
        res = await apply_mimicry_reaction(
            post_num=5001,
            board_id="b",
            post_data={"text": "Базированный чад победил в споре"},
            state=state,
            save_after=False
        )

    assert res is not None
    assert res["post_num"] == 5001
    assert res["persona"] == "based_chad"
    assert VIRTUAL_ANON_BASE_ID <= res["user_id"] < (VIRTUAL_ANON_BASE_ID + VIRTUAL_ANON_POOL_SIZE)
    assert len(res["reactions"]) >= 1

    # Verify ReactionQueue dispatch
    assert mock_add_queue.called
    assert mock_add_queue.call_args[1]["user_id"] == res["user_id"]
    assert mock_add_queue.call_args[1]["post_num"] == 5001

    # Verify post recorded in state
    assert 5001 in state["processed_post_nums"]
    assert state["persona_stats"]["based_chad"] >= 1
    assert state["total_reactions_placed"] >= 1

    # Repeat call for the same post_num must be deduplicated
    res_repeat = await apply_mimicry_reaction(
        post_num=5001,
        board_id="b",
        state=state,
        save_after=False
    )
    assert res_repeat is None


@pytest.mark.asyncio
async def test_history_cap_at_1000():
    """State trims processed_post_nums to max 1000 items."""
    state = get_default_state()
    # Pre-fill with 1000 items
    state["processed_post_nums"] = list(range(1, 1001))

    with patch("common.database.add_reaction_to_queue", AsyncMock()):
        await apply_mimicry_reaction(
            post_num=1001,
            board_id="b",
            post_data={"text": "Новый пост"},
            state=state,
            save_after=False
        )

    # Size must be exactly 1000
    assert len(state["processed_post_nums"]) == 1000
    # Oldest item (1) was pruned, newest (1001) is present
    assert 1 not in state["processed_post_nums"]
    assert 1001 in state["processed_post_nums"]


@pytest.mark.asyncio
async def test_run_mimicry_batch_sampling():
    """run_mimicry_batch samples candidate posts up to max_posts."""
    state = get_default_state()
    candidates = [
        {"post_num": i, "text": f"Пост номер {i} в треде", "board_id": "b"}
        for i in range(100, 120)  # 20 candidate posts
    ]

    mock_add_queue = AsyncMock()
    with patch("common.database.add_reaction_to_queue", mock_add_queue):
        results = await run_mimicry_batch(
            board_id="b",
            candidate_posts=candidates,
            sample_ratio=0.25,
            max_posts=4,
            state=state
        )

    assert 1 <= len(results) <= 4
    for res in results:
        assert res["post_num"] in state["processed_post_nums"]
        assert res["persona"] in PERSONAS
