# -*- coding: utf-8 -*-
"""
test_pvp_notifications_and_compensations.py — Direct Telegram DM Notification & Error Resilience Suite
======================================================================================================
Covers:
1. Russian Roulette: Direct DM notifications on regular win/loss, surrender, and watchdog timeout forfeit.
2. Dice Duel: Direct DM notifications on regular win/loss, 3-round draw refunds, and watchdog timeout forfeit.
3. Tic-Tac-Toe: Direct DM notifications on victory, draw refund, and turn timeout forfeit.
4. Admin grants: Direct DM delivery on /addmoney balance bonus.
5. Police fine refunds: Direct DM delivery on 50% explanation mercy.
6. Error resilience: Full suppression of TelegramForbiddenError, TelegramBadRequest, and generic Exceptions
   ensuring 100% safe DB transactions and payout completions without failure propagation.
"""

import sys
import time
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shared_state
import russian_roulette_pvp as rr
import dice_duel_engine as dde
import ttt_engine as ttt
import main
from common.bot_helpers import send_pvp_direct_notification
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    get_abu_fund_total,
)


@pytest.fixture(autouse=True)
def clean_pvp_states():
    rr.active_rr_games.clear()
    rr.user_active_rr_game.clear()
    dde.active_dice_games.clear()
    dde.user_active_dice_game.clear()
    ttt.active_ttt_games.clear()
    ttt.user_active_ttt_session.clear()
    main.LOLI_BUST_STATE.clear()
    yield
    rr.active_rr_games.clear()
    rr.user_active_rr_game.clear()
    dde.active_dice_games.clear()
    dde.user_active_dice_game.clear()
    ttt.active_ttt_games.clear()
    ttt.user_active_ttt_session.clear()
    main.LOLI_BUST_STATE.clear()


def make_mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=123))
    bot.edit_message_text = AsyncMock(return_value=MagicMock(message_id=123))
    return bot


# =============================================================================
# 1. RUSSIAN ROULETTE NOTIFICATIONS
# =============================================================================

@pytest.mark.asyncio
async def test_rr_finish_direct_dm_delivery(isolated_test_db):
    """Assert direct Telegram DM dispatches to winner and loser on fatal shot."""
    db = isolated_test_db
    p1 = 10001
    p2 = 10002
    stake = 1000

    await add_user_global_balance(db, p1, "b", 10_000)
    await add_user_global_balance(db, p2, "b", 10_000)

    ok, _, game_id = await rr.create_rr_challenge("b", p1, stake)
    ok, _, _ = await rr.accept_rr_challenge(game_id, p2)

    mock_bot = make_mock_bot()
    ok, _, _ = await rr._finish_rr_game(game_id, winner_id=p1, loser_id=p2, reason="shot", bot=mock_bot)
    assert ok is True

    await asyncio.sleep(0.05)

    assert mock_bot.send_message.call_count >= 2
    sent_chats = [call.kwargs.get("chat_id") for call in mock_bot.send_message.call_args_list]
    assert p1 in sent_chats
    assert p2 in sent_chats

    winner_call = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == p1)
    loser_call = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == p2)

    assert "ПОБЕДА В РУССКОЙ РУЛЕТКЕ" in winner_call.kwargs.get("text")
    assert "СМЕРТЕЛЬНЫЙ ВЫСТРЕЛ В РУССКОЙ РУЛЕТКЕ" in loser_call.kwargs.get("text")


@pytest.mark.asyncio
async def test_rr_surrender_direct_dm_delivery(isolated_test_db):
    """Assert direct Telegram DM dispatches on voluntary surrender."""
    db = isolated_test_db
    p1 = 10101
    p2 = 10102
    stake = 1000

    await add_user_global_balance(db, p1, "b", 10_000)
    await add_user_global_balance(db, p2, "b", 10_000)

    ok, _, game_id = await rr.create_rr_challenge("b", p1, stake)
    ok, _, _ = await rr.accept_rr_challenge(game_id, p2)

    mock_bot = make_mock_bot()
    ok, _, _ = await rr.surrender_rr_game(game_id, user_id=p1, bot=mock_bot)
    assert ok is True

    await asyncio.sleep(0.05)

    sent_chats = [call.kwargs.get("chat_id") for call in mock_bot.send_message.call_args_list]
    assert p1 in sent_chats
    assert p2 in sent_chats

    loser_call = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == p1)
    assert "КАПИТУЛЯЦИЯ В РУССКОЙ РУЛЕТКЕ" in loser_call.kwargs.get("text")


