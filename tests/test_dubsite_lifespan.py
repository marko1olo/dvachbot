import sys
import os
import unittest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
import asyncio
import types
from contextlib import asynccontextmanager
import json
import warnings
import logging

# Setup required env var
os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["FILE_UPLOADER_BOT_TOKEN"] = "test-token"
os.environ["FILE_STORAGE_CHANNEL_ID"] = "12345"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def mock_module(name):
    mod = types.ModuleType(name)
    mod.__path__ = [] # makes it a package
    sys.modules[name] = mod
    return mod

# Mock external third-party dependencies if not installed
mocked_deps = [
    'slowapi', 'slowapi.util', 'slowapi.errors', 'async_lru', 'uvicorn',
    'fastapi', 'fastapi.responses', 'fastapi.middleware', 'fastapi.middleware.cors',
    'fastapi.middleware.trustedhost', 'fastapi.middleware.gzip',
    'fastapi.staticfiles', 'fastapi.templating', 'fastapi.exceptions', 'fastapi.exception_handlers',
    'fastapi_cache', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator', 'geoip2', 'geoip2.database',
    'openai',
]

_added_mocks = []
for dep in mocked_deps:
    if dep not in sys.modules:
        _added_mocks.append(dep)
        mod = mock_module(dep)
        mod.__getattr__ = lambda name: MagicMock()

def tearDownModule():
    for dep in _added_mocks:
        if dep in sys.modules:
            del sys.modules[dep]

import Dubsite_tgach.main as main_module
from Dubsite_tgach.main import lifespan

class TestDubsiteLifespan(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        self.app = MagicMock()
        self.app.state = MagicMock()

        main_module.FILE_UPLOADER_BOT_TOKEN = 'test-token'
        main_module.FILE_STORAGE_CHANNEL_ID = '12345'
        main_module.BOARD_CONFIG = {}

    @patch('Dubsite_tgach.main.create_pool', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.initialize_database', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.sync_boards_with_config', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.get_db_connection')
    @patch('Dubsite_tgach.main.Bot')
    @patch('Dubsite_tgach.main.FastAPICache.init')
    async def test_lifespan_success(self, mock_cache_init, mock_bot, mock_get_db, mock_sync_boards, mock_init_db, mock_create_pool):
        @asynccontextmanager
        async def dummy_db_conn():
            conn = AsyncMock()

            @asynccontextmanager
            async def dummy_cursor(query, *args, **kwargs):
                cursor = AsyncMock()
                if "SELECT board_id, name, description" in query:
                    cursor.__aiter__.return_value = [
                        (1, "b1", "desc1"),
                        (2, "b2", "desc2")
                    ]
                elif "SELECT board_id, banner_data" in query:
                    cursor.__aiter__.return_value = [
                        (1, json.dumps({"banner": "test1"})),
                        (2, None) # test no banner data
                    ]
                yield cursor

            conn.execute = dummy_cursor
            yield conn

        mock_get_db.side_effect = dummy_db_conn

        mock_bot_instance = MagicMock()
        mock_bot_instance.session = AsyncMock()
        mock_bot.return_value = mock_bot_instance

        # Return a simple coroutine to avoid mock await errors, wrap it in a mock so side_effect is a coro factory
        with patch('Dubsite_tgach.main.spawn_task') as mock_spawn_task, \
             patch('Dubsite_tgach.main.asyncio.gather', new_callable=AsyncMock) as mock_gather, \
             patch('Dubsite_tgach.main.load_all_spam_words', new_callable=AsyncMock, create=True) as mock_load_spam, \
             patch('Dubsite_tgach.main.close_pool', new_callable=AsyncMock) as mock_close_pool, \
             patch('Dubsite_tgach.main.wal_checkpoint_truncate', new_callable=AsyncMock, create=True) as mock_wal_truncate, \
             patch('Dubsite_tgach.main.global_bot_pool', new_callable=AsyncMock) as mock_bot_pool, \
             patch('Dubsite_tgach.main.GLOBAL_HTTP_SESSION', new_callable=AsyncMock) as mock_http_session, \
             patch('site_tgach.neuro_poster.NeuroManager') as mock_neuro_manager_class:

            mock_neuro_manager = MagicMock()
            mock_neuro_manager_class.return_value = mock_neuro_manager

            # Since spawn_task takes coroutines, we mock spawn_task to consume the coroutines silently without await issues
            def mock_spawn(*args):
                for arg in args:
                    if asyncio.iscoroutine(arg):
                        arg.close() # Close it so we don't get 'never awaited' warnings
                m = MagicMock()
                m.done.return_value = True
                return m

            mock_spawn_task.side_effect = mock_spawn

            logger = logging.getLogger("Dubsite_tgach.main")
            old_level = logger.level
            logger.setLevel(logging.CRITICAL) # Suppress logger missing format field issues

            try:
                async with lifespan(self.app):
                    # Verify that tasks are initialized
                    mock_create_pool.assert_called_once()
                    mock_init_db.assert_called_once()
                    mock_sync_boards.assert_called_once()

                    # Verify cache and bot
                    mock_bot.assert_called_with(token='test-token')
                    mock_cache_init.assert_called_once()

                    # Check that state is updated
                    self.assertEqual(self.app.state.file_uploader_bot, mock_bot_instance)

                mock_gather.assert_called_once()
                mock_close_pool.assert_called_once()
            finally:
                logger.setLevel(old_level)

    @patch('Dubsite_tgach.main.create_pool', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.initialize_database', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.sync_boards_with_config', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.get_db_connection')
    async def test_lifespan_missing_env(self, mock_get_db, mock_sync_boards, mock_init_db, mock_create_pool):
        main_module.FILE_UPLOADER_BOT_TOKEN = None

        @asynccontextmanager
        async def dummy_db_conn():
            conn = AsyncMock()
            cursor = AsyncMock()
            cursor.__aiter__.return_value = []

            @asynccontextmanager
            async def dummy_cursor(*args, **kwargs):
                yield cursor

            conn.execute = dummy_cursor
            yield conn

        mock_get_db.side_effect = dummy_db_conn

        with self.assertRaises(ValueError) as context:
            async with lifespan(self.app):
                pass
        self.assertIn("Missing FILE_UPLOADER_BOT_TOKEN", str(context.exception))

if __name__ == '__main__':
    unittest.main()
