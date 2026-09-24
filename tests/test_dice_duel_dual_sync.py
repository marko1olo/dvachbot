import unittest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock

from dice_duel_engine import (
    create_dice_challenge,
    accept_dice_challenge,
    execute_player_roll,
    sync_dice_screens,
    active_dice_games,
    user_active_dice_game,
    get_dice_roll_keyboard,
    DICE_TURN_TIMEOUT_SEC,
    DICE_CHALLENGE_TIMEOUT_SEC,
)

class TestDiceDuelDualSync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        active_dice_games.clear()
        user_active_dice_game.clear()

        # Mock DB Pool
        self.mock_db = AsyncMock()
        self.mock_db.execute = AsyncMock()
        self.mock_db.commit = AsyncMock()

        self.pool_patch = patch("dice_duel_engine.get_pool", return_value=self.mock_db)
        self.pool_patch.start()

        self.bal_patch = patch("dice_duel_engine.get_user_global_balance", return_value=50000.0)
        self.bal_patch.start()
        self.deduct_patch = patch("dice_duel_engine.deduct_user_global_balance", return_value=(True, 50000.0))
        self.deduct_patch.start()
        self.add_patch = patch("dice_duel_engine.add_user_global_balance", return_value=(True, 50000.0))
        self.add_patch.start()
        self.tx_patch = patch("dice_duel_engine.record_user_transaction", return_value=None)
        self.tx_patch.start()
        self.fund_patch = patch("dice_duel_engine.add_to_abu_fund", return_value=None)
        self.fund_patch.start()
        self.bcast_patch = patch("dice_duel_engine.broadcast_dice_announcement", return_value=None)
        self.bcast_patch.start()
        self.notif_patch = patch("dice_duel_engine.send_pvp_direct_notification", return_value=None)
        self.notif_patch.start()

    async def asyncTearDown(self):
        patch.stopall()
        active_dice_games.clear()
        user_active_dice_game.clear()

    async def test_dual_screen_sync_and_buttons(self):
        p1 = 111111
        p2 = 222222
        bet = 1000

        mock_bot = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()

        # 1. Player 1 creates challenge
        ok, _, gid = await create_dice_challenge("b", p1, bet)
        self.assertTrue(ok)
        game = active_dice_games[gid]

        p1_chat = 111111
        p1_msg = 901
        game["chat_id"] = p1_chat
        game["msg_id"] = p1_msg
        game["player_msgs"][p1] = (p1_chat, p1_msg)

        # Broadcast card to P3
        p3_chat = 333333
        p3_msg = 902
        game["broadcast_msgs"].append((p3_chat, p3_msg))

        # 2. Player 2 accepts in their DM
        p2_chat = 222222
        p2_msg = 903
        ok, msg, game = await accept_dice_challenge(gid, p2)
        self.assertTrue(ok)
        game["player_msgs"][p2] = (p2_chat, p2_msg)

        # 3. Synchronize screens
        await sync_dice_screens(mock_bot, game)

        # Verify bot edited both P1 and P2 messages
        edited_calls = mock_bot.edit_message_text.call_args_list
        edited_chats = [c.kwargs.get("chat_id") for c in edited_calls]

        self.assertIn(p1_chat, edited_chats, "P1 screen must be edited")
        self.assertIn(p2_chat, edited_chats, "P2 screen must be edited")
        self.assertIn(p3_chat, edited_chats, "Third-party broadcast must be neutralized")

        # Verify buttons: Active player has roll button, waiting player has wait button
        turn = game["current_turn"]
        waiting_player = p2 if turn == p1 else p1

        p_turn_kb = get_dice_roll_keyboard(gid, is_my_turn=True)
        p_wait_kb = get_dice_roll_keyboard(gid, is_my_turn=False)

        self.assertIn("БРОСИТЬ КОСТИ", p_turn_kb.inline_keyboard[0][0].text)
        self.assertEqual(f"dice_roll:{gid}", p_turn_kb.inline_keyboard[0][0].callback_data)

        self.assertIn("Очередь соперника", p_wait_kb.inline_keyboard[0][0].text)
        self.assertEqual(f"dice_wait:{gid}", p_wait_kb.inline_keyboard[0][0].callback_data)

    async def test_constants_alignment(self):
        self.assertEqual(DICE_TURN_TIMEOUT_SEC, 120.0, "Turn timeout must be 120s")
        self.assertEqual(DICE_CHALLENGE_TIMEOUT_SEC, 600.0, "Challenge timeout must be 600s (10 min)")
