import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, User, Chat

import shared_state
from handlers.message_router import (
    _CYBERCHAD_USER_LAST_DIRECT,
    _CYBERCHAD_USER_LAST_REJECT,
    CYBERCHAD_RATE_LIMIT_REJECTIONS,
    CYBERCHAD_DIRECT_TRIGGER_REGEX,
    _is_direct_cyberchad_trigger,
    trigger_cyberchad_with_rate_limit,
    handle_cyberchad_rate_limit_and_trigger,
    handle_message,
)


class TestCyberchadRateLimitConstants(unittest.TestCase):
    """Verifies module-level data structures and curated phrases."""

    def test_rejection_phrases_count_and_content(self):
        self.assertEqual(len(CYBERCHAD_RATE_LIMIT_REJECTIONS), 20)
        for phrase in CYBERCHAD_RATE_LIMIT_REJECTIONS:
            self.assertIsInstance(phrase, str)
            self.assertGreater(len(phrase.strip()), 15)
            # Ensure no dummy/placeholder strings
            self.assertNotIn("test", phrase.lower())
            self.assertNotIn("todo", phrase.lower())

    def test_tracking_dictionaries_exist(self):
        self.assertIsInstance(_CYBERCHAD_USER_LAST_DIRECT, dict)
        self.assertIsInstance(_CYBERCHAD_USER_LAST_REJECT, dict)

    def test_exported_aliases(self):
        self.assertIs(trigger_cyberchad_with_rate_limit, handle_cyberchad_rate_limit_and_trigger)


class TestIsDirectCyberchadTrigger(unittest.IsolatedAsyncioTestCase):
    """Verifies direct Cyberchad trigger detection via text or reply-to metadata."""

    async def asyncSetUp(self):
        async with shared_state.storage_lock:
            shared_state.messages_storage.clear()

    async def asyncTearDown(self):
        async with shared_state.storage_lock:
            shared_state.messages_storage.clear()

    async def test_text_mention_cyberchad_variations(self):
        positive_cases = [
            "киберчед, поясни за шмот",
            "Киберчед ты кто вообще",
            "КИБЕРЧЕД ОТВЕТЬ",
            "слышь, кибер-чед, выходи",
            "киберчат завали",
            "кибердед проснись",
            "киберсыч не ной",
            "hey cyberchad what is this",
            "cyber_chad Alpha",
            "нейрочед выдай базу",
        ]
        for text in positive_cases:
            with self.subTest(text=text):
                res = await _is_direct_cyberchad_trigger(text, None)
                self.assertTrue(res, f"Expected True for '{text}'")

    async def test_text_normal_messages_return_false(self):
        negative_cases = [
            "привет аноны",
            "какой сегодня день",
            ">>100 согласен с автором",
            "человек в шляпе",
            "дедушка на лавочке",
            "",
            None,
        ]
        for text in negative_cases:
            with self.subTest(text=text):
                res = await _is_direct_cyberchad_trigger(text, None)
                self.assertFalse(res, f"Expected False for '{text}'")

    async def test_reply_to_cyberchad_author_id_0_in_ram(self):
        async with shared_state.storage_lock:
            shared_state.messages_storage[500] = {
                'post_num': 500,
                'author_id': 0,
                'content': {'type': 'voice', 'caption': '🔥 Разъёб от Киберчеда'}
            }

        res = await _is_direct_cyberchad_trigger("ты не прав", 500)
        self.assertTrue(res)

    async def test_reply_to_cyberchad_author_id_1488148800_in_ram(self):
        async with shared_state.storage_lock:
            shared_state.messages_storage[501] = {
                'post_num': 501,
                'author_id': 1488148800,
                'content': {'type': 'text', 'text': 'Тест'}
            }

        res = await _is_direct_cyberchad_trigger("заткнись", 501)
        self.assertTrue(res)

    async def test_reply_to_cyberchad_in_db(self):
        db_post = {
            'post_num': 600,
            'author_id': 0,
            'content': {'type': 'voice', 'caption': 'Голос'}
        }
        with patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=db_post):
            res = await _is_direct_cyberchad_trigger("ну и бред", 600)
            self.assertTrue(res)

    async def test_reply_to_cyberchad_ai_flags_in_content(self):
        db_post = {
            'post_num': 700,
            'author_id': 999,  # Even if non-zero author_id
            'content': {'is_ai_roast': True, 'is_cyberchad': True}
        }
        with patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=db_post):
            res = await _is_direct_cyberchad_trigger("ну и что", 700)
            self.assertTrue(res)

    async def test_reply_to_cyberchad_json_string_content(self):
        db_post = {
            'post_num': 800,
            'author_id': 999,
            'content': '{"is_cyberchad": true, "type": "voice"}'
        }
        with patch("handlers.message_router.get_post_by_num", new_callable=AsyncMock, return_value=db_post):
            res = await _is_direct_cyberchad_trigger("ответь мне", 800)
            self.assertTrue(res)

    async def test_reply_to_regular_user_returns_false(self):
        async with shared_state.storage_lock:
            shared_state.messages_storage[900] = {
                'post_num': 900,
                'author_id': 12345,
                'content': {'type': 'text', 'text': 'Обычный пост'}
            }

        res = await _is_direct_cyberchad_trigger("согласен", 900)
        self.assertFalse(res)


