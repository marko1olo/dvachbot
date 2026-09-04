import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import (
    Message, User, Chat,
    MessageOriginUser, MessageOriginHiddenUser, MessageOriginChat, MessageOriginChannel
)
from common.forward_utils import (
    is_forward_message, is_forwarded_from_bot, contains_board_post_header,
    extract_board_post_number, format_forwarded_quote, RE_BOARD_POST_HEADER
)
from common.text_utils import sanitize_html, clean_html_for_tg


class TestForwardedQuotesDetector(unittest.TestCase):
    def test_is_forward_message_none(self):
        self.assertFalse(is_forward_message(None))

    def test_is_forward_message_regular(self):
        msg = MagicMock(spec=Message)
        msg.forward_origin = None
        msg.forward_from = None
        msg.forward_from_chat = None
        msg.forward_sender_name = None
        msg.forward_date = None
        self.assertFalse(is_forward_message(msg))

    def test_is_forward_message_with_origin(self):
        msg = MagicMock(spec=Message)
        msg.forward_origin = MessageOriginUser(type="user", date=12345678, sender_user=User(id=123, is_bot=False, first_name="Anon"))
        self.assertTrue(is_forward_message(msg))

    def test_is_forward_message_with_legacy_from(self):
        msg = MagicMock(spec=Message)
        msg.forward_origin = None
        msg.forward_from = User(id=456, is_bot=True, first_name="BoardBot")
        self.assertTrue(is_forward_message(msg))

    def test_is_forwarded_from_bot_user(self):
        msg = MagicMock(spec=Message)
        bot_user = User(id=999999, is_bot=True, first_name="DvachBot", username="dvach_bot")
        msg.forward_origin = MessageOriginUser(type="user", date=12345678, sender_user=bot_user)
        msg.bot = MagicMock(id=999999)
        self.assertTrue(is_forwarded_from_bot(msg))

    def test_is_forwarded_from_bot_matching_bot_id(self):
        msg = MagicMock(spec=Message)
        bot_user = User(id=777777, is_bot=False, first_name="DvachBot")
        msg.forward_origin = MessageOriginUser(type="user", date=12345678, sender_user=bot_user)
        bot_instance = MagicMock(id=777777)
        self.assertTrue(is_forwarded_from_bot(msg, bot_instance))

    def test_is_forwarded_from_bot_channel(self):
        msg = MagicMock(spec=Message)
        channel = Chat(id=-1001234567890, type="channel", title="Archive")
        msg.forward_origin = MessageOriginChannel(type="channel", date=12345678, chat=channel, message_id=42)
        with patch("shared_state.ARCHIVE_CHANNEL_ID", -1001234567890):
            self.assertTrue(is_forwarded_from_bot(msg))

    def test_is_forwarded_from_bot_legacy_forward_from(self):
        msg = MagicMock(spec=Message)
        msg.forward_origin = None
        msg.forward_from = User(id=888888, is_bot=True, first_name="DvachBot", username="my_bot")
        self.assertTrue(is_forwarded_from_bot(msg))


