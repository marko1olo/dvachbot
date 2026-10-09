import unittest
from unittest.mock import AsyncMock, patch

from ttt_engine import (
    create_ttt_challenge,
    accept_ttt_challenge,
    sync_ttt_screens,
    active_ttt_games,
    user_active_ttt_session,
    TURN_TIMEOUT_SECONDS,
)

class TestTicTacToeDualSync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        active_ttt_games.clear()
        user_active_ttt_session.clear()

        # Mock DB Pool
        self.mock_db = AsyncMock()
        self.mock_db.execute = AsyncMock()
        self.mock_db.commit = AsyncMock()

        self.pool_patch = patch("ttt_engine.get_pool", return_value=self.mock_db)
        self.pool_patch.start()

        self.bal_patch = patch("ttt_engine.get_user_global_balance", return_value=50000.0)
        self.bal_patch.start()
        self.deduct_patch = patch("ttt_engine.deduct_user_global_balance", return_value=(True, 50000.0))
        self.deduct_patch.start()
        self.add_patch = patch("ttt_engine.add_user_global_balance", return_value=(True, 50000.0))
        self.add_patch.start()
        self.tx_patch = patch("ttt_engine.record_user_transaction", return_value=None)
        self.tx_patch.start()
        self.fund_patch = patch("ttt_engine.add_to_abu_fund", return_value=None)
        self.fund_patch.start()
        self.pub_patch = patch("ttt_engine.publish_ttt_board_announcement", return_value=None)
        self.pub_patch.start()
        self.notif_patch = patch("ttt_engine.send_pvp_direct_notification", return_value=None)
        self.notif_patch.start()

    async def asyncTearDown(self):
        patch.stopall()
        active_ttt_games.clear()
        user_active_ttt_session.clear()

    async def test_dual_screen_sync_and_broadcast_cleanup(self):
        p1 = 111111
        p2 = 222222
        bet = 1000

        mock_bot = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()

        # 1. P1 creates challenge
        ok, _, game = await create_ttt_challenge(
            bot=mock_bot,
            chat_id=111111,
            board_id="b",
            challenger_id=p1,
            bet=bet,
        )
        self.assertTrue(ok)
        gid = game.game_id

        p1_chat = 111111
        p1_msg = 901
        game.msg_id = p1_msg
        game.player_msgs[p1] = (p1_chat, p1_msg)

        # Broadcast card to P3
        p3_chat = 333333
        p3_msg = 902
        game.broadcast_msgs.append((p3_chat, p3_msg))

        # 2. P2 accepts challenge
        ok, _, game = await accept_ttt_challenge(mock_bot, gid, p2)
        self.assertTrue(ok)

        p2_chat = 222222
        p2_msg = 903
        game.player_msgs[p2] = (p2_chat, p2_msg)

        # 3. Synchronize screens
        await sync_ttt_screens(mock_bot, game)

        edited_calls = mock_bot.edit_message_text.call_args_list
        edited_chats = [c.kwargs.get("chat_id") for c in edited_calls]

        self.assertIn(p1_chat, edited_chats, "P1 screen must be edited")
        self.assertIn(p2_chat, edited_chats, "P2 screen must be edited")
        self.assertIn(p3_chat, edited_chats, "Third-party broadcast must be neutralized")

    async def test_ttt_turn_timeout_constant(self):
        self.assertEqual(TURN_TIMEOUT_SECONDS, 120, "TTT turn timeout must be 120 seconds")
