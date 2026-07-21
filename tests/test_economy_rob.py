import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
import time
import json

from aiogram import types
from economy_extension import cmd_rob

class MockDBExecute:
    def __init__(self, fetchone_return=None):
        self.fetchone_return = fetchone_return

    async def __aenter__(self):
        cm = AsyncMock()
        cm.fetchone.return_value = self.fetchone_return
        return cm

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def __await__(self):
        async def dummy():
            pass
        return dummy().__await__()

class MockDB:
    def __init__(self, queries=None):
        self.queries = queries or {}
        self.execute_calls = []
        self.commit = AsyncMock()

    def execute(self, query, params=None):
        self.execute_calls.append((query, params))
        res = ("{}",)
        for q, ret in self.queries.items():
            if q in query:
                res = ret
                break
        return MockDBExecute(res)

class TestCmdRob(unittest.IsolatedAsyncioTestCase):
    async def test_no_board_id(self):
        message = AsyncMock()
        result = await cmd_rob(message, board_id=None)
        self.assertIsNone(result)
        message.reply.assert_not_called()

    @patch('economy_extension.get_reply_target')
    async def test_no_target_id(self, mock_get_reply_target):
        mock_get_reply_target.return_value = None
        message = AsyncMock()
        message.from_user.id = 123
        await cmd_rob(message, board_id="b")
        message.reply.assert_called_with("Нужно сделать Reply на пост жертвы!")

    @patch('economy_extension.get_reply_target')
    async def test_target_self(self, mock_get_reply_target):
        mock_get_reply_target.return_value = 123
        message = AsyncMock()
        message.from_user.id = 123
        await cmd_rob(message, board_id="b")
        message.reply.assert_called_with("Нельзя ограбить самого себя.")

    @patch('economy_extension.get_pool')
    @patch('economy_extension.get_reply_target')
    async def test_no_knife_gun(self, mock_get_reply_target, mock_get_pool):
        mock_get_reply_target.return_value = 456
        message = AsyncMock()
        message.from_user.id = 123

        mock_db = MockDB(queries={"SELECT active_items FROM Users WHERE user_id = ?": ("{}",)})
        mock_get_pool.return_value = mock_db

        await cmd_rob(message, board_id="b")
        message.reply.assert_called_with("У тебя нет заточки! Купи её в /shop.")

    @patch('economy_extension.get_pool')
    @patch('economy_extension.get_reply_target')
    async def test_tinfoil_hat_blocks(self, mock_get_reply_target, mock_get_pool):
        mock_get_reply_target.return_value = 456
        message = AsyncMock()
        message.from_user.id = 123

        user_items = json.dumps({"knife_gun": True})
        target_items = json.dumps({"tinfoil_hat": int(time.time()) + 3600})

        mock_db = MockDB()
        def side_effect_execute(query, params=None):
            if "UPDATE" in query:
                return MockDBExecute(None)
            if params and params[0] == 456:
                return MockDBExecute((1000, target_items))
            elif params and params[0] == 123:
                return MockDBExecute((user_items,))
            return MockDBExecute(None)

        mock_db.execute = MagicMock(side_effect=side_effect_execute)
        mock_get_pool.return_value = mock_db

        await cmd_rob(message, board_id="b")

        message.bot.send_message.assert_any_call(123, "🔪 Твоя заточка сломалась о Шапочку из фольги жертвы! Ограбление не удалось.", parse_mode="HTML")
        message.bot.send_message.assert_any_call(456, "👽 Анон <code>123</code> попытался ограбить тебя, но твоя Шапочка из фольги спасла твои шекели!", parse_mode="HTML")
        message.delete.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch('economy_extension.get_pool')
    @patch('economy_extension.get_reply_target')
    async def test_target_too_poor(self, mock_get_reply_target, mock_get_pool):
        mock_get_reply_target.return_value = 456
        message = AsyncMock()
        message.from_user.id = 123

        user_items = json.dumps({"knife_gun": True})
        target_items = json.dumps({})

        mock_db = MockDB()
        def side_effect_execute(query, params=None):
            if "UPDATE" in query:
                return MockDBExecute(None)
            if params and params[0] == 456:
                return MockDBExecute((49, target_items))
            elif params and params[0] == 123:
                return MockDBExecute((user_items,))
            return MockDBExecute(None)

        mock_db.execute = MagicMock(side_effect=side_effect_execute)
        mock_get_pool.return_value = mock_db

        await cmd_rob(message, board_id="b")

        message.bot.send_message.assert_called_once_with(123, "🔪 Ты приставил заточку, но у жертвы в карманах только дыры... Грабить нечего.", parse_mode="HTML")
        message.delete.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch('economy_extension.random.uniform')
    @patch('economy_extension.get_pool')
    @patch('economy_extension.get_reply_target')
    async def test_successful_robbery(self, mock_get_reply_target, mock_get_pool, mock_uniform):
        mock_get_reply_target.return_value = 456
        mock_uniform.return_value = 0.2
        message = AsyncMock()
        message.from_user.id = 123

        user_items = json.dumps({"knife_gun": True})
        target_items = json.dumps({})

        mock_db = MockDB()
        def side_effect_execute(query, params=None):
            if "UPDATE" in query:
                return MockDBExecute(None)
            if params and params[0] == 456:
                return MockDBExecute((1000, target_items))
            elif params and params[0] == 123:
                return MockDBExecute((user_items,))
            return MockDBExecute(None)

        mock_db.execute = MagicMock(side_effect=side_effect_execute)
        mock_get_pool.return_value = mock_db

        await cmd_rob(message, board_id="b")

        message.bot.send_message.assert_any_call(456, "🔪 В подворотне тебя пырнул Анон <code>123</code> и отобрал <b>200 Шекелей</b>!", parse_mode="HTML")
        message.bot.send_message.assert_any_call(123, "🔪 Ограбление прошло успешно! Ты отжал у лоха <code>456</code> <b>200 Шекелей</b>.", parse_mode="HTML")
        message.delete.assert_called_once()
        mock_db.commit.assert_called_once()

if __name__ == '__main__':
    unittest.main()
