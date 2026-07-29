import pytest
from unittest.mock import AsyncMock
from aiogram import types
from aiogram.types import InlineKeyboardMarkup
from economy_extension import cmd_work_menu

@pytest.mark.asyncio
async def test_cmd_work_menu_no_board_id():
    message = AsyncMock(spec=types.Message)

    await cmd_work_menu(message)

    message.reply.assert_not_called()
    message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_cmd_work_menu_with_board_id():
    message = AsyncMock(spec=types.Message)
    message.reply = AsyncMock()
    message.delete = AsyncMock()
    board_id = "test_board"

    await cmd_work_menu(message, board_id=board_id)

    # Check that reply was called with correct text and markup
    message.reply.assert_called_once()
    args, kwargs = message.reply.call_args

    assert "Биржа Труда" in args[0]
    assert "Сдать стеклотару" in args[0]
    assert "Продать мать" in args[0]

    kb = kwargs.get("reply_markup")
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].callback_data == "work_bottles"
    assert kb.inline_keyboard[1][0].callback_data == "work_sell_mother"
    assert kwargs.get("parse_mode") == "HTML"

    message.delete.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_work_menu_delete_fails():
    message = AsyncMock(spec=types.Message)
    message.reply = AsyncMock()
    message.delete = AsyncMock(side_effect=Exception("Delete failed"))
    board_id = "test_board"

    # Should not raise exception
    await cmd_work_menu(message, board_id=board_id)

    message.reply.assert_called_once()
    message.delete.assert_called_once()
