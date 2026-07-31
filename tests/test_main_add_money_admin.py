import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import common.db_pool

# Mock common modules that might fail
sys.modules['bjoern'] = MagicMock()

class TestMainAddMoneyAdmin(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # We need to clean up modules to avoid test pollution
        pass

    @patch('main.is_admin')
    @patch('common.db_pool.get_pool')
    @patch('common.db_pool.db_lock')
    async def test_cmd_add_money_admin_html_escape(self, mock_db_lock, mock_get_pool, mock_is_admin):
        # Allow the module-level mocks inside cmd_add_money_admin to resolve
        mock_is_admin.return_value = True

        db_mock = AsyncMock()
        mock_get_pool.return_value = db_mock

        # We need an async context manager for db_lock
        mock_db_lock.__aenter__.return_value = None
        mock_db_lock.__aexit__.return_value = None

        from main import cmd_add_money_admin
        from aiogram.types import Message, User

        # Mock aiogram Message
        message = MagicMock(spec=Message)
        message.from_user = MagicMock(spec=User)
        message.from_user.id = 12345
        message.text = "/addmoney 98765 1000"
        message.caption = None
        message.answer = AsyncMock()
        message.delete = AsyncMock()

        message.bot = MagicMock()
        message.bot.send_message = AsyncMock()

        # board_id with HTML characters
        malicious_board_id = "<b>evil</b>"

        # Run function
        await cmd_add_money_admin(message, malicious_board_id)

        # Verify message.answer was called with the escaped board_id
        message.answer.assert_called_once_with(
            "✅ Нарисовано 1000 рублей для юзера 98765. Баланс пополнен (корзина /&lt;b&gt;evil&lt;/b&gt;/)."
        )

if __name__ == '__main__':
    unittest.main()
