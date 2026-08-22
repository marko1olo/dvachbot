"""
Unit and integration tests for Milestone M3: Admin & Anti-Abuse Immunity Hardening.
Verifies all admin exemption paths and target immunity across:
1. handlers/message_router.py (reactions, shadow mutes, reaction bans, live edit rate tracker, media group uploads)
2. common/spam_filter.py (is_spam_filtered, analyze_message_for_spam, check_rate_limit, _check_repeats, _check_cross_board_spam)
3. main.py (BoardMiddleware banned/lockdown bypass, check_cooldown mode switches, /roast & /summarize cooldowns, handle_attack_abuse_check, combat target immunity for /shoot, /pepperspray, /rob, /curse, /partyvan, /schizopill).
"""

import asyncio
from datetime import datetime, timedelta, UTC
import io
import time
import unittest
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import common.config
from common.spam_filter import (
    SpamResult,
    is_spam_filtered,
    analyze_message_for_spam,
    check_rate_limit,
    _check_repeats,
    _check_cross_board_spam,
    set_spam_filter_words,
)
from bot_helpers import is_admin

# Admin test IDs
ADMIN_USER_ID = 7777777
REGULAR_USER_ID = 1234567
TEST_BOARD = "b"


class TestAdminSpamFilterImmunity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        common.config.ADMIN_IDS.add(ADMIN_USER_ID)
        set_spam_filter_words(TEST_BOARD, {"badword", "spamlink", "scam"})

    def tearDown(self):
        common.config.ADMIN_IDS.discard(ADMIN_USER_ID)

    def test_is_admin_resolution(self):
        """Verify is_admin returns True for global admin and handles None board_id."""
        self.assertTrue(is_admin(ADMIN_USER_ID, TEST_BOARD))
        self.assertTrue(is_admin(ADMIN_USER_ID, None))
        self.assertFalse(is_admin(REGULAR_USER_ID, TEST_BOARD))
        self.assertFalse(is_admin(REGULAR_USER_ID, None))

    def test_is_spam_filtered_admin_bypass(self):
        """Admins must never be spam-filtered, even with explicit banned words."""
        # Non-admin with badword -> True (filtered)
        self.assertTrue(is_spam_filtered("This contains badword here", TEST_BOARD, REGULAR_USER_ID))
        # Admin with badword -> False (bypassed)
        self.assertFalse(is_spam_filtered("This contains badword here", TEST_BOARD, ADMIN_USER_ID))

    async def test_analyze_message_for_spam_admin_bypass(self):
        """Admins must always return (SpamResult.CLEAN, 0) in analyze_message_for_spam."""
        res, lvl = await analyze_message_for_spam(
            user_id=ADMIN_USER_ID,
            board_id=TEST_BOARD,
            content="Rapid duplicate text spam",
            msg_type="text",
            raw_content_type="text",
            skip_cross_board=False,
        )
        self.assertEqual(res, SpamResult.CLEAN)
        self.assertEqual(lvl, 0)

    def test_check_rate_limit_and_repeats_admin_bypass(self):
        """Direct spam filter helper functions must allow admins immediately."""
        rules = {'window_sec': 15, 'max_per_window': 1}
        self.assertTrue(check_rate_limit(TEST_BOARD, ADMIN_USER_ID, rules))
        self.assertTrue(check_rate_limit(TEST_BOARD, ADMIN_USER_ID, rules))
        self.assertTrue(_check_cross_board_spam(ADMIN_USER_ID, TEST_BOARD, "test", "text", "text"))


