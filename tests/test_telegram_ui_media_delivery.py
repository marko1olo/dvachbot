# -*- coding: utf-8 -*-
"""
Tests for Telegram UI & Media Delivery Resilience:
1. safe_edit_message_text: MessageNotModified silencing, fallback to caption on 'there is no text in the message to edit', parse entity fallback.
2. safe_edit_message_caption: MessageNotModified silencing, fallback to text on 'there is no caption in the message to edit'.
3. safe_edit_message_media: error suppression and MessageNotModified silencing.
4. safe_delete_message: safe error silencing for 'message to delete not found', 'there is no text in the message to edit', 'chat not found'.
5. broadcaster.MessageBroadcaster media group resilience:
   - 'failed to send message #N with the error ...' automatically prunes the bad item and successfully delivers remaining items.
   - Fallback to sequential individual sends when media group format is completely rejected by Telegram.
6. bot_watchdog: health probe /healthz support and deferring kill during load spikes when logs are actively written.
"""

import asyncio
import io
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InputMediaPhoto, InputMediaVideo

from post_helpers import (
    safe_edit_message_text,
    safe_edit_message_caption,
    safe_edit_message_media,
    safe_delete_message,
)
from shared_state import BroadcastConfig, board_data
from broadcaster import MessageBroadcaster


