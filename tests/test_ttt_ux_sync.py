import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from ttt_engine import (
    TicTacToeGame,
    active_ttt_games,
    user_active_ttt_session,
    cmd_ttt,
    render_game_text,
    get_ttt_game_keyboard,
    TURN_TIMEOUT_SECONDS,
)

@pytest.mark.asyncio
async def test_ttt_accept_already_active_game():
    # Setup active game for user 1001 and 1002
    gid = "test_active_gid_99"
    game = TicTacToeGame(
        game_id=gid,
        board_id="b",
        chat_id=-10012345,
        challenger_id=1001,
        opponent_id=1002,
        bet=500,
        status="active",
        current_turn=1002,
    )
    active_ttt_games[gid] = game
    user_active_ttt_session[1001] = gid
    user_active_ttt_session[1002] = gid

    msg = MagicMock()
    msg.from_user.id = 1002
    msg.chat.id = 1002
    msg.text = "/ttt accept"
    msg.answer = AsyncMock()
    msg.reply_to_message = None

    try:
        await cmd_ttt(msg, board_id="b")
        msg.answer.assert_called_once()
        call_args = msg.answer.call_args[0][0]
        assert "Партия уже идёт!" in call_args
        assert "Твой ход!" in call_args
    finally:
        active_ttt_games.pop(gid, None)
        user_active_ttt_session.pop(1001, None)
        user_active_ttt_session.pop(1002, None)


@pytest.mark.asyncio
async def test_ttt_accept_sends_board_to_acceptor():
    # Setup waiting challenge
    gid = "test_waiting_gid_88"
    game = TicTacToeGame(
        game_id=gid,
        board_id="b",
        chat_id=-10012345,
        challenger_id=2001,
        bet=200,
        status="waiting",
        msg_id=777,
    )
    active_ttt_games[gid] = game
    user_active_ttt_session[2001] = gid

    msg = MagicMock()
    msg.from_user.id = 2002
    msg.chat.id = 2002
    msg.text = "/ttt accept"
    msg.answer = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.edit_message_text = AsyncMock()
    msg.reply_to_message = None

    async def mock_accept(bot, gid, uid):
        game.status = "active"
        game.opponent_id = uid
        game.current_turn = 2001
        return True, "OK", game

    with patch("ttt_engine.accept_ttt_challenge", side_effect=mock_accept):

        try:
            await cmd_ttt(msg, board_id="b")
            # Challenger's original message was edited
            msg.bot.edit_message_text.assert_called_once()
            # Acceptor's chat received the board
            msg.answer.assert_called_once()
            call_text = msg.answer.call_args[1].get("text", msg.answer.call_args[0][0])
            assert "Вызов принят!" in call_text
        finally:
            active_ttt_games.pop(gid, None)
            user_active_ttt_session.pop(2001, None)
            user_active_ttt_session.pop(2002, None)
