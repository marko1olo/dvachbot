import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import json
import time
from aiogram import types

from economy_extension import cmd_rob

@pytest.fixture
def mock_message():
    msg = AsyncMock(spec=types.Message)
    msg.from_user = MagicMock()
    msg.from_user.id = 123
    msg.reply = AsyncMock()
    msg.bot = AsyncMock()
    msg.bot.send_message = AsyncMock()
    msg.delete = AsyncMock()
    return msg

class AsyncContextManagerMock:
    def __init__(self, fetchone_return_value):
        self.cursor = AsyncMock()
        self.cursor.fetchone.return_value = fetchone_return_value

    def __await__(self):
        # Allow being awaited like a standard coroutine
        async def mock_coro():
            return self.cursor
        return mock_coro().__await__()

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, exc_type, exc, tb):
        pass

class DummyLock:
    async def __aenter__(self):
        pass
    async def __aexit__(self, exc_type, exc, tb):
        pass

@pytest.fixture
def patch_db_lock():
    with patch('economy_extension.db_lock', new=DummyLock()):
        yield

@pytest.mark.asyncio
async def test_cmd_rob_no_board_id(mock_message):
    await cmd_rob(mock_message, board_id=None)
    mock_message.reply.assert_not_called()

@pytest.mark.asyncio
@patch('economy_extension.get_reply_target', return_value=None)
async def test_cmd_rob_no_target(mock_get_target, mock_message):
    await cmd_rob(mock_message, board_id="test_board")
    mock_message.reply.assert_called_with("Нужно сделать Reply на пост жертвы!")

@pytest.mark.asyncio
@patch('economy_extension.get_reply_target', return_value=123)
async def test_cmd_rob_self(mock_get_target, mock_message):
    await cmd_rob(mock_message, board_id="test_board")
    mock_message.reply.assert_called_with("Нельзя ограбить самого себя.")

@pytest.mark.asyncio
@patch('economy_extension.get_reply_target', return_value=456)
@patch('economy_extension.get_pool')
async def test_cmd_rob_no_knife(mock_get_pool, mock_get_target, mock_message, patch_db_lock):
    db_mock = MagicMock()
    # User has empty active_items
    db_mock.execute.return_value = AsyncContextManagerMock(fetchone_return_value=("{}",))
    mock_get_pool.return_value = db_mock

    await cmd_rob(mock_message, board_id="test_board")
    mock_message.reply.assert_called_with("У тебя нет заточки! Купи её в /shop.")

@pytest.mark.asyncio
@patch('economy_extension.get_reply_target', return_value=456)
@patch('economy_extension.get_pool')
async def test_cmd_rob_tinfoil_hat(mock_get_pool, mock_get_target, mock_message, patch_db_lock):
    db_mock = MagicMock()

    def side_effect(query, args):
        if query.startswith("SELECT active_items FROM Users WHERE user_id = ?"):
            # attacker
            if args[0] == 123:
                return AsyncContextManagerMock(fetchone_return_value=(json.dumps({"knife_gun": True}),))
        elif query.startswith("SELECT balance, active_items FROM Users WHERE user_id = ?"):
            # target
            if args[0] == 456:
                return AsyncContextManagerMock(fetchone_return_value=(1000, json.dumps({"tinfoil_hat": int(time.time()) + 1000})))
        return AsyncContextManagerMock(fetchone_return_value=None)

    db_mock.execute.side_effect = side_effect
    mock_get_pool.return_value = db_mock
    db_mock.commit = AsyncMock()

    await cmd_rob(mock_message, board_id="test_board")

    # Check that bot send message was called indicating tinfoil hat blocked it
    mock_message.bot.send_message.assert_any_call(
        123, "🔪 Твоя заточка сломалась о Шапочку из фольги жертвы! Ограбление не удалось.", parse_mode="HTML"
    )

@pytest.mark.asyncio
@patch('economy_extension.get_reply_target', return_value=456)
@patch('economy_extension.get_pool')
async def test_cmd_rob_poor_target(mock_get_pool, mock_get_target, mock_message, patch_db_lock):
    db_mock = MagicMock()

    def side_effect(query, args):
        if query.startswith("SELECT active_items FROM Users WHERE user_id = ?"):
            # attacker
            if args[0] == 123:
                return AsyncContextManagerMock(fetchone_return_value=(json.dumps({"knife_gun": True}),))
        elif query.startswith("SELECT balance, active_items FROM Users WHERE user_id = ?"):
            # target
            if args[0] == 456:
                # balance 40 (less than 50)
                return AsyncContextManagerMock(fetchone_return_value=(40, "{}"))
        return AsyncContextManagerMock(fetchone_return_value=None)

    db_mock.execute.side_effect = side_effect
    db_mock.commit = AsyncMock()
    mock_get_pool.return_value = db_mock

    await cmd_rob(mock_message, board_id="test_board")

    mock_message.bot.send_message.assert_any_call(
        123, "🔪 Ты приставил заточку, но у жертвы в карманах только дыры... Грабить нечего.", parse_mode="HTML"
    )

@pytest.mark.asyncio
@patch('economy_extension.get_reply_target', return_value=456)
@patch('economy_extension.get_pool')
@patch('economy_extension.random.uniform', return_value=0.2)
async def test_cmd_rob_success(mock_uniform, mock_get_pool, mock_get_target, mock_message, patch_db_lock):
    db_mock = MagicMock()

    def side_effect(query, args):
        if query.startswith("SELECT active_items FROM Users WHERE user_id = ?"):
            # attacker
            if args[0] == 123:
                return AsyncContextManagerMock(fetchone_return_value=(json.dumps({"knife_gun": True}),))
        elif query.startswith("SELECT balance, active_items FROM Users WHERE user_id = ?"):
            # target
            if args[0] == 456:
                # balance 500
                return AsyncContextManagerMock(fetchone_return_value=(500, "{}"))
        return AsyncContextManagerMock(fetchone_return_value=None)

    db_mock.execute.side_effect = side_effect
    db_mock.commit = AsyncMock()
    mock_get_pool.return_value = db_mock

    await cmd_rob(mock_message, board_id="test_board")

    # 20% of 500 is 100
    mock_message.bot.send_message.assert_any_call(
        456, f"🔪 В подворотне тебя пырнул Анон <code>123</code> и отобрал <b>100 Шекелей</b>!", parse_mode="HTML"
    )
    mock_message.bot.send_message.assert_any_call(
        123, f"🔪 Ограбление прошло успешно! Ты отжал у лоха <code>456</code> <b>100 Шекелей</b>.", parse_mode="HTML"
    )
