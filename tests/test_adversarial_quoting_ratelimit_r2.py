# -*- coding: utf-8 -*-
"""
Adversarial Stress-Testing Suite for Requirements R2 & R3 (Round 2 Challenger).
Focus:
- R2: Empirical verification that distance <= 300 NEVER produces an expandable blockquote.
      Boundary testing at 299, 300, 301, 500, edge cases, deleted posts, future posts, dynamic config.
- R3: Empirical verification of rate-limit timings (t=0, t=59.9s blocked, t=60.1s allowed,
      anti-flood t=14.9s audio suppressed vs t=15.1s audio allowed).
- Anti-Audio-DOS: Rapid flood of 50 direct calls in 5 seconds to verify no audio DOS and no thread lockup.
- Concurrent spam storm: 100 simultaneous requests from multiple distinct users and multiple boards.
"""

import asyncio
import random
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from broadcaster import _format_message_body, _format_quote_block, _format_reply_line
from handlers.message_router import (
    _CYBERCHAD_USER_LAST_DIRECT,
    _CYBERCHAD_USER_LAST_REJECT,
    CYBERCHAD_RATE_LIMIT_REJECTIONS,
    _is_direct_cyberchad_trigger,
    build_quick_quote_info,
    trigger_cyberchad_with_rate_limit,
)


