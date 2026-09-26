import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import time
import pytest

from common.text_utils import extract_post_num_from_message_text
import shared_state
from shared_state import messages_storage, post_to_messages, message_to_post, storage_lock, posts_pending_deletion
import main
from main import get_author_id_by_reply, get_post_num_by_reply, delete_user_posts


class TestAdminCommandsAudit(unittest.IsolatedAsyncioTestCase):

    def test_extract_post_num_from_message_text(self):
        # 1. Russian standard with quote - must NOT extract quoted number
        pnum, tnum = extract_post_num_from_message_text("<i>Пост №542203</i>\n\n>>542100 (You)\n\nСпам текст")
        self.assertEqual(pnum, 542203)
        self.assertIsNone(tnum)

        # 2. English standard with quote
        pnum, tnum = extract_post_num_from_message_text("<i>Post No.542204</i>\n\n>>542100\n\nSome text")
        self.assertEqual(pnum, 542204)
        self.assertIsNone(tnum)

        # 3. Japanese anime mode with quote
        pnum, tnum = extract_post_num_from_message_text("<i>🌸 投稿 542205 番</i>\n\n>>542100\n\n日本語")
        self.assertEqual(pnum, 542205)
        self.assertIsNone(tnum)

        # 4. Japanese normal with quote
        pnum, tnum = extract_post_num_from_message_text("<i>レス番 542206</i>\n\n>>542100\n\nテキスト")
        self.assertEqual(pnum, 542206)
        self.assertIsNone(tnum)

        # 5. Thread post with quote
        pnum, tnum = extract_post_num_from_message_text("<i>Пост №15/500</i>\n\n>>12\n\nТекст в треде")
        self.assertIsNone(pnum)
        self.assertEqual(tnum, 15)

        # 6. Post with prefix containing #
        pnum, tnum = extract_post_num_from_message_text("<i>### ЧМО ### Пост №542207</i>\n\n>>542100\n\nТекст")
        self.assertEqual(pnum, 542207)
        self.assertIsNone(tnum)

        # 7. Post where user typed quotes and hashes in text
        pnum, tnum = extract_post_num_from_message_text("<i>Пост №542208</i>\n\n>>999999 ты не прав, #111111 согласен")
        self.assertEqual(pnum, 542208)
        self.assertIsNone(tnum)

        # 8. Schizo mode
        pnum, tnum = extract_post_num_from_message_text("<i>++ СИГНАЛ #542209 ++</i>\n\n>>542100\n\nШизотекст")
        self.assertEqual(pnum, 542209)
        self.assertIsNone(tnum)

    async def test_get_author_id_by_reply_fallback_to_header_text(self):
        # Create mock message where RAM lookup and PostCopies return None,
        # but text header contains post number
        mock_msg = MagicMock()
        mock_msg.reply_to_message = MagicMock()
        mock_msg.reply_to_message.chat.id = 12345
        mock_msg.reply_to_message.message_id = 999
        mock_msg.reply_to_message.text = "<i>Пост №542203</i>\n\n>>542100 (You)\n\nСпам текст"
        mock_msg.reply_to_message.caption = None

        with patch("main.get_post_info_by_copy", new_callable=AsyncMock, return_value=None), \
             patch("main.get_post_author_by_copy", new_callable=AsyncMock, return_value=None), \
             patch("main.get_post_by_num", new_callable=AsyncMock, return_value={"post_num": 542203, "author_id": 6572792624}):
            
            author_id = await get_author_id_by_reply(mock_msg)
            pnum = await get_post_num_by_reply(mock_msg)
            self.assertEqual(author_id, 6572792624)
            self.assertEqual(pnum, 542203)

    async def test_delete_user_posts_pending_deletion_and_unlimited_window(self):
        # Verify that delete_user_posts populates posts_pending_deletion
        # and passes time_threshold_ts = 0.0 for duration all (>= 500000)
        mock_bot = MagicMock()
        user_id = 6572792624
        
        captured_threshold = []
        async def fake_delete_db(uid, threshold, board):
            captured_threshold.append(threshold)
            return [542203, 542204], [], []

        with patch("main._delete_user_posts_from_db", side_effect=fake_delete_db), \
             patch("main._clean_posts_from_ram", new_callable=AsyncMock), \
             patch("main._clean_posts_from_caches"), \
             patch("main._delete_posts_from_channels", new_callable=AsyncMock), \
             patch("main._delete_posts_from_pm_api", new_callable=AsyncMock), \
             patch("main.spawn_task"):
            
            posts_pending_deletion.clear()
            deleted = await delete_user_posts(mock_bot, user_id, 525600, "b")
            self.assertEqual(deleted, 2)
            self.assertEqual(captured_threshold[0], 0.0)
            self.assertIn(542203, posts_pending_deletion)
            self.assertIn(542204, posts_pending_deletion)
