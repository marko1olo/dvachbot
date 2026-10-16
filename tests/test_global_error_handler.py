import sys
import os
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio
import aiohttp
from aiogram.exceptions import (
    TelegramNetworkError,
    TelegramForbiddenError,
    TelegramConflictError,
    TelegramBadRequest,
    TelegramRetryAfter,
)
from aiogram import types

# Setup required env var
os.environ["SECRET_KEY"] = "test-secret-key-12345"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import types as pytypes

def mock_module(name):
    mod = pytypes.ModuleType(name)
    mod.__path__ = [] # makes it a package
    sys.modules[name] = mod
    return mod

# Mock heavy/missing dependencies to allow import
mocked_deps = [
    'site_tgach', 'site_tgach.mirror_worker', 'site_tgach.tagging_worker',
    'site_tgach.security', 'site_tgach.image_processing', 'site_tgach.catbox',
    'site_tgach.neuro_poster', 'site_tgach.rss', 'site_tgach.backup',
    'site_tgach.importer', 'site_tgach.neuro_scanner', 'site_tgach.admin_config',
    'site_tgach.voice_processing', 'warhammer_mode', 'japanese_translator',
    'slowapi', 'slowapi.util', 'slowapi.errors', 'async_lru', 'uvicorn',
    'fastapi', 'fastapi.responses', 'fastapi.middleware', 'fastapi.middleware.cors',
    'fastapi.middleware.trustedhost', 'fastapi.middleware.gzip',
    'fastapi.staticfiles', 'fastapi.templating', 'fastapi.exceptions',
    'fastapi_cache', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator', 'geoip2', 'geoip2.database', 'aiosqlite',
    'orjson', 'pydantic',
    'openai', 'pyrogram', 'pyrogram.errors', 'pyrogram.types'
]

for dep in mocked_deps:
    mock_module(dep)

# Return MagicMock for any attribute access on our mocked modules
for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        sys.modules[mod_name].__getattr__ = lambda name: MagicMock()

from main import global_error_handler

class TestGlobalErrorHandler(unittest.IsolatedAsyncioTestCase):

    @patch('main.print')
    async def test_no_exception_no_update(self, mock_print):
        event = MagicMock(spec=types.ErrorEvent)
        event.exception = None
        event.update = None

        result = await global_error_handler(event)

        self.assertTrue(result)
        mock_print.assert_called_with("⚠️ Получено событие без исключения и без update")

    @patch('main.print')
    async def test_no_exception_with_update(self, mock_print):
        event = MagicMock(spec=types.ErrorEvent)
        event.exception = None
        event.update = MagicMock()
        event.update.update_id = 123
        event.update.message = MagicMock()
        event.update.message.from_user.id = 456

        result = await global_error_handler(event)

        self.assertTrue(result)
        mock_print.assert_called_with("⚠️ Event without exception: Update 123 from user 456")

    @patch('main.print')
    async def test_network_errors(self, mock_print):
        exceptions = [
            TelegramNetworkError(message="network", method=MagicMock()),
            aiohttp.ClientConnectorError(MagicMock(), MagicMock()),
            asyncio.TimeoutError(),
            TelegramRetryAfter(message="retry", retry_after=10, method=MagicMock())
        ]

        for exc in exceptions:
            event = MagicMock(spec=types.ErrorEvent)
            event.exception = exc
            event.update = None

            result = await global_error_handler(event)

            self.assertTrue(result)
            mock_print.assert_called_with(f"🌐 Перехвачена штатная сетевая ошибка/флуд-контроль: {type(exc).__name__}: {exc}. Выполнение не блокируется.")

    @patch('main._handle_telegram_forbidden_error', new_callable=AsyncMock)
    async def test_telegram_forbidden_error(self, mock_handle):
        event = MagicMock(spec=types.ErrorEvent)
        event.exception = TelegramForbiddenError(message="forbidden", method=MagicMock())
        event.update = MagicMock()

        result = await global_error_handler(event)

        self.assertTrue(result)
        mock_handle.assert_called_once_with(event.update)

    @patch('main.asyncio.sleep', new_callable=AsyncMock)
    @patch('main.print')
    async def test_telegram_conflict_error(self, mock_print, mock_sleep):
        event = MagicMock(spec=types.ErrorEvent)
        event.exception = TelegramConflictError(message="conflict", method=MagicMock())
        event.update = None

        result = await global_error_handler(event)

        self.assertTrue(result)
        mock_print.assert_called_with(f"🌐 Конфликт: {event.exception}. Возможно, запущен другой экземпляр бота.")
        mock_sleep.assert_called_once_with(10)

    @patch('main._handle_telegram_bad_request', new_callable=AsyncMock)
    async def test_telegram_bad_request(self, mock_handle):
        event = MagicMock(spec=types.ErrorEvent)
        event.exception = TelegramBadRequest(message="bad request", method=MagicMock())
        event.update = MagicMock()

        result = await global_error_handler(event)

        self.assertTrue(result)
        mock_handle.assert_called_once_with(event.exception, event.update)

    @patch('main._handle_unhandled_exception', new_callable=AsyncMock)
    async def test_unhandled_exception(self, mock_handle):
        event = MagicMock(spec=types.ErrorEvent)
        event.exception = ValueError("some unhandled error")
        event.update = MagicMock()

        result = await global_error_handler(event)

        self.assertTrue(result)
        mock_handle.assert_called_once_with(event.exception, event.update)

if __name__ == '__main__':
    unittest.main()
