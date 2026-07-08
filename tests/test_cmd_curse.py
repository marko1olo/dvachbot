import unittest
from unittest.mock import AsyncMock
from common.cmd_curse_utils import cmd_curse_logic

class TestCmdCurse(unittest.IsolatedAsyncioTestCase):
    async def test_cmd_curse(self):
        mock_message = AsyncMock()
        await cmd_curse_logic(mock_message, board_id="test_board", stream="ru")

        mock_message.answer.assert_called_once_with(
            "⚠️ Проклятие Хуесоса было признано слишком кринжовым и убрано из Теневого Магазина."
        )

if __name__ == '__main__':
    unittest.main()