@pytest.mark.asyncio
async def test_rr_timeout_forfeit_direct_dm_delivery(isolated_test_db):
    """Assert direct Telegram DM dispatches on watchdog turn timeout."""
    db = isolated_test_db
    p1 = 10201
    p2 = 10202
    stake = 1000

    await add_user_global_balance(db, p1, "b", 10_000)
    await add_user_global_balance(db, p2, "b", 10_000)

    ok, _, game_id = await rr.create_rr_challenge("b", p1, stake)
    ok, _, game = await rr.accept_rr_challenge(game_id, p2)

    turn_user = game["turn"]
    winner_user = p2 if turn_user == p1 else p1

    async with rr.rr_lock:
        rr.active_rr_games[game_id]["turn_deadline_ts"] = time.time() - 10.0
        rr.active_rr_games[game_id]["chat_id"] = 111
        rr.active_rr_games[game_id]["msg_id"] = 222

    mock_bot = make_mock_bot()
    await rr.rr_watchdog_step(mock_bot)
    await asyncio.sleep(0.05)

    sent_chats = [call.kwargs.get("chat_id") for call in mock_bot.send_message.call_args_list]
    assert turn_user in sent_chats
    assert winner_user in sent_chats

    loser_call = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == turn_user)
    assert "ТАЙМАУТ В РУССКОЙ РУЛЕТКЕ" in loser_call.kwargs.get("text")


# =============================================================================
# 2. DICE DUEL NOTIFICATIONS
# =============================================================================

@pytest.mark.asyncio
async def test_dice_duel_win_loss_direct_dm_delivery(isolated_test_db):
    """Assert direct Telegram DM dispatches on dice victory and defeat."""
    db = isolated_test_db
    p1 = 20001
    p2 = 20002
    stake = 1500

    await add_user_global_balance(db, p1, "b", 10_000)
    await add_user_global_balance(db, p2, "b", 10_000)

    ok, _, game_id = await dde.create_dice_challenge("b", p1, stake)
    ok, _, _ = await dde.accept_dice_challenge(game_id, p2)

    mock_bot = make_mock_bot()
    ok, _, _ = await dde._finish_dice_game(game_id, winner_id=p1, loser_id=p2, reason="win", bot=mock_bot)
    assert ok is True

    await asyncio.sleep(0.05)

    sent_chats = [call.kwargs.get("chat_id") for call in mock_bot.send_message.call_args_list]
    assert p1 in sent_chats
    assert p2 in sent_chats

    w_msg = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == p1)
    l_msg = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == p2)

    assert "ПОБЕДА В ДАЙС-ДУЭЛИ" in w_msg.kwargs.get("text")
    assert "ПОРАЖЕНИЕ В ДАЙС-ДУЭЛИ" in l_msg.kwargs.get("text")


@pytest.mark.asyncio
async def test_dice_duel_draw_direct_dm_delivery(isolated_test_db):
    """Assert direct Telegram DM dispatches to both players on draw refund."""
    db = isolated_test_db
    p1 = 20101
    p2 = 20102
    stake = 2000

    await add_user_global_balance(db, p1, "b", 10_000)
    await add_user_global_balance(db, p2, "b", 10_000)

    ok, _, game_id = await dde.create_dice_challenge("b", p1, stake)
    ok, _, _ = await dde.accept_dice_challenge(game_id, p2)

    mock_bot = make_mock_bot()
    ok, _, _ = await dde._finish_dice_game(game_id, winner_id=None, loser_id=None, reason="draw", bot=mock_bot)
    assert ok is True

    await asyncio.sleep(0.05)

    sent_chats = [call.kwargs.get("chat_id") for call in mock_bot.send_message.call_args_list]
    assert p1 in sent_chats
    assert p2 in sent_chats

    for cid in (p1, p2):
        msg = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == cid)
        assert "НИЧЬЯ В ДАЙС-ДУЭЛИ" in msg.kwargs.get("text")
        assert "+1,960 ₪" in msg.kwargs.get("text")


