# -*- coding: utf-8 -*-
"""
tests/test_redteam_gameplay_behavior.py
Redteam Gameplay, Concurrency, and Bot Navigation Inquisitor Test Suite:
1. Concurrency double-click race condition prevention in _start_blackjack_game.
2. Insufficient funds session slot cleanup in _start_blackjack_game.
3. Exception safety and session release in _start_blackjack_game.
4. Concurrency & atomic balance/item updates in handle_darknet_item_buy.
5. Russian Roulette solo cashout and take synonym handling.
6. Bank deposit callback validation (format, NaN, Inf, negative, overflow).
7. Dead-end navigation resolution (menu_duel in dice duel, heist_hub in launder menu).
8. Auto-snitch unhandled exception resilience in on_snitch_callback_query.
9. PM / DM board_id is None fallback in casino handler.
"""

import sys
import os
import math
import time
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import casino_engine
from common.db_pool import db_transaction, db_lock, get_pool
from common.database import (
    add_user_global_balance,
    get_user_global_balance,
    deduct_user_global_balance,
)
from criminal_syndicate_engine import (
    handle_darknet_item_buy,
    load_user_active_items,
    save_user_active_items,
)
from bank_engine import cb_bank_do_deposit
from dice_duel_engine import (
    get_dice_lobby_keyboard,
    cb_menu_duel_alias,
)
from heist_and_loan_engine import cb_heist_hub
from handlers.message_router import on_snitch_callback_query
from main import (
    _start_blackjack_game,
    cb_casino_handler,
)


@pytest.fixture(autouse=True)
def clean_test_game_state():
    casino_engine.active_bj_sessions.clear()
    casino_engine.active_roulette_sessions.clear()
    casino_engine.user_casino_last_action.clear()
    yield
    casino_engine.active_bj_sessions.clear()
    casino_engine.active_roulette_sessions.clear()
    casino_engine.user_casino_last_action.clear()


# =============================================================================
# 1. BLACKJACK CONCURRENCY & RACE CONDITION DEFENSE
# =============================================================================

@pytest.mark.asyncio
async def test_blackjack_double_click_race_condition(isolated_test_db):
    """
    Simulates rapid double-click on 'Start Blackjack' button.
    Slot reservation must prevent the second click from double-deducting funds
    or corrupting game sessions.
    """
    db = isolated_test_db
    user_id = 999101
    board_id = "b"
    bet = 100

    # User balance is 500
    await add_user_global_balance(db, user_id, board_id, 500.0)

    mock_bot = AsyncMock()
    mock_send_banner = AsyncMock()

    # Mock cooldown check to return True so both racers reach the session_lock simultaneously
    with patch("banner_manager.send_banner_message", mock_send_banner), \
         patch("casino_engine.check_casino_cooldown", return_value=casino_engine.CooldownResult(True, 0.0, "")):
        # Launch 2 simultaneous calls to _start_blackjack_game
        t1 = asyncio.create_task(_start_blackjack_game(mock_bot, chat_id=123, user_id=user_id, board_id=board_id, bet=bet))
        t2 = asyncio.create_task(_start_blackjack_game(mock_bot, chat_id=123, user_id=user_id, board_id=board_id, bet=bet))

        await asyncio.gather(t1, t2)

    # Verify that the user was NOT charged twice (balance is either 400 or natural blackjack payout)
    final_balance = await get_user_global_balance(db, user_id)
    # If standard start: 500 - 100 = 400. If natural BJ (lucky 21 on deal): payout is >= 500.
    # It must NEVER be 300 (double deduction).
    assert final_balance >= 400.0, f"Double deduction detected! Final balance: {final_balance}"

    # Verify that banner warning about active game was called for the rejected racer
    active_warning_called = any(
        "У тебя уже есть активная партия" in str(c) for c in mock_send_banner.call_args_list
    )
    # One of the two must have received the active game warning
    assert active_warning_called, "Rejected double-click racer did not receive active session warning"


