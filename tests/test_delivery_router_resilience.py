# -*- coding: utf-8 -*-
"""
tests/test_delivery_router_resilience.py

Comprehensive test suite verifying resilience for:
1. anchor_bot: Gemini safety refusal detection, Groq/Cyberchad fallback, TTS timeout guard.
2. broadcaster: voice_messages_forbidden fallback with transcript & link, >10MB photo to document fallback.
3. delivery_manager: bounded concurrency post copy edits (_POST_EDIT_SEMAPHORE), fast non-blocking timeout.
4. message_router: safe UTF-8 log formatting (no mojibake), service timeout notifications.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile
import shared_state
from shared_state import BroadcastConfig, board_data, messages_storage, post_to_messages
import broadcaster
from broadcaster import MessageBroadcaster
import anchor_bot
from anchor_bot import is_gemini_service_refusal, generate_anchor_reply, fire_anchor_post, ANCHOR_FALLBACK_ROASTS
import delivery_manager
from delivery_manager import _POST_EDIT_SEMAPHORE, edit_post_for_all_recipients
import handlers.message_router as mr
from handlers.message_router import safe_format_log_text, notify_service_timeout


class TestAnchorBotResilience(unittest.IsolatedAsyncioTestCase):
    """Verifies anchor_bot safety refusal handling, multi-tier fallback, and TTS guards."""

    def test_gemini_service_refusal_patterns(self):
        # 1. Real Gemini refusal observed in production logs:
        real_refusal = (
            "I cannot adopt a persona to generate explicit profanity, insults, or targeted abuse. "
            "However, I can offer an objective analysis of why people might complain or express frustration..."
        )
        self.assertTrue(is_gemini_service_refusal(real_refusal))

        # 2. Common variants:
        self.assertTrue(is_gemini_service_refusal("I cannot fulfill this request due to safety policies."))
        self.assertTrue(is_gemini_service_refusal("As an AI language model, I cannot generate profanity."))
        self.assertTrue(is_gemini_service_refusal("Я не могу выполнить этот запрос в соответствии с политикой безопасности."))

        # 3. Legitimate Russian imageboard roast must NOT be flagged:
        legit_roast = "Хватит скулить в треде, омежки. Закройте двач и займитесь делом, пока жизнь вас не смыла."
        self.assertFalse(is_gemini_service_refusal(legit_roast))
        self.assertFalse(is_gemini_service_refusal(None))
        self.assertFalse(is_gemini_service_refusal(""))

    @patch("summarize.summarize_text_with_hf")
    async def test_generate_anchor_reply_gemini_refusal_falls_back_to_groq(self, mock_summarize):
        refusal_msg = "I cannot adopt a persona to generate explicit profanity, insults, or targeted abuse."
        groq_roast = "Опять перепись обиженных жизнью омежек. Соберитесь, тряпки, и перестаньте позориться."

        # First call (Gemini persona) returns refusal, second call (Groq llama) returns roast
        mock_summarize.side_effect = [refusal_msg, groq_roast]

        reply = await generate_anchor_reply(["Нытье 1", "Нытье 2"])
        self.assertEqual(reply, groq_roast)
        self.assertEqual(mock_summarize.call_count, 2)
        # Verify second call used model_preference="llama" (Groq)
        self.assertEqual(mock_summarize.call_args_list[1].kwargs.get("model_preference"), "llama")

    @patch("summarize.summarize_text_with_hf")
    async def test_generate_anchor_reply_all_refusals_falls_back_to_cyberchad_roast(self, mock_summarize):
        refusal_msg = "I cannot adopt a persona to generate explicit profanity..."
        # Both Gemini and Groq refuse or fail
        mock_summarize.side_effect = [refusal_msg, refusal_msg]

        reply = await generate_anchor_reply(["Нытье 1"])
        self.assertIsNotNone(reply)
        self.assertFalse(is_gemini_service_refusal(reply))
        self.assertIn(reply, ANCHOR_FALLBACK_ROASTS)

    @patch("common.tts_engine.synthesize_cyberchad_voice_with_meta")
    @patch("anchor_bot.generate_anchor_reply")
    async def test_fire_anchor_post_tts_guard_timeout(self, mock_gen, mock_tts):
        mock_gen.return_value = "Базированный разгон от Чеда"
        # Simulate TTS timing out
        mock_tts.side_effect = asyncio.TimeoutError()

        mock_bot = MagicMock()
        success = await fire_anchor_post(mock_bot, "b", "ru", ["контекст"])
        # Must gracefully abort without crashing and return False
        self.assertFalse(success)


class TestBroadcasterMediaAndVoiceResilience(unittest.IsolatedAsyncioTestCase):
    """Verifies broadcaster handling of voice_messages_forbidden and media > 10MB."""

    def setUp(self):
        board_data['b'] = {
            'users': {'banned': set(), 'active': set()},
            'user_settings': {},
            'user_state': {},
        }

    def _create_mock_bot(self):
        bot = MagicMock()
        mock_msg = MagicMock()
        mock_msg.message_id = 100201
        bot.send_message = AsyncMock(return_value=mock_msg)
        bot.send_photo = AsyncMock(return_value=mock_msg)
        bot.send_document = AsyncMock(return_value=mock_msg)
        bot.send_voice = AsyncMock(return_value=mock_msg)
        bot.send_media_group = AsyncMock(return_value=[mock_msg])
        return bot

    async def test_voice_messages_forbidden_fallback_delivers_transcript_and_link(self):
        """When Telegram returns voice_messages_forbidden, user must receive transcript & post link."""
        bot = self._create_mock_bot()
        # Simulate Telegram API privacy rejection
        bot.send_voice.side_effect = TelegramBadRequest(
            method="sendVoice",
            message="Bad Request: voice_messages_forbidden"
        )

        content = {
            'type': 'voice',
            'post_num': 88001,
            'voice_bytes': b"OggS_fake_audio_bytes",
            'caption': '🔥 Разъёб от Киберчеда',
            'transcription': 'Хватит ныть в треде, омежка. Иди делом займись.',
            'roast_text': 'Хватит ныть в треде, омежка. Иди делом займись.',
            'thread_id': 'thread_abc123'
        }

        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={9001},
            content=content,
            delivery_phase='active'
        )

        broadcaster_inst = MessageBroadcaster(cfg)
        res = await broadcaster_inst.broadcast()

        self.assertEqual(broadcaster_inst.stats['success'], 1)
        self.assertTrue(bot.send_message.called)
        sent_text = bot.send_message.call_args.kwargs['text']

        # Transcription and post link must be present in delivered text
        self.assertIn("Хватит ныть в треде, омежка", sent_text)
        self.assertIn("Голосовое сообщение", sent_text)
        self.assertIn("tgach.top/b/res/thread_abc123.html#88001", sent_text)

    async def test_single_photo_over_10mb_proactively_sent_as_document(self):
        """A photo file between 10MB and 50MB exceeds Telegram photo limit, so must send as document."""
        bot = self._create_mock_bot()
        # 12 MB image buffer
        large_image_bytes = b"X" * (12 * 1024 * 1024)

        content = {
            'type': 'photo',
            'post_num': 88002,
            'image_bytes': large_image_bytes,
            'caption': 'Большая пикча 12МБ'
        }

        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={9002},
            content=content,
            delivery_phase='active'
        )

        broadcaster_inst = MessageBroadcaster(cfg)
        await broadcaster_inst.broadcast()

        self.assertEqual(broadcaster_inst.stats['success'], 1)
        # Must be dispatched via send_document, NOT send_photo
        self.assertTrue(bot.send_document.called)
        self.assertFalse(bot.send_photo.called)

    async def test_photo_telegram_too_big_rejected_retries_as_document(self):
        """If Telegram rejects send_photo with 'too big for a photo', broadcaster retries as document."""
        bot = self._create_mock_bot()
        bot.send_photo.side_effect = TelegramBadRequest(
            method="sendPhoto",
            message="Bad Request: file of size 11000000 is too big for a photo"
        )

        content = {
            'type': 'photo',
            'post_num': 88003,
            'file_id': 'AgAC_huge_photo_fid',
            'caption': 'Пикча на границе 10МБ'
        }

        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={9003},
            content=content,
            delivery_phase='active'
        )

        broadcaster_inst = MessageBroadcaster(cfg)
        await broadcaster_inst.broadcast()

        self.assertEqual(broadcaster_inst.stats['success'], 1)
        self.assertTrue(bot.send_document.called)

    async def test_media_group_sequential_fallback_photo_too_big_uses_document(self):
        """In media group sequential fallback, if a photo is too big, it sends as document."""
        bot = self._create_mock_bot()
        # Fail the album send to trigger sequential fallback
        bot.send_media_group.side_effect = TelegramBadRequest(
            method="sendMediaGroup",
            message="Bad Request: failed to send media group"
        )
        # In sequential, send_photo fails because photo is too big
        bot.send_photo.side_effect = TelegramBadRequest(
            method="sendPhoto",
            message="Bad Request: file of size 12000000 is too big for a photo"
        )

        content = {
            'type': 'media_group',
            'post_num': 88004,
            'text': 'Альбом с тяжёлой картинкой',
            'media': [
                {'type': 'photo', 'media': 'AgAC_too_big_photo_fid'}
            ]
        }

        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={9004},
            content=content,
            delivery_phase='active'
        )

        broadcaster_inst = MessageBroadcaster(cfg)
        await broadcaster_inst.broadcast()

        self.assertEqual(broadcaster_inst.stats['success'], 1)
        # Photo was converted to document in sequential fallback
        self.assertTrue(bot.send_document.called)


class TestDeliveryManagerResilience(unittest.IsolatedAsyncioTestCase):
    """Verifies delivery_manager post copy edit concurrency, fast timeouts, and error safety."""

    def setUp(self):
        board_data['b'] = {
            'users': {'banned': set(), 'active': {2001, 2002}},
            'user_settings': {},
            'user_state': {},
        }

    def test_post_edit_semaphore_exists_and_bounded(self):
        self.assertIsInstance(_POST_EDIT_SEMAPHORE, asyncio.Semaphore)
        # Bounded ceiling of 10 concurrent edits
        self.assertEqual(_POST_EDIT_SEMAPHORE._value, 10)

    @patch("delivery_manager.safe_edit_message_text")
    @patch("delivery_manager.get_post_copies")
    async def test_edit_message_copies_fast_timeout_no_hang(self, mock_get_copies, mock_edit):
        """Simulate timeout on message edit: should not hang for 8s or throw unhandled exceptions."""
        mock_get_copies.return_value = [(2001, 5001), (2002, 5002)]
        mock_edit.side_effect = asyncio.TimeoutError()

        mock_bot = MagicMock()
        messages_storage[88005] = {
            'board_id': 'b',
            'content': {'type': 'text', 'text': 'Новый текст поста'},
            'author_id': 111,
            'reactions': {'users': {}}
        }
        post_to_messages[88005] = {2001: 5001, 2002: 5002}

        # Should finish fast (< 3 seconds for 2 users) without blocking
        t_start = asyncio.get_event_loop().time()
        await edit_post_for_all_recipients(88005, mock_bot)
        elapsed = asyncio.get_event_loop().time() - t_start

        self.assertLess(elapsed, 4.0)


class TestMessageRouterResilience(unittest.IsolatedAsyncioTestCase):
    """Verifies message_router log encoding hygiene and service timeout notifications."""

    def test_safe_format_log_text_cyrillic_encoding(self):
        cyrillic_sample = "Привет, двач! 🔥 Тестирование кириллицы без моджибейка и поломки ANSI.\nВторая строка."
        formatted = safe_format_log_text(cyrillic_sample, max_len=60)
        self.assertIn("Привет, двач!", formatted)
        self.assertNotIn("\n", formatted)
        self.assertTrue(len(formatted) <= 60)

        # Empty / None handling
        self.assertEqual(safe_format_log_text(None), "")
        self.assertEqual(safe_format_log_text(""), "")

    async def test_notify_service_timeout_sends_notification(self):
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=777))

        await notify_service_timeout(mock_bot, 12345, "Аниме-сервис")
        self.assertTrue(mock_bot.send_message.called)
        sent_text = mock_bot.send_message.call_args.kwargs['text']
        self.assertIn("Аниме-сервис временно не отвечает", sent_text)


if __name__ == '__main__':
    unittest.main()