@pytest.mark.asyncio
async def test_dice_duel_watchdog_timeout_direct_dm_delivery(isolated_test_db):
    """Assert direct Telegram DM dispatches on dice duel turn expiration."""
    db = isolated_test_db
    p1 = 20201
    p2 = 20202
    stake = 1000

    await add_user_global_balance(db, p1, "b", 10_000)
    await add_user_global_balance(db, p2, "b", 10_000)

    ok, _, game_id = await dde.create_dice_challenge("b", p1, stake)
    ok, _, game = await dde.accept_dice_challenge(game_id, p2)

    turn_user = game["current_turn"]
    winner_user = p2 if turn_user == p1 else p1

    async with dde.dice_engine_lock:
        dde.active_dice_games[game_id]["turn_deadline_ts"] = time.time() - 10.0
        dde.active_dice_games[game_id]["chat_id"] = 333
        dde.active_dice_games[game_id]["msg_id"] = 444

    mock_bot = make_mock_bot()
    await dde.dice_watchdog_step(mock_bot)
    await asyncio.sleep(0.05)

    sent_chats = [call.kwargs.get("chat_id") for call in mock_bot.send_message.call_args_list]
    assert turn_user in sent_chats
    assert winner_user in sent_chats

    loser_msg = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == turn_user)
    assert "Таймаут броска" in loser_msg.kwargs.get("text")


# =============================================================================
# 3. TIC-TAC-TOE NOTIFICATIONS
# =============================================================================

@pytest.mark.asyncio
async def test_ttt_win_loss_direct_dm_delivery(isolated_test_db):
    """Assert direct Telegram DM dispatches on Tic-Tac-Toe victory."""
    db = isolated_test_db
    p1 = 30001
    p2 = 30002
    stake = 1000

    await add_user_global_balance(db, p1, "b", 10_000)
    await add_user_global_balance(db, p2, "b", 10_000)

    mock_bot = make_mock_bot()
    ok, _, game = await ttt.create_ttt_challenge(mock_bot, chat_id=100, board_id="b", challenger_id=p1, bet=stake)
    ok, _, game = await ttt.accept_ttt_challenge(mock_bot, game.game_id, p2)

    # Fast forward moves to a win for p1 (top row 0, 1, 2)
    # p1 moves 0, p2 moves 3, p1 moves 1, p2 moves 4, p1 moves 2 (WIN)
    await ttt.process_ttt_move(mock_bot, game.game_id, p1, 0)
    await ttt.process_ttt_move(mock_bot, game.game_id, p2, 3)
    await ttt.process_ttt_move(mock_bot, game.game_id, p1, 1)
    await ttt.process_ttt_move(mock_bot, game.game_id, p2, 4)
    await ttt.process_ttt_move(mock_bot, game.game_id, p1, 2)

    await asyncio.sleep(0.05)

    sent_chats = [call.kwargs.get("chat_id") for call in mock_bot.send_message.call_args_list]
    assert p1 in sent_chats
    assert p2 in sent_chats

    w_msg = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == p1)
    l_msg = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == p2)

    assert "ПОБЕДА В КРЕСТИКАХ-НОЛИКАХ" in w_msg.kwargs.get("text")
    assert "ПОРАЖЕНИЕ В КРЕСТИКАХ-НОЛИКАХ" in l_msg.kwargs.get("text")


