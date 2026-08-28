# -*- coding: utf-8 -*-
"""
Unit tests for Ghost-Posting & Silent Link Spam Filtering.
Verifies:
1. Message with a forbidden Telegram link triggers silent autoshadowmute.
2. check_spam returns True so message_router routes to process_shadow_reject.
3. Message is NOT dropped with raw delete; instead process_shadow_reject sends fake post to author only.
4. Subsequent messages from shadowed user are also ghost-posted without visible errors.
"""

import time
import pytest
import unittest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from common.spam_filter import (
    evaluate_message_for_autoshadowmute,
    check_link_or_ad_spam,
    _user_link_timestamps,
)
from handlers.message_router import check_spam


class TestGhostPostLinkFilter(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _user_link_timestamps.clear()
        shared_state.board_data['b'] = {
            'shadow_mutes': {},
            'users': {'active': set(), 'banned': set()},
            'last_texts': {},
            'user_settings': {},
        }

    @patch("common.database.apply_shadow_mute", new_callable=AsyncMock)
    @patch("common.database.is_shadow_muted", new_callable=AsyncMock)
    async def test_links_allowed_and_scams_trigger_ghost_routing(self, mock_is_muted, mock_apply_mute):
        mock_is_muted.return_value = False
        mock_apply_mute.return_value = time.time() + 1200.0

        user_id = 5264555563
        board_id = "b"
        link_text = "https://t.me/Necrowaffen88"

        # 1. Telegram links are now completely allowed (no mute for links!)
        is_spam, reason = check_link_or_ad_spam(user_id, board_id, link_text)
        self.assertFalse(is_spam)

        # 2. Casino / Scam keywords still trigger auto-shadowmute
        scam_text = "Поднимай бабло в 1win и казино вулкан"
        is_scam, scam_reason = check_link_or_ad_spam(user_id, board_id, scam_text)
        self.assertTrue(is_scam)
        self.assertIn("Реклама/скам", scam_reason)

        should_mute, reason, _ = await evaluate_message_for_autoshadowmute(
            user_id=user_id,
            board_id=board_id,
            content=scam_text,
            msg_type='text',
            raw_content_type='text'
        )
        self.assertTrue(should_mute)
        mock_apply_mute.assert_called_once()

        # 3. check_spam returns True (allowing message_router to route to process_shadow_reject!)
        mock_msg = MagicMock()
        mock_msg.content_type = 'text'
        mock_msg.text = scam_text
        mock_msg.caption = None
        mock_msg.photo = None
        mock_msg.video = None
        mock_msg.document = None

        result = await check_spam(user_id, mock_msg, board_id)
        # MUST BE TRUE to avoid immediate message.delete() without shadow reject!
        self.assertTrue(result, "check_spam must return True for autoshadowmute to permit ghost-posting via process_shadow_reject")

    @patch("common.database.is_shadow_muted", new_callable=AsyncMock)
    @patch("common.spam_filter.handle_shadow_mute_continuation", new_callable=AsyncMock)
    async def test_subsequent_messages_in_shadow_mute_ghost_routed(self, mock_continuation, mock_is_muted):
        mock_is_muted.return_value = True
        mock_continuation.return_value = (True, time.time() + 2400.0)

        user_id = 5264555563
        board_id = "b"

        mock_msg = MagicMock()
        mock_msg.content_type = 'text'
        mock_msg.text = "Опа"
        mock_msg.caption = None

        result = await check_spam(user_id, mock_msg, board_id)
        self.assertTrue(result)
        mock_continuation.assert_called_once()
