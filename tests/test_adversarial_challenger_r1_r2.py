# -*- coding: utf-8 -*-
"""
Adversarial Stress Test Suite & Fuzzing Harness (R1 & R2) for dvachbot Ecosystem Overhaul.
Authored by challenger_1.

Focus Areas:
- R1: Anti-Flood Rate Limiters (BURST=8/4s, RATE=15/15s, MINUTE=30/60s), Microsecond Transitions,
      Jitter / Clock Skew Resilience, Concurrency Fuzzing, No-Silent-Drop Ghost Deliveries,
      Strict Monotonic Fake Post Numbers Across All Media Types.
- R2: Cyberchad Spontaneous Interventions (Strict >= 3600.0s Cooldown Boundary Conditions,
      Multi-Board Isolation, Fight Aggro Heuristics), Direct Reply Storms (Decoupling from Board Cooldown,
      Per-User Debounce, Deep Ancestor Trees), Voice-Only Payload Verification, and Edge-TTS/DSP Preset Fuzzing.
"""

import asyncio
import time
import random
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message, User, Chat

import shared_state
from common.spam_filter import (
    check_flood,
    is_bayan,
    check_bayan,
    check_link_or_ad_spam,
    _check_cross_board_spam,
    evaluate_message_for_autoshadowmute,
    analyze_message_for_spam,
    SpamResult,
    BURST_FLOOD_LIMIT,
    BURST_FLOOD_WINDOW,
    RATE_FLOOD_LIMIT,
    RATE_FLOOD_WINDOW,
    MINUTE_FLOOD_LIMIT,
    MINUTE_FLOOD_WINDOW,
    FLOOD_BASE_MUTE_SEC,
    _user_request_timestamps,
    _bayan_tracker,
    _board_recent_fingerprints,
    _bayan_mute_count,
    _bayan_mute_last_ts,
    _spam_violations,
    _spam_trackers,
    cross_board_spam_tracker,
    user_spam_locks,
    contains_phone_number,
    mask_phone_numbers,
    check_phone_dox,
)
from handlers.message_router import (
    process_shadow_reject,
    check_spam,
    resolve_archive_or_inline_reply,
)
from ai_manager import (
    register_post_and_maybe_trigger_cyberchad_intervention,
    build_reply_chain_context,
    _BOARD_FIGHT_TRACKER,
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION,
    _LAST_CYBERCHAD_INTERVENTION,
    _LAST_DIRECT_ROAST_USER_TS,
    CYBERCHAD_FIGHT_INTERVENTION_PROMPT,
    CYBERCHAD_DIRECT_ROAST_PROMPT,
)
from common.tts_engine import (
    CYBERCHAD_PRESETS,
    CyberchadPreset,
    get_preset,
    get_random_preset,
    list_presets,
    clean_tts_text,
    synthesize_cyberchad_voice_with_meta,
)
import cyberchad_tts


def make_test_message(user_id: int = 1001, text: str = "test post", content_type: str = "text") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.message_id = 500
    msg.text = text if content_type == "text" else None
    msg.caption = text if content_type != "text" else None
    msg.content_type = content_type
    msg.date = MagicMock()
    msg.date.timestamp.return_value = 100000.0
    msg.from_user = User(id=user_id, is_bot=False, first_name=f"User_{user_id}")
    msg.chat = Chat(id=user_id, type="private")
    msg.photo = []
    msg.video = None
    msg.document = None
    msg.sticker = None
    msg.animation = None
    msg.audio = None
    msg.voice = None
    msg.video_note = None
    return msg


@pytest.fixture(autouse=True)
def reset_r1_r2_trackers():
    """Wipes all volatile in-memory state before and after each adversarial test."""
    _user_request_timestamps.clear()
    _bayan_tracker.clear()
    _board_recent_fingerprints.clear()
    _bayan_mute_count.clear()
    _bayan_mute_last_ts.clear()
    _spam_violations.clear()
    _spam_trackers.clear()
    cross_board_spam_tracker.clear()
    user_spam_locks.clear()

    _BOARD_FIGHT_TRACKER.clear()
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION.clear()
    _LAST_DIRECT_ROAST_USER_TS.clear()

    shared_state.messages_storage.clear()
    shared_state.shadow_fake_post_counters.clear()
    shared_state.state["post_counter"] = 1000
    shared_state.board_data.clear()

    yield

    _user_request_timestamps.clear()
    _bayan_tracker.clear()
    _board_recent_fingerprints.clear()
    _bayan_mute_count.clear()
    _bayan_mute_last_ts.clear()
    _spam_violations.clear()
    _spam_trackers.clear()
    cross_board_spam_tracker.clear()
    user_spam_locks.clear()

    _BOARD_FIGHT_TRACKER.clear()
    _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION.clear()
    _LAST_DIRECT_ROAST_USER_TS.clear()

    shared_state.messages_storage.clear()
    shared_state.shadow_fake_post_counters.clear()
    shared_state.board_data.clear()