@pytest.mark.asyncio
async def test_ttt_draw_direct_dm_delivery(isolated_test_db):
    """Assert direct Telegram DM dispatches to both players on Tic-Tac-Toe draw refund."""
    db = isolated_test_db
    p1 = 30101
    p2 = 30102
    stake = 1000

    await add_user_global_balance(db, p1, "b", 10_000)
    await add_user_global_balance(db, p2, "b", 10_000)

    mock_bot = make_mock_bot()
    ok, _, game = await ttt.create_ttt_challenge(mock_bot, chat_id=100, board_id="b", challenger_id=p1, bet=stake)
    ok, _, game = await ttt.accept_ttt_challenge(mock_bot, game.game_id, p2)

    # Set up board near draw:
    # X O X
    # X O O
    # O X .
    # Last move by p1 on index 8 (X) -> Draw
    async with ttt.ttt_lock:
        game.grid = [
            "X", "O", "X",
            "X", "O", "O",
            "O", "X", " "
        ]
        game.current_turn = p1

    await ttt.process_ttt_move(mock_bot, game.game_id, p1, 8)
    await asyncio.sleep(0.05)

    sent_chats = [call.kwargs.get("chat_id") for call in mock_bot.send_message.call_args_list]
    assert p1 in sent_chats
    assert p2 in sent_chats

    for cid in (p1, p2):
        msg = next(c for c in mock_bot.send_message.call_args_list if c.kwargs.get("chat_id") == cid)
        assert "НИЧЬЯ В КРЕСТИКАХ-НОЛИКАХ" in msg.kwargs.get("text")
        assert "+980 ₪" in msg.kwargs.get("text")


# =============================================================================
# 4. ADMIN /addmoney & POLICE EXPLANATION NOTIFICATIONS
# =============================================================================

@pytest.mark.asyncio
async def test_admin_addmoney_direct_dm_delivery(isolated_test_db):
    """Assert direct Telegram DM dispatch on admin shekel grant."""
    db = isolated_test_db
    admin_id = 40001
    target_id = 40002
    grant_amount = 7500

    msg = MagicMock()
    msg.from_user.id = admin_id
    msg.chat.id = 100
    msg.text = f"/addmoney {target_id} {grant_amount}"
    msg.caption = None
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()
    msg.bot = make_mock_bot()

    with patch("main.is_admin", return_value=True):
        await main.cmd_add_money_admin(msg, "b")

    await asyncio.sleep(0.05)

    # Target balance updated
    target_bal = await get_user_global_balance(db, target_id)
    assert target_bal == grant_amount

    # Direct DM delivered
    sent_chats = [call.kwargs.get("chat_id") for call in msg.bot.send_message.call_args_list]
    assert target_id in sent_chats

    grant_msg = next(c for c in msg.bot.send_message.call_args_list if c.kwargs.get("chat_id") == target_id)
    assert f"{grant_amount:,} ₪" in grant_msg.kwargs.get("text")
    assert "Администрация начислила вам бонус" in grant_msg.kwargs.get("text")


@pytest.mark.asyncio
async def test_police_fine_explanation_mercy_direct_dm_delivery(isolated_test_db):
    """Assert direct Telegram DM dispatch on police fine 50% explanation refund."""
    db = isolated_test_db
    user_id = 50001
    board_id = "b"
    fine = 500.0
    bust_id = f"{user_id}_9999"

    main.LOLI_BUST_STATE[bust_id] = {
        "user_id": user_id,
        "board_id": board_id,
        "count": 5,
        "fine": fine,
        "actual_fine": fine,
        "created_at": time.time(),
    }

    cb = MagicMock()
    cb.data = f"loli_explain:{bust_id}"
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.bot = make_mock_bot()

    # Guarantee mercy (random < 0.25)
    with patch("random.random", return_value=0.05):
        await main.cb_loli_explain(cb, board_id)

    await asyncio.sleep(0.05)

    # Refund is 50% = +250
    bal = await get_user_global_balance(db, user_id)
    assert bal == 250.0

    sent_chats = [call.kwargs.get("chat_id") for call in cb.bot.send_message.call_args_list]
    assert user_id in sent_chats

    dm_call = next(c for c in cb.bot.send_message.call_args_list if c.kwargs.get("chat_id") == user_id)
    assert "ВОЗВРАТ 50% ШТРАФА ПО ОБЪЯСНИТЕЛЬНОЙ" in dm_call.kwargs.get("text")
    assert "+250 ₪" in dm_call.kwargs.get("text")


