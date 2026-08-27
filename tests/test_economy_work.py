# -*- coding: utf-8 -*-
import asyncio
import datetime
import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, User, Chat

import economy_extension
from economy_extension import cmd_work_menu, cb_work_action
import main


class TestEconomyWork(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_conn = await aiosqlite.connect(":memory:")
        await self.db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER,
                board_id TEXT,
                balance REAL DEFAULT 0,
                posts_count INTEGER DEFAULT 0,
                active_items TEXT DEFAULT '{}',
                is_verified_b INTEGER DEFAULT 0,
                last_failed_amount REAL DEFAULT 0,
                custom_prefix TEXT DEFAULT NULL,
                prefix_expires_at REAL DEFAULT 0,
                cursed_until REAL DEFAULT 0,
                PRIMARY KEY (user_id, board_id)
            )
            """
        )
        await self.db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS UserTransactions (
                tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                tx_type TEXT,
                description TEXT,
                created_at REAL
            )
            """
        )
        await self.db_conn.commit()

        self.user_id = 999001
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500, '{}')",
            (self.user_id,)
        )
        await self.db_conn.commit()

    async def asyncTearDown(self):
        await self.db_conn.close()

    def _synthetic_message(self, text: str) -> MagicMock:
        msg = MagicMock(spec=types.Message)
        msg.from_user = MagicMock(spec=types.User)
        msg.from_user.id = self.user_id
        msg.from_user.is_bot = False
        msg.from_user.first_name = "Anon"
        msg.chat = MagicMock(spec=types.Chat)
        msg.chat.id = self.user_id
        msg.message_id = 1
        msg.text = text
        msg.reply = AsyncMock()
        msg.delete = AsyncMock()
        msg.answer = AsyncMock()
        msg.bot = MagicMock()
        msg.bot.send_message = AsyncMock()
        msg.bot.send_photo = AsyncMock()
        return msg

    def _synthetic_callback(self, data: str) -> types.CallbackQuery:
        cb = MagicMock(spec=types.CallbackQuery)
        cb.id = "cb_123"
        cb.data = data
        cb.from_user = MagicMock(spec=types.User)
        cb.from_user.id = self.user_id
        cb.answer = AsyncMock()
        cb.message = MagicMock(spec=types.Message)
        cb.message.photo = None
        cb.message.edit_caption = AsyncMock()
        cb.message.edit_text = AsyncMock()
        return cb

    async def test_cmd_work_menu_no_board_id(self):
        msg = self._synthetic_message("/work")
        with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            await cmd_work_menu(msg, board_id=None)
            mock_banner.assert_not_called()

    async def test_cmd_work_menu_with_board_id(self):
        msg = self._synthetic_message("/work")
        with patch("main.get_pool", return_value=self.db_conn), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            await cmd_work_menu(msg, board_id="b")
            mock_banner.assert_called_once()
            args, kwargs = mock_banner.call_args
            self.assertIn("БИРЖА ТРУДА", kwargs["caption"].upper())

            # Check keyboard has 16 vacancies + side hustles
            markup = kwargs.get("reply_markup")
            self.assertIsInstance(markup, InlineKeyboardMarkup)
            all_callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
            self.assertIn("work_bottles", all_callbacks)
            self.assertIn("work_sell_mother", all_callbacks)
            self.assertIn("work_do_bottles", all_callbacks)
            self.assertIn("work_do_matrix_architect", all_callbacks)

    async def test_side_hustle_bottles_flow(self):
        # 1. First bottles collection succeeds
        cb = self._synthetic_callback("work_bottles")
        with patch("economy_extension.get_pool", return_value=self.db_conn), \
             patch("main.get_pool", return_value=self.db_conn):
            await cb_work_action(cb, board_id="b")
            self.assertTrue(cb.answer.called)
            self.assertIn("сдал бутылки", cb.answer.call_args[0][0].lower())

        # 2. Second bottles collection within 24h triggers cooldown
        cb2 = self._synthetic_callback("work_bottles")
        with patch("economy_extension.get_pool", return_value=self.db_conn), \
             patch("main.get_pool", return_value=self.db_conn):
            await cb_work_action(cb2, board_id="b")
            self.assertTrue(cb2.answer.called)
            self.assertIn("закрыты", cb2.answer.call_args[0][0].lower())

    async def test_side_hustle_sell_mother_flow(self):
        # 1. First mother sale awards 8000 shekels
        cb = self._synthetic_callback("work_sell_mother")
        with patch("economy_extension.get_pool", return_value=self.db_conn), \
             patch("main.get_pool", return_value=self.db_conn):
            await cb_work_action(cb, board_id="b")
            self.assertTrue(cb.answer.called)
            self.assertIn("8000", cb.answer.call_args[0][0])

        # 2. Second mother sale rejected
        cb2 = self._synthetic_callback("work_sell_mother")
        with patch("economy_extension.get_pool", return_value=self.db_conn), \
             patch("main.get_pool", return_value=self.db_conn):
            await cb_work_action(cb2, board_id="b")
            self.assertTrue(cb2.answer.called)
            self.assertIn("уже продал мать", cb2.answer.call_args[0][0].lower())


if __name__ == "__main__":
    unittest.main()
