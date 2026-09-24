import unittest
import asyncio
import time
from unittest.mock import AsyncMock, patch

from russian_roulette_pvp import (
    create_rr_challenge,
    accept_rr_challenge,
    pull_rr_trigger,
    sync_rr_screens,
    active_rr_games,
    user_active_rr_game,
    get_rr_game_keyboard,
    RR_TURN_TIMEOUT_SEC,
    RR_MUTE_DURATION_SEC
)

class TestRussianRouletteDualSync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        active_rr_games.clear()
        user_active_rr_game.clear()

        # Mock DB Pool
        self.mock_db = AsyncMock()
        self.mock_db.execute = AsyncMock()
        self.mock_db.commit = AsyncMock()
        
        # Patch db_pool
        self.pool_patch = patch("russian_roulette_pvp.get_pool", return_value=self.mock_db)
        self.pool_patch.start()
        
        # Patch user balance & transactions
        self.bal_patch = patch("russian_roulette_pvp.get_user_global_balance", return_value=50000.0)
        self.bal_patch.start()
        self.deduct_patch = patch("russian_roulette_pvp.deduct_user_global_balance", return_value=(True, 50000.0))
        self.deduct_patch.start()
        self.add_patch = patch("russian_roulette_pvp.add_user_global_balance", return_value=(True, 50000.0))
        self.add_patch.start()
        self.tx_patch = patch("russian_roulette_pvp.record_user_transaction", return_value=None)
        self.tx_patch.start()
        self.fund_patch = patch("russian_roulette_pvp.add_to_abu_fund", return_value=None)
        self.fund_patch.start()
        self.mute_patch = patch("russian_roulette_pvp.apply_regular_mute", return_value=True)
        self.mute_patch.start()

    async def asyncTearDown(self):
        patch.stopall()
        active_rr_games.clear()
        user_active_rr_game.clear()

    async def test_dual_screen_sync_and_buttons(self):
        p1 = 111111
        p2 = 222222
        bet = 1000

        # 1. Player 1 creates challenge
        ok, _, gid = await create_rr_challenge("b", p1, bet)
        self.assertTrue(ok)
        game = active_rr_games[gid]
        
        # Simulate P1 receiving card in their DM
        p1_chat = 111111
        p1_msg = 901
        game["chat_id"] = p1_chat
        game["msg_id"] = p1_msg
        game["player_msgs"][p1] = (p1_chat, p1_msg)
        
        # Third-party user receives broadcast card
        bcast_chat = 333333
        bcast_msg = 902
        game["broadcast_msgs"].append((bcast_chat, bcast_msg))

        # 2. Player 2 accepts in their DM
        p2_chat = 222222
        p2_msg = 903
        ok, msg, game = await accept_rr_challenge(gid, p2)
        self.assertTrue(ok)
        game["player_msgs"][p2] = (p2_chat, p2_msg)

        # Mock Bot to track edit_message_text calls
        mock_bot = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()

        # 3. Synchronize screens
        await sync_rr_screens(mock_bot, game)

        # Verify bot edited both P1 and P2 messages
        edited_calls = mock_bot.edit_message_text.call_args_list
        edited_chats = [c.kwargs.get("chat_id") for c in edited_calls]
        
        self.assertIn(p1_chat, edited_chats, "P1 screen must be edited")
        self.assertIn(p2_chat, edited_chats, "P2 screen must be edited")
        self.assertIn(bcast_chat, edited_chats, "Third-party broadcast must be neutralized")

        # Verify buttons: Active player has shoot button, waiting player has wait button
        turn = game["turn"]
        waiting_player = p2 if turn == p1 else p1
        
        p_turn_kb = get_rr_game_keyboard(gid, is_finished=False, is_my_turn=True)
        p_wait_kb = get_rr_game_keyboard(gid, is_finished=False, is_my_turn=False)

        self.assertIn("СПУСТИТЬ КУРОК", p_turn_kb.inline_keyboard[0][0].text)
        self.assertEqual(f"rr_shoot:{gid}", p_turn_kb.inline_keyboard[0][0].callback_data)
        
        self.assertIn("Очередь соперника", p_wait_kb.inline_keyboard[0][0].text)
        self.assertEqual(f"rr_wait:{gid}", p_wait_kb.inline_keyboard[0][0].callback_data)

    async def test_constants_alignment(self):
        self.assertEqual(RR_TURN_TIMEOUT_SEC, 120.0, "Turn timeout must be 120s")
        self.assertEqual(RR_MUTE_DURATION_SEC, 1800, "Mute must be 1800s (30 mins)")
