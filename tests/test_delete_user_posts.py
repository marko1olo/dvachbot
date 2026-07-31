import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from delete_user_posts import delete_user_posts

@pytest.mark.asyncio
async def test_delete_user_posts_basic():
    bot = AsyncMock()
    bot.delete_message = AsyncMock()

    class MockDB:
        def __init__(self):
            self.execute_calls = []

        def execute(self, query, *args):
            self.execute_calls.append((query, args))

            class MockContextManager:
                async def __aenter__(self):
                    return mock_cursor
                async def __aexit__(self, exc_type, exc, tb):
                    pass
                def __await__(self):
                    # Mock the case where someone incorrectly await db.execute instead of async with
                    # delete_user_posts actually does `await db.execute(...)` for some statements (DELETEs etc)
                    # and `async with db.execute(...)` for SELECTs.
                    # We need to handle both
                    async def _dummy(): pass
                    return _dummy().__await__()
            return MockContextManager()

    mock_db = MockDB()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock()

    call_count = 0
    async def mock_fetchall():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [(1,), (2,)] # user_posts
        elif call_count == 2:
            return [("t1",)] # threads_to_delete
        elif call_count == 3:
            return [(1,), (2,), (3,)] # posts_to_delete_set (t_ids query)
        elif call_count == 4:
            return [(123, 456, "b")] # messages_to_delete_from_api
        elif call_count == 5:
            return [] # channel_messages_to_delete
        return []

    mock_cursor.fetchall.side_effect = mock_fetchall

    class DummyAsyncLock:
        async def __aenter__(self): pass
        async def __aexit__(self, exc_type, exc, tb): pass

    async def mock_get_pool():
        return mock_db

    with patch('delete_user_posts.get_pool', side_effect=mock_get_pool), \
         patch('delete_user_posts.db_lock', DummyAsyncLock()), \
         patch('delete_user_posts.storage_lock', DummyAsyncLock(), create=True), \
         patch('delete_user_posts.messages_storage', {}, create=True), \
         patch('delete_user_posts.board_data', {}, create=True), \
         patch('delete_user_posts.post_to_messages', {}, create=True), \
         patch('delete_user_posts.message_to_post', {}, create=True), \
         patch('delete_user_posts.GLOBAL_BOTS', {'b': bot}, create=True), \
         patch('delete_user_posts.THREAD_BOARDS', set(), create=True), \
         patch('delete_user_posts.ARCHIVE_POSTING_BOT_ID', 'archive', create=True), \
         patch('delete_user_posts.bot_instance', bot, create=True), \
         patch('common.database._THREAD_CACHE', {}, create=True), \
         patch('common.database._VIDEO_CACHE', {}, create=True), \
         patch('common.database._IMAGE_CACHE', {}, create=True):

         deleted_count = await delete_user_posts(bot, 123, 60, "b")

         assert deleted_count == 1
         bot.delete_message.assert_called_once_with(123, 456)

         json_each_calls = [c for c in mock_db.execute_calls if 'json_each' in c[0]]
         assert len(json_each_calls) == 2
         assert "SELECT thread_id FROM Threads WHERE thread_id IN (SELECT value FROM json_each(?))" in json_each_calls[0][0]
         assert "SELECT post_num FROM Posts WHERE thread_id IN (SELECT value FROM json_each(?))" in json_each_calls[1][0]