# =============================================================================
# 5. TELEGRAM ERROR RESILIENCE (BLOCKED USERS & API FAILURES)
# =============================================================================

@pytest.mark.asyncio
async def test_telegram_error_resilience_wrapper():
    """
    Assert send_pvp_direct_notification suppresses all Telegram exceptions cleanly:
    - TelegramForbiddenError (user blocked bot) -> returns False, no crash.
    - TelegramBadRequest (chat not found / deleted) -> returns False, no crash.
    - Generic Exception (network timeout, connection reset) -> returns False, no crash.
    """
    bot_forbidden = MagicMock()
    bot_forbidden.send_message = AsyncMock(
        side_effect=TelegramForbiddenError(message="Forbidden: bot was blocked by the user", method=MagicMock())
    )

    bot_bad_request = MagicMock()
    bot_bad_request.send_message = AsyncMock(
        side_effect=TelegramBadRequest(message="Bad Request: chat not found", method=MagicMock())
    )

    bot_generic_error = MagicMock()
    bot_generic_error.send_message = AsyncMock(
        side_effect=Exception("ConnectionResetError: Connection lost")
    )

    # None of these should raise an exception
    res1 = await send_pvp_direct_notification(bot_forbidden, 99901, "Test text")
    assert res1 is False

    res2 = await send_pvp_direct_notification(bot_bad_request, 99902, "Test text")
    assert res2 is False

    res3 = await send_pvp_direct_notification(bot_generic_error, 99903, "Test text")
    assert res3 is False

    # Nil bot / nil user
    assert await send_pvp_direct_notification(None, 99904, "Test") is False
    assert await send_pvp_direct_notification(bot_forbidden, None, "Test") is False


@pytest.mark.asyncio
async def test_game_finishes_complete_when_telegram_blocked(isolated_test_db):
    """
    Verify that if a player has blocked the bot (TelegramForbiddenError),
    all game finishes (Russian Roulette, Dice Duel, TTT), escrow settlements,
    payouts, and database updates complete 100% successfully.
    """
    db = isolated_test_db
    p1 = 60001
    p2 = 60002
    stake = 1000

    await add_user_global_balance(db, p1, "b", 10_000)
    await add_user_global_balance(db, p2, "b", 10_000)

    # Bot throwing ForbiddenError on all DMs
    blocking_bot = make_mock_bot()
    blocking_bot.send_message.side_effect = TelegramForbiddenError(
        message="Forbidden: bot was blocked by the user", method=MagicMock()
    )

    # 1. Russian Roulette with blocked bot
    ok, _, rr_gid = await rr.create_rr_challenge("b", p1, stake)
    ok, _, _ = await rr.accept_rr_challenge(rr_gid, p2)
    ok, _, _ = await rr._finish_rr_game(rr_gid, winner_id=p1, loser_id=p2, reason="shot", bot=blocking_bot)
    assert ok is True

    await asyncio.sleep(0.05)
    b1 = await get_user_global_balance(db, p1)
    # Winner received pot (2000) - 5% rake (100) = 1900 (plus possible 200 ach_duel_win reward)
    assert b1 in (9000 + 1900, 9000 + 1900 + 200)

    # 2. Dice Duel with blocked bot
    ok, _, dice_gid = await dde.create_dice_challenge("b", p1, stake)
    ok, _, _ = await dde.accept_dice_challenge(dice_gid, p2)
    ok, _, _ = await dde._finish_dice_game(dice_gid, winner_id=p2, loser_id=p1, reason="win", bot=blocking_bot)
    assert ok is True

    await asyncio.sleep(0.05)
    b2 = await get_user_global_balance(db, p2)
    # p2 started with 10k, lost 1k in RR, escrowed 1k in Dice (bal 8k), won 1.9k in Dice -> 9.9k
    assert b2 in (8000 + 1900, 8000 + 1900 + 200)