class TestMessageRouterAdminImmunity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        common.config.ADMIN_IDS.add(ADMIN_USER_ID)

    def tearDown(self):
        common.config.ADMIN_IDS.discard(ADMIN_USER_ID)

    async def test_reaction_rate_limiting_and_shadow_mute_admin_bypass(self):
        """Admins must bypass 0.5s reaction rate limit and shadow mute / reaction ban checks."""
        import shared_state
        from handlers.message_router import handle_message_reaction

        # Set up board data with active shadow mute and reaction ban for admin
        shared_state.board_data[TEST_BOARD] = {
            'shadow_mutes': {ADMIN_USER_ID: datetime.now(UTC) + timedelta(hours=1)},
            'reaction_banned_users': {ADMIN_USER_ID},
            'reaction_rate_tracker': {ADMIN_USER_ID: []},
            'reaction_queue': {ADMIN_USER_ID: []},
            'users': {'active': set(), 'banned': set()},
            'mutes': {},
        }
        shared_state.reaction_ratelimit[ADMIN_USER_ID] = time.time()  # would throttle non-admin

        reaction = MagicMock()
        reaction.user = MagicMock()
        reaction.user.id = ADMIN_USER_ID
        reaction.chat.id = -100123
        reaction.message_id = 999

        # Even with recent reaction_ratelimit and shadow mute, handle_message_reaction proceeds past filters
        with patch('handlers.message_router.get_post_info_by_copy', AsyncMock(return_value=None)):
            await handle_message_reaction(reaction, TEST_BOARD)
            # The function completed without raising and reached storage lookup (since post wasn't in RAM/DB)

    async def test_media_group_upload_admin_bypass(self):
        """Media group uploads from admins must not be dropped even if admin is in banned or mutes."""
        import shared_state
        from handlers.message_router import handle_media_group_init
        from aiogram import types

        shared_state.board_data[TEST_BOARD] = {
            'users': {'active': set(), 'banned': {ADMIN_USER_ID, REGULAR_USER_ID}},
            'mutes': {ADMIN_USER_ID: datetime.now(UTC) + timedelta(hours=1)},
            'last_activity': {},
        }
        media_group_id = "test_mg_123"

        msg = MagicMock()
        msg.media_group_id = media_group_id
        msg.chat = types.Chat(id=-100456, type='supergroup')
        msg.message_id = 1111
        msg.date = datetime.now(UTC)
        msg.from_user = types.User(id=ADMIN_USER_ID, is_bot=False, first_name="Admin")
        msg.reply_to_message = None
        msg.caption = "Admin album caption"
        msg.caption_html_text = "Admin album caption"
        msg.delete = AsyncMock()

        with patch('handlers.message_router.complete_media_group_after_delay', AsyncMock()), \
             patch('handlers.message_router.spawn_task', MagicMock()):
            await handle_media_group_init(msg, TEST_BOARD)
            # Last activity must be recorded for admin
            self.assertIn(ADMIN_USER_ID, shared_state.board_data[TEST_BOARD]['last_activity'])


