import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from economy_extension import cmd_mega

class MockExecuteResult:
    def __init__(self, fetch_result=None):
        self.fetch_result = fetch_result

    def __await__(self):
        async def _awaitable():
            return self
        return _awaitable().__await__()

    async def __aenter__(self):
        self.cursor = AsyncMock()
        self.cursor.fetchone.return_value = self.fetch_result
        return self.cursor

    async def __aexit__(self, exc_type, exc, tb):
        pass

class TestCmdMega(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = AsyncMock()
        self.message.from_user.id = 111
        self.message.chat.id = 222
        self.message.reply_to_message.message_id = 333

    async def test_no_board(self):
        result = await cmd_mega(self.message, board_id=None)
        self.assertIsNone(result)

    @patch("economy_extension.get_reply_target", new_callable=AsyncMock)
    async def test_no_target(self, mock_get_target):
        mock_get_target.return_value = None
        await cmd_mega(self.message, board_id="b")
        self.message.reply.assert_awaited_with("Сделай Reply на СВОЙ пост, который хочешь закрепить!")

    @patch("economy_extension.get_reply_target", new_callable=AsyncMock)
    async def test_target_not_user(self, mock_get_target):
        mock_get_target.return_value = 999
        await cmd_mega(self.message, board_id="b")
        self.message.reply.assert_awaited_with("Мегафон работает только на свои собственные посты!")

    @patch("economy_extension.get_reply_target", new_callable=AsyncMock)
    @patch("economy_extension.get_pool", new_callable=AsyncMock)
    @patch("economy_extension.db_lock", new_callable=AsyncMock)
    async def test_no_megaphone(self, mock_db_lock, mock_get_pool, mock_get_target):
        mock_get_target.return_value = 111
        mock_db = MagicMock()
        mock_get_pool.return_value = mock_db

        mock_db.execute.return_value = MockExecuteResult([json.dumps({"other": True})])

        await cmd_mega(self.message, board_id="b")
        self.message.reply.assert_awaited_with("У тебя нет рупора! Купи его в /shop.")

    @patch("economy_extension.get_reply_target", new_callable=AsyncMock)
    @patch("economy_extension.get_pool", new_callable=AsyncMock)
    @patch("economy_extension.db_lock", new_callable=AsyncMock)
    async def test_success_pin(self, mock_db_lock, mock_get_pool, mock_get_target):
        mock_get_target.return_value = 111
        mock_db = MagicMock(commit=AsyncMock())
        mock_get_pool.return_value = mock_db

        execute_calls = []
        def mock_execute_side_effect(query, args):
            execute_calls.append((query, args))
            if query.startswith("SELECT"):
                return MockExecuteResult([json.dumps({"megaphone_gun": True})])
            else:
                return MockExecuteResult()

        mock_db.execute.side_effect = mock_execute_side_effect
        mock_db_lock.__aenter__ = AsyncMock(return_value=None)
        mock_db_lock.__aexit__ = AsyncMock(return_value=None)

        await cmd_mega(self.message, board_id="b")

        self.message.bot.pin_chat_message.assert_awaited_with(222, 333)
        self.message.bot.send_message.assert_any_call(
            111, "📣 Твой пост успешно закреплен с помощью Мегафона!", parse_mode="HTML"
        )
        self.message.bot.send_message.assert_any_call(
            222,
            "📣 <b>ВНИМАНИЕ!</b> Кто-то из анонов проплатил закрепление поста через Мегафон!",
            reply_to_message_id=333,
            parse_mode="HTML"
        )
        self.message.delete.assert_awaited_once()

        # Check active items update
        expected_items = json.dumps({"megaphone_gun": False})
        update_calls = [args for q, args in execute_calls if q.startswith("UPDATE")]
        self.assertTrue(any(args == (expected_items, 111, "b") for args in update_calls))

    @patch("economy_extension.get_reply_target", new_callable=AsyncMock)
    @patch("economy_extension.get_pool", new_callable=AsyncMock)
    @patch("economy_extension.db_lock", new_callable=AsyncMock)
    async def test_fail_pin(self, mock_db_lock, mock_get_pool, mock_get_target):
        mock_get_target.return_value = 111
        mock_db = MagicMock()
        mock_db.commit = AsyncMock() # Fix commit error
        mock_get_pool.return_value = mock_db

        execute_calls = []
        def mock_execute_side_effect(query, args):
            execute_calls.append((query, args))
            if query.startswith("SELECT"):
                return MockExecuteResult([json.dumps({"megaphone_gun": True})])
            else:
                return MockExecuteResult()

        mock_db.execute.side_effect = mock_execute_side_effect
        mock_db_lock.__aenter__ = AsyncMock(return_value=None)
        mock_db_lock.__aexit__ = AsyncMock(return_value=None)

        self.message.bot.pin_chat_message.side_effect = Exception("PinError")

        await cmd_mega(self.message, board_id="b")

        self.message.bot.pin_chat_message.assert_awaited_with(222, 333)
        self.message.bot.send_message.assert_any_call(
            111, "❌ Ошибка закрепления: PinError", parse_mode="HTML"
        )
        self.message.delete.assert_awaited_once()

        # Check refund
        expected_items = json.dumps({"megaphone_gun": True})
        update_calls = [args for q, args in execute_calls if q.startswith("UPDATE")]
        self.assertTrue(any(args == (expected_items, 111, "b") for args in update_calls))

if __name__ == "__main__":
    unittest.main()
