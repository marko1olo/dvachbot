import unittest
import os
import sys
import asyncio
import io
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramRetryAfter,
    TelegramForbiddenError,
)
from common.bot_pool import MultiStreamBotPool
from site_tgach.tagging_worker import (
    download_file_with_fallback,
    _download_via_bot,
    _build_download_candidates,
    get_tasks,
    is_audio_media,
    GET_FILE_TIMEOUT_PER_BOT,
    DOWNLOAD_DATA_TIMEOUT_PER_BOT,
    DOWNLOAD_TOTAL_TIMEOUT,
    MAX_FILE_SIZE_BOT_API,
)

class TestTaggerDownloadResilience(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pool = MultiStreamBotPool()
        self.pool._loaded_streams.update(['ru', 'en', 'jp'])

    async def test_bot_pool_download_candidates_ordering(self):
        """Test that get_download_candidates prioritizes ready bots over cooling bots."""
        bot1 = MagicMock(id=101, token='101:token1')
        bot2 = MagicMock(id=102, token='102:token2')
        bot3 = MagicMock(id=103, token='103:token3')

        self.pool._shared_bots = {101: bot1, 102: bot2, 103: bot3}
        self.pool.bots_map['ru'] = {101: bot1, 102: bot2, 103: bot3}

        # Put bot1 on cooldown
        self.pool.mark_bot_cooldown(101, duration_sec=30.0)

        # Candidates with primary_bot = bot1:
        # bot1 is on cooldown, so ready bots (bot2, bot3) should come before bot1
        candidates = self.pool.get_download_candidates(primary_bot=bot1)
        self.assertEqual(len(candidates), 3)
        self.assertIn(candidates[0], [bot2, bot3])
        self.assertEqual(candidates[-1], bot1)

    async def test_download_success_primary_bot(self):
        """Test successful download on primary bot."""
        mock_bot = MagicMock(id=101, token='101:token1')
        mock_file_info = MagicMock(file_path='photos/test.jpg', file_size=1024)
        mock_bot.get_file = AsyncMock(return_value=mock_file_info)
        mock_bot.download_file = AsyncMock(return_value=io.BytesIO(b'IMAGE_BYTES_12345'))

        with patch('site_tgach.tagging_worker.global_bot_pool', self.pool):
            self.pool._shared_bots = {101: mock_bot}
            img_bytes, active_bot, status = await download_file_with_fallback('file_abc123', primary_bot=mock_bot)

            self.assertEqual(img_bytes, b'IMAGE_BYTES_12345')
            self.assertEqual(active_bot, mock_bot)
            self.assertEqual(status, 'ok')

    async def test_download_timeout_rotates_to_next_bot_and_sets_cooldown(self):
        """Test that when a bot times out, it is put on cooldown and the next bot is used."""
        bot1 = MagicMock(id=101, token='101:token1')
        bot2 = MagicMock(id=102, token='102:token2')

        # Bot 1 times out
        bot1.get_file = AsyncMock(side_effect=asyncio.TimeoutError())
        # Bot 2 succeeds
        mock_file_info2 = MagicMock(file_path='photos/test2.jpg', file_size=2048)
        bot2.get_file = AsyncMock(return_value=mock_file_info2)
        bot2.download_file = AsyncMock(return_value=io.BytesIO(b'RECOVERED_BYTES'))

        with patch('site_tgach.tagging_worker.global_bot_pool', self.pool):
            self.pool._shared_bots = {101: bot1, 102: bot2}
            self.pool.bots_map['ru'] = {101: bot1, 102: bot2}

            img_bytes, active_bot, status = await download_file_with_fallback('file_timeout_test', primary_bot=bot1)

            self.assertEqual(img_bytes, b'RECOVERED_BYTES')
            self.assertEqual(active_bot, bot2)
            self.assertEqual(status, 'ok')
            # Bot 1 must now be in cooldown
            self.assertTrue(self.pool.is_bot_on_cooldown(101))

    async def test_download_flood_wait_sets_cooldown(self):
        """Test that FloodWait (TelegramRetryAfter) puts bot on cooldown and tries next bot."""
        bot1 = MagicMock(id=101, token='101:token1')
        bot2 = MagicMock(id=102, token='102:token2')

        # Bot 1 raises FloodWait
        bot1.get_file = AsyncMock(side_effect=TelegramRetryAfter(method=MagicMock(), message='Flood', retry_after=20))
        # Bot 2 succeeds
        mock_file_info2 = MagicMock(file_path='photos/test2.jpg', file_size=2048)
        bot2.get_file = AsyncMock(return_value=mock_file_info2)
        bot2.download_file = AsyncMock(return_value=io.BytesIO(b'RECOVERED_FLOOD'))

        with patch('site_tgach.tagging_worker.global_bot_pool', self.pool):
            self.pool._shared_bots = {101: bot1, 102: bot2}
            self.pool.bots_map['ru'] = {101: bot1, 102: bot2}

            img_bytes, active_bot, status = await download_file_with_fallback('file_flood_test', primary_bot=bot1)

            self.assertEqual(img_bytes, b'RECOVERED_FLOOD')
            self.assertEqual(active_bot, bot2)
            self.assertEqual(status, 'ok')
            self.assertTrue(self.pool.is_bot_on_cooldown(101))

    async def test_download_file_too_big_stops_early(self):
        """Test that files exceeding 20MB limit stop early with status file_too_big without wasting time on all bots."""
        bot1 = MagicMock(id=101, token='101:token1')
        bot2 = MagicMock(id=102, token='102:token2')

        # Bot 1 reports file_size = 25MB
        mock_file_info = MagicMock(file_path='videos/huge.mp4', file_size=25 * 1024 * 1024)
        bot1.get_file = AsyncMock(return_value=mock_file_info)
        bot2.get_file = AsyncMock()

        with patch('site_tgach.tagging_worker.global_bot_pool', self.pool):
            self.pool._shared_bots = {101: bot1, 102: bot2}
            self.pool.bots_map['ru'] = {101: bot1, 102: bot2}

            with patch('common.database.get_file_mirrors', AsyncMock(return_value={})):
                img_bytes, active_bot, status = await download_file_with_fallback('huge_file_id', primary_bot=bot1)

                self.assertIsNone(img_bytes)
                self.assertEqual(status, 'file_too_big')
                # Bot 2 should not have been called because >20MB cannot be downloaded on any bot
                bot2.get_file.assert_not_called()

    async def test_download_all_not_found_returns_not_found(self):
        """Test that when all bots return TelegramBadRequest file is not found, status is not_found."""
        bot1 = MagicMock(id=101, token='101:token1')
        bot2 = MagicMock(id=102, token='102:token2')

        bot1.get_file = AsyncMock(side_effect=TelegramBadRequest(method=MagicMock(), message='Bad Request: file is not found'))
        bot2.get_file = AsyncMock(side_effect=TelegramBadRequest(method=MagicMock(), message='Bad Request: wrong file identifier'))

        with patch('site_tgach.tagging_worker.global_bot_pool', self.pool):
            self.pool._shared_bots = {101: bot1, 102: bot2}
            self.pool.bots_map['ru'] = {101: bot1, 102: bot2}

            with patch('common.database.get_file_mirrors', AsyncMock(return_value={})):
                img_bytes, active_bot, status = await download_file_with_fallback('non_existent_file', primary_bot=bot1)

                self.assertIsNone(img_bytes)
                self.assertEqual(status, 'not_found')

    async def test_audio_media_detection(self):
        """Test audio detection helper correctly detects various audio types."""
        self.assertTrue(is_audio_media(file_type='audio'))
        self.assertTrue(is_audio_media(file_type='voice'))
        self.assertTrue(is_audio_media(mime_type='audio/ogg'))
        self.assertTrue(is_audio_media(mime_type='audio/mpeg'))
        self.assertTrue(is_audio_media(filename='song.flac'))
        self.assertTrue(is_audio_media(filename='track.mp3'))
        self.assertTrue(is_audio_media(data=b'ID3\x03\x00\x00\x00\x00\x00\x00\x00\x00'))
        self.assertTrue(is_audio_media(data=b'OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00'))
        self.assertFalse(is_audio_media(file_type='photo', mime_type='image/jpeg', filename='pic.jpg'))

if __name__ == '__main__':
    unittest.main()