class TestCyberchadRateLimitLifecycle(unittest.IsolatedAsyncioTestCase):
    """
    Verifies the timing and rate-limiting rules:
    - User call 1 at t=0: calls intervention handler.
    - User call 2 at t=5s: suppressed Gemini call; triggers synthesize_cyberchad_voice_with_meta & process_new_post.
    - User call 3 at t=10s: suppressed Gemini call & suppressed voice reject (15s anti-flood).
    - User call 4 at t=21s: suppressed Gemini call; triggers voice reject (>= 15s since t=5s).
    - User call 5 at t=61s: calls intervention handler (60s cooldown expired).
    - Multi-user isolation: User 102 at t=5s is NOT blocked by User 101's rate limit.
    """

    def setUp(self):
        _CYBERCHAD_USER_LAST_DIRECT.clear()
        _CYBERCHAD_USER_LAST_REJECT.clear()
        self.mock_bot = MagicMock()

    def tearDown(self):
        _CYBERCHAD_USER_LAST_DIRECT.clear()
        _CYBERCHAD_USER_LAST_REJECT.clear()

    async def test_rate_limit_timing_sequence(self):
        t0 = 100000.0

        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene, \
             patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp, \
             patch("handlers.message_router.time.time") as mock_time:

            mock_tts.return_value = (b"fake_rejection_audio_ogg", MagicMock())
            mock_pnp.return_value = 9999

            # --- CALL 1 at t = 0s ---
            mock_time.return_value = t0
            res1 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед поясни", post_num=1001, reply_to_post=None, stream="ru"
            )
            self.assertTrue(res1)
            mock_intervene.assert_called_once_with(
                self.mock_bot, "b", 101, "киберчед поясни", post_num=1001, reply_to_post=None, stream="ru"
            )
            mock_tts.assert_not_called()
            mock_pnp.assert_not_called()
            self.assertEqual(_CYBERCHAD_USER_LAST_DIRECT[("b", 101)], t0)

            # --- CALL 2 at t = 5s (Rate limit hit: offline voice roast triggered) ---
            mock_time.return_value = t0 + 5.0
            res2 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед ты тут?", post_num=1002, reply_to_post=None, stream="ru"
            )
            self.assertFalse(res2)
            # Intervention handler must NOT be called again (still 1 call)
            self.assertEqual(mock_intervene.call_count, 1)
            # Voice note must be synthesized
            mock_tts.assert_called_once()
            reject_text_used = mock_tts.call_args[0][0]
            self.assertIn(reject_text_used, CYBERCHAD_RATE_LIMIT_REJECTIONS)
            # process_new_post must be called to send the voice note
            mock_pnp.assert_called_once()
            pnp_params = mock_pnp.call_args[0][0]
            self.assertEqual(pnp_params.board_id, "b")
            self.assertEqual(pnp_params.user_id, 0)
            self.assertEqual(pnp_params.reply_to_post, 1002)
            self.assertEqual(pnp_params.content["type"], "voice")
            self.assertEqual(pnp_params.content["voice_bytes"], b"fake_rejection_audio_ogg")
            self.assertEqual(pnp_params.content["caption"], "🔥 Разъёб от Киберчеда")
            self.assertTrue(pnp_params.content["is_cyberchad"])
            self.assertEqual(_CYBERCHAD_USER_LAST_REJECT[("b", 101)], t0 + 5.0)

            # --- CALL 3 at t = 10s (Within 15s of reject: voice roast suppressed!) ---
            mock_time.return_value = t0 + 10.0
            res3 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед ало", post_num=1003, reply_to_post=None, stream="ru"
            )
            self.assertFalse(res3)
            # Neither intervention nor voice synthesis should be called
            self.assertEqual(mock_intervene.call_count, 1)
            self.assertEqual(mock_tts.call_count, 1)
            self.assertEqual(mock_pnp.call_count, 1)

            # --- CALL 4 at t = 21s (16s since reject at t=5s, but <60s from t=0: voice roast allowed again) ---
            mock_time.return_value = t0 + 21.0
            res4 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед ну ответь", post_num=1004, reply_to_post=None, stream="ru"
            )
            self.assertFalse(res4)
            self.assertEqual(mock_intervene.call_count, 1)
            self.assertEqual(mock_tts.call_count, 2)
            self.assertEqual(mock_pnp.call_count, 2)
            self.assertEqual(_CYBERCHAD_USER_LAST_REJECT[("b", 101)], t0 + 21.0)

            # --- CALL 5 at t = 61s (>= 60s from t=0: normal intervention allowed) ---
            mock_time.return_value = t0 + 61.0
            res5 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед минута прошла", post_num=1005, reply_to_post=None, stream="ru"
            )
            self.assertTrue(res5)
            self.assertEqual(mock_intervene.call_count, 2)
            self.assertEqual(mock_tts.call_count, 2)
            self.assertEqual(mock_pnp.call_count, 2)
            self.assertEqual(_CYBERCHAD_USER_LAST_DIRECT[("b", 101)], t0 + 61.0)

    async def test_multi_user_isolation(self):
        t0 = 200000.0

        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene, \
             patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_tts, \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp, \
             patch("handlers.message_router.time.time") as mock_time:

            mock_tts.return_value = (b"voice", MagicMock())

            # User 101 calls at t=0
            mock_time.return_value = t0
            await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед привет", post_num=1
            )
            self.assertEqual(mock_intervene.call_count, 1)

            # User 101 calls at t=5s -> blocked
            mock_time.return_value = t0 + 5.0
            await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед спам", post_num=2
            )
            self.assertEqual(mock_intervene.call_count, 1)

            # User 102 calls at t=5s -> NOT blocked!
            res_user2 = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 102, "киберчед я другой юзер", post_num=3
            )
            self.assertTrue(res_user2)
            self.assertEqual(mock_intervene.call_count, 2)
            self.assertEqual(_CYBERCHAD_USER_LAST_DIRECT[("b", 102)], t0 + 5.0)

    async def test_board_isolation(self):
        t0 = 300000.0

        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene, \
             patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock), \
             patch("handlers.message_router.time.time") as mock_time:

            # User 101 calls on board 'b' at t=0
            mock_time.return_value = t0
            await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед", post_num=1
            )
            self.assertEqual(mock_intervene.call_count, 1)

            # User 101 calls on board 'po' at t=5s -> NOT blocked on different board!
            mock_time.return_value = t0 + 5.0
            res_po = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "po", 101, "киберчед", post_num=2
            )
            self.assertTrue(res_po)
            self.assertEqual(mock_intervene.call_count, 2)

    async def test_non_direct_trigger_bypasses_60s_limit(self):
        t0 = 400000.0

        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene, \
             patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock), \
             patch("handlers.message_router.time.time") as mock_time:

            # Direct trigger at t=0
            mock_time.return_value = t0
            await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "киберчед поясни", post_num=1
            )
            self.assertEqual(mock_intervene.call_count, 1)

            # Non-direct message at t=5s (e.g. regular chat between users)
            mock_time.return_value = t0 + 5.0
            res_nondirect = await trigger_cyberchad_with_rate_limit(
                self.mock_bot, "b", 101, "обычный текст без упоминаний", post_num=2
            )
            self.assertTrue(res_nondirect)
            # Intervention handler called normally for fight tracking
            self.assertEqual(mock_intervene.call_count, 2)

    async def test_invalid_input_guards(self):
        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock) as mock_intervene:
            self.assertFalse(await trigger_cyberchad_with_rate_limit(self.mock_bot, "b", 0, "киберчед"))
            self.assertFalse(await trigger_cyberchad_with_rate_limit(self.mock_bot, "b", -1, "киберчед"))
            self.assertFalse(await trigger_cyberchad_with_rate_limit(self.mock_bot, "trash", 101, "киберчед"))
            self.assertFalse(await trigger_cyberchad_with_rate_limit(self.mock_bot, "b", 101, ""))
            mock_intervene.assert_not_called()

    async def test_tts_synthesis_failure_handled_gracefully(self):
        t0 = 500000.0

        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock), \
             patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", side_effect=RuntimeError("TTS failure")), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp, \
             patch("handlers.message_router.time.time", return_value=t0):

            # Call 1
            await trigger_cyberchad_with_rate_limit(self.mock_bot, "b", 101, "киберчед", post_num=1)

        with patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new_callable=AsyncMock), \
             patch("handlers.message_router.synthesize_cyberchad_voice_with_meta", side_effect=RuntimeError("TTS failure")), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_pnp, \
             patch("handlers.message_router.time.time", return_value=t0 + 5.0):

            # Call 2 with TTS failing: should not raise exception
            res = await trigger_cyberchad_with_rate_limit(self.mock_bot, "b", 101, "киберчед", post_num=2)
            self.assertFalse(res)
            mock_pnp.assert_not_called()


