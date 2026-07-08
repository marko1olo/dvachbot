import unittest
from unittest.mock import AsyncMock, patch

from common.pinned_messages import setup_pinned_messages

class TestSetupPinnedMessages(unittest.IsolatedAsyncioTestCase):
    async def test_setup_pinned_messages_thread_board(self):
        bot_mock = AsyncMock()
        bots = {'b': bot_mock}
        board_data = {'b': {}}
        board_config = {}
        thread_boards = ['b']

        with patch('common.pinned_messages.generate_boards_list', return_value="BOARD LINKS"), \
             patch('common.pinned_messages.random.choice', side_effect=lambda x: x[0]):

            await setup_pinned_messages(bots, board_data, board_config, thread_boards)

            b_data = board_data['b']
            self.assertIn('start_message_map', b_data)

            msg_map = b_data['start_message_map']
            self.assertIn('ru', msg_map)
            self.assertIn('en', msg_map)
            self.assertIn('jp', msg_map)

            # Check thread support text is present
            self.assertIn('This board supports threads!', msg_map['en'])
            self.assertIn('На этой доске есть треды!', msg_map['ru'])
            self.assertIn('この板はスレッドに対応しています！', msg_map['jp'])

            # Check board links are present
            self.assertIn('BOARD LINKS', msg_map['en'])

            # Since board_id is 'b', default language should be 'ru'
            self.assertEqual(b_data['start_message_text'], msg_map['ru'])

    async def test_setup_pinned_messages_non_thread_board_int(self):
        bot_mock = AsyncMock()
        bots = {'int': bot_mock}
        board_data = {'int': {}}
        board_config = {}
        thread_boards = []

        with patch('common.pinned_messages.generate_boards_list', return_value="LINKS"), \
             patch('common.pinned_messages.random.choice', return_value="BASE HELP"):

            await setup_pinned_messages(bots, board_data, board_config, thread_boards)

            b_data = board_data['int']
            msg_map = b_data['start_message_map']

            # Verify thread text is absent
            self.assertNotIn('This board supports threads!', msg_map['en'])
            self.assertNotIn('На этой доске есть треды!', msg_map['ru'])

            # For 'int' board, default lang is 'en'
            self.assertEqual(b_data['start_message_text'], msg_map['en'])

            self.assertIn("BASE HELP", msg_map['en'])
            self.assertIn("LINKS", msg_map['en'])

if __name__ == '__main__':
    unittest.main()