class TestBoardPostHeaderRegex(unittest.TestCase):
    def test_headers_detection(self):
        samples = [
            ("🟣 Пост №504200\nя нарошно 5к поставил на полную хуйню", 504200),
            ("Пост №504198\nребята я толькочто залудоманил все бабки", 504198),
            ("Пост #504198: текст", 504198),
            ("Post No.504200\nhello world", 504200),
            ("Post #12345\nsome english post", 12345),
            ("<i>🟣 Анонимный пользователь - 🔴 Пост №502710</i>\n\n>>502609 (You)\n\n❤", 502710),
            ("🪗 БАЯН ×2\n🟣 Пост №504200\nтекст", 504200),
            ("💙💛 Пост №12/500 (OP)\nтекст треда", 12),
            ("++ СИГНАЛ #12345 ++ \nтекст", 12345),
            ("⚡ Донесение №999\nрапорт готов", 999),
            ("🌸 投稿 88888 番\nяпонский пост", 88888),
            ("レス番 77777\nтекст", 77777),
            ("🔴 <b>/b/</b> | Пост №501389 (ответ на №501373)", 501389),
            ("💩 Пост №500325\n\n​​🤍 @RuSaverBot", 500325),
        ]

        for text, expected_num in samples:
            with self.subTest(text=text[:30]):
                self.assertTrue(contains_board_post_header(text), f"Failed to detect header in: {text[:30]}")
                extracted = extract_board_post_number(text)
                self.assertEqual(extracted, expected_num, f"Extracted {extracted} != expected {expected_num} for {text[:30]}")

    def test_regular_text_not_detected_as_header(self):
        non_headers = [
            "Привет всем!",
            ">>504200 это ссылка на пост",
            "Поставил 500 рублей на команду",
            "Номер дома 42",
            "Post office is closed today",
        ]
        for text in non_headers:
            with self.subTest(text=text):
                self.assertFalse(contains_board_post_header(text))
                self.assertIsNone(extract_board_post_number(text))


class TestForwardedQuoteFormatting(unittest.TestCase):
    def test_format_forwarded_bot_post(self):
        raw = "🟣 Пост №504200\nя нарошно 5к поставил на полную хуйню"
        formatted = format_forwarded_quote(raw, is_forward=True, expandable=False)
        self.assertEqual(formatted, f"<blockquote>{raw}</blockquote>")

    def test_format_board_post_without_forward_flag(self):
        raw = "Пост №504198\nребята я толькочто залудоманил все бабки. Мне очень стыдно"
        formatted = format_forwarded_quote(raw, is_forward=False, expandable=False)
        self.assertEqual(formatted, f"<blockquote>{raw}</blockquote>")

    def test_format_expandable_for_long_post(self):
        long_body = "x" * 200
        raw = f"🟣 Пост №504200\n{long_body}"
        formatted = format_forwarded_quote(raw, is_forward=True)
        self.assertTrue(formatted.startswith("<blockquote expandable>"))
        self.assertTrue(formatted.endswith("</blockquote>"))

    def test_no_double_wrapping(self):
        already_quoted = "<blockquote>🟣 Пост №504200\nтекст</blockquote>"
        formatted = format_forwarded_quote(already_quoted, is_forward=True)
        self.assertEqual(formatted, already_quoted)

    def test_nested_blockquote_flattening(self):
        raw = "🟣 Пост №504200\n<blockquote>вложенная цитата</blockquote>\nответ"
        formatted = format_forwarded_quote(raw, is_forward=True, expandable=False)
        self.assertNotIn("<blockquote><blockquote>", formatted)
        self.assertIn("<i>«вложенная цитата»</i>", formatted)
        self.assertTrue(formatted.startswith("<blockquote>"))
        self.assertTrue(formatted.endswith("</blockquote>"))

    def test_commentary_with_board_post(self):
        raw = "Лол зацените:\n\n🟣 Пост №504200\nя нарошно 5к поставил на полную хуйню"
        formatted = format_forwarded_quote(raw, is_forward=False, expandable=False)
        self.assertEqual(
            formatted,
            "Лол зацените:\n\n<blockquote>🟣 Пост №504200\nя нарошно 5к поставил на полную хуйню</blockquote>"
        )

    def test_html_entity_safety(self):
        raw = "🟣 Пост №504200\nтекст с <b>жирным</b> и &lt;тегами&gt; &amp; спецсимволами"
        formatted = format_forwarded_quote(raw, is_forward=True, expandable=False)
        self.assertEqual(
            formatted,
            "<blockquote>🟣 Пост №504200\nтекст с <b>жирным</b> и &lt;тегами&gt; &amp; спецсимволами</blockquote>"
        )

    def test_clean_html_for_tg_preserves_blockquote(self):
        text = "<blockquote><b>Цитата</b>\nтекст</blockquote>"
        cleaned = clean_html_for_tg(text)
        self.assertEqual(cleaned, "<blockquote><b>Цитата</b>\nтекст</blockquote>")

    def test_post_header_inside_code_tag_not_split_into_blockquote(self):
        raw = "🔥 <b>[КАНОНИЧНЫЙ БУГУРТ-ТРЕД]</b>\n\nТЫ ОМЕЖКА...\n\n<code>[2ch.hk/soc/ | Пост #2017344 | Постов: 192/500 | Сажа: +57 | Пасскод: Не куплен (Нищий)]</code>"
        self.assertFalse(contains_board_post_header(raw))
        formatted = format_forwarded_quote(raw)
        self.assertEqual(formatted, raw)
        self.assertNotIn("<blockquote", formatted)

    def test_unclosed_tag_in_prefix_prevents_malformed_blockquote(self):
        raw = "<b>Текст с открытым тегом Пост №504200 продолжение жирного</b>"
        formatted = format_forwarded_quote(raw)
        self.assertEqual(formatted, raw)
        self.assertNotIn("<blockquote", formatted)



class TestForwardedQuoteIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_handle_message_forward_from_bot(self):
        from handlers.message_router import handle_message
        import shared_state

        msg = MagicMock(spec=Message)
        msg.message_id = 1001
        msg.chat = MagicMock(id=12345)
        msg.from_user = User(id=12345, is_bot=False, first_name="Anon")
        msg.content_type = "text"
        msg.text = "🟣 Пост №504200\nя нарошно 5к поставил на полную хуйню"
        msg.html_text = "🟣 Пост №504200\nя нарошно 5к поставил на полную хуйню"
        msg.caption = None
        msg.caption_html_text = None
        msg.reply_to_message = None
        msg.media_group_id = None
        msg.bot = MagicMock(id=999999)
        msg.delete = AsyncMock()
        msg.answer = AsyncMock()

        # Mark as forward from bot
        msg.forward_origin = MessageOriginUser(type="user", date=12345678, sender_user=User(id=999999, is_bot=True, first_name="DvachBot"))
        msg.forward_from = None
        msg.forward_from_chat = None
        msg.forward_sender_name = None
        msg.forward_date = 12345678

        shared_state.board_data['b'] = {
            'users': {'active': {12345}, 'banned': set()},
            'mutes': {},
            'shadow_mutes': {},
            'user_state': {},
            'user_settings': {},
            'last_activity': {},
            'single_photo_counter': {12345: 0}
        }

        with patch("handlers.message_router.is_admin", return_value=False), \
             patch("handlers.message_router.get_pool", new_callable=AsyncMock), \
             patch("handlers.message_router.check_spam", return_value=True), \
             patch("handlers.message_router._get_user_active_items", new_callable=AsyncMock, return_value={}), \
             patch("common.database.is_shadow_muted", new_callable=AsyncMock, return_value=False), \
             patch("handlers.message_router.is_spam_filtered", return_value=False), \
             patch("handlers.message_router.resolve_archive_or_inline_reply", new_callable=AsyncMock, side_effect=lambda t: (None, t)), \
             patch("handlers.message_router.build_quick_quote_info", new_callable=AsyncMock, return_value=None), \
             patch("common.database.register_media_repost", new_callable=AsyncMock, return_value=1), \
             patch("handlers.message_router.add_or_activate_user", new_callable=AsyncMock), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp:

            mock_pnp.return_value = 505516
            await handle_message(msg, board_id="b", stream="ru")

            self.assertTrue(mock_pnp.called)
            params = mock_pnp.call_args[0][0]
            content = params.content
            self.assertTrue(content.get('is_forward'))
            self.assertIn("<blockquote>", content.get('text', ''))
            self.assertIn("🟣 Пост №504200", content.get('text', ''))
            self.assertIn("я нарошно 5к поставил на полную хуйню", content.get('text', ''))
            self.assertTrue(content.get('text', '').endswith("</blockquote>"))

    async def test_handle_message_photo_forward_caption(self):
        from handlers.message_router import handle_message
        import shared_state

        msg = MagicMock(spec=Message)
        msg.message_id = 1002
        msg.chat = MagicMock(id=12345)
        msg.from_user = User(id=12345, is_bot=False, first_name="Anon")
        msg.content_type = "photo"
        photo_mock = MagicMock(file_id="photo_file_123", file_unique_id="unique_123")
        msg.photo = [photo_mock]
        msg.text = None
        msg.html_text = None
        msg.caption = "🟣 Пост №504198\nребята я толькочто залудоманил все бабки. Мне очень стыдно"
        msg.caption_html_text = "🟣 Пост №504198\nребята я толькочто залудоманил все бабки. Мне очень стыдно"
        msg.reply_to_message = None
        msg.media_group_id = None
        msg.bot = MagicMock(id=999999)
        msg.delete = AsyncMock()
        msg.answer = AsyncMock()

        msg.forward_origin = MessageOriginUser(type="user", date=12345678, sender_user=User(id=999999, is_bot=True, first_name="DvachBot"))
        msg.forward_from = None
        msg.forward_from_chat = None
        msg.forward_sender_name = None
        msg.forward_date = 12345678

        shared_state.board_data['b'] = {
            'users': {'active': {12345}, 'banned': set()},
            'mutes': {},
            'shadow_mutes': {},
            'user_state': {},
            'user_settings': {},
            'last_activity': {},
            'single_photo_counter': {12345: 0}
        }

        with patch("handlers.message_router.is_admin", return_value=False), \
             patch("handlers.message_router.get_pool", new_callable=AsyncMock), \
             patch("handlers.message_router.check_spam", return_value=True), \
             patch("handlers.message_router._get_user_active_items", new_callable=AsyncMock, return_value={}), \
             patch("common.database.is_shadow_muted", new_callable=AsyncMock, return_value=False), \
             patch("handlers.message_router.is_spam_filtered", return_value=False), \
             patch("handlers.message_router.resolve_archive_or_inline_reply", new_callable=AsyncMock, side_effect=lambda t: (None, t)), \
             patch("handlers.message_router.build_quick_quote_info", new_callable=AsyncMock, return_value=None), \
             patch("common.database.register_media_repost", new_callable=AsyncMock, return_value=1), \
             patch("handlers.message_router.add_or_activate_user", new_callable=AsyncMock), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp:

            mock_pnp.return_value = 505517
            await handle_message(msg, board_id="b", stream="ru")

            self.assertTrue(mock_pnp.called)
            params = mock_pnp.call_args[0][0]
            content = params.content
            self.assertTrue(content.get('is_forward'))
            self.assertIn("<blockquote>", content.get('caption', ''))
            self.assertIn("🟣 Пост №504198", content.get('caption', ''))
            self.assertIn("ребята я толькочто залудоманил все бабки", content.get('caption', ''))
            self.assertTrue(content.get('caption', '').endswith("</blockquote>"))

    async def test_broadcaster_format_message_body_with_blockquote(self):
        from broadcaster import _format_message_body

        content = {
            'type': 'text',
            'text': '<blockquote>🟣 Пост №504200\nя нарошно 5к поставил на полную хуйню</blockquote>'
        }
        post_data = {'content': content, 'reactions': {}}
        body = await _format_message_body(
            content=content,
            user_id_for_context=0,
            post_data=post_data,
            reply_to_post_author_id=None,
            quote_info=None
        )
        self.assertEqual(body, '<blockquote>🟣 Пост №504200\nя нарошно 5к поставил на полную хуйню</blockquote>')


if __name__ == '__main__':
    unittest.main()