class TestHandleMessageIntegrationWithRateLimit(unittest.IsolatedAsyncioTestCase):
    """Verifies that handle_message properly delegates direct Cyberchad triggers through trigger_cyberchad_with_rate_limit."""

    async def test_handle_message_invokes_rate_limited_trigger(self):
        msg = MagicMock(spec=Message)
        msg.message_id = 777
        msg.chat = MagicMock(id=12345)
        msg.from_user = User(id=12345, is_bot=False, first_name="Anon")
        msg.content_type = "text"
        msg.text = "киберчед поясни за этот тред"
        msg.html_text = "киберчед поясни за этот тред"
        msg.caption = None
        msg.caption_html_text = None
        msg.reply_to_message = None
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

        spawned_tasks = []

        def fake_spawn_task(coro):
            spawned_tasks.append(coro)
            # Return dummy task
            t = asyncio.create_task(coro)
            return t

        with patch("handlers.message_router.is_admin", return_value=False), \
             patch("handlers.message_router.get_pool", new_callable=AsyncMock), \
             patch("handlers.message_router.check_spam", return_value=True), \
             patch("handlers.message_router._get_user_active_items", new_callable=AsyncMock, return_value={}), \
             patch("common.database.is_shadow_muted", new_callable=AsyncMock, return_value=False), \
             patch("handlers.message_router.is_spam_filtered", return_value=False), \
             patch("handlers.message_router.resolve_archive_or_inline_reply", new_callable=AsyncMock, return_value=(None, "киберчед поясни за этот тред")), \
             patch("handlers.message_router.get_max_post_num", new_callable=AsyncMock, return_value=1000), \
             patch("handlers.message_router.add_or_activate_user", new_callable=AsyncMock), \
             patch("handlers.message_router.process_new_post", new_callable=AsyncMock, return_value=1001), \
             patch("handlers.message_router.trigger_cyberchad_with_rate_limit", new_callable=AsyncMock) as mock_trigger, \
             patch("handlers.message_router.spawn_task", side_effect=fake_spawn_task):

            await handle_message(msg, board_id="b", stream="ru")

            # Await any pending background tasks
            if spawned_tasks:
                await asyncio.gather(*spawned_tasks, return_exceptions=True)

            mock_trigger.assert_called_once_with(
                msg.bot, "b", 12345, "киберчед поясни за этот тред",
                post_num=1001, reply_to_post=None, stream="ru"
            )


if __name__ == '__main__':
    unittest.main()
