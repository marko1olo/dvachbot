import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ttt_engine
import dice_duel_engine
import russian_roulette_pvp


class TestPvPLiveTickRefresh(unittest.IsolatedAsyncioTestCase):
    async def test_ttt_watchdog_live_tick_every_5_seconds(self):
        """TTT active games must auto-refresh screens for both players every 5 seconds."""
        mock_bot = MagicMock()
        mock_bot.edit_message_text = AsyncMock()

        game_id = "test_ttt_tick"
        game = ttt_engine.TicTacToeGame(
            game_id=game_id,
            board_id="b",
            chat_id=111,
            challenger_id=111,
            opponent_id=222,
            bet=100,
            status="active",
            current_turn=111,
            turn_start_time=time.time(),
            bot_instance=mock_bot,
            player_msgs={111: (111, 10), 222: (222, 20)},
            last_tick_ts=time.time() - 16.0  # 16 seconds ago (> 15s anti-flood interval)
        )
        ttt_engine.active_ttt_games[game_id] = game

        try:
            await ttt_engine.ttt_watchdog_step(mock_bot)
            # Both player screens should be updated
            self.assertEqual(mock_bot.edit_message_text.call_count, 2)
            self.assertAlmostEqual(game.last_tick_ts, time.time(), delta=1.5)
        finally:
            ttt_engine.active_ttt_games.pop(game_id, None)

    async def test_dice_duel_watchdog_live_tick_every_5_seconds(self):
        """Dice duel active games must auto-refresh screens every 15 seconds."""
        mock_bot = MagicMock()
        mock_bot.edit_message_text = AsyncMock()

        gid = "test_dice_tick"
        game = {
            "game_id": gid,
            "board_id": "b",
            "state": "playing",
            "bet": 100,
            "pot": 200,
            "player_1": 333,
            "player_2": 444,
            "current_player": 333,
            "round": 1,
            "scores": {333: 0, 444: 0},
            "p1_rolls": {},
            "p2_rolls": {},
            "turn_deadline_ts": time.time() + 50.0,
            "last_tick_ts": time.time() - 16.0,  # 16 seconds ago (> 15s anti-flood interval)
            "player_msgs": {333: (333, 101), 444: (444, 102)},
            "finished": False
        }
        dice_duel_engine.active_dice_games[gid] = game

        try:
            await dice_duel_engine.dice_watchdog_step(mock_bot)
            self.assertEqual(mock_bot.edit_message_text.call_count, 2)
            self.assertAlmostEqual(game["last_tick_ts"], time.time(), delta=1.5)
        finally:
            dice_duel_engine.active_dice_games.pop(gid, None)

    async def test_russian_roulette_watchdog_live_tick_every_5_seconds(self):
        """Russian roulette active games must auto-refresh screens every 15 seconds."""
        mock_bot = MagicMock()
        mock_bot.edit_message_text = AsyncMock()

        gid = "test_rr_tick"
        game = {
            "game_id": gid,
            "board_id": "b",
            "state": "playing",
            "challenger_id": 555,
            "acceptor_id": 666,
            "turn": 555,
            "bet": 200,
            "pot": 400,
            "chamber_count": 6,
            "current_chamber": 1,
            "bullet_position": 4,
            "turn_deadline_ts": time.time() + 100.0,
            "last_tick_ts": time.time() - 16.0,  # 16 seconds ago (> 15s anti-flood interval)
            "player_msgs": {555: (555, 201), 666: (666, 202)},
            "finished": False
        }
        russian_roulette_pvp.active_rr_games[gid] = game

        try:
            await russian_roulette_pvp.rr_watchdog_step(mock_bot)
            self.assertEqual(mock_bot.edit_message_text.call_count, 2)
            self.assertAlmostEqual(game["last_tick_ts"], time.time(), delta=1.5)
        finally:
            russian_roulette_pvp.active_rr_games.pop(gid, None)


if __name__ == "__main__":
    unittest.main()
