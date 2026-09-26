# -*- coding: utf-8 -*-
"""
test_game_banners_integration.py — Integration Tests for Tic-Tac-Toe and Roulette Banners
========================================================================================
Validates:
1. Banners exist on disk and are correctly categorized by banner_manager.
2. Explicit banner selection returns correct files for TTT and Roulette.
3. sync_ttt_screens edits photo messages via edit_message_caption when edit_message_text
   fails with "there is no text in the message to edit".
4. sync_rr_screens edits photo messages via edit_message_caption when edit_message_text
   fails with "there is no text in the message to edit".
"""

import unittest
from unittest.mock import AsyncMock
from pathlib import Path
from aiogram.exceptions import TelegramBadRequest

import banner_manager
from ttt_engine import (
    TicTacToeGame,
    sync_ttt_screens,
    active_ttt_games,
)
from russian_roulette_pvp import (
    sync_rr_screens,
    active_rr_games,
)


class TestGameBannersIntegration(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        banner_manager.reload_banners()

    def test_banner_files_exist_and_categorized(self):
        """Checks banner files are present in assets/banners/ and in category pools."""
        banners_dir = banner_manager.BANNERS_DIR
        ttt_banner = banners_dir / "banner_tictactoe_pvp.jpg"
        rr_banner = banners_dir / "banner_roulette_pvp.jpg"

        self.assertTrue(ttt_banner.exists(), f"Missing banner file: {ttt_banner}")
        self.assertTrue(rr_banner.exists(), f"Missing banner file: {rr_banner}")
        self.assertGreater(ttt_banner.stat().st_size, 500_000)
        self.assertGreater(rr_banner.stat().st_size, 500_000)

        # Check subsection pool binding (rich rotation across thousands of art banners)
        self.assertIn("ttt", banner_manager.SUBSECTION_CATEGORIES)
        self.assertIn("russian_roulette", banner_manager.SUBSECTION_CATEGORIES)

        ttt_candidates = banner_manager.resolve_category_candidates("ttt")
        self.assertTrue(any(c in ttt_candidates for c in ("games", "cyberpunk", "retro", "matrix")))

        rr_candidates = banner_manager.resolve_category_candidates("russian_roulette")
        self.assertTrue(any(c in rr_candidates for c in ("duel", "roulette", "games", "cyberpunk")))

        # Check banners are bound into existing pools
        games_pool = banner_manager._CATEGORIZED_BANNERS.get("games", [])
        self.assertIn("banner_tictactoe_pvp.jpg", games_pool)
        self.assertIn("banner_roulette_pvp.jpg", games_pool)

    def test_explicit_banner_name_resolution(self):
        """Verifies get_banner_file accurately returns requested banner file and payload."""
        fn_ttt, payload_ttt = banner_manager.get_banner_file(banner_name="banner_tictactoe_pvp.jpg")
        self.assertEqual(fn_ttt, "banner_tictactoe_pvp.jpg")
        self.assertTrue(payload_ttt is not None)

        fn_rr, payload_rr = banner_manager.get_banner_file(banner_name="banner_roulette_pvp.jpg")
        self.assertEqual(fn_rr, "banner_roulette_pvp.jpg")
        self.assertTrue(payload_rr is not None)

    async def test_ttt_sync_screens_photo_caption_fallback(self):
        """Verifies sync_ttt_screens falls back to edit_message_caption for photo banners."""
        game = TicTacToeGame(
            game_id="test_banner_ttt_1",
            board_id="b",
            chat_id=111,
            challenger_id=111,
            opponent_id=222,
            bet=100,
            status="active",
            current_turn=111,
        )
        p1_chat, p1_msg = 111, 501
        p2_chat, p2_msg = 222, 502
        game.player_msgs = {
            111: (p1_chat, p1_msg),
            222: (p2_chat, p2_msg),
        }

        mock_bot = AsyncMock()
        # Simulate Telegram behavior for photo messages: edit_message_text raises "there is no text"
        mock_bot.edit_message_text.side_effect = TelegramBadRequest(
            method="editMessageText",
            message="Bad Request: there is no text in the message to edit"
        )
        mock_bot.edit_message_caption = AsyncMock()

        await sync_ttt_screens(mock_bot, game)

        # edit_message_text was attempted
        self.assertEqual(mock_bot.edit_message_text.call_count, 2)
        # edit_message_caption was successfully called for both players!
        self.assertEqual(mock_bot.edit_message_caption.call_count, 2)

        caption_calls = mock_bot.edit_message_caption.call_args_list
        called_chats = [c.kwargs.get("chat_id") for c in caption_calls]
        self.assertIn(p1_chat, called_chats)
        self.assertIn(p2_chat, called_chats)

        for c in caption_calls:
            self.assertTrue(len(c.kwargs.get("caption", "")) > 0)
            self.assertIsNotNone(c.kwargs.get("reply_markup"))

    async def test_rr_sync_screens_photo_caption_fallback(self):
        """Verifies sync_rr_screens falls back to edit_message_caption for photo banners."""
        game = {
            "game_id": "test_banner_rr_1",
            "board_id": "b",
            "challenger_id": 333,
            "acceptor_id": 444,
            "target_id": None,
            "bet": 200,
            "state": "active",
            "bullet_chamber": 3,
            "current_chamber": 1,
            "turn": 333,
            "turn_deadline_ts": 9999999999.0,
            "created_ts": 1000.0,
            "last_action_ts": 1000.0,
            "finished": False,
            "outcome": None,
            "winner_id": None,
            "loser_id": None,
            "payout": 0,
            "player_msgs": {
                333: (333, 601),
                444: (444, 602),
            },
            "broadcast_msgs": []
        }

        mock_bot = AsyncMock()
        mock_bot.edit_message_text.side_effect = TelegramBadRequest(
            method="editMessageText",
            message="Bad Request: there is no text in the message to edit"
        )
        mock_bot.edit_message_caption = AsyncMock()

        await sync_rr_screens(mock_bot, game)

        # edit_message_text was attempted
        self.assertEqual(mock_bot.edit_message_text.call_count, 2)
        # edit_message_caption was called as fallback
        self.assertEqual(mock_bot.edit_message_caption.call_count, 2)

        caption_calls = mock_bot.edit_message_caption.call_args_list
        called_chats = [c.kwargs.get("chat_id") for c in caption_calls]
        self.assertIn(333, called_chats)
        self.assertIn(444, called_chats)


if __name__ == "__main__":
    unittest.main()