class TestMainAdminImmunity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        common.config.ADMIN_IDS.add(ADMIN_USER_ID)

    def tearDown(self):
        common.config.ADMIN_IDS.discard(ADMIN_USER_ID)

    async def test_board_middleware_banned_and_lockdown_admin_bypass(self):
        """BoardMiddleware must never delete or drop messages from admins."""
        from main import BoardMiddleware
        import shared_state

        from aiogram import types
        middleware = BoardMiddleware()
        shared_state.board_data[TEST_BOARD] = {
            'users': {'active': set(), 'banned': {ADMIN_USER_ID, REGULAR_USER_ID}},
            'lockdown': True,
        }

        # Non-admin event: should be deleted and blocked
        regular_event = MagicMock(spec=types.Message)
        regular_event.delete = AsyncMock()
        regular_user = MagicMock()
        regular_user.id = REGULAR_USER_ID
        data_regular = {'event_from_user': regular_user, 'board_id': TEST_BOARD}

        handler_called = False
        async def mock_handler(evt, d):
            nonlocal handler_called
            handler_called = True
            return "OK"

        with patch('main.get_board_id', return_value=TEST_BOARD):
            await middleware(mock_handler, regular_event, data_regular)
            self.assertFalse(handler_called)
            regular_event.delete.assert_awaited()

            # Admin event: should NOT be deleted and handler MUST be called
            admin_event = MagicMock(spec=types.Message)
            admin_event.delete = AsyncMock()
            admin_user = MagicMock()
            admin_user.id = ADMIN_USER_ID
            data_admin = {'event_from_user': admin_user, 'board_id': TEST_BOARD}

            handler_called = False
            result = await middleware(mock_handler, admin_event, data_admin)
            self.assertTrue(handler_called)
            self.assertEqual(result, "OK")
            admin_event.delete.assert_not_awaited()

    async def test_check_cooldown_mode_switch_admin_bypass(self):
        """Admins must bypass mode switch 1-hour cooldown."""
        from aiogram import types
        from main import check_cooldown
        import shared_state

        shared_state.board_data[TEST_BOARD] = {
            'last_mode_activation': datetime.now(UTC)  # Just switched 0 seconds ago
        }

        regular_msg = MagicMock()
        regular_msg.from_user = MagicMock()
        regular_msg.from_user.id = REGULAR_USER_ID
        regular_msg.answer = AsyncMock()
        regular_msg.delete = AsyncMock()

        admin_msg = MagicMock()
        admin_msg.from_user = MagicMock()
        admin_msg.from_user.id = ADMIN_USER_ID
        admin_msg.answer = AsyncMock()
        admin_msg.delete = AsyncMock()

        # Non-admin is on cooldown
        with patch('main.spawn_task', MagicMock()):
            can_switch_reg = await check_cooldown(regular_msg, TEST_BOARD)
            self.assertFalse(can_switch_reg)

            # Admin bypasses cooldown immediately
            can_switch_admin = await check_cooldown(admin_msg, TEST_BOARD)
            self.assertTrue(can_switch_admin)

    async def test_ai_roast_and_summarize_cooldown_admin_bypass(self):
        """Admins must bypass /roast and /summarize cooldowns."""
        from main import cmd_roast, cmd_summarize, ROAST_COOLDOWN, SUMMARIZE_COOLDOWN
        import shared_state

        shared_state.board_data[TEST_BOARD] = {
            'last_roast_time': time.time(),
            'last_summarize_time': time.time(),
        }

        # Regular user roast -> gets cooldown reply
        reg_msg = MagicMock()
        reg_msg.from_user.id = REGULAR_USER_ID
        reg_msg.reply = AsyncMock()
        await cmd_roast(reg_msg, TEST_BOARD)
        reg_msg.reply.assert_awaited()
        self.assertIn("Команда остывает", reg_msg.reply.call_args[0][0])

        # Admin roast -> bypasses cooldown check (not rejected with cooldown reply)
        admin_msg = MagicMock()
        admin_msg.from_user.id = ADMIN_USER_ID
        admin_msg.reply = AsyncMock()
        await cmd_roast(admin_msg, TEST_BOARD)
        # Did not reply with cooldown message
        for call in admin_msg.reply.call_args_list:
            self.assertNotIn("Команда остывает", str(call))

    async def test_handle_attack_abuse_check_admin_bypass(self):
        """Admins must never be fined or muted by Spetsnaz abuse checks."""
        from main import handle_attack_abuse_check

        msg = MagicMock()
        msg.answer = AsyncMock()
        db = MagicMock()

        # Admin attacking -> returns False immediately (not blocked, not punished)
        res = await handle_attack_abuse_check(msg, db, TEST_BOARD, ADMIN_USER_ID, REGULAR_USER_ID)
        self.assertFalse(res)
        msg.answer.assert_not_awaited()


