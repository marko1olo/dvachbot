import asyncio
import datetime
asyncio.set_event_loop(asyncio.new_event_loop())

import unittest
from unittest.mock import AsyncMock

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, User, Chat

from economy_extension import cmd_work_menu


class TestEconomyWork(unittest.IsolatedAsyncioTestCase):
    def _synthetic_message(self, text: str) -> types.Message:
        msg = types.Message(
            message_id=1,
            date=datetime.datetime.now(datetime.timezone.utc),
            chat=Chat(id=1, type="private"),
            from_user=User(id=1, is_bot=False, first_name="A"),
            text=text,
        )
        # Mock methods on Pydantic model
        object.__setattr__(msg, 'reply', AsyncMock())
        object.__setattr__(msg, 'delete', AsyncMock())
        return msg

    async def test_cmd_work_menu_no_board_id(self):
        msg = self._synthetic_message("/work")

        await cmd_work_menu(msg, board_id=None)

        msg.reply.assert_not_called()
        msg.delete.assert_not_called()

    async def test_cmd_work_menu_with_board_id(self):
        msg = self._synthetic_message("/work")

        await cmd_work_menu(msg, board_id="b")

        msg.reply.assert_called_once()
        args, kwargs = msg.reply.call_args

        self.assertIn("Биржа Труда", args[0])
        self.assertIn("Сдать стеклотару", args[0])
        self.assertIn("Продать мать", args[0])

        markup = kwargs.get("reply_markup")
        self.assertIsInstance(markup, InlineKeyboardMarkup)
        self.assertEqual(len(markup.inline_keyboard), 2)

        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "work_bottles")
        self.assertEqual(markup.inline_keyboard[1][0].callback_data, "work_sell_mother")

        msg.delete.assert_called_once()

    async def test_cmd_work_menu_delete_fails(self):
        msg = self._synthetic_message("/work")
        msg.delete.side_effect = Exception("delete failed")

        # Should not raise exception
        await cmd_work_menu(msg, board_id="b")

        msg.reply.assert_called_once()
        msg.delete.assert_called_once()