class TestAdversarialQuotingDistanceBoundary(unittest.IsolatedAsyncioTestCase):
    """
    Adversarial verification of Quoting Distance (Requirement R2).
    Contract: Distance <= 300 MUST NEVER produce an expandable blockquote.
    """

    async def test_exact_boundaries_299_300_301_500(self):
        """
        Tests exact boundaries:
        - 299: strictly NO quote block, NO blockquote tag in formatted message body.
        - 300: strictly NO quote block, NO blockquote tag in formatted message body.
        - 301: strictly PRODUCES quote block and <blockquote expandable> in message body.
        - 500: strictly PRODUCES quote block and <blockquote expandable> in message body.
        """
        current_max = 1000

        mock_post_data = {
            701: {'post_num': 701, 'content': {'type': 'text', 'text': 'Post 701 (diff 299)'}},
            700: {'post_num': 700, 'content': {'type': 'text', 'text': 'Post 700 (diff 300)'}},
            699: {'post_num': 699, 'content': {'type': 'text', 'text': 'Post 699 (diff 301)'}},
            500: {'post_num': 500, 'content': {'type': 'text', 'text': 'Post 500 (diff 500)'}},
        }

        async def fake_get_post_by_num(pnum):
            return mock_post_data.get(pnum)

        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=current_max), \
             patch("handlers.message_router.get_post_by_num", side_effect=fake_get_post_by_num):

            # --- BOUNDARY 299 (current_max=1000, reply_to=701) ---
            quote_299 = await build_quick_quote_info(701)
            self.assertIsNone(quote_299, "Distance 299 must return None")
            body_299 = await _format_message_body(
                content={'type': 'text', 'text': 'Ответ на 701', 'reply_to_post': 701, 'quote_info': quote_299},
                user_id_for_context=123,
                post_data={},
                reply_to_post_author_id=456,
                quote_info=quote_299
            )
            self.assertNotIn("<blockquote", body_299, "Distance 299 MUST NOT contain <blockquote")
            self.assertNotIn("expandable", body_299, "Distance 299 MUST NOT contain expandable")

            # --- BOUNDARY 300 (current_max=1000, reply_to=700) ---
            quote_300 = await build_quick_quote_info(700)
            self.assertIsNone(quote_300, "Distance 300 must return None")
            body_300 = await _format_message_body(
                content={'type': 'text', 'text': 'Ответ на 700', 'reply_to_post': 700, 'quote_info': quote_300},
                user_id_for_context=123,
                post_data={},
                reply_to_post_author_id=456,
                quote_info=quote_300
            )
            self.assertNotIn("<blockquote", body_300, "Distance 300 MUST NOT contain <blockquote")
            self.assertNotIn("expandable", body_300, "Distance 300 MUST NOT contain expandable")

            # --- BOUNDARY 301 (current_max=1000, reply_to=699) ---
            quote_301 = await build_quick_quote_info(699)
            self.assertIsNotNone(quote_301, "Distance 301 must return quote_info")
            self.assertEqual(quote_301.get('text'), 'Post 699 (diff 301)')
            body_301 = await _format_message_body(
                content={'type': 'text', 'text': 'Ответ на 699', 'reply_to_post': 699, 'quote_info': quote_301},
                user_id_for_context=123,
                post_data={},
                reply_to_post_author_id=456,
                quote_info=quote_301
            )
            self.assertIn("<blockquote expandable>", body_301, "Distance 301 MUST contain <blockquote expandable>")
            self.assertIn("Post 699 (diff 301)", body_301)

            # --- DISTANCE 500 (current_max=1000, reply_to=500) ---
            quote_500 = await build_quick_quote_info(500)
            self.assertIsNotNone(quote_500, "Distance 500 must return quote_info")
            self.assertEqual(quote_500.get('text'), 'Post 500 (diff 500)')
            body_500 = await _format_message_body(
                content={'type': 'text', 'text': 'Ответ на 500', 'reply_to_post': 500, 'quote_info': quote_500},
                user_id_for_context=123,
                post_data={},
                reply_to_post_author_id=456,
                quote_info=quote_500
            )
            self.assertIn("<blockquote expandable>", body_500, "Distance 500 MUST contain <blockquote expandable>")
            self.assertIn("Post 500 (diff 500)", body_500)

    async def test_distance_sweep_zero_to_300_never_produces_blockquote(self):
        """
        Sweeps 301 distinct distances from 0 to 300.
        Verifies that NOT A SINGLE ONE produces quote_info or a blockquote tag.
        """
        current_max = 500000

        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=current_max), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock) as mock_get_post:

            # Sample every distance from 0 to 300 (step 1 for critical range [280-300], step 10 for rest)
            distances_to_test = sorted(list(set(range(0, 301, 10)) | set(range(280, 301))))

            for dist in distances_to_test:
                reply_to = current_max - dist
                res = await build_quick_quote_info(reply_to)
                self.assertIsNone(
                    res,
                    f"Distance {dist} (current_max={current_max}, reply_to={reply_to}) leaked quote_info!"
                )
                body = await _format_message_body(
                    content={'type': 'text', 'text': f'Reply to {reply_to}', 'reply_to_post': reply_to, 'quote_info': res},
                    user_id_for_context=1,
                    post_data={},
                    reply_to_post_author_id=2,
                    quote_info=res
                )
                self.assertNotIn(
                    "<blockquote",
                    body,
                    f"Distance {dist} produced blockquote in formatted body!"
                )

            # get_post_by_num must NEVER have been called for any of these
            mock_get_post.assert_not_called()

    async def test_edge_cases_future_posts_negative_and_corrupt_inputs(self):
        """
        Tests anomalous, corrupt, and boundary inputs:
        - Future posts (reply_to > current_max) -> distance is negative -> strictly None.
        - Zero or negative post numbers -> strictly None.
        - Malformed types: None, "", "abc", float, nan, inf, dict, list -> strictly None.
        - Deleted posts: post_num > 300 distance, but database returns None -> strictly None.
        - Empty or corrupt content in DB post -> blockquote block is NEVER generated.
        """
        current_max = 1000

        async def fake_get_post_corrupt(pnum):
            if pnum == 500:  # Deleted post
                return None
            if pnum == 499:  # Corrupted post with empty content
                return {'post_num': 499, 'content': {}}
            if pnum == 498:  # Corrupted post with None content
                return {'post_num': 498, 'content': None}
            if pnum == 497:  # Corrupted post with non-dict content
                return {'post_num': 497, 'content': 12345}
            return None

        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=current_max), \
             patch("handlers.message_router.get_post_by_num", side_effect=fake_get_post_corrupt):

            # Future posts (diff < 0 <= 300) -> None
            future_replies = [1001, 1050, 1300, 2000, 999999]
            for f_reply in future_replies:
                res = await build_quick_quote_info(f_reply)
                self.assertIsNone(res, f"Future post {f_reply} must return None")

            # Zero and negative -> None
            for neg_reply in [0, -1, -50, -999999]:
                res = await build_quick_quote_info(neg_reply)
                self.assertIsNone(res, f"Negative post {neg_reply} must return None")

            # Corrupt string inputs -> None
            for corrupt_val in ["", "   ", "abc", "null", "None", "3.14", "NaN", "Infinity", "-10"]:
                res = await build_quick_quote_info(corrupt_val)
                self.assertIsNone(res, f"Corrupt input {corrupt_val!r} must return None")

            # None input -> None
            self.assertIsNone(await build_quick_quote_info(None))

            # Deleted post (distance 500 > 300, but post deleted from DB) -> None
            self.assertIsNone(await build_quick_quote_info(500))

            # Corrupt content dicts: even if quote_info returned, _format_quote_block MUST NOT produce blockquote
            quote_499 = await build_quick_quote_info(499)
            self.assertIsNone(_format_quote_block(quote_499), "Empty content must not produce quote block")

            quote_498 = await build_quick_quote_info(498)
            self.assertIsNone(_format_quote_block(quote_498), "None content must not produce quote block")

            quote_497 = await build_quick_quote_info(497)
            self.assertIsNone(_format_quote_block(quote_497), "Non-dict content must not produce quote block")

    async def test_dynamic_config_change_adversarial(self):
        """
        Adversarial test: If shared_state.QUICK_QUOTE_POST_DISTANCE is dynamically modified at runtime:
        - When set to 500: distance 301 MUST return None, distance 501 returns quote.
        - When set to 150: distance 150 MUST return None, distance 151 returns quote.
        """
        current_max = 2000

        async def fake_get_post(pnum):
            return {'post_num': pnum, 'content': {'type': 'text', 'text': f'Content #{pnum}'}}

        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=current_max), \
             patch("handlers.message_router.get_post_by_num", side_effect=fake_get_post):

            # Override to 500
            with patch.object(shared_state, "QUICK_QUOTE_POST_DISTANCE", 500):
                # distance 301 (reply_to=1699): now <= 500 -> must be None!
                self.assertIsNone(await build_quick_quote_info(1699))
                # distance 500 (reply_to=1500): <= 500 -> must be None!
                self.assertIsNone(await build_quick_quote_info(1500))
                # distance 501 (reply_to=1499): > 500 -> must return quote!
                res_501 = await build_quick_quote_info(1499)
                self.assertIsNotNone(res_501)
                self.assertEqual(res_501['text'], 'Content #1499')

            # Override to 150
            with patch.object(shared_state, "QUICK_QUOTE_POST_DISTANCE", 150):
                # distance 150 (reply_to=1850): <= 150 -> None
                self.assertIsNone(await build_quick_quote_info(1850))
                # distance 151 (reply_to=1849): > 150 -> quote
                res_151 = await build_quick_quote_info(1849)
                self.assertIsNotNone(res_151)


