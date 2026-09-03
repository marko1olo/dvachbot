# -*- coding: utf-8 -*-
"""
tests/test_pvp_lobbies_dynamic.py
=================================
Comprehensive test suite verifying Requirement R3:
Dynamic PvP Duel & Game Lobby (/duel, /dice, /ttt, /rr).
- Dynamic stake selector lobbies adapting to player balance (50, 100, 250... /2, x2, 💰 ВА-БАНК)
- Support for direct amount commands (/rr 500, /dice 1000, /duel 250, /ttt 100)
- Confirmation before broadcasting challenge
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from russian_roulette_pvp import (
    cmd_russian_roulette,
    get_rr_lobby_keyboard,
    get_adaptive_rr_bet_presets,
    format_rr_lobby_message,
    MIN_RR_BET,
    MAX_RR_BET,
)
from dice_duel_engine import (
    get_dice_lobby_keyboard,
    get_adaptive_dice_bet_presets,
    format_dice_bet_amount,
    cmd_dice_duel_entry,
    MIN_DICE_BET,
    MAX_DICE_BET,
)
from ttt_engine import get_ttt_lobby_keyboard, cmd_ttt
from common.database import add_user_global_balance


def test_rr_adaptive_bet_presets():
    """Verifies RR presets adapt cleanly across balance tiers."""
    # Low balance
    p_low = get_adaptive_rr_bet_presets(balance=80, current_bet=50)
    assert p_low == [50]

    # Moderate balance (1,500)
    p_med = get_adaptive_rr_bet_presets(balance=1500, current_bet=100)
    assert len(p_med) <= 5
    assert all(p <= 1500 for p in p_med)
    assert 50 in p_med

    # High balance (500,000)
    p_high = get_adaptive_rr_bet_presets(balance=500000, current_bet=100)
    assert len(p_high) <= 5
    assert all(p <= 500000 for p in p_high)


def test_rr_lobby_keyboard_structure():
    """Verifies RR keyboard has preset row, quick modifier row (/2, x2, ВА-БАНК), and confirmation."""
    kb = get_rr_lobby_keyboard(bet=250, balance=5000, target_id=0)
    buttons = kb.inline_keyboard
    assert len(buttons) >= 4

    # Row 0: Challenge Confirmation Button
    confirm_btn = buttons[0][0]
    assert "Бросить вызов" in confirm_btn.text
    assert confirm_btn.callback_data.startswith("rr:create:250")

    # Row 2: Quick Modifiers (/2, x2, 💰 ВА-БАНК)
    ctrl_row = buttons[2]
    ctrl_texts = [b.text for b in ctrl_row]
    assert "/2" in ctrl_texts
    assert "x2" in ctrl_texts
    assert "💰 ВА-БАНК" in ctrl_texts


def test_dice_adaptive_bet_presets():
    """Verifies Dice Duel presets adapt cleanly across balance tiers."""
    p_low = get_adaptive_dice_bet_presets(balance=60, current_bet=50)
    assert p_low == [50]

    p_med = get_adaptive_dice_bet_presets(balance=3000, current_bet=100)
    assert len(p_med) <= 5
    assert all(p <= 3000 for p in p_med)

    p_high = get_adaptive_dice_bet_presets(balance=1000000, current_bet=100)
    assert len(p_high) <= 5
    assert all(p <= 1000000 for p in p_high)


def test_dice_lobby_keyboard_structure():
    """Verifies Dice keyboard has 2d6/3d6 create buttons, presets, modifiers (/2, x2, ВА-БАНК)."""
    kb = get_dice_lobby_keyboard(balance=10000, current_bet=500, target_id=0)
    buttons = kb.inline_keyboard
    assert len(buttons) >= 4

    # Row 0: 2d6 and 3d6 Confirmation Buttons
    row0 = buttons[0]
    assert "2d6" in row0[0].text
    assert "3d6" in row0[1].text
    assert row0[0].callback_data.startswith("dice_create_fast:2d6:500")
    assert row0[1].callback_data.startswith("dice_create_fast:3d6:500")

    # Row 2: Modifiers
    ctrl_row = buttons[2]
    ctrl_texts = [b.text for b in ctrl_row]
    assert "/2" in ctrl_texts
    assert "x2" in ctrl_texts
    assert "💰 ВА-БАНК" in ctrl_texts


@pytest.mark.asyncio
async def test_rr_command_without_args_opens_lobby(isolated_test_db):
    """Verifies /rr with no arguments opens the dynamic stake selector lobby."""
    db = isolated_test_db
    user_id = 11111
    board_id = "b"

    await add_user_global_balance(db, user_id, board_id, 2500)

    mock_msg = MagicMock()
    mock_msg.from_user.id = user_id
    mock_msg.chat.id = 10001
    mock_msg.text = "/rr"
    mock_msg.caption = None
    mock_msg.reply_to_message = None
    mock_msg.answer = AsyncMock()

    await cmd_russian_roulette(mock_msg, board_id=board_id)

    assert mock_msg.answer.called
    args = mock_msg.answer.call_args
    text = args[0][0]
    reply_markup = args[1].get("reply_markup")

    assert "РУССКАЯ РУЛЕТКА" in text
    assert "Твой баланс" in text
    assert reply_markup is not None
    # Confirmation button present in markup
    assert "Бросить вызов" in reply_markup.inline_keyboard[0][0].text


@pytest.mark.asyncio
async def test_rr_command_with_direct_amount(isolated_test_db):
    """Verifies /rr 500 creates a challenge for 500 shekels."""
    db = isolated_test_db
    user_id = 22222
    board_id = "b"

    await add_user_global_balance(db, user_id, board_id, 5000)

    mock_msg = MagicMock()
    mock_msg.from_user.id = user_id
    mock_msg.chat.id = 20002
    mock_msg.message_id = 101
    mock_msg.text = "/rr 500"
    mock_msg.caption = None
    mock_msg.reply_to_message = None
    mock_msg.answer = AsyncMock()
    mock_msg.bot.send_message = AsyncMock()

    await cmd_russian_roulette(mock_msg, board_id=board_id)

    assert mock_msg.answer.called
    text = mock_msg.answer.call_args[0][0]
    assert "ВЫЗОВ НА СМЕРТЕЛЬНУЮ ДУЭЛЬ" in text
    assert "500 ₪" in text


@pytest.mark.asyncio
async def test_dice_command_without_args_opens_lobby(isolated_test_db):
    """Verifies /dice with no arguments opens the dynamic stake selector lobby."""
    db = isolated_test_db
    user_id = 33333
    board_id = "b"

    await add_user_global_balance(db, user_id, board_id, 4000)

    mock_msg = MagicMock()
    mock_msg.from_user.id = user_id
    mock_msg.chat.id = 30003
    mock_msg.text = "/dice"
    mock_msg.caption = None
    mock_msg.reply_to_message = None
    mock_msg.answer = AsyncMock()

    await cmd_dice_duel_entry(mock_msg, board_id=board_id)

    assert mock_msg.answer.called
    args = mock_msg.answer.call_args
    text = args[0][0]
    reply_markup = args[1].get("reply_markup")

    assert "ДАЙС-ДУЭЛЬ" in text
    assert "Твой баланс" in text
    assert reply_markup is not None
    # 2d6 and 3d6 creation buttons present
    assert "2d6" in reply_markup.inline_keyboard[0][0].text
    assert "3d6" in reply_markup.inline_keyboard[0][1].text


@pytest.mark.asyncio
async def test_dice_command_with_direct_amount(isolated_test_db):
    """Verifies /dice 1000 creates a challenge for 1000 shekels."""
    db = isolated_test_db
    user_id = 44444
    board_id = "b"

    await add_user_global_balance(db, user_id, board_id, 10000)

    mock_msg = MagicMock()
    mock_msg.from_user.id = user_id
    mock_msg.chat.id = 40004
    mock_msg.message_id = 202
    mock_msg.text = "/dice 1000"
    mock_msg.caption = None
    mock_msg.reply_to_message = None
    mock_msg.answer = AsyncMock()

    await cmd_dice_duel_entry(mock_msg, board_id=board_id)

    assert mock_msg.answer.called
    text = mock_msg.answer.call_args[0][0]
    assert "1,000 ₪" in text or "1000" in text