@pytest.mark.asyncio
async def test_blackjack_double_click_cooldown_defense(isolated_test_db):
    """
    Simulates rapid double-click under natural conditions (without bypassing cooldown).
    Enforces that casino cooldown intercepts rapid rapid-fire attempts and returns cooldown banner.
    """
    db = isolated_test_db
    user_id = 999109
    board_id = "b"
    bet = 100

    await add_user_global_balance(db, user_id, board_id, 500.0)

    mock_bot = AsyncMock()
    mock_send_banner = AsyncMock()

    with patch("banner_manager.send_banner_message", mock_send_banner):
        t1 = asyncio.create_task(_start_blackjack_game(mock_bot, chat_id=123, user_id=user_id, board_id=board_id, bet=bet))
        t2 = asyncio.create_task(_start_blackjack_game(mock_bot, chat_id=123, user_id=user_id, board_id=board_id, bet=bet))

        await asyncio.gather(t1, t2)

    # Balance deducted at most once
    final_balance = await get_user_global_balance(db, user_id)
    assert final_balance >= 400.0

    # One of the calls was caught either by cooldown or active session
    cooldown_or_session_warned = any(
        "Колода еще тасуется" in str(c) or "У тебя уже есть активная партия" in str(c)
        for c in mock_send_banner.call_args_list
    )
    assert cooldown_or_session_warned


@pytest.mark.asyncio
async def test_blackjack_insufficient_funds_slot_cleanup(isolated_test_db):
    """
    When user has insufficient funds, _start_blackjack_game must pop the
    pre-reserved busy slot from active_bj_sessions so the user is not locked out.
    """
    db = isolated_test_db
    user_id = 999102
    board_id = "b"
    bet = 200

    # User has only 50
    await add_user_global_balance(db, user_id, board_id, 50.0)

    mock_bot = AsyncMock()
    mock_send_banner = AsyncMock()

    with patch("banner_manager.send_banner_message", mock_send_banner):
        await _start_blackjack_game(mock_bot, chat_id=123, user_id=user_id, board_id=board_id, bet=bet)

    # Session slot must be cleanly removed
    assert user_id not in casino_engine.active_bj_sessions
    bal = await get_user_global_balance(db, user_id)
    assert bal == 50.0


@pytest.mark.asyncio
async def test_blackjack_exception_slot_cleanup(isolated_test_db):
    """
    When an unexpected exception occurs inside the game creation,
    the busy slot must be removed to avoid hanging session state.
    """
    db = isolated_test_db
    user_id = 999103
    board_id = "b"
    bet = 100

    await add_user_global_balance(db, user_id, board_id, 1000.0)

    mock_bot = AsyncMock()

    with patch("main.get_user_global_balance", side_effect=RuntimeError("Simulated DB Crash")):
        with pytest.raises(RuntimeError, match="Simulated DB Crash"):
            await _start_blackjack_game(mock_bot, chat_id=123, user_id=user_id, board_id=board_id, bet=bet)

    # Verify session slot was cleaned up
    assert user_id not in casino_engine.active_bj_sessions


# =============================================================================
# 2. CRIMINAL SYNDICATE DARKNET CONCURRENCY & ATOMICITY
# =============================================================================

@pytest.mark.asyncio
async def test_darknet_item_buy_concurrency_insufficient_funds(isolated_test_db):
    """
    User has 500 shekels. Lockpick costs 400 shekels.
    Simultaneous double-click must purchase exactly 1 item and reject the 2nd.
    Balance must be 100 (not negative or double-deducted).
    """
    db = isolated_test_db
    user_id = 999201
    board_id = "b"

    await add_user_global_balance(db, user_id, board_id, 500.0)

    t1 = asyncio.create_task(handle_darknet_item_buy(db, user_id, board_id, "lockpick"))
    t2 = asyncio.create_task(handle_darknet_item_buy(db, user_id, board_id, "lockpick"))

    res1, res2 = await asyncio.gather(t1, t2)

    successes = [r for r in [res1, res2] if r[0] is True]
    failures = [r for r in [res1, res2] if r[0] is False]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}"
    assert "НЕДОСТАТОЧНО ШЕКЕЛЕЙ" in failures[0][1]

    bal = await get_user_global_balance(db, user_id)
    assert bal == 100.0

    items = await load_user_active_items(db, user_id, board_id)
    assert items.get("lockpick") == 1


