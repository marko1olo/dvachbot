import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, User, Chat

import shared_state
from handlers.message_router import build_quick_quote_info, handle_message
from broadcaster import _format_quote_block, _format_reply_line, _format_message_body
from post_helpers import _quote_info_from_content


class TestQuickQuoteConfiguration(unittest.TestCase):
    """Verifies that the quote distance threshold is set to 300 in shared_state and properly exported."""

    def test_quick_quote_distance_constant(self):
        self.assertEqual(shared_state.QUICK_QUOTE_POST_DISTANCE, 300)

    def test_quick_quote_distance_in_all(self):
        self.assertIn('QUICK_QUOTE_POST_DISTANCE', shared_state.__all__)


class TestBuildQuickQuoteInfoDistanceLogic(unittest.IsolatedAsyncioTestCase):
    """
    Tests build_quick_quote_info with various distances:
    - Distance <= 300: strictly returns None (no quote block).
    - Distance > 300: fetches post data and returns quote_info dict.
    """

    async def test_distance_exactly_300_returns_none(self):
        # current_max_post = 1000, reply_to_post = 700 -> distance = 300 (<= 300) -> returns None
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock) as mock_get_post:
            result = await build_quick_quote_info(700)
            self.assertIsNone(result)
            mock_get_post.assert_not_called()

    async def test_distance_under_300_returns_none(self):
        # Test various distances below 300: 299, 200, 100, 1, 0
        test_replies = [
            (1000, 701),   # diff = 299
            (1000, 800),   # diff = 200
            (1000, 900),   # diff = 100
            (1000, 999),   # diff = 1
            (1000, 1000),  # diff = 0
            (500000, 499700),  # diff = 300
            (500000, 499850),  # diff = 150
            (500000, 499999),  # diff = 1
        ]
        for current_max, reply_to in test_replies:
            with self.subTest(current_max=current_max, reply_to=reply_to):
                with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=current_max), \
                     patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock) as mock_get_post:
                    result = await build_quick_quote_info(reply_to)
                    self.assertIsNone(result, f"Expected None for diff {current_max - reply_to}")
                    mock_get_post.assert_not_called()

    async def test_distance_over_300_fetches_and_returns_quote(self):
        # Distance > 300 should fetch post data and return quote_info dict
        sample_post_data = {
            'post_num': 699,
            'content': {
                'type': 'text',
                'text': 'Древний пост из глубин архива'
            }
        }
        # diff = 301 (1000 - 699) -> > 300
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=sample_post_data) as mock_get_post:
            result = await build_quick_quote_info(699)
            self.assertIsNotNone(result)
            self.assertEqual(result.get('text'), 'Древний пост из глубин архива')
            self.assertEqual(result.get('files'), [])
            mock_get_post.assert_awaited_once_with(699)

    async def test_distance_ancient_posts_various_offsets(self):
        ancient_replies = [
            (1000, 699),   # diff = 301
            (1000, 500),   # diff = 500
            (1000, 100),   # diff = 900
            (1000, 1),     # diff = 999
            (500000, 499699),  # diff = 301
            (500000, 100000),  # diff = 400000
        ]
        for current_max, reply_to in ancient_replies:
            with self.subTest(current_max=current_max, reply_to=reply_to):
                post_data = {
                    'post_num': reply_to,
                    'content': {'type': 'text', 'text': f'Post #{reply_to}'}
                }
                with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=current_max), \
                     patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=post_data) as mock_get_post:
                    result = await build_quick_quote_info(reply_to)
                    self.assertIsNotNone(result)
                    self.assertEqual(result.get('text'), f'Post #{reply_to}')
                    mock_get_post.assert_awaited_once_with(reply_to)

    async def test_distance_over_300_with_media_content(self):
        # Test ancient post with media (photo, video, etc.)
        photo_post_data = {
            'post_num': 100,
            'content': {
                'type': 'photo',
                'caption': 'Фотокарточка треда',
                'file_id': 'photo_12345'
            }
        }
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=photo_post_data):
            result = await build_quick_quote_info(100)
            self.assertIsNotNone(result)
            self.assertEqual(result.get('text'), 'Фотокарточка треда')
            self.assertEqual(len(result.get('files', [])), 1)
            self.assertEqual(result['files'][0]['type'], 'photo')


class TestBuildQuickQuoteInfoEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Tests edge cases for build_quick_quote_info."""

    async def test_reply_to_none_returns_none(self):
        result = await build_quick_quote_info(None)
        self.assertIsNone(result)

    async def test_reply_to_zero_or_negative_returns_none(self):
        for invalid_post in [0, -1, -500]:
            with self.subTest(invalid_post=invalid_post):
                result = await build_quick_quote_info(invalid_post)
                self.assertIsNone(result)

    async def test_reply_to_non_numeric_returns_none(self):
        for invalid_input in ["abc", "", [], {}]:
            with self.subTest(invalid_input=invalid_input):
                result = await build_quick_quote_info(invalid_input)
                self.assertIsNone(result)

    async def test_reply_to_string_integer_parsed_correctly(self):
        # "699" should be parsed to 699 and trigger quote if distance > 300
        post_data = {
            'post_num': 699,
            'content': {'type': 'text', 'text': 'Строковый номер поста'}
        }
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=post_data):
            result = await build_quick_quote_info("699")
            self.assertIsNotNone(result)
            self.assertEqual(result.get('text'), 'Строковый номер поста')

        # "800" should be parsed to 800 and return None (distance <= 300)
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock) as mock_get_post:
            result = await build_quick_quote_info("800")
            self.assertIsNone(result)
            mock_get_post.assert_not_called()

    async def test_reply_to_future_post_returns_none(self):
        # reply_to > current_max_post (e.g. max=1000, reply=1200) -> difference = -200 <= 300 -> returns None
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock) as mock_get_post:
            result = await build_quick_quote_info(1200)
            self.assertIsNone(result)
            mock_get_post.assert_not_called()

    async def test_ancient_post_not_in_db_returns_none(self):
        # Distance > 300, but get_post_by_num returns None (e.g. purged/deleted post)
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=None):
            result = await build_quick_quote_info(500)
            self.assertIsNone(result)

    async def test_ancient_post_with_non_dict_content_returns_none(self):
        # Distance > 300, but content in DB is None or invalid
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value={'content': None}):
            result = await build_quick_quote_info(500)
            self.assertIsNone(result)

    async def test_get_max_post_num_exception_safe_fallback(self):
        # If get_max_post_num raises, should safely fallback to current_max=0 without uncaught exception
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, side_effect=Exception("DB locked")):
            result = await build_quick_quote_info(500)
            # current_max=0, reply_to=500 -> diff = -500 <= 300 -> returns None
            self.assertIsNone(result)

    async def test_dynamic_threshold_override(self):
        # When QUICK_QUOTE_POST_DISTANCE is overridden in shared_state
        post_data = {
            'post_num': 800,
            'content': {'type': 'text', 'text': 'Динамический порог'}
        }
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=post_data), \
             patch.object(shared_state, "QUICK_QUOTE_POST_DISTANCE", 100):
            # Distance is 1000 - 800 = 200 > 100 -> should return quote
            result = await build_quick_quote_info(800)
            self.assertIsNotNone(result)
            self.assertEqual(result.get('text'), 'Динамический порог')

    async def test_disabled_threshold_zero(self):
        # When QUICK_QUOTE_POST_DISTANCE is set to 0 (distance check disabled)
        post_data = {
            'post_num': 990,
            'content': {'type': 'text', 'text': 'Порог отключен'}
        }
        with patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=post_data), \
             patch.object(shared_state, "QUICK_QUOTE_POST_DISTANCE", 0):
            # Difference is 10, but threshold is 0 -> should return quote
            result = await build_quick_quote_info(990)
            self.assertIsNotNone(result)
            self.assertEqual(result.get('text'), 'Порог отключен')


class TestBroadcasterQuoteFormatting(unittest.IsolatedAsyncioTestCase):
    """Tests the quote block formatting in broadcaster.py when quote_info is present vs None."""

    def test_format_quote_block_none_returns_none(self):
        self.assertIsNone(_format_quote_block(None))

    def test_format_quote_block_empty_dict_returns_none(self):
        self.assertIsNone(_format_quote_block({}))
        self.assertIsNone(_format_quote_block({'text': '', 'files': []}))

    def test_format_quote_block_valid_text(self):
        quote_info = {'text': 'Ответ на древний пост'}
        formatted = _format_quote_block(quote_info)
        self.assertEqual(formatted, '<blockquote expandable>Ответ на древний пост</blockquote>')

    def test_format_quote_block_truncates_long_text(self):
        long_text = "A" * 200
        quote_info = {'text': long_text}
        formatted = _format_quote_block(quote_info)
        expected_inner = "A" * 140 + "..."
        self.assertEqual(formatted, f'<blockquote expandable>{expected_inner}</blockquote>')

    def test_format_quote_block_escapes_html_and_strips_tags(self):
        # clean_html_tags strips raw html tags, escape_html escapes special chars like & and "
        quote_info = {'text': '<script>alert("hack")</script> & "quotes"'}
        formatted = _format_quote_block(quote_info)
        self.assertEqual(formatted, '<blockquote expandable>alert(&quot;hack&quot;) &amp; &quot;quotes&quot;</blockquote>')

        quote_info_special = {'text': 'a & b "test"'}
        formatted_special = _format_quote_block(quote_info_special)
        self.assertEqual(formatted_special, '<blockquote expandable>a &amp; b &quot;test&quot;</blockquote>')

    def test_format_quote_block_with_media_counts(self):
        quote_info = {
            'text': 'Текст с медиа',
            'files': [{'type': 'photo'}, {'type': 'photo'}, {'type': 'video'}]
        }
        formatted = _format_quote_block(quote_info)
        self.assertIn('Текст с медиа', formatted)
        self.assertIn('<i>[2 фото, 1 видео]</i>', formatted)

    def test_format_reply_line_without_quote_info(self):
        # When quote_info is None (distance <= 300), reply line should be wrapped in <code>
        content = {'reply_to_post': 700}
        reply_line = _format_reply_line(content, user_id_for_context=123, reply_to_post_author_id=456, quote_info=None)
        self.assertEqual(reply_line, '<code>&gt;&gt;700</code>')

    def test_format_reply_line_without_quote_info_author_match(self):
        # When user matches replied post author and quote_info is None
        content = {'reply_to_post': 700}
        reply_line = _format_reply_line(content, user_id_for_context=456, reply_to_post_author_id=456, quote_info=None)
        self.assertEqual(reply_line, '<code>&gt;&gt;700 (You)</code>')

    def test_format_reply_line_with_quote_info(self):
        # When quote_info is present (distance > 300), reply line is unwrapped (blockquote handles container)
        content = {'reply_to_post': 100}
        quote_info = {'text': 'Древний пост'}
        reply_line = _format_reply_line(content, user_id_for_context=123, reply_to_post_author_id=456, quote_info=quote_info)
        self.assertEqual(reply_line, '>>100')

    async def test_format_message_body_integration_recent_reply_no_blockquote(self):
        # Distance <= 300: message body contains code tag for reply, NO blockquote tag
        content = {
            'type': 'text',
            'text': 'Мой свежий ответ на недавний пост',
            'reply_to_post': 800
        }
        post_data = {'content': content, 'reactions': {}}
        body = await _format_message_body(
            content=content,
            user_id_for_context=123,
            post_data=post_data,
            reply_to_post_author_id=456,
            quote_info=None  # No quote info for recent post!
        )
        self.assertNotIn('<blockquote', body)
        self.assertIn('<code>&gt;&gt;800</code>', body)
        self.assertIn('Мой свежий ответ на недавний пост', body)

    async def test_format_message_body_integration_ancient_reply_includes_blockquote(self):
        # Distance > 300: message body contains blockquote with quote text
        content = {
            'type': 'text',
            'text': 'Отвечаю на древнейший пост',
            'reply_to_post': 100
        }
        quote_info = {
            'text': 'Древний текст из прошлого года',
            'files': []
        }
        post_data = {'content': content, 'reactions': {}}
        body = await _format_message_body(
            content=content,
            user_id_for_context=123,
            post_data=post_data,
            reply_to_post_author_id=456,
            quote_info=quote_info  # Quote info provided for ancient post!
        )
        self.assertIn('<blockquote expandable>Древний текст из прошлого года</blockquote>', body)
        self.assertIn('>>100', body)
        self.assertIn('Отвечаю на древнейший пост', body)


class TestMessageRouterDispatchQuotes(unittest.IsolatedAsyncioTestCase):
    """Tests that message_router correctly omits quote_info for <=300 and includes it for >300."""

    async def test_handle_message_recent_reply_omits_quote_info(self):
        msg = MagicMock(spec=Message)
        msg.message_id = 2001
        msg.chat = MagicMock(id=12345)
        msg.from_user = User(id=12345, is_bot=False, first_name="Anon")
        msg.content_type = "text"
        msg.text = ">>800 свежий ответ"
        msg.html_text = ">>800 свежий ответ"
        msg.caption = None
        msg.caption_html_text = None
        msg.reply_to_message = None
        msg.photo = None
        msg.media_group_id = None
        msg.bot = MagicMock(id=999999)
        msg.delete = AsyncMock()
        msg.answer = AsyncMock()
        msg.forward_origin = None
        msg.forward_from = None
        msg.forward_from_chat = None
        msg.forward_sender_name = None
        msg.forward_date = None

        shared_state.board_data['b'] = {
            'users': {'active': {12345}, 'banned': set()},
            'mutes': {},
            'shadow_mutes': {},
            'user_state': {},
            'user_settings': {},
            'last_activity': {},
            'single_photo_counter': {12345: 0}
        }

        # current_max = 1000, reply_to = 800 -> diff 200 <= 300 -> build_quick_quote_info returns None
        with patch("handlers.message_router.is_admin", return_value=False), \
             patch("handlers.message_router.get_pool", new_callable=AsyncMock), \
             patch("handlers.message_router.check_spam", return_value=True), \
             patch("handlers.message_router._get_user_active_items", new_callable=AsyncMock, return_value={}), \
             patch("common.database.is_shadow_muted", new_callable=AsyncMock, return_value=False), \
             patch("handlers.message_router.is_spam_filtered", return_value=False), \
             patch("handlers.message_router.resolve_archive_or_inline_reply", new_callable=AsyncMock, return_value=(800, "свежий ответ")), \
             patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock) as mock_get_post, \
             patch("handlers.message_router.add_or_activate_user", new_callable=AsyncMock), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp:

            mock_pnp.return_value = 1001
            await handle_message(msg, board_id="b", stream="ru")

            self.assertTrue(mock_pnp.called)
            params = mock_pnp.call_args[0][0]
            content = params.content
            # quote_info must NOT be present (or None)
            self.assertIsNone(content.get('quote_info'))
            mock_get_post.assert_not_called()

    async def test_handle_message_ancient_reply_includes_quote_info(self):
        msg = MagicMock(spec=Message)
        msg.message_id = 2002
        msg.chat = MagicMock(id=12345)
        msg.from_user = User(id=12345, is_bot=False, first_name="Anon")
        msg.content_type = "text"
        msg.text = ">>500 ответ на древний пост"
        msg.html_text = ">>500 ответ на древний пост"
        msg.caption = None
        msg.caption_html_text = None
        msg.reply_to_message = None
        msg.photo = None
        msg.media_group_id = None
        msg.bot = MagicMock(id=999999)
        msg.delete = AsyncMock()
        msg.answer = AsyncMock()
        msg.forward_origin = None
        msg.forward_from = None
        msg.forward_from_chat = None
        msg.forward_sender_name = None
        msg.forward_date = None

        shared_state.board_data['b'] = {
            'users': {'active': {12345}, 'banned': set()},
            'mutes': {},
            'shadow_mutes': {},
            'user_state': {},
            'user_settings': {},
            'last_activity': {},
            'single_photo_counter': {12345: 0}
        }

        ancient_post_data = {
            'post_num': 500,
            'content': {'type': 'text', 'text': 'Древний пост 500'}
        }

        # current_max = 1000, reply_to = 500 -> diff 500 > 300 -> build_quick_quote_info fetches post 500
        with patch("handlers.message_router.is_admin", return_value=False), \
             patch("handlers.message_router.get_pool", new_callable=AsyncMock), \
             patch("handlers.message_router.check_spam", return_value=True), \
             patch("handlers.message_router._get_user_active_items", new_callable=AsyncMock, return_value={}), \
             patch("common.database.is_shadow_muted", new_callable=AsyncMock, return_value=False), \
             patch("handlers.message_router.is_spam_filtered", return_value=False), \
             patch("handlers.message_router.resolve_archive_or_inline_reply", new_callable=AsyncMock, return_value=(500, "ответ на древний пост")), \
             patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=ancient_post_data), \
             patch("handlers.message_router.add_or_activate_user", new_callable=AsyncMock), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp:

            mock_pnp.return_value = 1002
            await handle_message(msg, board_id="b", stream="ru")

            self.assertTrue(mock_pnp.called)
            params = mock_pnp.call_args[0][0]
            content = params.content
            # quote_info MUST be populated with post 500's content
            self.assertIsNotNone(content.get('quote_info'))
            self.assertEqual(content['quote_info']['text'], 'Древний пост 500')

    async def test_handle_message_multi_reply_quotes_handling(self):
        msg = MagicMock(spec=Message)
        msg.message_id = 2003
        msg.chat = MagicMock(id=12345)
        msg.from_user = User(id=12345, is_bot=False, first_name="Anon")
        msg.content_type = "text"
        msg.text = ">>800 ответ недавнему\n>>400 ответ древнему"
        msg.html_text = ">>800 ответ недавнему\n>>400 ответ древнему"
        msg.caption = None
        msg.caption_html_text = None
        msg.reply_to_message = None
        msg.photo = None
        msg.media_group_id = None
        msg.bot = MagicMock(id=999999)
        msg.delete = AsyncMock()
        msg.answer = AsyncMock()
        msg.forward_origin = None
        msg.forward_from = None
        msg.forward_from_chat = None
        msg.forward_sender_name = None
        msg.forward_date = None

        shared_state.board_data['b'] = {
            'users': {'active': {12345}, 'banned': set()},
            'mutes': {},
            'shadow_mutes': {},
            'user_state': {},
            'user_settings': {},
            'last_activity': {},
            'single_photo_counter': {12345: 0}
        }

        # Multi-reply blocks: (800, "ответ недавнему"), (400, "ответ древнему")
        multi_blocks = [(800, "ответ недавнему"), (400, "ответ древнему")]

        ancient_post_data = {
            'post_num': 400,
            'content': {'type': 'text', 'text': 'Пост 400'}
        }

        async def fake_get_post(p_num):
            if p_num == 400:
                return ancient_post_data
            if p_num == 800:
                return {'post_num': 800, 'content': {'type': 'text', 'text': 'Пост 800'}}
            return None

        with patch("handlers.message_router.is_admin", return_value=False), \
             patch("handlers.message_router.get_pool", new_callable=AsyncMock), \
             patch("handlers.message_router.check_spam", return_value=True), \
             patch("handlers.message_router._get_user_active_items", new_callable=AsyncMock, return_value={}), \
             patch("common.database.is_shadow_muted", new_callable=AsyncMock, return_value=False), \
             patch("handlers.message_router.is_spam_filtered", return_value=False), \
             patch("handlers.message_router._parse_and_split_multi_replies", return_value=(multi_blocks, False)), \
             patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, side_effect=fake_get_post), \
             patch("handlers.message_router.add_or_activate_user", new_callable=AsyncMock), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp:

            mock_pnp.side_effect = [1003, 1004]
            await handle_message(msg, board_id="b", stream="ru")

            self.assertEqual(mock_pnp.call_count, 2)
            # Call 1: reply to 800 (diff 200 <= 300) -> quote_info omitted
            content_1 = mock_pnp.call_args_list[0][0][0].content
            self.assertIsNone(content_1.get('quote_info'))

            # Call 2: reply to 400 (diff 600 > 300) -> quote_info included
            content_2 = mock_pnp.call_args_list[1][0][0].content
            self.assertIsNotNone(content_2.get('quote_info'))
            self.assertEqual(content_2['quote_info']['text'], 'Пост 400')

    async def test_handle_message_passive_persona_stochastic_trigger_with_mock_message(self):
        """Regression test for Challenger 2 finding: ensures random passive persona trigger does not crash on MagicMock(spec=Message)."""
        msg = MagicMock(spec=Message)
        msg.message_id = 2004
        msg.chat = MagicMock(id=12345)
        msg.from_user = User(id=12345, is_bot=False, first_name="Anon")
        msg.content_type = "text"
        msg.text = ">>800 длинный текст сообщения"
        msg.html_text = ">>800 длинный текст сообщения"
        msg.caption = None
        msg.caption_html_text = None
        msg.reply_to_message = None
        # Note: photo attribute intentionally not set on MagicMock(spec=Message) to verify getattr safety
        msg.media_group_id = None
        msg.bot = MagicMock(id=999999)
        msg.delete = AsyncMock()
        msg.answer = AsyncMock()
        msg.forward_origin = None
        msg.forward_from = None
        msg.forward_from_chat = None
        msg.forward_sender_name = None
        msg.forward_date = None

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
             patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value={'post_num': 800, 'content': {'type': 'text', 'text': '800'}}), \
             patch("handlers.message_router.add_or_activate_user", new_callable=AsyncMock), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock, return_value=1005), \
             patch("handlers.message_router.schedule_persona_reply", new_callable=AsyncMock), \
             patch("anchor_bot.anchor_tick", return_value=False), \
             patch("random.random", return_value=0.01):

            # Should complete cleanly without raising AttributeError: Mock object has no attribute 'photo'
            await handle_message(msg, board_id="b", stream="ru")


if __name__ == '__main__':
    unittest.main()
