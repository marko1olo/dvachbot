import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio
import os
import sys
import builtins

# Setting required env vars to avoid main module crashing on load
os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

# Make sure we don't conflict with current loop
asyncio.set_event_loop(asyncio.new_event_loop())

import delete_user_posts as target_module

@pytest.mark.asyncio
async def test_delete_user_posts_value_error(mocker, monkeypatch):
    class DummyLock:
        async def __aenter__(self): pass
        async def __aexit__(self, exc_type, exc_val, exc_tb): pass

    # We must provide the missing globals to target_module
    mocker.patch.object(target_module, 'storage_lock', DummyLock(), create=True)
    mocker.patch.object(target_module, 'messages_storage', {123: {'thread_id': '456'}}, create=True)
    mocker.patch.object(target_module, 'THREAD_BOARDS', ['b'], create=True)
    mocker.patch.object(target_module, 'board_data', {'b': {'threads_data': {'456': {'posts': [789]}}}}, create=True)
    mocker.patch.object(target_module, 'post_to_messages', {}, create=True)
    mocker.patch.object(target_module, 'message_to_post', {}, create=True)
    mocker.patch.object(target_module, 'GLOBAL_BOTS', {}, create=True)
    mocker.patch.object(target_module, 'ARCHIVE_POSTING_BOT_ID', 999, create=True)

    # Mocks for DB
    mocker.patch('common.db_pool.db_lock', DummyLock())

    class CursorContextMock:
        def __init__(self, fetch_return):
            self.fetch_return = fetch_return
        async def __aenter__(self):
            cursor = AsyncMock()
            cursor.fetchall.return_value = self.fetch_return
            return cursor
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        def __await__(self):
            async def _return_self():
                cursor = AsyncMock()
                cursor.fetchall.return_value = self.fetch_return
                return cursor
            return _return_self().__await__()

    class DBConn:
        def execute(self, query, *args):
            fetch_return = []
            if "SELECT post_num FROM Posts" in query and "thread_id IN" not in query:
                fetch_return = [(123,)]
            return CursorContextMock(fetch_return)

    async def mock_get_pool():
        return DBConn()

    mocker.patch('common.db_pool.get_pool', mock_get_pool)

    mocker.patch('common.database._THREAD_CACHE', {})
    mocker.patch('common.database._VIDEO_CACHE', {})
    mocker.patch('common.database._IMAGE_CACHE', {})

    bot_mock = AsyncMock()

    res = await target_module.delete_user_posts(bot_mock, user_id=1, time_period_minutes=60, board_id='b')

    assert res == 0
    assert 123 not in target_module.messages_storage