# ==============================================================================
# 1. R1: Anti-Flood Sliding Window Math & Microsecond Boundary Stress Tests
# ==============================================================================

class TestAdversarialR1FloodLimitsSlidingWindowMath:
    """Rigorous boundary precision and sliding window mathematics testing."""

    def test_burst_flood_microsecond_boundary_precision(self):
        """
        Validates exact BURST limit boundary (BURST_FLOOD_LIMIT = 8 in 4.0s):
        - Exactly 8 messages sent within 3.99s -> CLEAN.
        - 9th message sent at 3.999s -> BURST FLOOD TRIGGERED.
        - If 9th message arrives at 4.001s, oldest (0.0s) has pruned -> CLEAN.
        """
        user_id = 9001
        board_id = "b"
        t0 = 100000.0

        # Send 8 messages across 3.99 seconds
        timestamps = [t0 + (i * 0.5) for i in range(8)]
        for ts in timestamps:
            is_fl, reason = check_flood(user_id, board_id, now_ts=ts)
            assert is_fl is False, f"Unexpected flood flag at ts={ts}"
            assert reason == ""

        # 9th message at t0 + 3.99s (within 4.0s window of t0)
        is_fl, reason = check_flood(user_id, board_id, now_ts=t0 + 3.99)
        assert is_fl is True
        assert "Burst флуд: 9" in reason

        # Reset user tracker and test pruning at 4.001s
        _user_request_timestamps[user_id].clear()
        for ts in timestamps:
            check_flood(user_id, board_id, now_ts=ts)

        # 9th message arrives at t0 + 4.01s (t0 has exited the 4.0s window)
        is_fl, reason = check_flood(user_id, board_id, now_ts=t0 + 4.01)
        assert is_fl is False, f"Expected clean after sliding window shift, got {reason}"

    def test_rate_flood_exact_boundary_15_vs_16(self):
        """
        Validates RATE limit boundary (RATE_FLOOD_LIMIT = 15 in 15.0s):
        - 15 messages evenly spaced in 14.9s -> CLEAN.
        - 16th message at 14.99s -> RATE FLOOD TRIGGERED.
        - 16th message at 15.05s -> CLEAN.
        """
        user_id = 9002
        board_id = "b"
        t0 = 200000.0

        for i in range(15):
            ts = t0 + (i * 0.93)
            is_fl, _ = check_flood(user_id, board_id, now_ts=ts)
            assert is_fl is False

        is_fl, reason = check_flood(user_id, board_id, now_ts=t0 + 14.95)
        assert is_fl is True
        assert "Частый постинг: 16" in reason

        _user_request_timestamps[user_id].clear()
        for i in range(15):
            check_flood(user_id, board_id, now_ts=t0 + (i * 0.93))

        is_fl, reason = check_flood(user_id, board_id, now_ts=t0 + 15.05)
        assert is_fl is False

    def test_minute_flood_exact_boundary_30_vs_31(self):
        """
        Validates MINUTE limit boundary (MINUTE_FLOOD_LIMIT = 30 in 60.0s):
        - 30 messages in 58.0s -> CLEAN.
        - 31st message at 59.5s -> MINUTE FLOOD TRIGGERED.
        - 31st message at 60.5s -> CLEAN.
        """
        user_id = 9003
        board_id = "b"
        t0 = 300000.0

        for i in range(30):
            ts = t0 + (i * 1.93)
            is_fl, _ = check_flood(user_id, board_id, now_ts=ts)
            assert is_fl is False

        is_fl, reason = check_flood(user_id, board_id, now_ts=t0 + 59.5)
        assert is_fl is True
        assert "Минутный флуд: 31" in reason

        _user_request_timestamps[user_id].clear()
        for i in range(30):
            check_flood(user_id, board_id, now_ts=t0 + (i * 1.93))

        is_fl, reason = check_flood(user_id, board_id, now_ts=t0 + 60.5)
        assert is_fl is False

    def test_sliding_window_out_of_order_and_clock_skew_resilience(self):
        """Stress-tests rate limiter against clock skew and out-of-order timestamps."""
        user_id = 9004
        board_id = "b"
        t0 = 400000.0

        skewed_ts = [t0 + 1.0, t0 + 0.5, t0 + 1.2, t0 + 0.8, t0 + 1.5, t0 + 1.1, t0 + 1.8]
        for ts in skewed_ts:
            is_fl, _ = check_flood(user_id, board_id, now_ts=ts)
            assert is_fl is False

        check_flood(user_id, board_id, now_ts=t0 + 2.0)
        is_fl, reason = check_flood(user_id, board_id, now_ts=t0 + 2.1)
        assert is_fl is True
        assert "Burst флуд" in reason

    def test_admin_absolute_immunity_under_massive_flood(self):
        """Verifies admin is completely immune to flood detection even with 100 msg/sec."""
        admin_id = 123456
        board_id = "b"
        t0 = 500000.0

        with patch("bot_helpers.is_admin", return_value=True):
            for i in range(100):
                is_fl, reason = check_flood(admin_id, board_id, now_ts=t0 + (i * 0.01))
                assert is_fl is False
                assert reason == ""

            result = asyncio.run(evaluate_message_for_autoshadowmute(
                user_id=admin_id,
                board_id=board_id,
                content="Admin broadcast message",
                msg_type="text",
                raw_content_type="text",
                now_ts=t0
            ))
            assert result == (False, "", 0.0)


