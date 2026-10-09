# -*- coding: utf-8 -*-
"""
tests/test_shadowmute_trap_and_whitelist.py
============================================
Verification suite for:
1. Infinite shadowmute escalation loop fix (Shadowmute Trap):
   - Muted user messages are silently dropped / ghost-routed without exponential compounding.
   - Mute expires at its original scheduled expiration time.
   - No mute notification is sent to the user.
2. Archive / Board whitelist and Telegram links de-escalation:
   - Official whitelist (tgchan_archive, tgach.top, 2ch.hk, etc.) is respected.
   - Telegram links do not trigger spam filter sanctions.
   - Anti-Dox mobile phone leak detection remains active.
"""

import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from common.spam_filter import (
    URL_WHITELIST,
    check_link_or_ad_spam,
    is_spam_filtered,
    evaluate_message_for_autoshadowmute,
)
from handlers.message_router import check_spam


class TestShadowmuteTrapAndWhitelist(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = 1163970492
        self.board_id = "b"
        shared_state.board_data['b'] = {
            'shadow_mutes': {},
            'users': {'active': set(), 'banned': set()},
            'last_texts': {},
            'user_settings': {},
        }

    @patch("common.database.is_shadow_muted", new_callable=AsyncMock)
    @patch("common.database.get_shadow_mute_info", new_callable=AsyncMock)
    @patch("common.database.apply_shadow_mute", new_callable=AsyncMock)
    async def test_muted_user_posts_dropped_silently_without_timer_escalation(
        self, mock_apply_mute, mock_get_info, mock_is_muted
    ):
        """
        Verify that an active shadowmute is maintained without extending duration,
        messages are silently routed to ghost-reject without notification, and
        no exponential escalation occurs.
        """
        original_expires_at = time.time() + 600.0  # 10 minutes left
        mock_is_muted.return_value = True
        mock_get_info.return_value = {
            'user_id': self.user_id,
            'board_id': self.board_id,
            'is_muted': True,
            'expires_at': original_expires_at,
            'remaining_seconds': 600.0,
        }

        # 1. Direct evaluate_message_for_autoshadowmute check
        should_mute, reason, exp = await evaluate_message_for_autoshadowmute(
            user_id=self.user_id,
            board_id=self.board_id,
            content="Сообщение в шедоумуте с повтором или флудом",
            msg_type='text',
            raw_content_type='text'
        )
        self.assertTrue(should_mute)
        self.assertEqual(exp, original_expires_at)
        # apply_shadow_mute must NOT have been called!
        mock_apply_mute.assert_not_called()

        # 2. check_spam check for incoming message
        mock_msg = MagicMock()
        mock_msg.content_type = 'text'
        mock_msg.text = "Повторное сообщение нарушителя"
        mock_msg.caption = None
        mock_msg.sticker = None

        result = await check_spam(self.user_id, mock_msg, self.board_id)
        # Returns True so message_router passes it to process_shadow_reject (silent ghost post)
        self.assertTrue(result)
        # Still, apply_shadow_mute must NEVER be called to extend the mute
        mock_apply_mute.assert_not_called()

    def test_official_whitelist_contains_archive_and_board_domains(self):
        """Ensure all required board and archive links are in URL_WHITELIST."""
        required = [
            "tgchan_archive",
            "tgach_archive",
            "t.me/tgchan_archive",
            "t.me/tgach_archive",
            "tgach.top",
            "2ch.hk",
            "dvach.top"
        ]
        for r in required:
            self.assertIn(r, URL_WHITELIST)

    def test_archive_links_and_telegram_links_not_flagged(self):
        """
        Verify that:
        1. Archive links (t.me/tgchan_archive, tgach.top, 2ch.hk) are never flagged as spam.
        2. Regular Telegram links (t.me/..., telegram.me/...) do not trigger spam sanctions.
        3. Doxing phone leaks DO trigger spam detection.
        """
        now = time.time()

        # Archive links
        is_sp, _ = check_link_or_ad_spam(self.user_id, self.board_id, "https://t.me/tgchan_archive/501707", now_ts=now)
        self.assertFalse(is_sp)

        is_sp, _ = check_link_or_ad_spam(self.user_id, self.board_id, "Архив тут: tgach.top/b/res/123.html и 2ch.hk", now_ts=now)
        self.assertFalse(is_sp)

        # General Telegram links (per user directive: no bans for telegram links)
        is_sp, _ = check_link_or_ad_spam(self.user_id, self.board_id, "https://t.me/some_random_chat_or_channel", now_ts=now)
        self.assertFalse(is_sp)

        is_sp, _ = check_link_or_ad_spam(self.user_id, self.board_id, "Вступайте: t.me/+InviteLink123", now_ts=now)
        self.assertFalse(is_sp)

        # Anti-Dox: Leaked phone numbers MUST be flagged
        is_sp, r = check_link_or_ad_spam(self.user_id, self.board_id, "Номер куратора: +79161234567 звоните", now_ts=now)
        self.assertTrue(is_sp)
        self.assertIn("Anti-Dox", r)

    def test_is_spam_filtered_ignores_whitelisted_archive(self):
        """Ensure is_spam_filtered correctly ignores whitelisted archive links."""
        # Clean text with archive link
        res = is_spam_filtered("Смотрите пост на https://t.me/tgchan_archive/12345", "b", self.user_id)
        self.assertFalse(res)