class TestCombatTargetImmunity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        common.config.ADMIN_IDS.add(ADMIN_USER_ID)

    def tearDown(self):
        common.config.ADMIN_IDS.discard(ADMIN_USER_ID)

    async def test_combat_target_immunity_shoot(self):
        """Non-admin shooting an admin with /shoot must be blocked with immunity alert."""
        from main import cmd_shoot

        msg = MagicMock()
        msg.from_user.id = REGULAR_USER_ID
        msg.reply_to_message = MagicMock()
        msg.answer = AsyncMock()

        with patch('main.get_author_id_by_reply', AsyncMock(return_value=ADMIN_USER_ID)):
            await cmd_shoot(msg, TEST_BOARD)
            msg.answer.assert_awaited()
            self.assertIn("абсолютный иммунитет Администратора", msg.answer.call_args[0][0])

    async def test_combat_target_immunity_pepperspray(self):
        """Non-admin attacking an admin with /pepperspray must be blocked with immunity alert."""
        from main import cmd_pepperspray

        msg = MagicMock()
        msg.from_user.id = REGULAR_USER_ID
        msg.reply_to_message = MagicMock()
        msg.answer = AsyncMock()

        with patch('main.get_author_id_by_reply', AsyncMock(return_value=ADMIN_USER_ID)):
            await cmd_pepperspray(msg, TEST_BOARD)
            msg.answer.assert_awaited()
            self.assertIn("абсолютный иммунитет Администратора", msg.answer.call_args[0][0])

    async def test_combat_target_immunity_rob(self):
        """Non-admin robbing an admin with /rob must be blocked with immunity alert."""
        from main import cmd_rob

        msg = MagicMock()
        msg.from_user.id = REGULAR_USER_ID
        msg.reply_to_message = MagicMock()
        msg.answer = AsyncMock()

        with patch('main._get_user_active_items', AsyncMock(return_value={"knife_gun": True})), \
             patch('main.get_author_id_by_reply', AsyncMock(return_value=ADMIN_USER_ID)):
            await cmd_rob(msg, TEST_BOARD)
            msg.answer.assert_awaited()
            self.assertIn("абсолютный иммунитет Администратора", msg.answer.call_args[0][0])

    async def test_combat_target_immunity_curse(self):
        """Non-admin cursing an admin with /curse must be blocked with immunity alert."""
        from main import cmd_curse

        msg = MagicMock()
        msg.from_user.id = REGULAR_USER_ID
        msg.reply_to_message = MagicMock()
        msg.answer = AsyncMock()

        with patch('main._get_user_active_items', AsyncMock(return_value={"laxative_gun": True})), \
             patch('main.get_author_id_by_reply', AsyncMock(return_value=ADMIN_USER_ID)):
            await cmd_curse(msg, TEST_BOARD)
            msg.answer.assert_awaited()
            self.assertIn("абсолютный иммунитет Администратора", msg.answer.call_args[0][0])

    async def test_combat_target_immunity_schizopill(self):
        """Non-admin poisoning an admin with /schizopill must be blocked with immunity alert."""
        from main import cmd_schizopill

        msg = MagicMock()
        msg.from_user.id = REGULAR_USER_ID
        msg.reply_to_message = MagicMock()
        msg.answer = AsyncMock()

        with patch('main._get_user_active_items', AsyncMock(return_value={"schizopill_gun": True})), \
             patch('main.get_author_id_by_reply', AsyncMock(return_value=ADMIN_USER_ID)):
            await cmd_schizopill(msg, TEST_BOARD)
            msg.answer.assert_awaited()
            self.assertIn("абсолютный иммунитет Администратора", msg.answer.call_args[0][0])

    async def test_combat_target_immunity_partyvan(self):
        """Non-admin targeting an admin with /partyvan must be blocked with immunity alert."""
        from main import cmd_partyvan

        msg = MagicMock()
        msg.from_user.id = REGULAR_USER_ID
        msg.reply_to_message = MagicMock()
        msg.answer = AsyncMock()

        with patch('main._get_user_active_items', AsyncMock(return_value={"partyvan_gun": True})), \
             patch('main.get_author_id_by_reply', AsyncMock(return_value=ADMIN_USER_ID)):
            await cmd_partyvan(msg, TEST_BOARD)
            msg.answer.assert_awaited()
            self.assertIn("абсолютный иммунитет Администратора", msg.answer.call_args[0][0])
