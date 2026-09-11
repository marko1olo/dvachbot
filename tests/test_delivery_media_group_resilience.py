import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared_state import BroadcastConfig, board_data
from broadcaster import MessageBroadcaster
from aiogram.exceptions import TelegramBadRequest


class TestDeliveryMediaGroupResilience(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        board_data['b'] = {
            'users': {'banned': set(), 'active': set()},
            'user_settings': {},
            'user_state': {},
        }

    def _create_mock_bot(self):
        bot = MagicMock()
        mock_msg = MagicMock()
        mock_msg.message_id = 12345
        bot.send_message = AsyncMock(return_value=mock_msg)
        bot.send_media_group = AsyncMock(return_value=[mock_msg, mock_msg])
        bot.send_photo = AsyncMock(return_value=mock_msg)
        return bot

    async def test_media_group_with_file_object_placeholders_falls_back_to_text(self):
        bot = self._create_mock_bot()
        content = {
            'type': 'media_group',
            'post_num': 523156,
            'text': 'Тестовый пост с битой медиагруппой',
            'media': [
                {'type': 'photo', 'media': '<объект файла: photo1.png>'},
                {'type': 'photo', 'media': '<объект файла: photo2.png>'}
            ]
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={1001, 1002},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 2)
        self.assertEqual(broadcaster.stats['errors'], 0)
        self.assertTrue(bot.send_message.called)
        self.assertFalse(bot.send_media_group.called)

    async def test_media_group_telegram_media_invalid_switches_to_text_safely(self):
        bot = self._create_mock_bot()
        bot.send_media_group.side_effect = TelegramBadRequest(
            method='sendMediaGroup',
            message='failed to send message #1 with the error message "MEDIA_INVALID"'
        )
        content = {
            'type': 'media_group',
            'post_num': 523157,
            'text': 'Пост с отклоненной медиагруппой',
            'media': [
                {'type': 'photo', 'media': 'AgACAgIAAxkBAAIvalidId1'},
                {'type': 'photo', 'media': 'AgACAgIAAxkBAAIvalidId2'}
            ]
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={2001, 2002},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 2)
        self.assertEqual(broadcaster.stats['errors'], 0)
        self.assertTrue(broadcaster.media_group_fallback_to_text)
        self.assertTrue(bot.send_message.called)

    async def test_single_media_with_placeholder_falls_back_to_text(self):
        bot = self._create_mock_bot()
        content = {
            'type': 'photo',
            'post_num': 523158,
            'text': 'Одиночный пост с битым плейсхолдером',
            'file_id': '<объект файла: broken.jpg>'
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={3001},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)
        self.assertTrue(bot.send_message.called)


if __name__ == '__main__':
    unittest.main()
