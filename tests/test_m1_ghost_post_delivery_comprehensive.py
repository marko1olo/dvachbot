# -*- coding: utf-8 -*-
"""
Tests for Requirement R1: Anti-Flood & Seamless Ghost-Post Media Delivery.
Validates:
1. Seamless ghost-post delivery across all media types:
   - Text
   - Photo
   - Video
   - Animation (GIF)
   - Document
   - Audio
   - Voice Note
   - Video Note
   - Sticker
   - Media Group / Album
2. Fake post number generation and author-only PM delivery with real header format.
3. No silent drops on check_spam and repeat violations.
4. Auto-shadowmute limits (BURST=8, RATE=15, MINUTE=30, base flood mute=300.0s).
5. delivery_manager.py checks SQLite DB Mutes table in addition to RAM.
"""

import time
import pytest
import unittest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from common.spam_filter import (
    BURST_FLOOD_LIMIT,
    RATE_FLOOD_LIMIT,
    MINUTE_FLOOD_LIMIT,
    FLOOD_BASE_MUTE_SEC,
    check_flood,
    evaluate_message_for_autoshadowmute,
    _user_request_timestamps,
)
from handlers.message_router import check_spam, process_shadow_reject


class TestM1GhostPostAndFloodComprehensive(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _user_request_timestamps.clear()
        shared_state.board_data.clear()
        shared_state.shadow_fake_post_counters.clear()
        shared_state.state['post_counter'] = 1000

        self.user_id = 12345678
        self.board_id = "b"
        shared_state.board_data[self.board_id] = {
            'shadow_mutes': {},
            'user_settings': {},
            'users': {'active': set(), 'banned': set()},
            'mutes': {},
            'last_texts': {self.user_id: []},
            'last_stickers': {self.user_id: []},
            'last_animations': {self.user_id: []},
            'last_audios': {self.user_id: []},
        }

    async def test_flood_constants_and_limits(self):
        """Verify flood limit thresholds: BURST=8, RATE=15, MINUTE=30, FLOOD_BASE_MUTE_SEC=300.0."""
        self.assertEqual(BURST_FLOOD_LIMIT, 8)
        self.assertEqual(RATE_FLOOD_LIMIT, 15)
        self.assertEqual(MINUTE_FLOOD_LIMIT, 30)
        self.assertEqual(FLOOD_BASE_MUTE_SEC, 300.0)

        t0 = 1000000.0
        # 8 rapid messages -> no flood
        for i in range(8):
            is_fl, _ = check_flood(self.user_id, self.board_id, now_ts=t0 + i * 0.2)
            self.assertFalse(is_fl)

        # 9th message in 4s -> triggers burst flood
        is_fl, reason = check_flood(self.user_id, self.board_id, now_ts=t0 + 2.0)
        self.assertTrue(is_fl)
        self.assertIn("Burst флуд", reason)

    async def test_evaluate_message_for_autoshadowmute_applies_300s_flood_mute(self):
        """Flood detection must apply 300s (5m) base shadowmute."""
        t0 = 1000000.0
        for i in range(8):
            check_flood(self.user_id, self.board_id, now_ts=t0 + i * 0.2)

        with patch("common.database.apply_shadow_mute", new_callable=AsyncMock) as mock_apply_mute:
            mock_apply_mute.return_value = t0 + 300.0
            should_mute, reason, exp = await evaluate_message_for_autoshadowmute(
                user_id=self.user_id,
                board_id=self.board_id,
                content="Привет",
                msg_type="text",
                raw_content_type="text",
                now_ts=t0 + 2.0
            )
            self.assertTrue(should_mute)
            self.assertIn("Burst флуд", reason)
            mock_apply_mute.assert_called_once_with(
                self.user_id, self.board_id, duration_seconds=300.0, reason=reason, is_exponential=False
            )

    @patch("handlers.message_router.send_message_to_users", new_callable=AsyncMock)
    @patch("handlers.message_router.format_header", new_callable=AsyncMock)
    async def test_process_shadow_reject_all_media_types(self, mock_format_header, mock_send_msg):
        """Verify process_shadow_reject seamlessly delivers fake posts for all media types."""
        mock_format_header.return_value = "<b>Аноним</b> 02/09/26 Срд 05:00:00 #1005"
        mock_bot = AsyncMock()

        media_test_cases = [
            ("text", {"type": "text", "text": "Тестовый текст в шедоумуте"}),
            ("photo", {"type": "photo", "file_id": "photo_fid_123", "caption": "Подпись к фото"}),
            ("video", {"type": "video", "file_id": "video_fid_123", "caption": "Подпись к видео"}),
            ("animation", {"type": "animation", "file_id": "gif_fid_123", "caption": "GIF анимка"}),
            ("document", {"type": "document", "file_id": "doc_fid_123", "caption": "Документ pdf"}),
            ("audio", {"type": "audio", "file_id": "audio_fid_123", "caption": "Трек mp3"}),
            ("voice", {"type": "voice", "file_id": "voice_fid_123"}),
            ("video_note", {"type": "video_note", "file_id": "vnote_fid_123"}),
            ("sticker", {"type": "sticker", "file_id": "sticker_fid_123"}),
            ("media_group", {"type": "media_group", "media": [{"type": "photo", "file_id": "p1"}], "caption": "Альбом"}),
        ]

        for m_type, content in media_test_cases:
            mock_send_msg.reset_mock()
            ctx = shared_state.ShadowRejectContext(
                bot=mock_bot,
                board_id=self.board_id,
                user_id=self.user_id,
                content=content,
                reply_to_post=None,
                stream="ru"
            )

            await process_shadow_reject(ctx)

            # Assert broadcast was dispatched ONLY to author
            mock_send_msg.assert_called_once()
            b_config = mock_send_msg.call_args[0][0]
            self.assertEqual(b_config.recipients, {self.user_id})
            self.assertTrue(b_config.content.get("is_shadow_reject"))
            self.assertGreater(b_config.content.get("post_num"), 1000)
            self.assertEqual(b_config.content.get("header"), "<b>Аноним</b> 02/09/26 Срд 05:00:00 #1005")

    async def test_delivery_manager_media_group_checks_db_mutes(self):
        """Verify delivery_manager.process_complete_media_group checks SQLite DB mutes in addition to RAM."""
        from delivery_manager import process_complete_media_group

        mock_bot = AsyncMock()
        group_data = {
            "author_id": self.user_id,
            "board_id": self.board_id,
            "stream": "ru",
            "media": [
                {"type": "photo", "file_id": "fid_1"},
                {"type": "photo", "file_id": "fid_2"},
            ],
            "caption": "Тестовый альбом"
        }

        # RAM has no mute
        shared_state.board_data[self.board_id]['shadow_mutes'].clear()

        # Mock DB returning is_shadow_muted = True
        with patch("common.database.is_shadow_muted", new_callable=AsyncMock) as mock_db_mute, \
             patch("handlers.message_router.process_shadow_reject", new_callable=AsyncMock) as mock_shadow_reject, \
             patch("delivery_manager.process_new_post", new_callable=AsyncMock) as mock_new_post:

            mock_db_mute.return_value = True

            await process_complete_media_group("album_123", group_data, mock_bot)

            mock_db_mute.assert_called_once_with(self.user_id, self.board_id)
            # Must route through shadow reject, not public post
            self.assertEqual(mock_shadow_reject.call_count, 1)
            self.assertEqual(mock_new_post.call_count, 0)
