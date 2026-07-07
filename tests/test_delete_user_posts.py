import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
import sys

@pytest.fixture
def mock_delete_user_posts_module(monkeypatch):
    """Safely patch sys.modules to allow delete_user_posts to be imported."""
    monkeypatch.setitem(sys.modules, 'common', MagicMock())
    monkeypatch.setitem(sys.modules, 'common.db_pool', MagicMock())

    mock_database = MagicMock()
    mock_database._THREAD_CACHE = {}
    mock_database._VIDEO_CACHE = {}
    mock_database._IMAGE_CACHE = {}
    monkeypatch.setitem(sys.modules, 'common.database', mock_database)

    import builtins
    monkeypatch.setattr(builtins, 'Bot', MagicMock(), raising=False)

    import types
    # Mock Telegram errors and bot classes
    mock_aiohttp = types.ModuleType('aiohttp')
    mock_aiohttp.ClientError = type('ClientError', (Exception,), {})
    mock_aiohttp.ClientOSError = type('ClientOSError', (Exception,), {})
    monkeypatch.setitem(sys.modules, 'aiohttp', mock_aiohttp)

    # We must mock builtins that it expects
    import datetime
    monkeypatch.setattr(builtins, 'UTC', datetime.timezone.utc, raising=False)
    monkeypatch.setattr(builtins, 'TelegramBadRequest', type('TelegramBadRequest', (Exception,), {}), raising=False)
    monkeypatch.setattr(builtins, 'TelegramForbiddenError', type('TelegramForbiddenError', (Exception,), {}), raising=False)
    monkeypatch.setattr(builtins, 'TelegramNetworkError', type('TelegramNetworkError', (Exception,), {}), raising=False)

    import delete_user_posts
    return delete_user_posts

@pytest.mark.asyncio
async def test_delete_user_posts_value_error(mocker, mock_delete_user_posts_module):
    """Test that ValueError is caught properly when removing from threads_data posts."""
    module = mock_delete_user_posts_module

    # Mock global state
    mock_db = AsyncMock()
    def fetchall_side_effect(*args, **kwargs):
        if not hasattr(fetchall_side_effect, 'called'):
            fetchall_side_effect.called = True
            return [[1]]
        return []

    mock_db.execute.return_value.__aenter__.return_value.fetchall.side_effect = fetchall_side_effect

    mock_get_pool = AsyncMock(return_value=mock_db)

    mock_db_lock = AsyncMock()
    mock_db_lock.__aenter__.return_value = None

    mock_storage_lock = AsyncMock()
    mock_storage_lock.__aenter__.return_value = None

    mocker.patch.object(module, 'db_lock', mock_db_lock, create=True)
    mocker.patch.object(module, 'get_pool', mock_get_pool, create=True)
    mocker.patch.object(module, 'storage_lock', mock_storage_lock, create=True)
    mocker.patch.object(module, 'GLOBAL_BOTS', {}, create=True)
    mocker.patch.object(module, 'ARCHIVE_POSTING_BOT_ID', 'test', create=True)

    mock_messages_storage = {
        1: {'thread_id': 'thread_1'}
    }
    mock_thread_boards = ['test_board']
    mock_board_data = {
        'test_board': {
            'threads_data': {
                'thread_1': {
                    'posts': [2, 3] # This will trigger ValueError when remove(1) is called
                }
            }
        }
    }

    mocker.patch.object(module, 'messages_storage', mock_messages_storage, create=True)
    mocker.patch.object(module, 'THREAD_BOARDS', mock_thread_boards, create=True)
    mocker.patch.object(module, 'board_data', mock_board_data, create=True)
    mocker.patch.object(module, 'post_to_messages', {}, create=True)
    mocker.patch.object(module, 'message_to_post', {}, create=True)

    mock_bot = MagicMock()

    res = await module.delete_user_posts(bot_instance=mock_bot, user_id=123, time_period_minutes=60, board_id='test_board')

    # Ensure ValueError was caught and it didn't blow up
    assert mock_board_data['test_board']['threads_data']['thread_1']['posts'] == [2, 3]

@pytest.mark.asyncio
async def test_delete_user_posts_key_error(mocker, mock_delete_user_posts_module):
    """Test that KeyError is caught properly when a KeyError occurs accessing or modifying 'posts' key."""
    module = mock_delete_user_posts_module

    mock_db = AsyncMock()

    def fetchall_side_effect(*args, **kwargs):
        if not hasattr(fetchall_side_effect, 'called'):
            fetchall_side_effect.called = True
            return [[1]]
        return []

    mock_db.execute.return_value.__aenter__.return_value.fetchall.side_effect = fetchall_side_effect
    mock_get_pool = AsyncMock(return_value=mock_db)

    mock_db_lock = AsyncMock()
    mock_db_lock.__aenter__.return_value = None

    mock_storage_lock = AsyncMock()
    mock_storage_lock.__aenter__.return_value = None

    mocker.patch.object(module, 'db_lock', mock_db_lock, create=True)
    mocker.patch.object(module, 'get_pool', mock_get_pool, create=True)
    mocker.patch.object(module, 'storage_lock', mock_storage_lock, create=True)
    mocker.patch.object(module, 'GLOBAL_BOTS', {}, create=True)
    mocker.patch.object(module, 'ARCHIVE_POSTING_BOT_ID', 'test', create=True)

    mock_messages_storage = {
        1: {'thread_id': 'thread_1'}
    }
    mock_thread_boards = ['test_board']

    class FakeDict(dict):
        def __contains__(self, key):
            return True
        def __getitem__(self, key):
            raise KeyError(key)

    mock_board_data = {
        'test_board': {
            'threads_data': {
                'thread_1': FakeDict()
            }
        }
    }

    mocker.patch.object(module, 'messages_storage', mock_messages_storage, create=True)
    mocker.patch.object(module, 'THREAD_BOARDS', mock_thread_boards, create=True)
    mocker.patch.object(module, 'board_data', mock_board_data, create=True)
    mocker.patch.object(module, 'post_to_messages', {}, create=True)
    mocker.patch.object(module, 'message_to_post', {}, create=True)

    mock_bot = MagicMock()

    res = await module.delete_user_posts(bot_instance=mock_bot, user_id=123, time_period_minutes=60, board_id='test_board')

    # Ensure KeyError was caught
    assert 'test_board' in mock_board_data
