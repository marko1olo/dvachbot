# -*- coding: utf-8 -*-
"""
Tests for CyberChad 15-second Activation Debounce & Message Accumulation.
Verifies the user directive:
- When user summons CyberChad, do not reply immediately.
- Wait up to 15 seconds, accumulating follow-up messages into a unified batch.
- When timer expires (or user goes silent, or max 3 messages reached),
  dispatch a single unified CyberChad response.
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from common.cyberchad_debouncer import (
    clear_all_debounce_sessions,
    is_user_debouncing,
    get_debounce_session,
    format_debounce_batch_text,
    CyberchadDebounceItem,
    MAX_DEBOUNCE_SECONDS,
    DEFAULT_SILENCE_SECONDS,
    MAX_BATCH_MESSAGES,
)
from handlers.message_router import (
    _CYBERCHAD_USER_LAST_DIRECT,
    _CYBERCHAD_USER_LAST_REJECT,
    trigger_cyberchad_with_rate_limit,
)


class TestCyberchadDebounceLifecycle(unittest.IsolatedAsyncioTestCase):
    """Verifies the complete debounce accumulator lifecycle."""

    async def asyncSetUp(self):
        clear_all_debounce_sessions()
        _CYBERCHAD_USER_LAST_DIRECT.clear()
        _CYBERCHAD_USER_LAST_REJECT.clear()
        self.mock_bot = MagicMock()
        async with shared_state.storage_lock:
            shared_state.messages_storage.clear()

    async def asyncTearDown(self):
        clear_all_debounce_sessions()
        _CYBERCHAD_USER_LAST_DIRECT.clear()
        _CYBERCHAD_USER_LAST_REJECT.clear()
        async with shared_state.storage_lock:
            shared_state.messages_storage.clear()

    def test_constants_and_formatting(self):
        self.assertEqual(MAX_DEBOUNCE_SECONDS, 15.0)
        self.assertEqual(DEFAULT_SILENCE_SECONDS, 4.0)
        self.assertEqual(MAX_BATCH_MESSAGES, 3)

        # Single message formatting returns text as-is
        item1 = CyberchadDebounceItem(post_num=101, text="Киберчед ответь", reply_to_post=None, timestamp=1.0)
        self.assertEqual(format_debounce_batch_text([item1]), "Киберчед ответь")

        # Multi-message formatting produces clear bullet list of posts
        item2 = CyberchadDebounceItem(post_num=102, text="он гонит пургу", reply_to_post=None, timestamp=2.0)
        formatted = format_debounce_batch_text([item1, item2])
        self.assertIn("• #101: Киберчед ответь", formatted)
        self.assertIn("• #102: он гонит пургу", formatted)

    async def test_single_message_flushes_after_silence_timeout(self):
        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene:
            # Trigger summon with debounce=True and short test timeout (0.15s)
            res = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед поясни",
                post_num=1001, reply_to_post=None, stream="ru",
                debounce=True, debounce_seconds=1.0, silence_seconds=0.15
            )
            self.assertTrue(res)
            # Must be actively debouncing, NOT dispatched to intervene yet!
            self.assertTrue(is_user_debouncing("b", 101))
            mock_intervene.assert_not_called()

            # Wait for silence timeout
            await asyncio.sleep(0.25)

            # Debounce session must be finished and flushed
            self.assertFalse(is_user_debouncing("b", 101))
            mock_intervene.assert_called_once()
            call_kwargs = mock_intervene.call_args[1] if mock_intervene.call_args[1] else {}
            call_args = mock_intervene.call_args[0]
            # Verify target post and text
            self.assertEqual(call_args[1], "b")
            self.assertEqual(call_args[2], 101)
            self.assertEqual(call_args[3], "киберчед поясни")
            self.assertEqual(call_kwargs.get("post_num") or call_args[4], 1001)

            # User rate limit timestamp must be recorded after flush
            self.assertIn(("b", 101), _CYBERCHAD_USER_LAST_DIRECT)

    async def test_accumulates_followup_messages_into_single_batch(self):
        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene:
            # Post 1 (Summon mentioning CyberChad)
            res1 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "Киберчед, глянь на него",
                post_num=1001, reply_to_post=900, stream="ru",
                debounce=True, debounce_seconds=2.0, silence_seconds=0.3
            )
            self.assertTrue(res1)
            self.assertTrue(is_user_debouncing("b", 101))

            # Post 2 (Follow-up WITHOUT mentioning CyberChad)
            await asyncio.sleep(0.05)
            res2 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "он утверждает что земля плоская",
                post_num=1002, reply_to_post=None, stream="ru",
                debounce=True, debounce_seconds=2.0, silence_seconds=0.3
            )
            self.assertTrue(res2)
            # Session must contain 2 messages
            session = get_debounce_session("b", 101)
            self.assertIsNotNone(session)
            self.assertEqual(len(session.messages), 2)

            # Post 3 (Second follow-up -> max batch size 3 reached -> triggers immediate flush!)
            await asyncio.sleep(0.05)
            res3 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "поясни ему за физику",
                post_num=1003, reply_to_post=None, stream="ru",
                debounce=True, debounce_seconds=2.0, silence_seconds=0.3
            )
            self.assertTrue(res3)

            # Yield to loop to let flush complete
            await asyncio.sleep(0.05)

            # Debounce finished
            self.assertFalse(is_user_debouncing("b", 101))
            # Exactly 1 intervention call dispatched!
            self.assertEqual(mock_intervene.call_count, 1)

            call_args = mock_intervene.call_args[0]
            combined_text = call_args[3]
            target_post_num = mock_intervene.call_args[1].get("post_num") or call_args[4]
            target_reply_to = mock_intervene.call_args[1].get("reply_to_post")

            # Target post must be the LATEST message from the batch (#1003)
            self.assertEqual(target_post_num, 1003)
            # Parent post must preserve the initial target (#900)
            self.assertEqual(target_reply_to, 900)
            # Combined text must contain all three user statements
            self.assertIn("• #1001: Киберчед, глянь на него", combined_text)
            self.assertIn("• #1002: он утверждает что земля плоская", combined_text)
            self.assertIn("• #1003: поясни ему за физику", combined_text)

    async def test_multi_user_debounce_isolation(self):
        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene:
            # User 101 calls CyberChad
            await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед юзер 101 пост 1",
                post_num=1001, reply_to_post=None, stream="ru",
                debounce=True, debounce_seconds=1.0, silence_seconds=0.2
            )

            # User 102 calls CyberChad on same board
            await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 102, "киберчед юзер 102 пост 1",
                post_num=2001, reply_to_post=None, stream="ru",
                debounce=True, debounce_seconds=1.0, silence_seconds=0.5
            )

            # User 101 adds second message
            await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "юзер 101 пост 2",
                post_num=1002, reply_to_post=None, stream="ru",
                debounce=True
            )

            # User 101's silence timer (0.2s) should flush first
            await asyncio.sleep(0.3)
            self.assertFalse(is_user_debouncing("b", 101))
            self.assertTrue(is_user_debouncing("b", 102))
            self.assertEqual(mock_intervene.call_count, 1)
            self.assertEqual(mock_intervene.call_args[0][2], 101)

            # User 102 flushes next
            await asyncio.sleep(0.35)
            self.assertFalse(is_user_debouncing("b", 102))
            self.assertEqual(mock_intervene.call_count, 2)
            self.assertEqual(mock_intervene.call_args[0][2], 102)

    async def test_rate_limit_cooldown_enforced_after_batch_flush(self):
        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene:
            # 1. Trigger summon
            await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед эй",
                post_num=1001, reply_to_post=None, stream="ru",
                debounce=True, debounce_seconds=0.2, silence_seconds=0.1
            )
            # Wait for flush
            await asyncio.sleep(0.25)
            self.assertEqual(mock_intervene.call_count, 1)

            # 2. Attempt to summon again immediately (< 30s user cooldown)
            res_repeat = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед я снова тут",
                post_num=1002, reply_to_post=None, stream="ru",
                debounce=True
            )
            # Must be rejected by rate limiter
            self.assertFalse(res_repeat)
            # No new debounce session opened
            self.assertFalse(is_user_debouncing("b", 101))
            # Intervention must still be only 1 call
            self.assertEqual(mock_intervene.call_count, 1)


if __name__ == "__main__":
    unittest.main()
