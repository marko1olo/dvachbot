import unittest
import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# We patch the database calls and get_reply_target before importing
with patch("economy_extension.get_pool", new_callable=AsyncMock), \
     patch("economy_extension.db_lock", new_callable=AsyncMock), \
     patch("economy_extension.get_reply_target", new_callable=AsyncMock):
    from economy_extension import cmd_mega

class MockExecuteCM:
    def __init__(self, cursor):
        self.cursor = cursor
    def __await__(self):
        yield
        return self
    async def __aenter__(self):
        return self.cursor
    async def __aexit__(self, exc_type, exc, tb):
        pass

class MockLockCM:
    async def __aenter__(self):
        return None
    async def __aexit__(self, exc_type, exc, tb):
        pass

class TestCmdMega(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = AsyncMock()
        self.message.from_user.id = 123
        self.message.chat.id = 456
        self.message.reply_to_message = MagicMock()
        self.message.reply_to_message.message_id = 789

    async def test_missing_board_id(self):
        result = await cmd_mega(self.message, board_id=None)
        self.assertIsNone(result)
        self.message.reply.assert_not_called()

    @patch("economy_extension.get_reply_target", return_value=None)
    async def test_missing_reply_target(self, mock_get_reply_target):
        await cmd_mega(self.message, board_id="test_board")
        self.message.reply.assert_called_once_with("Сделай Reply на СВОЙ пост, который хочешь закрепить!")

    @patch("economy_extension.get_reply_target", return_value=999)
    async def test_target_mismatch(self, mock_get_reply_target):
        # user_id is 123, target_id is 999
        await cmd_mega(self.message, board_id="test_board")
        self.message.reply.assert_called_once_with("Мегафон работает только на свои собственные посты!")

    @patch("economy_extension.get_reply_target", return_value=123)
    @patch("economy_extension.get_pool")
    async def test_missing_megaphone(self, mock_get_pool, mock_get_reply_target):
        mock_db = MagicMock()
        mock_cursor = AsyncMock()
        # Empty active_items
        mock_cursor.fetchone.return_value = ("{}",)

        mock_db.execute.return_value = MockExecuteCM(mock_cursor)
        mock_get_pool.return_value = mock_db

        await cmd_mega(self.message, board_id="test_board")
        self.message.reply.assert_called_once_with("У тебя нет рупора! Купи его в /shop.")

    @patch("economy_extension.get_reply_target", return_value=123)
    @patch("economy_extension.get_pool")
    @patch("economy_extension.db_lock", new_callable=MagicMock)
    async def test_successful_pin(self, mock_db_lock, mock_get_pool, mock_get_reply_target):
        mock_db = MagicMock()
        mock_db.execute = MagicMock()
        mock_db.commit = AsyncMock()
        mock_cursor = AsyncMock()

        # Has megaphone
        mock_cursor.fetchone.return_value = (json.dumps({"megaphone_gun": True}),)

        # Setup execute to return our context manager
        mock_db.execute.return_value = MockExecuteCM(mock_cursor)
        mock_get_pool.return_value = mock_db

        # Setup db_lock context manager
        mock_db_lock.__aenter__ = AsyncMock(return_value=None)
        mock_db_lock.__aexit__ = AsyncMock(return_value=None)

        await cmd_mega(self.message, board_id="test_board")

        # Verify db update
        expected_json = json.dumps({"megaphone_gun": False})
        mock_db.execute.assert_any_call(
            "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
            (expected_json, 123, "test_board")
        )
        mock_db.commit.assert_called_once()

        # Verify pin
        self.message.bot.pin_chat_message.assert_called_once_with(456, 789)

        # Verify user alert
        self.message.bot.send_message.assert_any_call(
            123, "📣 Твой пост успешно закреплен с помощью Мегафона!", parse_mode="HTML"
        )

        # Verify group alert
        self.message.bot.send_message.assert_any_call(
            456,
            "📣 <b>ВНИМАНИЕ!</b> Кто-то из анонов проплатил закрепление поста через Мегафон!",
            reply_to_message_id=789,
            parse_mode="HTML"
        )

        # Verify original message deleted
        self.message.delete.assert_called_once()

    @patch("economy_extension.get_reply_target", return_value=123)
    @patch("economy_extension.get_pool")
    @patch("economy_extension.db_lock", new_callable=MagicMock)
    async def test_exception_during_pin(self, mock_db_lock, mock_get_pool, mock_get_reply_target):
        mock_db = MagicMock()
        mock_db.execute = MagicMock()
        mock_db.commit = AsyncMock()
        mock_cursor = AsyncMock()

        # Has megaphone
        mock_cursor.fetchone.return_value = (json.dumps({"megaphone_gun": True}),)

        # Cursor async context manager
        mock_db.execute.return_value = MockExecuteCM(mock_cursor)
        mock_get_pool.return_value = mock_db

        # Setup db_lock context manager
        mock_db_lock.__aenter__ = AsyncMock(return_value=None)
        mock_db_lock.__aexit__ = AsyncMock(return_value=None)

        # Force pin error
        self.message.bot.pin_chat_message.side_effect = Exception("Test pin failed")

        await cmd_mega(self.message, board_id="test_board")

        # Verify db update (refunded)
        expected_json = json.dumps({"megaphone_gun": True})
        mock_db.execute.assert_any_call(
            "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
            (expected_json, 123, "test_board")
        )

        # Verify user alert contains exception info
        self.message.bot.send_message.assert_any_call(
            123, "❌ Ошибка закрепления: Test pin failed", parse_mode="HTML"
        )

if __name__ == "__main__":
    unittest.main()