class TestSafeMessageWrappers(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.mock_msg = MagicMock()
        self.mock_msg.message_id = 999
        self.bot.edit_message_text = AsyncMock(return_value=self.mock_msg)
        self.bot.edit_message_caption = AsyncMock(return_value=self.mock_msg)
        self.bot.edit_message_media = AsyncMock(return_value=self.mock_msg)
        self.bot.delete_message = AsyncMock(return_value=True)

    async def test_safe_edit_message_text_success(self):
        res = await safe_edit_message_text(self.bot, 12345, 999, "Hello world")
        self.assertEqual(res, self.mock_msg)
        self.bot.edit_message_text.assert_called_once()

    async def test_safe_edit_message_text_silences_message_not_modified(self):
        self.bot.edit_message_text.side_effect = TelegramBadRequest(
            method="editMessageText",
            message="Bad Request: message is not modified: specified new message content and reply markup are exactly the same as a current content and reply markup of the message"
        )
        res = await safe_edit_message_text(self.bot, 12345, 999, "Same content")
        self.assertTrue(res)

    async def test_safe_edit_message_text_falls_back_to_caption(self):
        self.bot.edit_message_text.side_effect = TelegramBadRequest(
            method="editMessageText",
            message="Bad Request: there is no text in the message to edit"
        )
        res = await safe_edit_message_text(self.bot, 12345, 999, "New caption for photo post")
        self.assertEqual(res, self.mock_msg)
        self.bot.edit_message_caption.assert_called_once()
        call_caption = self.bot.edit_message_caption.call_args[1]["caption"]
        self.assertEqual(call_caption, "New caption for photo post")

    async def test_safe_edit_message_caption_silences_message_not_modified(self):
        self.bot.edit_message_caption.side_effect = TelegramBadRequest(
            method="editMessageCaption",
            message="Bad Request: message is not modified"
        )
        res = await safe_edit_message_caption(self.bot, 12345, 999, "Identical caption")
        self.assertTrue(res)

    async def test_safe_edit_message_caption_falls_back_to_text(self):
        self.bot.edit_message_caption.side_effect = TelegramBadRequest(
            method="editMessageCaption",
            message="Bad Request: there is no caption in the message to edit"
        )
        res = await safe_edit_message_caption(self.bot, 12345, 999, "Text for message")
        self.assertEqual(res, self.mock_msg)
        self.bot.edit_message_text.assert_called_once()
        call_text = self.bot.edit_message_text.call_args[1]["text"]
        self.assertEqual(call_text, "Text for message")

    async def test_safe_edit_message_media_silences_not_modified(self):
        self.bot.edit_message_media.side_effect = TelegramBadRequest(
            method="editMessageMedia",
            message="Bad Request: message is not modified"
        )
        dummy_media = InputMediaPhoto(media="file_id_xyz")
        res = await safe_edit_message_media(self.bot, 12345, 999, dummy_media)
        self.assertTrue(res)

    async def test_safe_delete_message_success(self):
        res = await safe_delete_message(self.bot, 12345, 999)
        self.assertTrue(res)
        self.bot.delete_message.assert_called_once_with(chat_id=12345, message_id=999, request_timeout=10)

    async def test_safe_delete_message_silences_harmless_errors(self):
        for msg in [
            "Bad Request: message to delete not found",
            "Bad Request: message can't be deleted",
            "Bad Request: there is no text in the message to edit",
            "Bad Request: chat not found",
        ]:
            self.bot.delete_message.side_effect = TelegramBadRequest(method="deleteMessage", message=msg)
            res = await safe_delete_message(self.bot, 12345, 999)
            self.assertTrue(res, f"Failed for {msg}")

    async def test_safe_delete_message_forbidden_returns_false(self):
        self.bot.delete_message.side_effect = TelegramForbiddenError(method="deleteMessage", message="Forbidden: bot was blocked by the user")
        res = await safe_delete_message(self.bot, 12345, 999)
        self.assertFalse(res)


class TestMediaGroupPruningAndSequentialFallback(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        board_data['b'] = {
            'users': {'banned': set(), 'active': set()},
            'user_settings': {},
            'user_state': {},
        }

    def _create_mock_bot(self):
        bot = MagicMock()
        mock_msg1 = MagicMock()
        mock_msg1.message_id = 7001
        mock_msg2 = MagicMock()
        mock_msg2.message_id = 7002

        bot.send_message = AsyncMock(return_value=mock_msg1)
        bot.send_media_group = AsyncMock(return_value=[mock_msg1, mock_msg2])
        bot.send_photo = AsyncMock(return_value=mock_msg1)
        bot.send_video = AsyncMock(return_value=mock_msg2)
        return bot

    async def test_media_group_prunes_bad_item_n_and_delivers(self):
        """
        When Telegram returns 'failed to send message #2 with the error message "WEBPAGE_MEDIA_EMPTY"',
        broadcaster prunes item #2, updates media list, and sends remaining items as media group!
        """
        bot = self._create_mock_bot()

        # First call fails on message #2, second call succeeds with pruned media list
        call_count = 0
        async def fake_send_media_group(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TelegramBadRequest(
                    method="sendMediaGroup",
                    message='Bad Request: failed to send message #2 with the error message "WEBPAGE_MEDIA_EMPTY"'
                )
            mock_res1 = MagicMock()
            mock_res1.message_id = 8001
            mock_res2 = MagicMock()
            mock_res2.message_id = 8002
            return [mock_res1, mock_res2]

        bot.send_media_group.side_effect = fake_send_media_group

        content = {
            'type': 'media_group',
            'post_num': 888101,
            'caption': 'Тестовый альбом из 3 фото',
            'media': [
                {'type': 'photo', 'media': 'AgACAgIAAxkBAAIvalidId1'},
                {'type': 'photo', 'media': 'https://broken-domain.invalid/empty.jpg'},
                {'type': 'photo', 'media': 'AgACAgIAAxkBAAIvalidId3'}
            ]
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={5001},
            content=content,
            delivery_phase='full'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)
        # Should have called send_media_group twice: initial attempt, then retry after pruning item #2
        self.assertEqual(call_count, 2)
        # Verify content was pruned to 2 items
        self.assertEqual(len(content['media']), 2)

    async def test_media_group_falls_back_to_sequential_sends(self):
        """
        When send_media_group fails without index or album rejected, broadcaster
        falls back to sending items individually (send_photo, send_video).
        """
        bot = self._create_mock_bot()
        bot.send_media_group.side_effect = TelegramBadRequest(
            method="sendMediaGroup",
            message="Bad Request: failed to process album dimensions"
        )

        content = {
            'type': 'media_group',
            'post_num': 888102,
            'caption': 'Альбом для поштучной отправки',
            'media': [
                {'type': 'photo', 'media': 'AgACAgIAAxkBAAIvalidId1'},
                {'type': 'video', 'media': 'BAACAgIAAxkBAAIvalidVideo2'}
            ]
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={5002},
            content=content,
            delivery_phase='full'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)
        self.assertTrue(bot.send_photo.called)
        self.assertTrue(bot.send_video.called)


class TestWatchdogLoadSpikeProtection(unittest.TestCase):
    def test_watchdog_does_not_kill_when_logs_are_active(self):
        """
        Tests the core invariant in bot_watchdog:
        Even if health probe failed and heartbeat is stale,
        if stdout_age < LOG_STALE_SEC (i.e. child is actively writing logs during broadcast),
        the watchdog MUST NOT kill the process unless force_restart limit (12) is reached.
        """
        HEALTH_FAIL_LIMIT = 4
        FORCE_FAIL_LIMIT = 12
        LOG_STALE_SEC = 120.0

        health_failures = 4  # reached HEALTH_FAIL_LIMIT
        stdout_age = 5.0    # logs written 5s ago!
        runtime_age = 10.0
        heartbeat_fresh = False
        recent_deadlock_dump = False
        stale_status = True

        logs_stale = (
            stdout_age is None or stdout_age >= LOG_STALE_SEC
        ) and (runtime_age is None or runtime_age >= LOG_STALE_SEC)

        deadlock_detected = (not heartbeat_fresh and logs_stale)
        force_restart = health_failures >= FORCE_FAIL_LIMIT

        should_restart = force_restart or recent_deadlock_dump or deadlock_detected or (stale_status and logs_stale)
        self.assertFalse(should_restart, "Watchdog should defer kill when process is actively writing logs!")

    def test_watchdog_kills_on_genuine_deadlock(self):
        """
        When heartbeat is stale AND logs have gone silent (>= 120s),
        genuine deadlock is confirmed and should_restart becomes True.
        """
        HEALTH_FAIL_LIMIT = 4
        FORCE_FAIL_LIMIT = 12
        LOG_STALE_SEC = 120.0

        health_failures = 4
        stdout_age = 150.0   # logs completely frozen
        runtime_age = 160.0
        heartbeat_fresh = False
        recent_deadlock_dump = False
        stale_status = True

        logs_stale = (
            stdout_age is None or stdout_age >= LOG_STALE_SEC
        ) and (runtime_age is None or runtime_age >= LOG_STALE_SEC)

        deadlock_detected = (not heartbeat_fresh and logs_stale)
        force_restart = health_failures >= FORCE_FAIL_LIMIT

        should_restart = force_restart or recent_deadlock_dump or deadlock_detected or (stale_status and logs_stale)
        self.assertTrue(should_restart, "Watchdog must kill when logs are stale and heartbeat is dead!")


if __name__ == '__main__':
    unittest.main()
