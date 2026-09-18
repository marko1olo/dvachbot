# -*- coding: utf-8 -*-
"""
tests/test_anti_hijacking.py — Verification of message ownership and anti-hijacking guards:
1. /top [🪪 Мой паспорт] rejects taps by other chatters.
2. /top [🧾 Выписка] rejects taps by other chatters.
3. /shop categories and purchases reject taps by other chatters.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import CallbackQuery, Message, User, Chat

from main import (
    _MENU_MESSAGE_OWNERS,
    _record_menu_owner,
    _check_menu_owner,
    cb_prof_card,
    cb_prof_ledger,
    cb_shop_cat_weapons,
    cb_shop_buy,
)

@pytest.fixture(autouse=True)
def clean_owners():
    _MENU_MESSAGE_OWNERS.clear()
    yield
    _MENU_MESSAGE_OWNERS.clear()


@pytest.mark.asyncio
async def test_top_prof_card_hijacking_rejection():
    """Verify other chatters cannot hijack /top with their own passport."""
    chat_id = -100123456
    msg_id = 500
    owner_id = 1111
    hijacker_id = 2222

    _record_menu_owner(chat_id, msg_id, owner_id)

    # Hijacker taps [🪪 Мой паспорт]
    callback = MagicMock(spec=CallbackQuery)
    callback.data = f"prof_card:{owner_id}"
    callback.from_user = User(id=hijacker_id, is_bot=False, first_name="Hijacker")
    callback.message = MagicMock(spec=Message)
    callback.message.chat = MagicMock(id=chat_id)
    callback.message.message_id = msg_id
    callback.answer = AsyncMock()

    await cb_prof_card(callback, board_id="b")

    # Must show alert and reject
    assert callback.answer.call_count == 1
    call_args = callback.answer.call_args
    assert "чужая карточка" in call_args[0][0]
    assert call_args[1].get("show_alert") is True


@pytest.mark.asyncio
async def test_top_prof_card_owner_allowed():
    """Verify owner can view their own passport."""
    chat_id = -100123456
    msg_id = 501
    owner_id = 1111

    _record_menu_owner(chat_id, msg_id, owner_id)

    callback = MagicMock(spec=CallbackQuery)
    callback.data = f"prof_card:{owner_id}"
    callback.from_user = User(id=owner_id, is_bot=False, first_name="Owner")
    callback.message = MagicMock(spec=Message)
    callback.message.chat = MagicMock(id=chat_id)
    callback.message.message_id = msg_id
    callback.answer = AsyncMock()

    with patch("stats_generator.generate_user_stats_card", return_value=(None, "Passport HTML")):
        await cb_prof_card(callback, board_id="b")

    # Owner should get regular loading answer
    assert callback.answer.call_count == 1
    call_args = callback.answer.call_args
    assert "Обновляю" in call_args[0][0]
    assert call_args[1].get("show_alert") is False


@pytest.mark.asyncio
async def test_shop_hijacking_rejection():
    """Verify other chatters cannot interact with or buy from someone else's /shop."""
    chat_id = -100123456
    msg_id = 600
    owner_id = 3333
    hijacker_id = 4444

    _record_menu_owner(chat_id, msg_id, owner_id)

    callback = MagicMock(spec=CallbackQuery)
    callback.data = "shop_cat_weapons"
    callback.from_user = User(id=hijacker_id, is_bot=False, first_name="Sneaky")
    callback.message = MagicMock(spec=Message)
    callback.message.chat = MagicMock(id=chat_id)
    callback.message.message_id = msg_id
    callback.answer = AsyncMock()

    await cb_shop_cat_weapons(callback, board_id="b")

    assert callback.answer.call_count == 1
    call_args = callback.answer.call_args
    assert "чужой магазин" in call_args[0][0]
    assert call_args[1].get("show_alert") is True

    # Test purchase hijacking rejection
    callback.data = "shop_buy_knife"
    callback.answer.reset_mock()
    await cb_shop_buy(callback, board_id="b")

    assert callback.answer.call_count == 1
    call_args = callback.answer.call_args
    assert "чужой магазин" in call_args[0][0]
    assert call_args[1].get("show_alert") is True