@pytest.mark.asyncio
async def test_darknet_item_buy_concurrency_atomic_multi_purchase(isolated_test_db):
    """
    User has 1000 shekels. Lockpick costs 400 shekels.
    Concurrent double-click must award BOTH lockpicks (lockpick == 2)
    without lost updates due to read-modify-write races.
    """
    db = isolated_test_db
    user_id = 999202
    board_id = "b"

    await add_user_global_balance(db, user_id, board_id, 1000.0)

    t1 = asyncio.create_task(handle_darknet_item_buy(db, user_id, board_id, "lockpick"))
    t2 = asyncio.create_task(handle_darknet_item_buy(db, user_id, board_id, "lockpick"))

    res1, res2 = await asyncio.gather(t1, t2)

    assert res1[0] is True
    assert res2[0] is True

    bal = await get_user_global_balance(db, user_id)
    assert bal == 200.0

    items = await load_user_active_items(db, user_id, board_id)
    assert items.get("lockpick") == 2


# =============================================================================
# 3. RUSSIAN ROULETTE SOLO CASHOUT & TAKE SYNONYMS
# =============================================================================

@pytest.mark.asyncio
async def test_russian_roulette_cashout_and_take_synonyms(isolated_test_db):
    """
    Validates that both 'cashout' and 'take' actions correctly cash out
    the solo Russian Roulette session and answer callback queries.
    """
    db = isolated_test_db
    user_id = 999301
    board_id = "b"

    await add_user_global_balance(db, user_id, board_id, 1000.0)

    # 1. Test 'cashout' action
    casino_engine.active_roulette_sessions[user_id] = {
        "bet": 200,
        "current_mult": 1.5,
        "current_step": 2,
    }

    cb_cashout = AsyncMock(spec=types.CallbackQuery)
    cb_cashout.from_user = MagicMock(id=user_id)
    cb_cashout.data = "cas:roulette:cashout:200"
    cb_cashout.bot = AsyncMock()
    cb_cashout.message = AsyncMock(caption="Roulette Msg")
    cb_cashout.answer = AsyncMock()

    await cb_casino_handler(cb_cashout, board_id)

    assert user_id not in casino_engine.active_roulette_sessions
    cb_cashout.answer.assert_called_once()
    bal1 = await get_user_global_balance(db, user_id)
    # Net profit: 200 * 1.5 - 200 = 100. Payout: 300. (Plus any tax deduction)
    assert bal1 > 1000.0

    # 2. Test 'take' action
    casino_engine.active_roulette_sessions[user_id] = {
        "bet": 200,
        "current_mult": 2.0,
        "current_step": 3,
    }

    cb_take = AsyncMock(spec=types.CallbackQuery)
    cb_take.from_user = MagicMock(id=user_id)
    cb_take.data = "cas:roulette:take:200"
    cb_take.bot = AsyncMock()
    cb_take.message = AsyncMock(caption="Roulette Msg")
    cb_take.answer = AsyncMock()

    await cb_casino_handler(cb_take, board_id)

    assert user_id not in casino_engine.active_roulette_sessions
    cb_take.answer.assert_called_once()
    bal2 = await get_user_global_balance(db, user_id)
    assert bal2 > bal1


# =============================================================================
# 4. BANK DEPOSIT CALLBACK VALIDATION & BOUNDS
# =============================================================================

@pytest.mark.asyncio
async def test_bank_do_deposit_validation(isolated_test_db):
    """
    Verifies that cb_bank_do_deposit validates data parts, rejecting
    NaN, Inf, negative values, and overflows with alerts while always answering callback.
    """
    user_id = 999401

    invalid_cases = [
        ("bank_do_deposit:sych", "Некорректный формат"),
        ("bank_do_deposit:sych:notanumber", "Некорректная сумма"),
        ("bank_do_deposit:sych:nan", "положительным числом"),
        ("bank_do_deposit:sych:inf", "положительным числом"),
        ("bank_do_deposit:sych:-100", "положительным числом"),
        ("bank_do_deposit:sych:0", "положительным числом"),
        ("bank_do_deposit:sych:2000000000", "Максимальная сумма разового вклада"),
    ]

    for data, err_snippet in invalid_cases:
        cb = AsyncMock(spec=types.CallbackQuery)
        cb.from_user = MagicMock(id=user_id)
        cb.data = data
        cb.answer = AsyncMock()

        await cb_bank_do_deposit(cb, board_id="b")

        cb.answer.assert_called_once()
        call_args = cb.answer.call_args
        msg = call_args[0][0] if call_args[0] else call_args[1].get("text", "")
        alert = call_args[1].get("show_alert", False)

        assert alert is True, f"Expected show_alert=True for {data}"
        assert err_snippet.lower() in msg.lower(), f"Expected '{err_snippet}' in error message for {data}, got '{msg}'"


