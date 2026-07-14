import pytest
from unittest.mock import AsyncMock, MagicMock
import asyncio

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test")
    monkeypatch.setenv("BOT_TOKEN", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

@pytest.fixture
def mock_db_pool():
    mock_db_pool = AsyncMock()
    mock_db = AsyncMock()
    mock_db_pool.return_value = mock_db
    return mock_db_pool

@pytest.mark.asyncio
async def test_delete_user_posts_basic(monkeypatch, mock_env):
    from main import delete_user_posts

    mock_db_pool = AsyncMock()
    mock_db_lock = MagicMock()
    mock_db_lock.__aenter__ = AsyncMock(return_value=None)
    mock_db_lock.__aexit__ = AsyncMock(return_value=None)

    class MockCursor:
        def __init__(self, rows=None):
            self.rows = rows or []
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def fetchall(self):
            return self.rows

    class MockContextManager:
        def __init__(self, rows=None):
            self.rows = rows
        async def __aenter__(self):
            return MockCursor(self.rows)
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    def execute_side_effect(query, *args, **kwargs):
        if "SELECT post_num FROM Posts WHERE author_id =" in query:
            return MockContextManager([(1,), (2,)])
        elif "SELECT thread_id FROM Threads WHERE thread_id IN" in query:
            return MockContextManager([(10,)])
        elif "SELECT post_num FROM Posts WHERE thread_id IN" in query:
            return MockContextManager([(1,), (2,), (3,)])
        elif "SELECT pc.recipient_id, pc.message_id, p.board_id" in query:
            return MockContextManager([(100, 200, 'test_board'), (101, 201, 'test_board')])
        elif "SELECT cc.channel_id, cc.message_id, p.board_id" in query:
            return MockContextManager([(-100, 300, 'test_board')])
        return MockContextManager([])

    class MagicExecuteMock:
        def __init__(self, query, args=None):
            self.query = query
            self.cm = execute_side_effect(query, args)
        def __await__(self):
            async def _aw():
                return self.cm
            return _aw().__await__()
        async def __aenter__(self):
            return await self.cm.__aenter__()
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await self.cm.__aexit__(exc_type, exc_val, exc_tb)

    mock_db = AsyncMock()
    mock_db.execute = MagicMock(side_effect=lambda query, *args, **kwargs: MagicExecuteMock(query, args))
    mock_db_pool.return_value = mock_db

    monkeypatch.setattr("common.db_pool.get_pool", mock_db_pool)
    monkeypatch.setattr("common.db_pool.db_lock", mock_db_lock)

    monkeypatch.setattr("common.database._THREAD_CACHE", {"test_board": ["1", "2", "3"]})
    monkeypatch.setattr("common.database._VIDEO_CACHE", {"test_board": [(1,), (2,), (3,)]})
    monkeypatch.setattr("common.database._IMAGE_CACHE", {"test_board": [(1,), (2,), (3,)]})

    monkeypatch.setattr("main.storage_lock", mock_db_lock)
    monkeypatch.setattr("main.messages_storage", {1: {'thread_id': 't1'}, 2: {'thread_id': 't2'}})
    monkeypatch.setattr("main.THREAD_BOARDS", ["test_board"])
    monkeypatch.setattr("main.board_data", {"test_board": {"threads_data": {"t1": {"posts": [1]}, "t2": {"posts": [2]}}}})

    bot_instance = AsyncMock()
    bot_instance.delete_message = AsyncMock(return_value=True)

    monkeypatch.setattr("main.GLOBAL_BOTS", {'archive': bot_instance})
    monkeypatch.setattr("main.ARCHIVE_POSTING_BOT_ID", 'archive')

    result = await delete_user_posts(bot_instance, user_id=123, time_period_minutes=60, board_id="test_board")
    assert result == 2

    # Test 2: No posts found
    def execute_side_effect_empty(query, *args, **kwargs):
        if "SELECT post_num FROM Posts WHERE author_id =" in query:
            return MockContextManager([])
        return MockContextManager([])

    mock_db.execute = MagicMock(side_effect=lambda query, *args, **kwargs: MagicExecuteMockEmpty(query, args))

    class MagicExecuteMockEmpty(MagicExecuteMock):
        def __init__(self, query, args=None):
            self.query = query
            self.cm = execute_side_effect_empty(query, args)

    mock_db.execute = MagicMock(side_effect=lambda query, *args, **kwargs: MagicExecuteMockEmpty(query, args))

    result = await delete_user_posts(bot_instance, user_id=123, time_period_minutes=60, board_id="test_board")
    assert result == 0

@pytest.mark.asyncio
async def test_delete_user_posts_db_locked(monkeypatch, mock_env):
    from main import delete_user_posts

    mock_db_pool = AsyncMock()
    mock_db_lock = MagicMock()
    mock_db_lock.__aenter__ = AsyncMock(return_value=None)
    mock_db_lock.__aexit__ = AsyncMock(return_value=None)

    mock_db = AsyncMock()

    # Simulate a database locked error
    class MagicExecuteError:
        def __init__(self, query, args=None):
            pass
        def __await__(self):
            async def _aw():
                raise Exception("database is locked")
            return _aw().__await__()
        async def __aenter__(self):
            raise Exception("database is locked")
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_db.execute = MagicMock(side_effect=lambda query, *args, **kwargs: MagicExecuteError(query, args))
    mock_db_pool.return_value = mock_db

    monkeypatch.setattr("common.db_pool.get_pool", mock_db_pool)
    monkeypatch.setattr("common.db_pool.db_lock", mock_db_lock)

    bot_instance = AsyncMock()

    # In main, when locked, it retries and then sleeps.
    # Patch sleep to not take actual time.
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    result = await delete_user_posts(bot_instance, user_id=123, time_period_minutes=60, board_id="test_board")
    assert result == 0