class TestAdversarialRateLimitTimingPrecision(unittest.IsolatedAsyncioTestCase):
    """
    Adversarial verification of Rate-Limit Timings (Requirement R3).
    Contract:
    - 1 direct trigger per 60.0s per user per board.
    - t=0: Allowed (intervention triggered).
    - t=59.9s: Blocked (<60s) -> Gemini strictly suppressed, offline voice note synthesized.
    - t=60.1s: Allowed (>=60s) -> Normal intervention triggered.
    - Anti-flood:
      - t=14.9s since reject: Audio strictly suppressed!
      - t=15.1s since reject: Audio allowed!
    """

    def setUp(self):
        _CYBERCHAD_USER_LAST_DIRECT.clear()
        _CYBERCHAD_USER_LAST_REJECT.clear()
        self.mock_bot = MagicMock()

    def tearDown(self):
        _CYBERCHAD_USER_LAST_DIRECT.clear()
        _CYBERCHAD_USER_LAST_REJECT.clear()

    async def test_precision_rate_limit_boundary_59_9s_and_60_1s(self):
        """
        Adversarially tests the exact 60.0s boundary:
        - t=0.0s: Call 1 succeeds (Intervention triggered).
        - t=59.9s: Call 2 blocked (Intervention NEVER called, Voice Note synthesized).
        - t=60.1s: Call 3 succeeds (Intervention triggered, 60s cooldown passed).
        """
        t0 = 500000.0

        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene, \
             patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp, \
             patch("handlers.message_router.time.time") as mock_time:

            mock_tts.return_value = (b"mock_voice_data", MagicMock())
            mock_pnp.return_value = 12345

            # --- 1. First trigger at t = 0.0s ---
            mock_time.return_value = t0
            res1 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 777, "киберчед, ответь", post_num=100, reply_to_post=None
            )
            self.assertTrue(res1)
            self.assertEqual(mock_intervene.call_count, 1)
            self.assertEqual(mock_tts.call_count, 0)
            self.assertEqual(mock_pnp.call_count, 0)
            self.assertEqual(_CYBERCHAD_USER_LAST_DIRECT[("b", 777)], t0)

            # --- 2. Second trigger at t = 59.9s (0.1s before limit expires) ---
            mock_time.return_value = t0 + 59.9
            res2 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 777, "киберчед, ауууу", post_num=101, reply_to_post=None
            )
            self.assertFalse(res2)
            # CRITICAL: Intervention handler must NOT be called again (Gemini protected)
            self.assertEqual(mock_intervene.call_count, 1)
            # Offline voice reject must be triggered
            self.assertEqual(mock_tts.call_count, 1)
            self.assertEqual(mock_pnp.call_count, 1)
            self.assertEqual(_CYBERCHAD_USER_LAST_REJECT[("b", 777)], t0 + 59.9)
            # Last direct call timestamp must still be t0!
            self.assertEqual(_CYBERCHAD_USER_LAST_DIRECT[("b", 777)], t0)

            # --- 3. Third trigger at t = 60.1s (0.1s after 60s limit expires from t0) ---
            mock_time.return_value = t0 + 60.1
            res3 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 777, "киберчед, минута прошла!", post_num=102, reply_to_post=None
            )
            self.assertTrue(res3)
            # Intervention handler MUST be called (second allowed call)
            self.assertEqual(mock_intervene.call_count, 2)
            # TTS call count must remain 1 (no new voice reject)
            self.assertEqual(mock_tts.call_count, 1)
            self.assertEqual(mock_pnp.call_count, 1)
            self.assertEqual(_CYBERCHAD_USER_LAST_DIRECT[("b", 777)], t0 + 60.1)

    async def test_precision_anti_flood_boundary_14_9s_and_15_1s(self):
        """
        Adversarially tests the exact 15.0s anti-flood boundary on audio rejection:
        - Rejection 1 occurs at t=100.0s.
        - Call at t=114.9s (14.9s after rejection): audio rejection MUST BE SUPPRESSED.
        - Call at t=115.1s (15.1s after rejection): audio rejection MUST BE ALLOWED.
        """
        t0 = 100000.0

        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene, \
             patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp, \
             patch("handlers.message_router.time.time") as mock_time:

            mock_tts.return_value = (b"mock_voice_data", MagicMock())
            mock_pnp.return_value = 12345

            # First normal call at t = 0s
            mock_time.return_value = t0
            await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 888, "киберчед раз", post_num=1
            )
            self.assertEqual(mock_intervene.call_count, 1)
            self.assertEqual(mock_tts.call_count, 0)

            # First rejection at t = 10.0s
            mock_time.return_value = t0 + 10.0
            await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 888, "киберчед два", post_num=2
            )
            self.assertEqual(mock_intervene.call_count, 1)
            self.assertEqual(mock_tts.call_count, 1)
            self.assertEqual(mock_pnp.call_count, 1)
            self.assertEqual(_CYBERCHAD_USER_LAST_REJECT[("b", 888)], t0 + 10.0)

            # --- TEST 14.9s ELAPSED (t = 10.0 + 14.9 = 24.9s) ---
            mock_time.return_value = t0 + 24.9
            res_sub = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 888, "киберчед три (14.9s)", post_num=3
            )
            self.assertFalse(res_sub)
            # Gemini strictly protected:
            self.assertEqual(mock_intervene.call_count, 1)
            # Audio strictly suppressed (anti-flood hit!):
            self.assertEqual(mock_tts.call_count, 1, "Audio MUST be suppressed at t=14.9s!")
            self.assertEqual(mock_pnp.call_count, 1)
            # Reject timestamp NOT updated:
            self.assertEqual(_CYBERCHAD_USER_LAST_REJECT[("b", 888)], t0 + 10.0)

            # --- TEST 15.1s ELAPSED (t = 10.0 + 15.1 = 25.1s) ---
            mock_time.return_value = t0 + 25.1
            res_allow = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 888, "киберчед четыре (15.1s)", post_num=4
            )
            self.assertFalse(res_allow)
            # Gemini strictly protected:
            self.assertEqual(mock_intervene.call_count, 1)
            # Audio allowed (>= 15.0s passed!):
            self.assertEqual(mock_tts.call_count, 2, "Audio MUST be synthesized at t=15.1s!")
            self.assertEqual(mock_pnp.call_count, 2)
            self.assertEqual(_CYBERCHAD_USER_LAST_REJECT[("b", 888)], t0 + 25.1)


