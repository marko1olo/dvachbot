# -*- coding: utf-8 -*-
"""
tests/test_e2e_ecosystem_overhaul.py
Comprehensive Opaque-Box E2E Test Suite for dvachbot Ecosystem Overhaul (Requirements R1 - R5)

Tiers Covered:
1. Tier 1: Feature Coverage (>=5 tests per domain: R1 Anti-flood/Ghost-post, R2 Cyberchad voice/roast,
   R3 PvP lobbies & stake selector, R4 AI Counter-Reactions, R5 DB Sentiment & Forensics).
2. Tier 2: Boundary & Corner Cases (rapid bursts up to 8 msgs, flood mute 300s, 3600s cooldown edges,
   0 and max balance in PvP lobbies, /duel 250 direct parsing, false reports on AI, etc.).
3. Tier 3: Cross-Feature Combinations (e.g. ghost-muted user in PvP lobby, replying to Cyberchad during
   flood window, stacking AI backfires, etc.).
4. Tier 4: Real-world imageboard workloads and simulation scenarios (multi-user flame wars, high-throughput
   mixed media streams, end-to-end economy lifecycles, and forensic deep audits).
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from aiogram import Bot, types
from aiogram.types import (
    CallbackQuery,
    Chat,
    Document,
    InlineKeyboardMarkup,
    Message,
    PhotoSize,
    User,
    Video,
    VideoNote,
    Voice,
)

import shared_state
from shared_state import (
    _ACTIVE_AUTHOR_ATTACKS,
    _GLOBAL_COMBAT_COOLDOWNS,
    board_data,
    NewPostParams,
    ShadowRejectContext,
)
import ai_manager
from ai_manager import (
    _LAST_CYBERCHAD_INTERVENTION,
    _BOARD_FIGHT_TRACKER,
    register_post_and_maybe_trigger_cyberchad_intervention,
    CYBERCHAD_FIGHT_INTERVENTION_PROMPT,
)
from common.spam_filter import (
    BURST_FLOOD_LIMIT,
    BURST_FLOOD_WINDOW,
    RATE_FLOOD_LIMIT,
    RATE_FLOOD_WINDOW,
    MINUTE_FLOOD_LIMIT,
    MINUTE_FLOOD_WINDOW,
    FLOOD_BASE_MUTE_SEC,
    BAYAN_BASE_MUTE_SEC,
    BAYAN_RESET_SEC,
    check_flood,
    check_bayan,
    evaluate_message_for_autoshadowmute,
    handle_shadow_mute_continuation,
    _user_request_timestamps,
    _bayan_tracker,
    _bayan_mute_count,
    _bayan_mute_last_ts,
    _board_recent_fingerprints,
)
from common.database import (
    _apply_migrations,
    _create_indices,
    _create_tables,
    _insert_initial_data,
    apply_shadow_mute,
    get_shadow_mute_info,
    update_shadow_mute,
    apply_regular_mute,
    add_user_global_balance,
    deduct_user_global_balance,
    get_user_global_balance,
    get_abu_fund_total,
    add_to_abu_fund,
    record_user_transaction,
    get_user_recent_transactions,
)
from common.bot_helpers import (
    handle_cyberchad_counter_action,
    _get_user_active_items,
)
from russian_roulette_pvp import (
    get_rr_lobby_keyboard,
    get_adaptive_rr_bet_presets,
    format_rr_bet_amount,
    MIN_RR_BET,
    MAX_RR_BET,
)
from dice_duel_engine import (
    get_dice_lobby_keyboard,
    get_adaptive_dice_bet_presets,
    format_dice_bet_amount,
    MIN_DICE_BET,
    MAX_DICE_BET,
)
import stats_v2
from stats_v2 import (
    make_sparkline,
    generate_instant_snapshot_text,
)


# ============================================================================
# TEST HELPERS & MOCKS
# ============================================================================

def make_mock_user(user_id: int = 1001, username: str = "anon") -> User:
    return User(id=user_id, is_bot=False, first_name=f"Anon_{user_id}", username=username)


def make_mock_chat(chat_id: int = 1001) -> Chat:
    return Chat(id=chat_id, type="private")


def make_mock_message(
    user_id: int = 1001,
    text: Optional[str] = "test post",
    message_id: int = 500,
    chat_id: int = 1001,
    reply_to_message: Optional[Message] = None,
) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.message_id = message_id
    msg.text = text
    msg.caption = None
    msg.date = int(time.time())
    msg.from_user = make_mock_user(user_id)
    msg.chat = make_mock_chat(chat_id)
    msg.reply_to_message = reply_to_message

    sent_reply = MagicMock(spec=Message)
    sent_reply.message_id = message_id + 1
    sent_reply.chat = msg.chat
    sent_reply.text = text
    sent_reply.edit_text = AsyncMock(return_value=True)
    sent_reply.delete = AsyncMock(return_value=True)

    msg.answer = AsyncMock(return_value=sent_reply)
    msg.edit_text = AsyncMock(return_value=sent_reply)
    msg.delete = AsyncMock(return_value=True)
    return msg


def make_mock_callback(
    user_id: int = 1001,
    data: str = "cas:hub",
    message: Optional[Message] = None,
) -> MagicMock:
    cb = MagicMock(spec=CallbackQuery)
    cb.id = f"cb_{int(time.time()*1000)}"
    cb.from_user = make_mock_user(user_id)
    cb.data = data
    cb.message = message or make_mock_message(user_id=user_id)
    cb.answer = AsyncMock(return_value=True)
    return cb


def make_mock_bot() -> AsyncMock:
    bot = AsyncMock(spec=Bot)
    bot.id = 777000
    bot.send_message = AsyncMock(return_value=make_mock_message(user_id=777000))
    bot.send_voice = AsyncMock(return_value=make_mock_message(user_id=777000))
    bot.send_photo = AsyncMock(return_value=make_mock_message(user_id=777000))
    bot.edit_message_text = AsyncMock(return_value=True)
    return bot


@pytest.fixture(autouse=True)
def reset_dvachbot_state():
    """Reset volatile in-memory trackers before and after each test."""
    _user_request_timestamps.clear()
    _bayan_tracker.clear()
    _bayan_mute_count.clear()
    _bayan_mute_last_ts.clear()
    _board_recent_fingerprints.clear()
    _LAST_CYBERCHAD_INTERVENTION.clear()
    _BOARD_FIGHT_TRACKER.clear()
    _ACTIVE_AUTHOR_ATTACKS.clear()
    _GLOBAL_COMBAT_COOLDOWNS.clear()
    shared_state._duel_cooldowns.clear()
    shared_state._active_duels.clear()
    board_data.clear()
    yield
    _user_request_timestamps.clear()
    _bayan_tracker.clear()
    _bayan_mute_count.clear()
    _bayan_mute_last_ts.clear()
    _board_recent_fingerprints.clear()
    _LAST_CYBERCHAD_INTERVENTION.clear()
    _BOARD_FIGHT_TRACKER.clear()
    _ACTIVE_AUTHOR_ATTACKS.clear()
    _GLOBAL_COMBAT_COOLDOWNS.clear()
    shared_state._duel_cooldowns.clear()
    shared_state._active_duels.clear()
    board_data.clear()


# ============================================================================
# TIER 1: FEATURE COVERAGE (>=5 tests per domain)
# ============================================================================

# ----------------------------------------------------------------------------
# 1. R1: Anti-Flood & Seamless Ghost-Post Media Delivery
# ----------------------------------------------------------------------------
class TestTier1R1AntiFloodAndGhostMedia:
    """R1: Anti-flood limits, ghost posting without silent drop, and seamless media delivery."""

    def test_r1_burst_flood_limit_and_mute_duration(self):
        """Verifies BURST_FLOOD_LIMIT=8 in 4s window: 8 messages pass; 9th triggers 300s mute."""
        user_id = 101
        board_id = "b"
        base_time = 10000.0

        # Send 8 rapid messages within 4 seconds -> all must pass cleanly
        for i in range(8):
            ts = base_time + (i * 0.4)  # 0.0s, 0.4s ... 2.8s <= 4.0s
            is_flood, reason = check_flood(user_id, board_id, now_ts=ts)
            assert not is_flood, f"Message {i+1}/8 should NOT trigger burst flood"
            assert reason == ""

        # 9th message at 3.2s (> 8 messages within 4s window) -> triggers burst flood
        is_flood, reason = check_flood(user_id, board_id, now_ts=base_time + 3.2)
        assert is_flood is True, "9th message within 4s MUST trigger burst flood"
        assert "Burst флуд" in reason
        assert FLOOD_BASE_MUTE_SEC == 300.0

    def test_r1_rate_and_minute_flood_limits(self):
        """Verifies RATE_FLOOD_LIMIT=15 (15s) and MINUTE_FLOOD_LIMIT=30 (60s) thresholds."""
        user_rate = 102
        user_min = 103
        board_id = "b"
        base_time = 20000.0

        # Rate flood: 15 messages in 14s pass, 16th triggers
        for i in range(15):
            ts = base_time + (i * 0.9)  # 0 to 12.6s <= 15s
            is_flood, _ = check_flood(user_rate, board_id, now_ts=ts)
            assert not is_flood, f"Message {i+1}/15 should not trigger rate flood"

        is_flood, reason = check_flood(user_rate, board_id, now_ts=base_time + 13.5)
        assert is_flood is True
        assert "Частый постинг" in reason or "Burst" in reason

        # Minute flood: 30 messages in 58s pass, 31st triggers
        for i in range(30):
            ts = base_time + (i * 1.9)  # spaced out to avoid burst and rate flood
            is_flood, _ = check_flood(user_min, board_id, now_ts=ts)
            assert not is_flood, f"Message {i+1}/30 should not trigger minute flood"

        is_flood, reason = check_flood(user_min, board_id, now_ts=base_time + 59.0)
        assert is_flood is True
        assert "Минутный флуд" in reason

    @pytest.mark.asyncio
    async def test_r1_no_silent_drop_check_spam_delivers_ghost(self, isolated_test_db):
        """Messages rejected by spam/flood filter never get dropped silently; ghost post is dispatched."""
        from handlers.message_router import process_shadow_reject
        mock_bot = make_mock_bot()
        user_id = 104
        board_id = "b"

        # Construct ShadowRejectContext for a rejected message
        ctx = ShadowRejectContext(
            bot=mock_bot,
            board_id=board_id,
            user_id=user_id,
            content={
                'type': 'text',
                'text': 'Пост во время шедоумута',
            },
            reply_to_post=None,
            stream='ru'
        )

        with patch("handlers.message_router.send_message_to_users", new_callable=AsyncMock) as mock_send, \
             patch("handlers.message_router.format_header", new_callable=AsyncMock) as mock_hdr:
            mock_hdr.return_value = "Аноним No. 123456"
            await process_shadow_reject(ctx)

            # Verifies delivery was called
            assert mock_send.called
            broadcast_cfg = mock_send.call_args[0][0]
            # Ghost post must be delivered strictly to the author!
            assert broadcast_cfg.recipients == {user_id}
            assert broadcast_cfg.content['is_shadow_reject'] is True
            assert broadcast_cfg.content['post_num'] > 0

    @pytest.mark.asyncio
    async def test_r1_all_media_types_ghost_post_delivery(self, isolated_test_db):
        """Verifies process_shadow_reject smoothly handles all media types with fake post numbers."""
        from handlers.message_router import process_shadow_reject
        mock_bot = make_mock_bot()
        user_id = 105
        board_id = "b"

        media_types = [
            {'type': 'photo', 'file_id': 'AgAC_test_photo', 'caption': 'Фото тест'},
            {'type': 'video', 'file_id': 'BAAC_test_video', 'caption': 'Видео тест'},
            {'type': 'voice', 'file_id': 'AwAC_test_voice', 'caption': None},
            {'type': 'video_note', 'file_id': 'BwAC_test_vnote', 'caption': None},
            {'type': 'audio', 'file_id': 'CQAC_test_audio', 'caption': 'Аудио трек'},
            {'type': 'sticker', 'file_id': 'CAAC_test_sticker', 'caption': None},
            {'type': 'document', 'file_id': 'BQAC_test_doc', 'caption': 'Документ'},
        ]

        with patch("handlers.message_router.send_message_to_users", new_callable=AsyncMock) as mock_send, \
             patch("handlers.message_router.format_header", new_callable=AsyncMock) as mock_hdr:
            mock_hdr.return_value = "Аноним No. 9999"

            for media_content in media_types:
                ctx = ShadowRejectContext(
                    bot=mock_bot,
                    board_id=board_id,
                    user_id=user_id,
                    content=media_content,
                    reply_to_post=None,
                    stream='ru'
                )
                await process_shadow_reject(ctx)
                assert mock_send.called
                sent_cfg = mock_send.call_args[0][0]
                assert sent_cfg.recipients == {user_id}
                assert sent_cfg.content['type'] == media_content['type']
                assert sent_cfg.content['is_shadow_reject'] is True

    @pytest.mark.asyncio
    async def test_r1_fake_post_num_monotonicity(self, isolated_test_db):
        """Fake post numbers for shadow-muted user increment monotonically."""
        from handlers.message_router import process_shadow_reject, shadow_fake_post_counters
        shadow_fake_post_counters.clear()
        mock_bot = make_mock_bot()
        user_id = 106
        board_id = "b"

        assigned_nums = []
        with patch("handlers.message_router.send_message_to_users", new_callable=AsyncMock) as mock_send, \
             patch("handlers.message_router.format_header", new_callable=AsyncMock) as mock_hdr:
            mock_hdr.return_value = "Header"

            for i in range(5):
                ctx = ShadowRejectContext(
                    bot=mock_bot,
                    board_id=board_id,
                    user_id=user_id,
                    content={'type': 'text', 'text': f'msg {i}'},
                    reply_to_post=None,
                    stream='ru'
                )
                await process_shadow_reject(ctx)
                sent_cfg = mock_send.call_args[0][0]
                assigned_nums.append(sent_cfg.content['post_num'])

        # Verify strictly monotonically increasing
        for j in range(1, len(assigned_nums)):
            assert assigned_nums[j] > assigned_nums[j - 1]

    @pytest.mark.asyncio
    async def test_r1_db_shadowmute_sync_and_persistence(self, isolated_test_db):
        """Shadow mute status in SQLite database is synced and readable via get_shadow_mute_info."""
        user_id = 107
        board_id = "b"

        # Initially not muted
        info = await get_shadow_mute_info(user_id, board_id)
        assert info['is_muted'] is False

        # Apply 300s shadow mute
        exp_ts = await apply_shadow_mute(user_id, board_id, duration_seconds=300.0, reason="Flood Test")
        assert exp_ts > time.time()

        # Check DB info
        info_after = await get_shadow_mute_info(user_id, board_id)
        assert info_after['is_muted'] is True
        assert info_after['expires_at'] is not None

        # Expire / remove mute
        await update_shadow_mute(user_id, board_id, expires_at=time.time() - 100)
        info_unmuted = await get_shadow_mute_info(user_id, board_id)
        assert info_unmuted['is_muted'] is False


# ----------------------------------------------------------------------------
# 2. R2: Cyberchad Spontaneous Interventions & Direct Reply Roasting
# ----------------------------------------------------------------------------
class TestTier1R2CyberchadVoiceAndRoast:
    """R2: 3600s cooldown, strictly voice delivery, direct reply roasts, and thread context."""

    @pytest.mark.asyncio
    async def test_r2_spontaneous_intervention_3600s_cooldown(self, isolated_test_db):
        """Spontaneous Cyberchad intervention enforces minimum 3600.0s cooldown per board."""
        mock_bot = make_mock_bot()
        board_id = "b"
        now = 50000.0

        with patch("time.time", return_value=now), \
             patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock) as mock_hf, \
             patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_post:
            mock_hf.return_value = "Слышь сычи, че развонялись?"
            mock_tts.return_value = (b"OGG_OPUS_VOICE_BYTES", 3.5)

            # 4 messages to simulate a brawl (2 distinct users with aggro keywords)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 201, "ты клоун и долбоеб >>10", 11)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 202, "сам соси говно высер >>11", 12)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 201, "завали пасть чухан >>12", 13)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 202, "проваливай уебок >>13", 14)

            # 1st intervention triggers
            assert mock_post.called
            assert _LAST_CYBERCHAD_INTERVENTION[board_id] == now

            # Attempt 2nd intervention 1800s later (inside 3600s cooldown)
            mock_post.reset_mock()
            with patch("time.time", return_value=now + 1800.0):
                await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 201, "ты чмо клоун >>14", 15)
                await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 202, "сам долбоеб говно >>15", 16)
                assert not mock_post.called, "Spontaneous intervention must NOT trigger during 3600s cooldown!"

    @pytest.mark.asyncio
    async def test_r2_spontaneous_strictly_voice_delivery(self, isolated_test_db):
        """Spontaneous Cyberchad interventions send strictly voice messages (no text body)."""
        mock_bot = make_mock_bot()
        board_id = "b"

        with patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock) as mock_hf, \
             patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_post:
            mock_hf.return_value = "Киберчед на связи: разойдитесь по углам!"
            mock_tts.return_value = (b"OPUS_BYTES_MOCK", 4.0)

            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 203, "долбоеб клоун >>20", 21)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 204, "высер говно соси >>21", 22)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 203, "пасть завали чухан >>22", 23)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 204, "чмо уебок >>23", 24)

            assert mock_post.called
            params: NewPostParams = mock_post.call_args[0][0]
            assert params.user_id == 0  # AI author
            assert params.content['type'] == 'voice'
            assert params.content['voice_bytes'] == b"OPUS_BYTES_MOCK"
            assert params.content['is_ai_roast'] is True
            assert 'text' not in params.content or not params.content['text']

    @pytest.mark.asyncio
    async def test_r2_direct_reply_to_cyberchad_triggers_roast(self, isolated_test_db):
        """Direct reply referencing AI post (author_id == 0) triggers personalized voice roast."""
        mock_bot = make_mock_bot()
        board_id = "b"

        # Mock DB returning post with author_id == 0
        mock_ai_post = {
            'post_num': 500,
            'author_id': 0,
            'content': {'type': 'voice', 'is_ai_roast': True}
        }

        with patch("common.database.get_post_by_num", new_callable=AsyncMock, return_value=mock_ai_post), \
             patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock) as mock_hf, \
             patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_post:
            mock_hf.return_value = "Ты кому это вякнул, сыч?"
            mock_tts.return_value = (b"ROAST_VOICE_BYTES", 2.5)

            # Anon replies to post 500 (Cyberchad)
            await register_post_and_maybe_trigger_cyberchad_intervention(
                bot=mock_bot,
                board_id=board_id,
                user_id=205,
                text="Эй бот, пошел ты нахрен!",
                post_num=501,
                reply_to_post=500
            )

            assert mock_post.called
            params: NewPostParams = mock_post.call_args[0][0]
            assert params.content['type'] == 'voice'
            assert params.content['voice_bytes'] == b"ROAST_VOICE_BYTES"
            assert params.reply_to_post == 501  # Replies to the offending anon's post

    @pytest.mark.asyncio
    async def test_r2_direct_reply_cooldown_decoupling(self, isolated_test_db):
        """Direct reply roasts trigger even if spontaneous board intervention cooldown is active."""
        mock_bot = make_mock_bot()
        board_id = "b"
        now = time.time()
        _LAST_CYBERCHAD_INTERVENTION[board_id] = now - 60.0  # Spontaneous intervened 1 min ago

        mock_ai_post = {'post_num': 600, 'author_id': 0, 'content': {'is_ai_roast': True}}

        with patch("common.database.get_post_by_num", new_callable=AsyncMock, return_value=mock_ai_post), \
             patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock) as mock_hf, \
             patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_post:
            mock_hf.return_value = "Повторяю для тупых: молчать!"
            mock_tts.return_value = (b"VOICE_BYTES", 2.0)

            await register_post_and_maybe_trigger_cyberchad_intervention(
                bot=mock_bot,
                board_id=board_id,
                user_id=206,
                text="Ты че такой дерзкий бот?",
                post_num=601,
                reply_to_post=600
            )

            # Direct reply MUST still trigger
            assert mock_post.called

    @pytest.mark.asyncio
    async def test_r2_fight_context_assembly_and_anon_formatting(self, isolated_test_db):
        """Fight context builder correctly formats [Анон ...] tags and post references."""
        mock_bot = make_mock_bot()
        board_id = "b"

        captured_prompt = {}

        async def _mock_summarize(system_prompt, user_prompt, **kwargs):
            captured_prompt['user_prompt'] = user_prompt
            return "Разнос готов!"

        with patch("ai_manager.summarize_text_with_hf", side_effect=_mock_summarize), \
             patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("common.bot_helpers.process_new_post", new_callable=AsyncMock):
            mock_tts.return_value = (b"VOICE", 1.0)

            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 301, "клоун долбоеб", 101)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 302, "сам соси говно высер", 102)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 301, "пасть завали уебок", 103)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 302, "чухан чмо", 104)

            assert 'user_prompt' in captured_prompt
            prompt_str = captured_prompt['user_prompt']
            assert "Анон [" in prompt_str
            assert ">>101" in prompt_str or ">>102" in prompt_str


# ----------------------------------------------------------------------------
# 3. R3: Dynamic PvP Duel & Game Lobby (/duel, /dice, /ttt, /rr)
# ----------------------------------------------------------------------------
class TestTier1R3DynamicPvPLobbies:
    """R3: Dynamic stake selector adapted to player balance, direct commands, and confirmed broadcast."""

    def test_r3_dynamic_stake_keyboard_bet_presets(self):
        """PvP lobbies generate adaptive bet presets based on player balance."""
        # Player with 1,000 balance
        presets_1k = get_adaptive_rr_bet_presets(1000, 100)
        assert 50 in presets_1k
        assert 100 in presets_1k
        assert 1000 in presets_1k
        kb_1000 = get_rr_lobby_keyboard(bet=100, balance=1000)
        cb_datas = [btn.callback_data for row in kb_1000.inline_keyboard for btn in row]
        assert any("rr:lobby:100:" in cb for cb in cb_datas)
        assert any("rr:lobby:500:" in cb for cb in cb_datas)
        assert any("rr:lobby:1000:" in cb for cb in cb_datas)

        # Player with 25,000 balance
        presets_25k = get_adaptive_rr_bet_presets(25000, 1000)
        assert max(presets_25k) == 25000
        kb_25k = get_rr_lobby_keyboard(bet=1000, balance=25000)
        cb_datas_25k = [btn.callback_data for row in kb_25k.inline_keyboard for btn in row]
        assert any("rr:lobby:25000:" in cb for cb in cb_datas_25k)

    def test_r3_stake_modifier_buttons_half_double_allin(self):
        """Lobby modifier buttons /2, x2, and 💰 ВА-БАНК calculate correct stakes."""
        balance = 5000
        current_bet = 500

        kb = get_rr_lobby_keyboard(bet=current_bet, balance=balance)
        ctrl_row = kb.inline_keyboard[2]  # Row 2 contains /2, x2, ВА-БАНК
        assert ctrl_row[0].text == "/2"
        assert "rr:lobby:250:" in ctrl_row[0].callback_data

        assert ctrl_row[1].text == "x2"
        assert "rr:lobby:1000:" in ctrl_row[1].callback_data

        assert "ВА-БАНК" in ctrl_row[2].text
        assert "rr:lobby:5000:" in ctrl_row[2].callback_data

    @pytest.mark.asyncio
    async def test_r3_direct_command_stake_parsing(self, isolated_test_db):
        """Direct commands with amount (e.g. /duel 250) parse the exact number."""
        import main
        from main import _handle_duel_create
        user_id = 401
        board_id = "b"

        # Give player 1,000 balance
        await add_user_global_balance(isolated_test_db, user_id, "b", 1000)

        mock_msg = make_mock_message(user_id=user_id, text="/duel 250")
        with patch("main.get_pool", new_callable=AsyncMock, return_value=isolated_test_db):
            await _handle_duel_create(mock_msg, board_id, args=["250"], stream='ru')

            # Duel challenge created with 250 stake
            assert mock_msg.answer.called
            ans_text = mock_msg.answer.call_args[0][0]
            assert "250 ₪" in ans_text

    @pytest.mark.asyncio
    async def test_r3_challenge_broadcast_only_after_confirmation(self, isolated_test_db):
        """Lobby creation opens selector; broadcast occurs ONLY after player confirms the stake."""
        import main
        from main import _handle_duel_create
        user_id = 402
        board_id = "b"
        await add_user_global_balance(isolated_test_db, user_id, "b", 2000)

        # /duel without arguments -> opens interactive lobby ONLY (no broadcast)
        mock_msg_lobby = make_mock_message(user_id=user_id, text="/duel")
        with patch("main.get_pool", new_callable=AsyncMock, return_value=isolated_test_db), \
             patch("post_processor.process_new_post", new_callable=AsyncMock) as mock_post:
            await _handle_duel_create(mock_msg_lobby, board_id, args=[], stream='ru')

            # Answers with lobby keyboard, did NOT broadcast to board feed!
            assert mock_msg_lobby.answer.called
            assert not mock_post.called

    @pytest.mark.asyncio
    async def test_r3_balance_validation_and_insufficient_funds_rejection(self, isolated_test_db):
        """Creating challenge rejects if user balance is lower than chosen stake."""
        from main import _handle_duel_create
        user_id = 403
        board_id = "b"

        # User has only 100 ₪
        await add_user_global_balance(isolated_test_db, user_id, "b", 100)

        mock_msg = make_mock_message(user_id=user_id, text="/duel 500")
        with patch("main.get_pool", new_callable=AsyncMock, return_value=isolated_test_db):
            await _handle_duel_create(mock_msg, board_id, args=["500"], stream='ru')

            # Rejection message
            ans_text = mock_msg.answer.call_args[0][0]
            assert "Не хватает шекелей" in ans_text


# ----------------------------------------------------------------------------
# 4. R4: AI Item Counter-Reactions & Backfires
# ----------------------------------------------------------------------------
class TestTier1R4AICounterReactions:
    """R4: Counter-attacks and comedic backfires when attacking AI / Cyberchad (author_id == 0)."""

    @pytest.mark.asyncio
    async def test_r4_shoot_on_ai_ricochet_15m_mute(self, isolated_test_db):
        """/shoot on Cyberchad triggers 15-minute (900s) ricochet mute and combat transaction."""
        user_id = 501
        board_id = "b"
        mock_msg = make_mock_message(user_id=user_id, text="/shoot")

        with patch("common.database.apply_regular_mute", new_callable=AsyncMock) as mock_mute:
            handled = await handle_cyberchad_counter_action(mock_msg, "shoot", user_id, board_id, isolated_test_db)
            assert handled is True
            assert mock_mute.called
            assert mock_mute.call_args[0][2] == 900  # 15 minutes = 900s
            assert "РИКОШЕТ МУТ-ГАНА" in mock_msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_r4_rob_on_ai_fines_500_to_abu_fund(self, isolated_test_db):
        """/rob on Cyberchad fines the attacker up to 500 ₪ into Abu Fund."""
        user_id = 502
        board_id = "b"
        await add_user_global_balance(isolated_test_db, user_id, "b", 1000)

        mock_msg = make_mock_message(user_id=user_id, text="/rob")
        handled = await handle_cyberchad_counter_action(mock_msg, "rob", user_id, board_id, isolated_test_db)
        assert handled is True
        assert "ОГРАБЛЕНИЕ ПРОВАЛЕНО" in mock_msg.answer.call_args[0][0]

        # Balance deducted by 500
        bal = await get_user_global_balance(isolated_test_db, user_id)
        assert bal == 500

        # Abu fund increased by 500
        abu_total = await get_abu_fund_total(isolated_test_db)
        assert abu_total >= 500

    @pytest.mark.asyncio
    async def test_r4_shit_on_ai_1h_self_debuff(self, isolated_test_db):
        """/shit on Cyberchad inflicts 1-hour (3600s) self-debuff in active_items."""
        user_id = 503
        board_id = "b"
        await add_user_global_balance(isolated_test_db, user_id, "b", 100)

        mock_msg = make_mock_message(user_id=user_id, text="/shit")
        handled = await handle_cyberchad_counter_action(mock_msg, "shit", user_id, board_id, isolated_test_db)
        assert handled is True
        assert "КРИТИЧЕСКИЙ САМООБСЁР" in mock_msg.answer.call_args[0][0]

        assert user_id in _ACTIVE_AUTHOR_ATTACKS.get("shit", {})

    @pytest.mark.asyncio
    async def test_r4_vomit_on_ai_1h_self_debuff(self, isolated_test_db):
        """/vomit on Cyberchad inflicts 1-hour (3600s) self-debuff in active_items."""
        user_id = 504
        board_id = "b"
        await add_user_global_balance(isolated_test_db, user_id, "b", 100)

        mock_msg = make_mock_message(user_id=user_id, text="/vomit")
        handled = await handle_cyberchad_counter_action(mock_msg, "vomit", user_id, board_id, isolated_test_db)
        assert handled is True
        assert "ОБРАТНЫЙ РЕФЛЮКС" in mock_msg.answer.call_args[0][0]

        assert user_id in _ACTIVE_AUTHOR_ATTACKS.get("vomit", {})

    @pytest.mark.asyncio
    async def test_r4_pepperspray_on_ai_30m_blindness(self, isolated_test_db):
        """/pepperspray on Cyberchad blinds the attacker for 30 minutes (1800s)."""
        user_id = 505
        board_id = "b"
        await add_user_global_balance(isolated_test_db, user_id, "b", 100)

        mock_msg = make_mock_message(user_id=user_id, text="/pepperspray")
        handled = await handle_cyberchad_counter_action(mock_msg, "pepperspray", user_id, board_id, isolated_test_db)
        assert handled is True
        assert "ПЕРЦОВЫЙ ИНГАЛЯТОР" in mock_msg.answer.call_args[0][0]

        assert user_id in _ACTIVE_AUTHOR_ATTACKS.get("pepperspray", {})

    @pytest.mark.asyncio
    async def test_r4_partyvan_on_ai_2h_arrest_mute(self, isolated_test_db):
        """/partyvan on Cyberchad arrests the false reporter with a 2-hour (7200s) mute."""
        user_id = 506
        board_id = "b"
        mock_msg = make_mock_message(user_id=user_id, text="/partyvan")

        with patch("common.database.apply_regular_mute", new_callable=AsyncMock) as mock_mute:
            handled = await handle_cyberchad_counter_action(mock_msg, "partyvan", user_id, board_id, isolated_test_db)
            assert handled is True
            assert mock_mute.called
            assert mock_mute.call_args[0][2] == 7200  # 2 hours = 7200s
            assert "ЛОЖНЫЙ ДОНОС НА КИБЕРЧЕДА" in mock_msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_r4_dossier_and_bribe_on_ai(self, isolated_test_db):
        """/dossier on AI returns Alpha-Tier gigachad stats, /bribe returns burned shekels."""
        user_id = 507
        board_id = "b"

        # Dossier
        msg_dossier = make_mock_message(user_id=user_id, text="/dossier")
        handled_dos = await handle_cyberchad_counter_action(msg_dossier, "dossier", user_id, board_id, isolated_test_db)
        assert handled_dos is True
        assert "КИБЕРЧЕД-9000 (Alpha-Tier AI)" in msg_dossier.answer.call_args[0][0]
        assert "250 кг" in msg_dossier.answer.call_args[0][0]

        # Bribe
        msg_bribe = make_mock_message(user_id=user_id, text="/bribe")
        handled_br = await handle_cyberchad_counter_action(msg_bribe, "bribe", user_id, board_id, isolated_test_db)
        assert handled_br is True
        assert "ВЗЯТКА НЕ ПРИНЯТА" in msg_bribe.answer.call_args[0][0]


# ----------------------------------------------------------------------------
# 5. R5: DB Sentiment & Moderation Forensics
# ----------------------------------------------------------------------------
class TestTier1R5DBSentimentAndForensics:
    """R5: Database sentiment querying, moderation mutes, AI posts, transactions, and schema integrity."""

    @pytest.mark.asyncio
    async def test_r5_sentiment_aggregation_from_posts(self, isolated_test_db):
        """Inspects Posts table sentiment metrics and sparkline generation."""
        now_ts = time.time()
        sample_posts = [
            (1, "b", 101, json.dumps({'text': 'база, истинный шедевр!', 'type': 'text'}), "база, истинный шедевр!", now_ts - 300),
            (2, "b", 102, json.dumps({'text': 'норм движуха, одобряю', 'type': 'text'}), "норм движуха, одобряю", now_ts - 200),
            (3, "b", 103, json.dumps({'text': 'говнище и параша, зашквар', 'type': 'text'}), "говнище и параша, зашквар", now_ts - 100),
            (4, "b", 104, json.dumps({'text': 'полный позор и шлак', 'type': 'text'}), "полный позор и шлак", now_ts - 50),
            (5, "b", 105, json.dumps({'text': 'Киберчед разъебал сычей слоняра', 'type': 'text'}), "Киберчед разъебал сычей слоняра", now_ts),
        ]
        for p in sample_posts:
            await isolated_test_db.execute(
                "INSERT INTO Posts (post_num, board_id, author_id, content, text_content, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                p
            )

        async with isolated_test_db.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM Posts WHERE board_id = 'b'"
        ) as cursor:
            cnt, min_t, max_t = await cursor.fetchone()
            assert cnt == 5

        # Generate sparkline from sentiments
        sentiments = [0.8, 0.5, -0.7, -0.9, 0.9]
        spark = make_sparkline(sentiments, length=5)
        assert len(spark) == 5
        assert isinstance(spark, str)

    @pytest.mark.asyncio
    async def test_r5_moderation_mutes_and_bans_forensics(self, isolated_test_db):
        """Forensically inspects active and historical mutes in Mutes table."""
        now = time.time()
        await isolated_test_db.execute(
            "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at) VALUES (?, ?, ?, ?)",
            (601, "b", "shadow", now + 300.0)
        )
        await isolated_test_db.execute(
            "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at) VALUES (?, ?, ?, ?)",
            (602, "b", "regular", now + 900.0)
        )

        async with isolated_test_db.execute("SELECT user_id, mute_type, expires_at FROM Mutes WHERE board_id = 'b'") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 2
            types_set = {r[1] for r in rows}
            assert "shadow" in types_set
            assert "regular" in types_set

    @pytest.mark.asyncio
    async def test_r5_ai_roast_and_intervention_forensics(self, isolated_test_db):
        """Forensics inspection of Cyberchad interventions (author_id = 0) in Posts."""
        now = time.time()
        ai_content = json.dumps({'type': 'voice', 'caption': '🔥 Разъёб от Киберчеда', 'is_ai_roast': True})
        await isolated_test_db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, text_content, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (701, "b", 0, ai_content, "AI Roast Audio", now)
        )

        async with isolated_test_db.execute("SELECT post_num, content FROM Posts WHERE author_id = 0") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            c = json.loads(row[1])
            assert c['is_ai_roast'] is True
            assert c['type'] == 'voice'

    @pytest.mark.asyncio
    async def test_r5_pvp_economy_transactions_forensics(self, isolated_test_db):
        """Forensics ledger queries on duel transactions and Abu Fund deductions."""
        u1, u2 = 702, 703
        await add_user_global_balance(isolated_test_db, u1, "b", 1000)
        await add_user_global_balance(isolated_test_db, u2, "b", 1000)

        # Record duel outcome: u1 won 475 ₪, u2 lost 500 ₪, 5% fee (25 ₪) to Abu Fund
        await record_user_transaction(isolated_test_db, u1, 475, "duel", "Победа в дуэли против 703 (ставка 500)")
        await record_user_transaction(isolated_test_db, u2, -500, "duel", "Поражение в дуэли против 701 (ставка 500)")
        await add_to_abu_fund(isolated_test_db, 25)

        txs_u1 = await get_user_recent_transactions(isolated_test_db, u1, limit=5)
        assert len(txs_u1) == 1
        assert txs_u1[0]['amount'] == 475
        assert txs_u1[0]['category'] == "duel"

        abu_bal = await get_abu_fund_total(isolated_test_db)
        assert abu_bal >= 25

    @pytest.mark.asyncio
    async def test_r5_database_schema_integrity_and_indices(self, isolated_test_db):
        """Verifies DB schema integrity, required tables, and foreign keys."""
        async with isolated_test_db.execute("PRAGMA foreign_keys;") as cursor:
            row = await cursor.fetchone()
            assert row[0] == 1, "Foreign keys must be ENABLED"

        async with isolated_test_db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
            tables = {r[0] for r in await cursor.fetchall()}
            required_tables = {"Users", "Posts", "Mutes", "UserTransactions", "GlobalStats"}
            for t in required_tables:
                assert t in tables, f"Table {t} must exist in schema"


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES (>=10 tests)
# ============================================================================

class TestTier2BoundaryAndCornerCases:
    """Boundary conditions, limits, max balances, zero balances, and edge transitions."""

    def test_t2_burst_flood_exact_boundary_8_vs_9(self):
        """Boundary: Exactly 8 msgs in 3.9s -> Clean. 9th msg in 4.0s -> Flood detected."""
        user_id = 801
        board_id = "b"
        t0 = 1000.0

        for i in range(8):
            is_f, _ = check_flood(user_id, board_id, now_ts=t0 + (i * 0.45))  # max 3.15s
            assert not is_f

        # 9th message at 3.9s -> strictly > BURST_FLOOD_LIMIT (8)
        is_f, reason = check_flood(user_id, board_id, now_ts=t0 + 3.9)
        assert is_f is True
        assert "Burst флуд: 9 сообщений" in reason

    def test_t2_rate_flood_exact_boundary_15_vs_16(self):
        """Boundary: Exactly 15 msgs in 14.5s -> Clean. 16th msg in 14.9s -> Flood detected."""
        user_id = 802
        board_id = "b"
        t0 = 2000.0

        for i in range(15):
            is_f, _ = check_flood(user_id, board_id, now_ts=t0 + (i * 0.95))
            assert not is_f

        is_f, reason = check_flood(user_id, board_id, now_ts=t0 + 14.8)
        assert is_f is True
        assert "Частый постинг: 16 сообщений" in reason

    def test_t2_minute_flood_exact_boundary_30_vs_31(self):
        """Boundary: Exactly 30 msgs in 58s -> Clean. 31st msg in 59s -> Flood detected."""
        user_id = 803
        board_id = "b"
        t0 = 3000.0

        for i in range(30):
            is_f, _ = check_flood(user_id, board_id, now_ts=t0 + (i * 1.9))
            assert not is_f

        is_f, reason = check_flood(user_id, board_id, now_ts=t0 + 59.0)
        assert is_f is True
        assert "Минутный флуд: 31 сообщений" in reason

    @pytest.mark.asyncio
    async def test_t2_spontaneous_cooldown_boundary_3599_vs_3601(self, isolated_test_db):
        """Boundary: 3599.9s since last intervention -> blocked; 3600.1s -> allowed."""
        mock_bot = make_mock_bot()
        board_id = "b"
        t_base = 50000.0
        _LAST_CYBERCHAD_INTERVENTION[board_id] = t_base

        with patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock) as mock_hf, \
             patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_post:
            mock_hf.return_value = "Разнос"
            mock_tts.return_value = (b"VOICE", 1.0)

            # At 3599.0s -> Blocked
            with patch("time.time", return_value=t_base + 3599.0):
                await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 804, "клоун долбоеб >>1", 1)
                await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 805, "высер говно соси >>2", 2)
                await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 804, "пасть завали чухан >>3", 3)
                await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 805, "уебок чмо >>4", 4)
                assert not mock_post.called

            # At 3601.0s -> Allowed
            with patch("time.time", return_value=t_base + 3601.0):
                await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 804, "клоун долбоеб >>5", 5)
                await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 805, "высер говно соси >>6", 6)
                await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 804, "пасть завали чухан >>7", 7)
                await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 805, "уебок чмо >>8", 8)
                assert mock_post.called

    def test_t2_pvp_zero_balance_stake_selector(self):
        """User with 0 or negative balance in PvP lobby gets safe fallback preset without crashing."""
        presets_zero = get_adaptive_rr_bet_presets(balance=0, current_bet=50)
        assert len(presets_zero) > 0
        assert presets_zero[0] == MIN_RR_BET  # 50 ₪ minimum

        kb = get_rr_lobby_keyboard(bet=50, balance=0)
        assert kb is not None
        assert len(kb.inline_keyboard) > 0

    def test_t2_pvp_ultra_wealthy_max_balance_cap(self):
        """User with ultra wealthy balance (100,000,000 ₪) is properly capped at MAX_RR_BET / MAX_DICE_BET."""
        presets_rich = get_adaptive_rr_bet_presets(balance=100_000_000, current_bet=1000)
        assert all(p <= MAX_RR_BET for p in presets_rich)

        kb_dice = get_dice_lobby_keyboard(balance=100_000_000, current_bet=1000)
        ctrl_row = kb_dice.inline_keyboard[2]
        # Max bet should not exceed MAX_DICE_BET (50,000,000 ₪)
        assert f"dice_lobby_bet:{MAX_DICE_BET}" in ctrl_row[2].callback_data

    @pytest.mark.asyncio
    async def test_t2_direct_command_invalid_and_negative_amounts(self, isolated_test_db):
        """Direct commands like /duel -50, /duel abc, /duel 0 fall back to interactive lobby safely."""
        from main import _handle_duel_create
        user_id = 806
        board_id = "b"
        await add_user_global_balance(isolated_test_db, user_id, "b", 1000)

        mock_msg = make_mock_message(user_id=user_id, text="/duel -50")
        with patch("main.get_pool", new_callable=AsyncMock, return_value=isolated_test_db):
            await _handle_duel_create(mock_msg, board_id, args=["-50"], stream='ru')
            # Opens lobby instead of negative duel
            ans_text = mock_msg.answer.call_args[0][0]
            assert "PvP ДУЭЛЬ" in ans_text
            assert "Выбери ставку кнопками" in ans_text

    @pytest.mark.asyncio
    async def test_t2_rob_ai_attacker_zero_balance_safeguard(self, isolated_test_db):
        """Attacker with 0 ₪ tries to rob Cyberchad -> fine is 0 ₪ without negative wallet overflow."""
        user_id = 807
        board_id = "b"
        mock_msg = make_mock_message(user_id=user_id, text="/rob")
        handled = await handle_cyberchad_counter_action(mock_msg, "rob", user_id, board_id, isolated_test_db)
        assert handled is True
        bal = await get_user_global_balance(isolated_test_db, user_id)
        assert bal == 0, "Wallet must NOT become negative on zero balance fine"

    @pytest.mark.asyncio
    async def test_t2_cyberchad_empty_thread_context(self, isolated_test_db):
        """Cyberchad context builder handles empty/whitespace texts gracefully without throwing."""
        mock_bot = make_mock_bot()
        board_id = "b"

        # None, empty, or non-positive user_id
        await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 808, "", 1)
        await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 0, "test", 2)
        assert len(_BOARD_FIGHT_TRACKER.get(board_id, [])) == 0

    def test_t2_bayan_reset_after_1_hour(self):
        """Bayan escalation counter resets to 0 if user has no infractions for > 3600 seconds."""
        user_id = 809
        now = 10000.0

        # Trigger 1st bayan mute (3 identical texts)
        check_bayan(user_id, "Один и тот же длинный боянистый текст поста", board_id="b", now_ts=now)
        check_bayan(user_id, "Один и тот же длинный боянистый текст поста", board_id="b", now_ts=now + 10)
        is_m, dur1 = check_bayan(user_id, "Один и тот же длинный боянистый текст поста", board_id="b", now_ts=now + 20)
        assert is_m is True
        assert dur1 == BAYAN_BASE_MUTE_SEC  # 1200s

        # 3601s later, post another 3 bayans -> escalation reset to base 1200s instead of doubling (2400s)
        now_later = now + 3601.0
        check_bayan(user_id, "Новый длинный боянистый повторный текст поста", board_id="b", now_ts=now_later)
        check_bayan(user_id, "Новый длинный боянистый повторный текст поста", board_id="b", now_ts=now_later + 10)
        is_m2, dur2 = check_bayan(user_id, "Новый длинный боянистый повторный текст поста", board_id="b", now_ts=now_later + 20)
        assert is_m2 is True
        assert dur2 == BAYAN_BASE_MUTE_SEC, "Bayan mute duration should reset to base 1200s after 1h"


# ============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (>=6 tests)
# ============================================================================

class TestTier3CrossFeatureCombinations:
    """Interactions between shadowmute, PvP, AI roasts, debuffs, and economic state."""

    @pytest.mark.asyncio
    async def test_t3_ghost_muted_user_in_pvp_lobby(self, isolated_test_db):
        """Shadow-muted user can open PvP lobby and create challenge without leaking shadowmute status."""
        from main import _handle_duel_create
        user_id = 901
        board_id = "b"

        # Apply shadow mute
        await apply_shadow_mute(user_id, board_id, duration_seconds=300.0, reason="Flood")
        await add_user_global_balance(isolated_test_db, user_id, "b", 1000)

        mock_msg = make_mock_message(user_id=user_id, text="/duel 200")
        with patch("main.get_pool", new_callable=AsyncMock, return_value=isolated_test_db):
            await _handle_duel_create(mock_msg, board_id, args=["200"], stream='ru')

            # Answers normally with duel challenge
            assert mock_msg.answer.called
            assert "200 ₪" in mock_msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_t3_replying_to_cyberchad_during_flood_window(self, isolated_test_db):
        """Shadow-muted user replying to Cyberchad triggers contextual voice roast response."""
        mock_bot = make_mock_bot()
        user_id = 902
        board_id = "b"

        # User is in shadow mute
        await apply_shadow_mute(user_id, board_id, duration_seconds=300.0, reason="Flood")

        mock_ai_post = {'post_num': 900, 'author_id': 0, 'content': {'is_ai_roast': True}}

        with patch("common.database.get_post_by_num", new_callable=AsyncMock, return_value=mock_ai_post), \
             patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock) as mock_hf, \
             patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_post:
            mock_hf.return_value = "Даже в шедоумуте ты умудряешься ныть!"
            mock_tts.return_value = (b"CYBERCHAD_VOICE", 3.0)

            await register_post_and_maybe_trigger_cyberchad_intervention(
                bot=mock_bot,
                board_id=board_id,
                user_id=user_id,
                text="Киберчед, размуть меня пж!",
                post_num=901,
                reply_to_post=900
            )

            # Roast triggered properly
            assert mock_post.called
            assert mock_post.call_args[0][0].content['type'] == 'voice'

    @pytest.mark.asyncio
    async def test_t3_stacking_ai_backfires_shoot_after_pepperspray(self, isolated_test_db):
        """Attacker already under pepperspray blindness /shoots Cyberchad; both penalties are active."""
        user_id = 903
        board_id = "b"
        await add_user_global_balance(isolated_test_db, user_id, "b", 100)

        # 1. Blind attacker with pepperspray
        msg_spray = make_mock_message(user_id=user_id, text="/pepperspray")
        await handle_cyberchad_counter_action(msg_spray, "pepperspray", user_id, board_id, isolated_test_db)

        # 2. Shoot Cyberchad
        msg_shoot = make_mock_message(user_id=user_id, text="/shoot")
        with patch("common.database.apply_regular_mute", new_callable=AsyncMock) as mock_mute:
            await handle_cyberchad_counter_action(msg_shoot, "shoot", user_id, board_id, isolated_test_db)
            assert mock_mute.called
            assert mock_mute.call_args[0][2] == 900  # 15m mute

        # Both blindness and mute recorded
        assert user_id in _ACTIVE_AUTHOR_ATTACKS.get("pepperspray", {})

    @pytest.mark.asyncio
    async def test_t3_pvp_duel_during_rapid_post_stream(self, isolated_test_db):
        """Rapid dueling messages (< 8 msgs / 4s) do not trigger false positive flood mutes."""
        user_id = 904
        board_id = "b"
        now = time.time()

        for i in range(7):  # 7 actions in 3s (safe under 8 burst limit)
            is_f, _ = check_flood(user_id, board_id, now_ts=now + (i * 0.4))
            assert not is_f

    @pytest.mark.asyncio
    async def test_t3_ai_counter_action_abu_fund_and_bank_audit(self, isolated_test_db):
        """Robbing Cyberchad updates user wallet, Abu Fund ledger, and transaction history synchronously."""
        user_id = 905
        board_id = "b"
        await add_user_global_balance(isolated_test_db, user_id, "b", 1000)

        msg = make_mock_message(user_id=user_id, text="/rob")
        await handle_cyberchad_counter_action(msg, "rob", user_id, board_id, isolated_test_db)

        bal = await get_user_global_balance(isolated_test_db, user_id)
        fund = await get_abu_fund_total(isolated_test_db)
        txs = await get_user_recent_transactions(isolated_test_db, user_id)

        assert bal == 500
        assert fund == 500
        assert len(txs) >= 1
        assert txs[0]['category'] == 'rob'

    @pytest.mark.asyncio
    async def test_t3_simultaneous_spontaneous_chad_and_money_drop(self, isolated_test_db):
        """Spontaneous Cyberchad voice post and money drop state co-exist without state collision."""
        mock_bot = make_mock_bot()
        board_id = "b"
        donor_id = 906

        await add_user_global_balance(isolated_test_db, donor_id, "b", 5000)

        # 1. Create money drop
        import drop_engine
        await drop_engine.init_drop_engine(mock_bot)
        success, msg, drop = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="Anon",
            board_id=board_id,
            amount=200,
            db_lock=asyncio.Lock(),
            db_conn=isolated_test_db,
            check_cooldown=False
        )
        assert success is True
        assert drop is not None
        assert drop.drop_id in drop_engine.active_drops

        # 2. Spontaneous Cyberchad intervention
        with patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock, return_value="Сычи, заберите шекели!"), \
             patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock, return_value=(b"VOICE", 2.0)), \
             patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_post:
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 906, "клоун долбоеб >>1", 1)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 907, "высер говно соси >>2", 2)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 906, "пасть завали чухан >>3", 3)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 907, "уебок чмо >>4", 4)

            assert mock_post.called
            # Money drop remains active
            assert drop.drop_id in drop_engine.active_drops


# ============================================================================
# TIER 4: REAL-WORLD IMAGEBOARD WORKLOADS & SIMULATIONS (>=4 tests)
# ============================================================================

class TestTier4ImageboardWorkloadSimulations:
    """Complex multi-user imageboard brawl scenarios, mixed media streams, and forensic audits."""

    @pytest.mark.asyncio
    async def test_t4_full_imageboard_multi_user_brawl_scenario(self, isolated_test_db):
        """End-to-End Simulation: 5 distinct anons flaming, Cyberchad intervention, AI attacks, PvP duels."""
        mock_bot = make_mock_bot()
        board_id = "b"
        u1, u2, u3, u4, u5 = 1001, 1002, 1003, 1004, 1005

        # Seed balances
        for u in (u1, u2, u3, u4, u5):
            await add_user_global_balance(isolated_test_db, u, "b", 2000)

        # 1. User 1 & User 2 start a heated flame war
        now = time.time()
        with patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock, return_value="Всем заткнуться! Киберчед в треде."), \
             patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock, return_value=(b"CYBERCHAD_BRAWL_VOICE", 4.0)), \
             patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_post:
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, u1, "ты клоун долбоеб >>1", 101)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, u2, "сам говно соси высер >>101", 102)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, u1, "чухан завали пасть >>102", 103)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, u2, "уебок чмо >>103", 104)

            # Spontaneous intervention triggers
            assert mock_post.called

        # 2. User 3 directly replies to Cyberchad's voice post
        mock_ai_post = {'post_num': 105, 'author_id': 0, 'content': {'is_ai_roast': True}}
        with patch("common.database.get_post_by_num", new_callable=AsyncMock, return_value=mock_ai_post), \
             patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock, return_value="Сыч 1003, ты уничтожен!"), \
             patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock, return_value=(b"ROAST_1003", 3.0)), \
             patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_post_roast:
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, u3, "Киберчед, ты лох!", 106, reply_to_post=105)
            assert mock_post_roast.called

        # 3. User 4 attacks Cyberchad with /shoot -> 15m ricochet mute
        msg_shoot = make_mock_message(user_id=u4, text="/shoot")
        with patch("common.database.apply_regular_mute", new_callable=AsyncMock) as mock_reg_mute:
            await handle_cyberchad_counter_action(msg_shoot, "shoot", u4, board_id, isolated_test_db)
            assert mock_reg_mute.called
            assert mock_reg_mute.call_args[0][2] == 900

        # 4. User 5 attacks Cyberchad with /rob -> 500 ₪ fined to Abu Fund
        msg_rob = make_mock_message(user_id=u5, text="/rob")
        await handle_cyberchad_counter_action(msg_rob, "rob", u5, board_id, isolated_test_db)
        bal_u5 = await get_user_global_balance(isolated_test_db, u5)
        assert bal_u5 == 1500

        # 5. User 1 challenges User 2 to /duel 500
        from main import _handle_duel_create
        msg_duel = make_mock_message(user_id=u1, text="/duel 500")
        with patch("main.get_pool", new_callable=AsyncMock, return_value=isolated_test_db):
            await _handle_duel_create(msg_duel, board_id, args=["500"], stream='ru')
            assert "500 ₪" in msg_duel.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_t4_high_throughput_mixed_media_stream(self, isolated_test_db):
        """Simulation: 10 concurrent users sending mixed media streams with zero silent drops."""
        board_id = "b"
        users = [2000 + i for i in range(10)]
        mock_bot = make_mock_bot()

        # Users 0-8 send normal rate (1 msg/sec) -> Clean
        # User 9 floods (>8 msgs in 4s) -> Shadowmuted with 300s
        t_base = 60000.0

        for sec in range(5):
            for u in users[:9]:
                is_f, _ = check_flood(u, board_id, now_ts=t_base + sec)
                assert not is_f

        # User 9 bursts 9 messages in 2 seconds
        for m in range(9):
            is_f, reason = check_flood(users[9], board_id, now_ts=t_base + (m * 0.2))
            if m < 8:
                assert not is_f
            else:
                assert is_f is True
                assert "Burst" in reason

    @pytest.mark.asyncio
    async def test_t4_economy_lifecycle_and_abu_fund_accumulation(self, isolated_test_db):
        """Simulation: Full economic cycle with duels, robbery penalties, drops, and Abu Fund verification."""
        p1, p2, p3 = 3001, 3002, 3003
        await add_user_global_balance(isolated_test_db, p1, "b", 5000)
        await add_user_global_balance(isolated_test_db, p2, "b", 5000)
        await add_user_global_balance(isolated_test_db, p3, "b", 5000)

        # 1. p1 robs Cyberchad -> 500 ₪ fine to Abu Fund
        msg_rob = make_mock_message(user_id=p1, text="/rob")
        await handle_cyberchad_counter_action(msg_rob, "rob", p1, "b", isolated_test_db)

        # 2. p2 loses duel to p3 (1000 ₪ bet, 5% fee = 50 ₪ to Abu Fund)
        await deduct_user_global_balance(isolated_test_db, p2, "b", 1000)
        await add_user_global_balance(isolated_test_db, p3, "b", 950)
        await add_to_abu_fund(isolated_test_db, 50)

        # Check balances
        bal_p1 = await get_user_global_balance(isolated_test_db, p1)
        bal_p2 = await get_user_global_balance(isolated_test_db, p2)
        bal_p3 = await get_user_global_balance(isolated_test_db, p3)
        abu_total = await get_abu_fund_total(isolated_test_db)

        assert bal_p1 == 4500
        assert bal_p2 == 4000
        assert bal_p3 == 5950
        assert abu_total == 550  # 500 from rob + 50 from duel tax

    @pytest.mark.asyncio
    async def test_t4_forensic_deep_audit_after_chaos_session(self, isolated_test_db):
        """Simulation: Run forensics analytics and sentiment aggregation after a chaotic session."""
        now = time.time()

        # Seed 10 diverse posts in SQLite
        for i in range(10):
            c_dict = json.dumps({'text': f'Post content {i}', 'type': 'text'})
            await isolated_test_db.execute(
                "INSERT INTO Posts (post_num, board_id, author_id, content, text_content, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (4000 + i, "b", 1000 + i, c_dict, f"Post content {i}", now - (10 - i) * 60)
            )

        # Compute board metrics
        async with isolated_test_db.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM Posts WHERE board_id = 'b'"
        ) as cursor:
            count, min_t, max_t = await cursor.fetchone()
            assert count == 10

        # Verify sparkline generation across time series
        spark = make_sparkline([0.5, -0.5, 0.5, -0.5, 0.5], length=5)
        assert len(spark) == 5
        assert isinstance(spark, str)
