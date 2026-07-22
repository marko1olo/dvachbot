import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json
import time

from economy_extension import cmd_curse

@pytest.fixture
def mock_message():
    msg = AsyncMock()
    msg.from_user.id = 123
    msg.reply = AsyncMock()
    msg.bot.send_message = AsyncMock()
    msg.delete = AsyncMock()
    return msg

class MockCursor:
    def __init__(self):
        self.fetchone = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class MockDB:
    def __init__(self, cursor):
        self.cursor = cursor
        self.execute_mock = MagicMock()
        self.commit = AsyncMock()

    def execute(self, *args, **kwargs):
        self.execute_mock(*args, **kwargs)

        class ExecuteResult:
            def __init__(self, parent_cursor):
                self.parent_cursor = parent_cursor

            def __await__(self):
                async def _coro():
                    return self.parent_cursor
                return _coro().__await__()

            async def __aenter__(self):
                return self.parent_cursor

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return ExecuteResult(self.cursor)

@pytest.fixture
def mock_db():
    cursor = MockCursor()
    db = MockDB(cursor)
    return db, cursor

@pytest.fixture
def mock_get_pool(mock_db):
    db, _ = mock_db
    with patch("economy_extension.get_pool", return_value=db) as mock:
        yield mock

@pytest.fixture
def mock_get_reply_target():
    with patch("economy_extension.get_reply_target", new_callable=AsyncMock) as mock:
        yield mock

@pytest.fixture
def mock_db_lock():
    with patch("economy_extension.db_lock", new_callable=AsyncMock) as mock:
        mock.__aenter__.return_value = None
        mock.__aexit__.return_value = None
        yield mock

@pytest.mark.asyncio
async def test_cmd_curse_no_board_id(mock_message):
    await cmd_curse(mock_message, board_id=None)
    mock_message.reply.assert_not_called()

@pytest.mark.asyncio
async def test_cmd_curse_no_target(mock_message, mock_get_reply_target):
    mock_get_reply_target.return_value = None
    await cmd_curse(mock_message, board_id="test_board")
    mock_message.reply.assert_called_once_with("Нужно сделать Reply на пост жертвы!")

@pytest.mark.asyncio
async def test_cmd_curse_self_target(mock_message, mock_get_reply_target):
    mock_get_reply_target.return_value = 123 # Same as mock_message.from_user.id
    await cmd_curse(mock_message, board_id="test_board")
    mock_message.reply.assert_called_once_with("Сам себе слабительное?")

@pytest.mark.asyncio
async def test_cmd_curse_no_laxative_gun(mock_message, mock_get_reply_target, mock_get_pool, mock_db):
    mock_get_reply_target.return_value = 456
    db, cursor = mock_db

    # User has no active items
    cursor.fetchone.return_value = ("{}",)

    await cmd_curse(mock_message, board_id="test_board")
    mock_message.reply.assert_called_once_with("У тебя нет слабительного! Купи его в /shop.")

@pytest.mark.asyncio
async def test_cmd_curse_target_has_tinfoil_hat(mock_message, mock_get_reply_target, mock_get_pool, mock_db, mock_db_lock):
    mock_get_reply_target.return_value = 456
    db, cursor = mock_db

    # User has laxative gun
    user_items = {"laxative_gun": True}

    # Target has tinfoil hat that expires in the future
    future_time = int(time.time()) + 3600
    target_items = {"tinfoil_hat": future_time}

    cursor.fetchone.side_effect = [
        (json.dumps(user_items),),
        (json.dumps(target_items),)
    ]

    await cmd_curse(mock_message, board_id="test_board")

    # Tinfoil blocks the attack
    mock_message.bot.send_message.assert_any_call(
        123,
        "🚽 Твоё проклятие отскочило от Шапочки из фольги жертвы! Своё слабительное ты потратил впустую.",
        parse_mode="HTML"
    )
    mock_message.bot.send_message.assert_any_call(
        456,
        f"👽 Анон <code>123</code> попытался подсыпать тебе слабительное, но твоя Шапочка из фольги спасла твои штаны!",
        parse_mode="HTML"
    )
    mock_message.delete.assert_called_once()

    # Ensure item was removed from user
    db.execute_mock.assert_any_call(
        "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
        (json.dumps({"laxative_gun": False}), 123, "test_board")
    )
    db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_curse_success(mock_message, mock_get_reply_target, mock_get_pool, mock_db, mock_db_lock):
    mock_get_reply_target.return_value = 456
    db, cursor = mock_db

    # User has laxative gun
    user_items = {"laxative_gun": True}

    # Target has no items
    target_items = {}

    cursor.fetchone.side_effect = [
        (json.dumps(user_items),),
        (json.dumps(target_items),)
    ]

    now = int(time.time())
    with patch("time.time", return_value=now):
        await cmd_curse(mock_message, board_id="test_board")

        curse_until = now + 3600

        db.execute_mock.assert_any_call(
            "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
            (json.dumps({"laxative_gun": False}), 123, "test_board")
        )
        db.execute_mock.assert_any_call(
            "UPDATE Users SET cursed_until = ? WHERE user_id = ? AND board_id = ?",
            (curse_until, 456, "test_board")
        )
        assert db.commit.call_count == 1

        mock_message.bot.send_message.assert_any_call(
            456,
            "🚽 Тебе подсыпали слабительное! В течение 1 часа ты не сможешь писать посты длиннее 50 символов (не успеешь дописать и побежишь в туалет).",
            parse_mode="HTML"
        )
        mock_message.bot.send_message.assert_any_call(
            123,
            "🚽 Ты успешно подсыпал слабительное анону <code>456</code>!",
            parse_mode="HTML"
        )
        mock_message.delete.assert_called_once()