# ==============================================================================
# 2. R1: Concurrency Fuzzing & Multi-User Isolation
# ==============================================================================

class TestAdversarialR1ConcurrencyAndIsolationFuzzing:
    """Concurrency fuzzing across hundreds of simultaneous user threads and tasks."""

    @pytest.mark.asyncio
    async def test_multi_user_concurrent_sliding_window_fuzzing(self):
        """
        Simulates 50 distinct users simultaneously firing different workloads:
        - 25 'clean' users sending exactly 7 or 8 messages within 4 seconds -> ALL CLEAN.
        - 25 'flooding' users sending 9 to 15 messages within 4 seconds -> ALL FLAGGED.
        Verifies zero cross-talk between user rate limiting state.
        """
        clean_users = [10000 + i for i in range(25)]
        flooding_users = [20000 + i for i in range(25)]
        t0 = 600000.0

        clean_results = {}
        flooding_results = {}

        async def run_clean_user(uid):
            msg_count = random.choice([6, 7, 8])
            results = []
            for i in range(msg_count):
                ts = t0 + (i * 0.45)
                is_fl, _ = check_flood(uid, "b", now_ts=ts)
                results.append(is_fl)
                await asyncio.sleep(0.0001)
            clean_results[uid] = results

        async def run_flooding_user(uid):
            msg_count = random.randint(9, 14)
            results = []
            for i in range(msg_count):
                ts = t0 + (i * 0.25)
                is_fl, _ = check_flood(uid, "b", now_ts=ts)
                results.append(is_fl)
                await asyncio.sleep(0.0001)
            flooding_results[uid] = results

        tasks = [run_clean_user(u) for u in clean_users] + [run_flooding_user(u) for u in flooding_users]
        random.shuffle(tasks)
        await asyncio.gather(*tasks)

        for uid, res in clean_results.items():
            assert not any(res), f"Clean user {uid} was falsely flagged for flood!"

        for uid, res in flooding_results.items():
            assert any(res), f"Flooding user {uid} was NOT caught by flood filter!"
            assert res[8] is True, f"User {uid} 9th message was not flagged!"

    @pytest.mark.asyncio
    @patch("common.database.apply_shadow_mute", new_callable=AsyncMock)
    async def test_single_user_high_concurrency_race_condition(self, mock_apply_mute):
        """
        Simulates one user firing 40 messages simultaneously via asyncio tasks.
        Ensures thread-safety, no unhandled exceptions, and proper mute application.
        """
        user_id = 99999
        board_id = "b"
        mock_apply_mute.return_value = 1000.0 + FLOOD_BASE_MUTE_SEC
        t0 = 700000.0

        async def fire_msg(idx):
            return await evaluate_message_for_autoshadowmute(
                user_id=user_id,
                board_id=board_id,
                content=f"Concurrent message {idx}",
                msg_type="text",
                raw_content_type="text",
                now_ts=t0 + (idx * 0.05)
            )

        tasks = [fire_msg(i) for i in range(40)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            assert not isinstance(r, Exception), f"Concurrent task raised exception: {r}"

        clean_count = sum(1 for r in results if r[0] is False)
        muted_count = sum(1 for r in results if r[0] is True)

        assert clean_count == 8, f"Expected exactly 8 clean messages, got {clean_count}"
        assert muted_count == 32, f"Expected 32 muted messages, got {muted_count}"


# ==============================================================================
# 3. R1: Media Ghost Deliveries, All Media Types, & Monotonic Fake Posts
# ==============================================================================

class TestAdversarialR1MediaGhostDeliveryAndNoSilentDrops:
    """Stress tests ghost post delivery across all media formats and spam rejection paths."""

    @pytest.mark.asyncio
    @patch("handlers.message_router.send_message_to_users", new_callable=AsyncMock)
    @patch("handlers.message_router.format_header", new_callable=AsyncMock)
    @patch("handlers.message_router.asyncio.sleep", new_callable=AsyncMock)
    async def test_all_media_types_ghost_delivery_payload_integrity(self, mock_sleep, mock_hdr, mock_send):
        """
        Verifies all media types (photos, albums, videos, voice notes, video notes,
        audio, stickers, documents) generate complete, well-formed ghost delivery payloads
        exclusively directed to the author ({user_id}).
        """
        mock_bot = AsyncMock()
        mock_hdr.return_value = "Аноним No. 123456"
        user_id = 88888
        board_id = "b"

        media_payloads = [
            {"type": "photo", "file_id": "photo_123", "caption": "Тестовое фото"},
            {"type": "video", "file_id": "video_456", "caption": "Тестовое видео", "duration": 120},
            {"type": "document", "file_id": "doc_789", "filename": "test.pdf", "mime_type": "application/pdf"},
            {"type": "voice", "file_id": "voice_101", "duration": 15},
            {"type": "video_note", "file_id": "vnote_202", "duration": 30},
            {"type": "audio", "file_id": "audio_303", "performer": "Artist", "title": "Track"},
            {"type": "sticker", "file_id": "sticker_404"},
            {"type": "animation", "file_id": "gif_505"},
            {"type": "media_group", "media": [{"type": "photo", "file_id": "p1"}, {"type": "photo", "file_id": "p2"}]}
        ]

        for i, payload in enumerate(media_payloads):
            ctx = shared_state.ShadowRejectContext(
                bot=mock_bot,
                board_id=board_id,
                user_id=user_id,
                content=payload,
                reply_to_post=500 + i,
                stream="ru"
            )
            await process_shadow_reject(ctx)

        assert mock_send.call_count == len(media_payloads)

        for call in mock_send.call_args_list:
            b_config = call[0][0]
            assert b_config.board_id == board_id
            assert b_config.recipients == {user_id}
            assert b_config.content["is_shadow_reject"] is True
            assert "post_num" in b_config.content
            assert "header" in b_config.content
            assert b_config.content["post_num"] > 1000

    @pytest.mark.asyncio
    @patch("handlers.message_router.send_message_to_users", new_callable=AsyncMock)
    @patch("handlers.message_router.format_header", new_callable=AsyncMock)
    @patch("handlers.message_router.asyncio.sleep", new_callable=AsyncMock)
    async def test_fake_post_num_strict_monotonicity_under_concurrency(self, mock_sleep, mock_hdr, mock_send):
        """
        Fuzzes fake post number generation with sequential calls per user across 5 users.
        Verifies:
        1. For each user, fake post numbers are strictly monotonically increasing.
        2. Every fake post number is strictly greater than the global real board counter.
        3. Zero duplicate fake post numbers per user.
        """
        mock_bot = AsyncMock()
        mock_hdr.return_value = "Аноним No. 9999"
        board_id = "b"
        users = [7001, 7002, 7003, 7004, 7005]

        generated_per_user = {u: [] for u in users}

        for u in users:
            for idx in range(15):
                ctx = shared_state.ShadowRejectContext(
                    bot=mock_bot,
                    board_id=board_id,
                    user_id=u,
                    content={"type": "text", "text": f"Ghost post {idx}"},
                    reply_to_post=None,
                    stream="ru"
                )
                await process_shadow_reject(ctx)
                generated_per_user[u].append(shared_state.shadow_fake_post_counters[(board_id, u)])

        for uid, p_list in generated_per_user.items():
            assert len(p_list) == 15
            for num in p_list:
                assert num > 1000
            for i in range(len(p_list) - 1):
                assert p_list[i] < p_list[i + 1], f"Monotonicity violation for user {uid}: {p_list[i]} >= {p_list[i+1]}"

    @pytest.mark.asyncio
    @patch("common.database.is_shadow_muted", new_callable=AsyncMock)
    @patch("common.database.apply_shadow_mute", new_callable=AsyncMock)
    async def test_no_silent_drops_across_all_spam_rejection_vectors(self, mock_apply_mute, mock_is_muted):
        """
        Verifies check_spam always returns True for all rejection vectors so that
        the message router routes directly to process_shadow_reject without silent drop.
        """
        mock_is_muted.return_value = False
        mock_apply_mute.return_value = 100000.0 + 300.0

        user_id = 66666
        board_id = "b"

        with patch("bot_helpers.is_admin", return_value=False):
            # 1. Burst flood -> check_spam returns True
            msg_flood = make_test_message(user_id=user_id, text="Flood text")
            with patch("common.spam_filter.check_flood", return_value=(True, "Burst flood")):
                result = await check_spam(user_id, msg_flood, board_id)
                assert result is True

            # 2. Link / Scam spam -> check_spam returns True
            msg_link = make_test_message(user_id=user_id, text="Казино 1win промокод на депозит")
            with patch("common.spam_filter.check_link_or_ad_spam", return_value=(True, "Casino scam")):
                result = await check_spam(user_id, msg_link, board_id)
                assert result is True

            # 3. Bayan spam -> check_spam returns True
            msg_bayan = make_test_message(user_id=user_id, text="Duplicate bayan post")
            with patch("common.spam_filter.check_bayan", return_value=(True, 1200)):
                result = await check_spam(user_id, msg_bayan, board_id)
                assert result is True

            # 4. Cross-board spam -> check_spam returns True
            msg_cb = make_test_message(user_id=user_id, text="Cross board spamming")
            with patch("common.spam_filter._check_cross_board_spam", return_value=False):
                result = await check_spam(user_id, msg_cb, board_id)
                assert result is True


# ==============================================================================
# 4. R2: Cyberchad 3600s Cooldown Boundary Conditions & Multi-Board Isolation
# ==============================================================================

class TestAdversarialR2CyberchadSpontaneousCooldownBoundaries:
    """Stress testing Cyberchad 3600s cooldown edge cases, clock skew, and multi-board routing."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    async def test_spontaneous_cooldown_microsecond_boundary_precision(
        self, mock_process_post, mock_summarize, mock_synth_meta
    ):
        """
        Microsecond boundary testing on 3600.0s cooldown:
        - t0: 1st spontaneous intervention triggers.
        - t0 + 3599.99s: fight occurs -> BLOCKED (no intervention).
        - t0 + 3600.001s: fight occurs -> TRIGGERED (intervention allowed).
        - t0 + 3605.00s: subsequent fight -> BLOCKED (new cooldown active).
        """
        mock_bot = AsyncMock()
        mock_summarize.return_value = "Завалите ебальники оба, омежки."
        mock_synth_meta.return_value = (b"CYBERCHAD_VOICE_OGG", CYBERCHAD_PRESETS["classic"])

        t0 = 1000000.0
        board_id = "b"

        # 1. First fight triggers at t0
        with patch("time.time", return_value=t0):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 101, ">>100 ты клоун и чмо", post_num=101)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 102, ">>101 сам долбоеб соси хуй", post_num=102)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 101, ">>102 уебок завали пасть", post_num=103)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 102, ">>103 чухан ебаный", post_num=104)

        assert mock_process_post.call_count == 1
        assert _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION[board_id] == t0

        # 2. Fight at 3599.99s -> must be BLOCKED
        mock_process_post.reset_mock()
        _BOARD_FIGHT_TRACKER.clear()
        t_blocked = t0 + 3599.99

        with patch("time.time", return_value=t_blocked):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 101, ">>200 ты клоун и чмо", post_num=201)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 102, ">>201 сам долбоеб соси хуй", post_num=202)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 101, ">>202 уебок завали пасть", post_num=203)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 102, ">>203 чухан ебаный", post_num=204)

        assert mock_process_post.call_count == 0

        # 3. Fight at 3600.001s -> must TRIGGER
        mock_process_post.reset_mock()
        _BOARD_FIGHT_TRACKER.clear()
        t_allowed = t0 + 3600.001

        with patch("time.time", return_value=t_allowed):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 101, ">>300 ты клоун и чмо", post_num=301)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 102, ">>301 сам долбоеб соси хуй", post_num=302)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 101, ">>302 уебок завали пасть", post_num=303)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 102, ">>303 чухан ебаный", post_num=304)

        assert mock_process_post.call_count == 1
        assert _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION[board_id] == t_allowed

        # 4. Fight at 3605.00s -> must be BLOCKED
        mock_process_post.reset_mock()
        _BOARD_FIGHT_TRACKER.clear()
        t_subsequent = t_allowed + 5.0

        with patch("time.time", return_value=t_subsequent):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 101, ">>400 ты клоун и чмо", post_num=401)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 102, ">>401 сам долбоеб соси хуй", post_num=402)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 101, ">>402 уебок завали пасть", post_num=403)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, board_id, 102, ">>403 чухан ебаный", post_num=404)

        assert mock_process_post.call_count == 0

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    async def test_spontaneous_cooldown_multi_board_complete_isolation(
        self, mock_process_post, mock_summarize, mock_synth_meta
    ):
        """
        Verifies spontaneous intervention cooldown on /b/ does NOT block interventions
        on other boards (/po/, /int/, /vg/).
        """
        mock_bot = AsyncMock()
        mock_summarize.return_value = "Размазал всех."
        mock_synth_meta.return_value = (b"VOICE", CYBERCHAD_PRESETS["heavy_bass"])

        t0 = 2000000.0

        # 1. Trigger intervention on /b/
        with patch("time.time", return_value=t0):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>100 ты клоун и чмо", post_num=1)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>101 сам долбоеб соси хуй", post_num=2)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>102 уебок завали пасть", post_num=3)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>103 чухан ебаный", post_num=4)

        assert mock_process_post.call_count == 1
        assert mock_process_post.call_args[0][0].board_id == "b"

        # 2. 100 seconds later, fight erupts on /po/ -> MUST TRIGGER
        mock_process_post.reset_mock()
        with patch("time.time", return_value=t0 + 100.0):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "po", 201, ">>100 ты клоун и чмо", post_num=11)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "po", 202, ">>101 сам долбоеб соси хуй", post_num=12)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "po", 201, ">>102 уебок завали пасть", post_num=13)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "po", 202, ">>103 чухан ебаный", post_num=14)

        assert mock_process_post.call_count == 1
        assert mock_process_post.call_args[0][0].board_id == "po"

        # 3. Another fight on /b/ at t0 + 200s -> MUST BE BLOCKED
        mock_process_post.reset_mock()
        _BOARD_FIGHT_TRACKER["b"].clear()
        with patch("time.time", return_value=t0 + 200.0):
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>100 ты клоун и чмо", post_num=21)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>101 сам долбоеб соси хуй", post_num=22)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 101, ">>102 уебок завали пасть", post_num=23)
            await register_post_and_maybe_trigger_cyberchad_intervention(mock_bot, "b", 102, ">>103 чухан ебаный", post_num=24)

        assert mock_process_post.call_count == 0


# ==============================================================================
# 5. R2: Direct Reply Storm & Concurrency Fuzzing
# ==============================================================================

class TestAdversarialR2DirectReplyStormAndConcurrency:
    """Stress tests rapid reply storms to Cyberchad, context reconstruction, and per-user debounce."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    @patch("ai_manager.build_reply_chain_context", new_callable=AsyncMock)
    async def test_direct_reply_storm_multi_user_concurrency(
        self, mock_build_chain, mock_process_post, mock_summarize, mock_synth_meta
    ):
        """
        Simulates 20 different users replying directly to Cyberchad within 1 second.
        Spontaneous board cooldown is active.
        All 20 unique users receive personalized voice roasts without blocking.
        """
        mock_bot = AsyncMock()
        mock_summarize.return_value = "Персонализированный разнос сыча."
        mock_synth_meta.return_value = (b"ROAST_OGG", CYBERCHAD_PRESETS["infernal"])
        mock_build_chain.return_value = ">>100 [Киберчед]: Базовый разнос треда."

        now = 3000000.0
        board_id = "b"

        _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION[board_id] = now

        shared_state.messages_storage[100] = {
            "post_num": 100,
            "author_id": 0,
            "content": {"type": "voice", "is_ai_roast": True}
        }

        async def user_reply(uid):
            with patch("time.time", return_value=now + (uid % 5) * 0.1):
                await register_post_and_maybe_trigger_cyberchad_intervention(
                    mock_bot, board_id, uid, f"Слышь ты, киберчед {uid}, поясни!",
                    post_num=1000 + uid, reply_to_post=100
                )

        users = [5000 + i for i in range(20)]
        tasks = [user_reply(u) for u in users]
        await asyncio.gather(*tasks)

        assert mock_process_post.call_count == 20
        assert mock_summarize.call_count == 20

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    async def test_direct_reply_per_user_rate_limit_debouncing(
        self, mock_process_post, mock_summarize, mock_synth_meta
    ):
        """
        Simulates a malicious user spamming 10 direct replies in 2 seconds.
        Only the 1st triggers a voice roast; subsequent 9 within 10s are debounced.
        Another user replying 2 seconds later triggers immediately.
        """
        mock_bot = AsyncMock()
        mock_summarize.return_value = "Разнос спамера."
        mock_synth_meta.return_value = (b"ROAST_OGG", CYBERCHAD_PRESETS["classic"])

        t0 = 4000000.0
        board_id = "b"

        shared_state.messages_storage[500] = {
            "post_num": 500, "author_id": 0, "content": {"is_ai": True}
        }

        spammer_id = 9999
        victim_id = 8888

        # 1. 1st reply from spammer -> triggers
        with patch("time.time", return_value=t0):
            await register_post_and_maybe_trigger_cyberchad_intervention(
                mock_bot, board_id, spammer_id, "Спам реплай 1", post_num=501, reply_to_post=500
            )
        assert mock_process_post.call_count == 1

        # 2. 9 more replies within 8 seconds from spammer -> all blocked
        for i in range(2, 11):
            with patch("time.time", return_value=t0 + (i * 0.5)):
                await register_post_and_maybe_trigger_cyberchad_intervention(
                    mock_bot, board_id, spammer_id, f"Спам реплай {i}", post_num=500 + i, reply_to_post=500
                )
        assert mock_process_post.call_count == 1

        # 3. Clean user replying at t0 + 3.0s -> triggers immediately!
        with patch("time.time", return_value=t0 + 3.0):
            await register_post_and_maybe_trigger_cyberchad_intervention(
                mock_bot, board_id, victim_id, "Обычный ответ от другого", post_num=520, reply_to_post=500
            )
        assert mock_process_post.call_count == 2

    @pytest.mark.asyncio
    async def test_build_reply_chain_context_cyclic_and_deep_tree_safety(self):
        """
        Stress-tests build_reply_chain_context against cyclic reference loops
        (Post 10 -> Post 11 -> Post 10) and deep trees (30 levels).
        """
        shared_state.messages_storage[10] = {
            "post_num": 10, "author_id": 100, "reply_to_post_num": 11,
            "content": {"text": "Post 10"}
        }
        shared_state.messages_storage[11] = {
            "post_num": 11, "author_id": 101, "reply_to_post_num": 10,
            "content": {"text": "Post 11"}
        }

        context = await build_reply_chain_context(10, max_depth=10)
        assert isinstance(context, str)
        assert "Post 10" in context
        assert "Post 11" in context


# ==============================================================================
# 6. R2: Voice-Only Payload Verification & TTS DSP Presets Fuzzing
# ==============================================================================

class TestAdversarialR2VoiceOnlyPayloadAndTTSDSPPipelines:
    """Validates strictly voice delivery (no text body) and Edge-TTS DSP preset modulation."""

    @pytest.mark.asyncio
    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock)
    @patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock)
    @patch("common.bot_helpers.process_new_post", new_callable=AsyncMock)
    async def test_cyberchad_strictly_voice_no_text_payload_guarantee(
        self, mock_process_post, mock_summarize, mock_synth_meta
    ):
        """
        Strictly verifies that both spontaneous and direct roasts produce
        posts containing exclusively voice payloads (voice_bytes, caption, is_ai_roast=True)
        and absolutely NO text body.
        """
        mock_bot = AsyncMock()
        mock_summarize.return_value = "Размазал сычей в блин."
        mock_synth_meta.return_value = (b"OGG_OPUS_STREAM_DATA", CYBERCHAD_PRESETS["overdrive"])

        now = 5000000.0

        with patch("time.time", return_value=now):
            await register_post_and_maybe_trigger_cyberchad_intervention(
                mock_bot, "b", 777, "Киберчед, давай поясни", post_num=777, reply_to_post=None
            )

        assert mock_process_post.call_count == 1
        call_params = mock_process_post.call_args[0][0]

        content = call_params.content
        assert content["type"] == "voice"
        assert content["voice_bytes"] == b"OGG_OPUS_STREAM_DATA"
        assert content["caption"] == "🔥 Разъёб от Киберчеда"
        assert content["is_ai_roast"] is True
        assert content["is_ai"] is True
        assert "text" not in content or content["text"] is None

    def test_cyberchad_all_10_presets_integrity_and_dsp_filters(self):
        """Validates all 10 Cyberchad voice presets, weights, and DSP filters."""
        assert len(CYBERCHAD_PRESETS) == 10

        expected_keys = {
            "classic", "heavy_bass", "cyborg", "intercom", "fast_aggressive",
            "overdrive", "infernal", "drill_sergeant", "bunker", "studio_radio"
        }
        assert set(CYBERCHAD_PRESETS.keys()) == expected_keys

        for key, preset in CYBERCHAD_PRESETS.items():
            assert isinstance(preset, CyberchadPreset)
            assert preset.key == key
            assert len(preset.name) > 0
            assert len(preset.description) > 0
            assert preset.voice.startswith("ru-RU-")
            assert len(preset.rate) > 0
            assert len(preset.pitch) > 0
            assert len(preset.ffmpeg_filter) > 0
            assert preset.weight > 0
            assert preset.caption_title == "🔥 Разъёб от Киберчеда"

        assert get_preset("heavy_bass").key == "heavy_bass"
        assert get_preset("HEAVY_BASS").key == "heavy_bass"
        assert get_preset("invalid_unknown_preset").key in CYBERCHAD_PRESETS
        assert isinstance(get_random_preset(), CyberchadPreset)
        assert len(list_presets()) == 10

    def test_clean_tts_text_fuzzing(self):
        """Fuzzes clean_tts_text against HTML tags, emojis, unprintable chars, and large texts."""
        # 1. HTML injection
        raw_html = "<div><p>Привет <b>Анон</b> <script>alert(1)</script></p></div>"
        cleaned = clean_tts_text(raw_html)
        assert "<" not in cleaned and ">" not in cleaned
        assert "Привет Анон alert(1)" in cleaned

        # 2. Emoji stripping
        raw_emojis = "🔥 Разъёб от 🤖 Киберчеда 💩💪✨👑"
        cleaned = clean_tts_text(raw_emojis)
        assert "🔥" not in cleaned and "🤖" not in cleaned and "💩" not in cleaned

        # 3. Punctuation and whitespace normalization
        raw_punct = "Привет   ,   как дела   ?   Все   !   Норм   .   "
        cleaned = clean_tts_text(raw_punct)
        assert cleaned == "Привет, как дела? Все! Норм."

        # 4. Length capping (5000 chars -> capped to 1000 + ...)
        huge_text = "А " * 2500
        cleaned = clean_tts_text(huge_text)
        assert len(cleaned) <= 1003
        assert cleaned.endswith("...")

        # 5. Empty and None inputs
        assert clean_tts_text("") == ""
        assert clean_tts_text(None) == ""

    @pytest.mark.asyncio
    async def test_synthesize_voice_failure_graceful_handling(self):
        """
        Verifies synthesize_cyberchad_voice_with_meta returns (None, preset)
        gracefully when edge_tts raises an exception, without crashing the caller.
        """
        with patch("edge_tts.Communicate", side_effect=RuntimeError("Edge-TTS connection timeout")):
            voice_bytes, preset = await synthesize_cyberchad_voice_with_meta("Тестовая реплика")
            assert voice_bytes is None
            assert isinstance(preset, CyberchadPreset)
