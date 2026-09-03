# -*- coding: utf-8 -*-
import pytest
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
import main
import ai_manager
from post_helpers import _MEDIA_DESC_CACHE

UTC = timezone.utc

class TestRichChunkIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.orig_messages = main.messages_storage.copy()
        main.messages_storage.clear()
        _MEDIA_DESC_CACHE.clear()

    async def asyncTearDown(self):
        main.messages_storage.clear()
        main.messages_storage.update(self.orig_messages)
        _MEDIA_DESC_CACHE.clear()

    async def test_get_board_chunk_batch_query_execution(self):
        # Create 10 posts with photos
        for i in range(1, 11):
            main.messages_storage[100 + i] = {
                'author_id': 1000 + i,
                'timestamp': datetime.now(UTC),
                'board_id': 'b',
                'content': {
                    'type': 'photo',
                    'file_id': f'photo_fid_{i}',
                    'text': f'Post number {i}'
                }
            }

        # Mock database cursor to verify single batch query
        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [
            (f'photo_fid_{i}', f'tag_{i}, anime', f'Description for photo {i}')
            for i in range(1, 11)
        ]
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_cursor
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_ctx

        with patch('common.database.get_pool', return_value=mock_db):
            chunk = await main.get_board_chunk('b', hours=1)

        # Verify DB was queried exactly ONCE in a batch
        assert mock_db.execute.call_count == 1
        query_sql = mock_db.execute.call_args[0][0]
        assert "SELECT file_id, tags, description FROM FileRegistry WHERE file_id IN (" in query_sql
        query_params = mock_db.execute.call_args[0][1]
        assert len(query_params) == 10

        # Verify chunk content contains rich media annotations
        for i in range(1, 11):
            assert f"[Фото: Description for photo {i}. Теги: tag_{i}, anime] Post number {i}" in chunk

    async def test_get_board_chunk_cache_reuse(self):
        # Prepopulate cache for photo_cached
        _MEDIA_DESC_CACHE['photo_cached'] = {
            'description': 'Cached description',
            'tags': 'cached_tag'
        }

        main.messages_storage[201] = {
            'author_id': 5555,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'content': {
                'type': 'photo',
                'file_id': 'photo_cached',
                'text': 'Check cache'
            }
        }

        mock_db = AsyncMock()
        with patch('common.database.get_pool', return_value=mock_db):
            chunk = await main.get_board_chunk('b', hours=1)

        # Database shouldn't be queried because file_id is in _MEDIA_DESC_CACHE
        assert mock_db.execute.call_count == 0
        assert "[Фото: Cached description. Теги: cached_tag] Check cache" in chunk

    async def test_get_board_chunk_35k_limit_enforcement(self):
        # Create many large posts exceeding 35k chars
        for i in range(1, 50):
            main.messages_storage[300 + i] = {
                'author_id': 2000 + i,
                'timestamp': datetime.now(UTC),
                'board_id': 'b',
                'content': {
                    'type': 'text',
                    'text': f"Post #{i} " + ("X" * 1000)
                }
            }

        chunk = await main.get_board_chunk('b', hours=1)
        assert len(chunk) <= 35000
        # Should include newest posts
        assert "Post #49" in chunk

    async def test_ai_manager_get_board_chunk_sync(self):
        main.messages_storage[401] = {
            'author_id': 3333,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'content': {
                'type': 'photo',
                'file_id': 'photo_ai_1',
                'text': 'AI chunk test'
            }
        }

        _MEDIA_DESC_CACHE['photo_ai_1'] = {
            'description': 'AI detected sunset',
            'tags': 'sunset, orange_sky'
        }

        chunk = await ai_manager.get_board_chunk('b', hours=1)
        assert "[Фото: AI detected sunset. Теги: sunset, orange_sky] AI chunk test" in chunk

    async def test_build_board_atmosphere_context_rich_media(self):
        main.messages_storage[501] = {
            'author_id': 7777,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'content': {
                'type': 'photo',
                'file_id': 'photo_atm_1'
            }
        }

        _MEDIA_DESC_CACHE['photo_atm_1'] = {
            'description': 'Смешной мем с жабой',
            'tags': 'pepe, meme'
        }

        atm = await main.build_board_atmosphere_context('b', limit=1)
        assert "[Фото: Смешной мем с жабой. Теги: pepe, meme]" in atm

    async def test_build_reply_chain_context_rich_media(self):
        main.messages_storage[601] = {
            'author_id': 8888,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'content': {
                'type': 'photo',
                'file_id': 'photo_chain_1'
            }
        }
        main.messages_storage[602] = {
            'author_id': 9999,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'reply_to_post_num': 601,
            'content': {
                'type': 'text',
                'text': 'Отличный арт!'
            }
        }

        _MEDIA_DESC_CACHE['photo_chain_1'] = {
            'description': 'Арт с киберпанком',
            'tags': 'cyberpunk, city'
        }

        chain = await main.build_reply_chain_context(602, max_depth=10)
        assert "[Фото: Арт с киберпанком. Теги: cyberpunk, city]" in chain
        assert "Отличный арт!" in chain
