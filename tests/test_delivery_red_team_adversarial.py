import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared_state import BroadcastConfig, board_data
from broadcaster import MessageBroadcaster
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError, TelegramServerError
)


class TestDeliveryRedTeamAdversarial(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        board_data['b'] = {
            'users': {'banned': set(), 'active': set()},
            'user_settings': {},
            'user_state': {},
        }

    def _create_mock_bot(self):
        bot = MagicMock()
        mock_msg = MagicMock()
        mock_msg.message_id = 99901
        mock_photo = MagicMock()
        mock_photo.file_id = "AgACvalidPhotoFid"
        mock_msg.photo = [mock_photo]
        mock_msg.video = None
        mock_msg.document = None
        mock_msg.audio = None
        mock_msg.voice = None
        bot.send_message = AsyncMock(return_value=mock_msg)
        bot.send_media_group = AsyncMock(return_value=[mock_msg, mock_msg])
        bot.send_photo = AsyncMock(return_value=mock_msg)
        bot.send_video = AsyncMock(return_value=mock_msg)
        bot.send_voice = AsyncMock(return_value=mock_msg)
        return bot

    async def test_media_group_over_10_items_sliced_to_10(self):
        """Edge Case 1: Telegram strictly limits albums to 10 items.
        If a post has 12 items, it must slice to 10 and send as album instead of failing.
        """
        bot = self._create_mock_bot()
        content = {
            'type': 'media_group',
            'post_num': 524001,
            'text': 'Пост с 12 изображениями',
            'media': [{'type': 'photo', 'media': f'AgACAgIAAxkBAAIvalid_{i}'} for i in range(12)]
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={4001},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)
        self.assertTrue(bot.send_media_group.called)
        sent_media = bot.send_media_group.call_args.kwargs['media']
        self.assertEqual(len(sent_media), 10)

    async def test_media_group_malformed_items_resilience(self):
        """Edge Case 2: Media array containing strings, None, ints should not crash with AttributeError."""
        bot = self._create_mock_bot()
        content = {
            'type': 'media_group',
            'post_num': 524002,
            'text': 'Пост с неоднородной медиагруппой',
            'media': [
                'AgACAgIAAxkBAAIrawStringId1',
                None,
                123456,
                {'type': 'photo', 'media': 'AgACAgIAAxkBAAIvalidDictId2'},
                {'type': 'photo', 'media': '<объект файла: invalid>'}
            ]
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={4002},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)
        self.assertTrue(bot.send_media_group.called)
        sent_media = bot.send_media_group.call_args.kwargs['media']
        self.assertEqual(len(sent_media), 2)

    async def test_media_group_single_valid_item_sends_as_single_media(self):
        """Edge Case 3: When an album has only 1 valid item after filtering broken ones,
        it should deliver that 1 item via send_photo/video instead of discarding the image.
        """
        bot = self._create_mock_bot()
        content = {
            'type': 'media_group',
            'post_num': 524003,
            'text': 'Пост с 1 валидной и 1 битой пикчей',
            'media': [
                {'type': 'photo', 'media': 'AgACAgIAAxkBAAIvalidSingle'},
                {'type': 'photo', 'media': '<объект файла: dead>'}
            ]
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={4003},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)
        self.assertTrue(bot.send_photo.called)
        self.assertEqual(bot.send_photo.call_args.kwargs.get('photo'), 'AgACAgIAAxkBAAIvalidSingle')

    async def test_reply_deleted_during_split_text_no_duplicate_media_group(self):
        """Edge Case 4: Long text split follow-up fails with 'message to be replied not found'.
        Must NOT retry the entire media group causing duplicate delivery.
        """
        bot = self._create_mock_bot()
        album_msg = MagicMock()
        album_msg.message_id = 88801
        bot.send_media_group = AsyncMock(return_value=[album_msg, album_msg])

        reply_err = TelegramBadRequest(method='sendMessage', message='Bad Request: message to be replied not found')
        ok_msg = MagicMock()
        ok_msg.message_id = 88802
        bot.send_message.side_effect = [reply_err, ok_msg]

        long_text = "A" * 1500
        content = {
            'type': 'media_group',
            'post_num': 524004,
            'text': long_text,
            'media': [
                {'type': 'photo', 'media': 'AgACAgIAAxkBAAIvalid1'},
                {'type': 'photo', 'media': 'AgACAgIAAxkBAAIvalid2'}
            ]
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={4004},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)
        # Verify media group was sent exactly ONCE (no duplicate!)
        self.assertEqual(bot.send_media_group.call_count, 1)

    async def test_stats_blocked_key_error_fixed(self):
        """Edge Case 5: Blocked user during hide filter check should increment stats['blocks'], not 'blocked'."""
        bot = self._create_mock_bot()
        bot.send_message.side_effect = TelegramForbiddenError(method='sendMessage', message='Forbidden: bot was blocked by the user')

        board_data['b']['user_settings'][4005] = {'hide': {'мат'}}
        content = {
            'type': 'text',
            'post_num': 524005,
            'text': 'Мат перемат в посте'
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={4005},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        # Should not raise KeyError: 'blocked'
        res = await broadcaster.broadcast()
        self.assertEqual(broadcaster.stats['blocks'], 1)

    async def test_html_parse_error_inside_text_fallback_preserves_post(self):
        """Edge Case 6: Malformed HTML in text fallback must be caught and delivered as plain text."""
        bot = self._create_mock_bot()
        # First send_message with HTML fails with parse error, second with plain text succeeds
        parse_err = TelegramBadRequest(method='sendMessage', message="Bad Request: can't parse entities: Character '<' is reserved")
        ok_msg = MagicMock()
        ok_msg.message_id = 77701
        bot.send_message.side_effect = [parse_err, ok_msg]

        content = {
            'type': 'media_group',
            'post_num': 524006,
            'text': 'Пост с битым тегом <bad_tag> и битыми картинками',
            'media': [
                {'type': 'photo', 'media': '<битая1>'},
                {'type': 'photo', 'media': '<битая2>'}
            ]
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={4006},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)
        self.assertTrue(bot.send_message.called)

    async def test_anti_fat_all_files_too_big_falls_back_to_text(self):
        """Edge Case 7: When Telegram rejects file as too big, post text must be delivered, NEVER return None."""
        bot = self._create_mock_bot()
        too_big_err = TelegramBadRequest(method='sendPhoto', message='Bad Request: file is too big')
        bot.send_photo.side_effect = too_big_err

        content = {
            'type': 'photo',
            'post_num': 524007,
            'text': 'Очень важный пост с гигантским файлом',
            'file_id': 'AgACAgIAAxkBAAIhugeFile'
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={4007},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)
        self.assertTrue(bot.send_message.called)

    async def test_voice_messages_forbidden_delivers_text(self):
        """Edge Case 8: User with Telegram Premium voice privacy receives text fallback instead of drop."""
        bot = self._create_mock_bot()
        voice_err = TelegramBadRequest(method='sendVoice', message='Bad Request: voice_messages_forbidden')
        bot.send_voice = AsyncMock(side_effect=voice_err)

        content = {
            'type': 'voice',
            'post_num': 524008,
            'text': 'Текст голосового сообщения или роаста',
            'file_id': 'AwACAgIAAxkBAAIvoiceId'
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={4008},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)
        self.assertTrue(bot.send_message.called)

    async def test_deleted_target_in_plain_text_parts_delivers_message(self):
        """Edge Case 9: When target message to reply was deleted, plain text fallback still delivers without reply_to."""
        bot = self._create_mock_bot()
        reply_err = TelegramBadRequest(method='sendMessage', message='Bad Request: message to be replied not found')
        ok_msg = MagicMock()
        ok_msg.message_id = 66601
        bot.send_message.side_effect = [reply_err, ok_msg]

        content = {
            'type': 'text',
            'post_num': 524009,
            'text': 'Обычный текст с удаленным reply_to_mid',
            'reply_to_post': 999999
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={4009},
            content=content,
            reply_info={4009: 123456789},
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)

    async def test_transient_telegram_server_error_retries_and_succeeds(self):
        """Edge Case 10: Transient Telegram 502/500 error on attempt 0 retries and succeeds on attempt 1."""
        bot = self._create_mock_bot()
        srv_err = TelegramServerError(method='sendMessage', message='502 Bad Gateway')
        ok_msg = MagicMock()
        ok_msg.message_id = 55501
        bot.send_message.side_effect = [srv_err, ok_msg]

        content = {
            'type': 'text',
            'post_num': 524010,
            'text': 'Пост при временном лаге Telegram'
        }
        cfg = BroadcastConfig(
            bot_instance=bot,
            board_id='b',
            recipients={4010},
            content=content,
            delivery_phase='active'
        )
        broadcaster = MessageBroadcaster(cfg)
        res = await broadcaster.broadcast()

        self.assertEqual(broadcaster.stats['success'], 1)
        self.assertEqual(broadcaster.stats['errors'], 0)


if __name__ == '__main__':
    unittest.main()