# =============================================================================
# 5. DEAD-END NAVIGATION RESOLUTION (DUEL & HEIST)
# =============================================================================

@pytest.mark.asyncio
async def test_dice_duel_menu_duel_alias_resolved(isolated_test_db):
    """
    Verifies that the backward-compatibility alias 'menu_duel' is handled,
    answers callback, and edits message to duel lobby without unhandled exception.
    """
    db = isolated_test_db
    user_id = 999501
    await add_user_global_balance(db, user_id, "b", 300.0)

    cb = AsyncMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock(id=user_id)
    cb.data = "menu_duel"
    cb.message = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    await cb_menu_duel_alias(cb)

    cb.answer.assert_called_once()
    cb.message.edit_text.assert_called_once()
    assert "PvP КОСТИ" in cb.message.edit_text.call_args[0][0]


def test_dice_lobby_keyboard_contains_canonical_duel_callback():
    """
    Verifies that get_dice_lobby_keyboard uses the canonical 'cas:menu:duel'
    instead of the unhandled 'menu_duel'.
    """
    kb = get_dice_lobby_keyboard(balance=500, current_bet=100)
    all_callbacks = [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "cas:menu:duel" in all_callbacks
    assert "menu_duel" not in all_callbacks


@pytest.mark.asyncio
async def test_launder_menu_heist_hub_callback_resolved():
    """
    Verifies that 'heist_hub' callback from empty launder card
    is handled by cb_heist_hub, answers callback and routes to cmd_start_heist.
    """
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock(id=999502)
    cb.data = "heist_hub"
    cb.answer = AsyncMock()
    cb.bot = AsyncMock()
    cb.message = AsyncMock()

    with patch("heist_and_loan_engine.cmd_start_heist", new=AsyncMock()) as mock_heist_cmd:
        await cb_heist_hub(cb)
        cb.answer.assert_called_once()
        mock_heist_cmd.assert_called_once()


# =============================================================================
# 6. AUTO-SNITCH UNHANDLED EXCEPTION RESILIENCE
# =============================================================================

@pytest.mark.asyncio
async def test_on_snitch_callback_query_exception_resilience():
    """
    Verifies that on_snitch_callback_query catches any unexpected exception from
    handle_snitch_callback and answers callback with alert, preventing UI spinner freeze.
    """
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock(id=999601)
    cb.data = "snitch:burn:12345:b:999"
    cb.answer = AsyncMock()

    with patch("admin_manager.handle_snitch_callback", side_effect=RuntimeError("Unexpected snitch failure")):
        await on_snitch_callback_query(cb)

    cb.answer.assert_called_once()
    call_args = cb.answer.call_args
    msg = call_args[0][0] if call_args[0] else call_args[1].get("text", "")
    alert = call_args[1].get("show_alert", False)
    assert alert is True
    assert "Автостукач" in msg


# =============================================================================
# 7. PRIVATE MESSAGE (board_id IS None) FALLBACK
# =============================================================================

@pytest.mark.asyncio
async def test_casino_handler_board_id_none_fallback(isolated_test_db):
    """
    When callback is received in PM/DM where board_id is None,
    cb_casino_handler must fallback to 'b' rather than returning early without answering.
    """
    db = isolated_test_db
    user_id = 999701
    await add_user_global_balance(db, user_id, "b", 1000.0)

    cb = AsyncMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock(id=user_id)
    cb.data = "cas:hub"
    cb.message = AsyncMock(caption="Test Caption")
    cb.message.edit_caption = AsyncMock()
    cb.answer = AsyncMock()

    # Pass board_id=None (as occurs in private chat)
    await cb_casino_handler(cb, board_id=None)

    cb.answer.assert_called_once()
    cb.message.edit_caption.assert_called_once()
    caption_text = cb.message.edit_caption.call_args[1].get("caption", "") or cb.message.edit_caption.call_args[0][0]
    assert "ПОДПОЛЬНОЕ КАЗИНО ТГАЧА" in caption_text