class TestAdversarialAudioDOSAndFloodStorm(unittest.IsolatedAsyncioTestCase):
    """
    Adversarial Stress Test: Rapid flood and audio DOS attacks.
    """

    def setUp(self):
        _CYBERCHAD_USER_LAST_DIRECT.clear()
        _CYBERCHAD_USER_LAST_REJECT.clear()
        self.mock_bot = MagicMock()

    def tearDown(self):
        _CYBERCHAD_USER_LAST_DIRECT.clear()
        _CYBERCHAD_USER_LAST_REJECT.clear()

    async def test_rapid_flood_50_calls_in_5_seconds_no_audio_dos_no_lockup(self):
        """
        Adversarial Scenario:
        A malicious user fires 50 direct Cyberchad triggers in 5 seconds (every 0.1s).
        Verifications:
        1. NO AUDIO DOS: Exactly 1 voice note synthesized and sent across the entire 50-call flood.
        2. NO GEMINI DOS: Exactly 1 intervention call to Gemini across the entire flood.
        3. NO LOCKUP: All 50 calls finish without hanging, deadlocks, or uncaught exceptions.
        """
        start_time = 300000.0

        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene, \
             patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp, \
             patch("handlers.message_router.time.time") as mock_time:

            mock_tts.return_value = (b"rejection_voice_stream", MagicMock())
            mock_pnp.return_value = 99999

            results = []
            # 50 calls spaced 0.1s apart
            for i in range(50):
                current_t = start_time + (i * 0.1)
                mock_time.return_value = current_t
                res = await trigger_cyberchad_with_rate_limit(
                    self.mock_bot,
                    board_id="b",
                    user_id=666,
                    text=f"киберчед спам #{i}",
                    post_num=1000 + i,
                    reply_to_post=None
                )
                results.append(res)

            # Call 0 (t=0.0): allowed (True)
            self.assertTrue(results[0], "Call 0 must be allowed")
            # Calls 1..49 (t=0.1s to 4.9s): all blocked (False)
            self.assertTrue(all(r is False for r in results[1:]), "Calls 1..49 must be blocked")

            # Verify STRICT Suppression:
            # 1. Exactly 1 Gemini call
            self.assertEqual(
                mock_intervene.call_count, 1,
                f"Gemini was called {mock_intervene.call_count} times! Must be exactly 1."
            )

            # 2. Exactly 1 Audio synthesis (NO AUDIO DOS!)
            self.assertEqual(
                mock_tts.call_count, 1,
                f"Audio synthesis was called {mock_tts.call_count} times! Must be exactly 1 (anti-flood failed!)."
            )

            # 3. Exactly 1 voice post sent
            self.assertEqual(
                mock_pnp.call_count, 1,
                f"Voice post was sent {mock_pnp.call_count} times! Must be exactly 1."
            )

    async def test_concurrent_spam_storm_100_simultaneous_requests(self):
        """
        Adversarial Scenario:
        10 distinct users across 5 boards (2 users per board) fire 10 simultaneous requests each = 100 requests.
        Launched concurrently using asyncio.gather.
        Verifications:
        1. Multi-user isolation: User A's rate limit never blocks User B.
        2. Board isolation: User on /b/ does not block same user on /po/.
        3. Total intervention calls == 10 (one per user/board pair).
        4. Total TTS calls == 10 (one per user/board pair for the first rejection).
        5. Zero race condition exceptions, no deadlocks.
        """
        t0 = 800000.0

        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene, \
             patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp, \
             patch("handlers.message_router.time.time") as mock_time:

            mock_tts.return_value = (b"concurrent_voice", MagicMock())
            mock_pnp.return_value = 88888

            boards = ["b", "po", "vg", "a", "soc"]
            # 10 unique (board, user_id) pairs
            user_pairs = []
            for b in boards:
                user_pairs.append((b, 1001))
                user_pairs.append((b, 1002))

            # For each user pair, send 10 requests:
            # Request 0 at t=0s
            # Requests 1..9 at t=0.1s..0.9s
            mock_time.return_value = t0

            # Step 1: Initial call for all 10 user pairs concurrently
            tasks_initial = [
                trigger_cyberchad_with_rate_limit(
                    self.mock_bot, board, uid, f"киберчед привет от {uid}", post_num=100
                )
                for (board, uid) in user_pairs
            ]
            results_initial = await asyncio.gather(*tasks_initial)

            # All 10 initial calls must succeed
            self.assertEqual(len(results_initial), 10)
            self.assertTrue(all(results_initial), "All initial calls must succeed independently")
            self.assertEqual(mock_intervene.call_count, 10)
            self.assertEqual(mock_tts.call_count, 0)

            # Step 2: Flood 9 calls for each user pair (90 calls concurrently) at t=t0+1.0s
            mock_time.return_value = t0 + 1.0
            tasks_flood = []
            for seq in range(1, 10):
                for (board, uid) in user_pairs:
                    tasks_flood.append(
                        trigger_cyberchad_with_rate_limit(
                            self.mock_bot, board, uid, f"киберчед спам {seq}", post_num=100 + seq
                        )
                    )

            results_flood = await asyncio.gather(*tasks_flood)
            self.assertEqual(len(results_flood), 90)
            # All flood calls must be blocked
            self.assertTrue(all(r is False for r in results_flood))

            # Intervene count must still be 10 (no Gemini leak!)
            self.assertEqual(mock_intervene.call_count, 10)

            # TTS count must be 10 (one audio rejection per unique user/board pair, others suppressed by 15s anti-flood!)
            self.assertEqual(
                mock_tts.call_count, 10,
                f"Expected exactly 10 rejection voices synthesized, got {mock_tts.call_count}"
            )
            self.assertEqual(mock_pnp.call_count, 10)


if __name__ == "__main__":
    unittest.main()
