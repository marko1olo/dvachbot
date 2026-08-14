import unittest
from unittest.mock import AsyncMock, MagicMock
import asyncio

from main import (
    cmd_matrix,
    cmd_america,
    cmd_holiday,
    cmd_oldweb,
    cmd_jewish,
    _trigger_generic_mode,
    UNFINISHED_NEW_MODES
)

class TestDisabledNewModes(unittest.TestCase):
    def setUp(self):
        self.mock_message = AsyncMock()
        self.mock_message.answer = AsyncMock()

    def test_unfinished_modes_set(self):
        expected_modes = {'matrix_mode', 'america_mode', 'holiday_mode', 'oldweb_mode', 'jewish_mode'}
        self.assertEqual(UNFINISHED_NEW_MODES, expected_modes)

    def test_cmd_matrix(self):
        asyncio.run(cmd_matrix(self.mock_message, 'b', 'ru'))
        self.mock_message.answer.assert_called_once_with("⚠️ Данный режим не активен и находится в разработке.")

    def test_cmd_america(self):
        asyncio.run(cmd_america(self.mock_message, 'b', 'ru'))
        self.mock_message.answer.assert_called_once_with("⚠️ Данный режим не активен и находится в разработке.")

    def test_cmd_holiday(self):
        asyncio.run(cmd_holiday(self.mock_message, 'b', 'ru'))
        self.mock_message.answer.assert_called_once_with("⚠️ Данный режим не активен и находится в разработке.")

    def test_cmd_oldweb(self):
        asyncio.run(cmd_oldweb(self.mock_message, 'b', 'ru'))
        self.mock_message.answer.assert_called_once_with("⚠️ Данный режим не активен и находится в разработке.")

    def test_cmd_jewish(self):
        asyncio.run(cmd_jewish(self.mock_message, 'b', 'ru'))
        self.mock_message.answer.assert_called_once_with("⚠️ Данный режим не активен и находится в разработке.")

    def test_trigger_generic_mode_interception(self):
        for mode in UNFINISHED_NEW_MODES:
            mock_msg = AsyncMock()
            asyncio.run(_trigger_generic_mode(mock_msg, 'b', 'ru', mode, [], 300, 'TEST'))
            mock_msg.answer.assert_called_once_with("⚠️ Данный режим не активен и находится в разработке.")

if __name__ == '__main__':
    unittest.main()
