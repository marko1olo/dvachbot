import sys
import os
import unittest
import types
from unittest.mock import MagicMock, AsyncMock, patch

# Setup required env var
os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"
os.environ["DB_USER"] = "test"
os.environ["DB_PASS"] = "test"
os.environ["DB_HOST"] = "localhost"
os.environ["DB_NAME"] = "test"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def mock_module(name):
    mod = types.ModuleType(name)
    mod.__path__ = [] # makes it a package
    sys.modules[name] = mod
    return mod

mocked_deps = [
    'site_tgach', 'site_tgach.mirror_worker', 'site_tgach.tagging_worker',
    'site_tgach.security', 'site_tgach.image_processing', 'site_tgach.catbox',
    'site_tgach.neuro_poster', 'site_tgach.rss', 'site_tgach.backup',
    'site_tgach.importer', 'site_tgach.neuro_scanner', 'site_tgach.admin_config',
    'site_tgach.voice_processing', 'site_tgach.html_sanitizer', 'warhammer_mode', 'japanese_translator',
    'slowapi', 'slowapi.util', 'slowapi.errors', 'async_lru', 'uvicorn',
    'fastapi', 'fastapi.responses', 'fastapi.middleware', 'fastapi.middleware.cors',
    'fastapi.middleware.trustedhost', 'fastapi.middleware.gzip',
    'fastapi.staticfiles', 'fastapi.templating', 'fastapi.exceptions',
    'fastapi_cache', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator', 'geoip2', 'geoip2.database', 'aiosqlite', 'aiogram',
    'aiogram.types', 'aiogram.exceptions', 'aiogram.enums', 'aiogram.client',
    'aiogram.client.default', 'aiogram.client.session', 'aiogram.client.session.aiohttp', 'common.bot_pool',
    'aiogram.filters', 'aiogram.fsm', 'aiogram.fsm.context', 'aiogram.fsm.state', 'aiogram.fsm.storage', 'aiogram.fsm.storage.memory',
    'aiogram.webhook', 'aiogram.webhook.aiohttp_server', 'orjson', 'pydantic',
    'aiogram.utils', 'aiogram.utils.media_group', 'aiogram.utils.keyboard',
    'openai', 'pyrogram', 'pyrogram.errors', 'pyrogram.types'
]

for dep in mocked_deps:
    mock_module(dep)

for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        sys.modules[mod_name].__getattr__ = lambda name: MagicMock()

class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
sys.modules['fastapi'].HTTPException = HTTPException

import asyncio
import time
import Dubsite_tgach.main
from Dubsite_tgach.main import check_and_punish_site_spam, site_spam_tracker

class TestCheckAndPunishSiteSpam(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        site_spam_tracker.clear()

    @patch('Dubsite_tgach.main.apply_regular_mute', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.log_system_event')
    async def test_casino_spam(self, mock_log, mock_mute):
        t_mock = MagicMock(side_effect=lambda key, default=None: default[0] if isinstance(default, list) else (default if default else key))

        with self.assertRaises(HTTPException) as cm:
            await check_and_punish_site_spam("b", 123, " 🎲 ", [], t_mock)

        self.assertEqual(cm.exception.status_code, 400)
        mock_mute.assert_awaited_once_with(123, "b", 60)
        mock_log.assert_called_once()

    @patch('Dubsite_tgach.main.apply_regular_mute', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.time.time')
    async def test_text_spam_max_per_window(self, mock_time, mock_mute):
        t_mock = MagicMock()
        base_time = 1000.0

        max_msgs = Dubsite_tgach.main.SITE_SPAM_RULES['text']['max_per_window']
        penalty = Dubsite_tgach.main.SITE_SPAM_RULES['text']['penalty_seconds']

        for i in range(max_msgs - 1):
            mock_time.return_value = base_time + i
            await check_and_punish_site_spam("b", 123, f"msg{i}", [], t_mock)

        mock_time.return_value = base_time + max_msgs - 1
        with self.assertRaises(HTTPException) as cm:
            await check_and_punish_site_spam("b", 123, f"msg{max_msgs - 1}", [], t_mock)

        self.assertEqual(cm.exception.status_code, 429)
        mock_mute.assert_awaited_once_with(123, "b", penalty)

    @patch('Dubsite_tgach.main.apply_regular_mute', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.time.time')
    async def test_text_spam_max_repeats(self, mock_time, mock_mute):
        t_mock = MagicMock()
        base_time = 1000.0

        max_repeats = Dubsite_tgach.main.SITE_SPAM_RULES['text']['max_repeats']
        penalty = Dubsite_tgach.main.SITE_SPAM_RULES['text']['penalty_seconds']

        for i in range(max_repeats - 1):
            mock_time.return_value = base_time + i
            await check_and_punish_site_spam("b", 123, "spam text", [], t_mock)

        mock_time.return_value = base_time + max_repeats - 1
        with self.assertRaises(HTTPException) as cm:
            await check_and_punish_site_spam("b", 123, "spam text", [], t_mock)

        self.assertEqual(cm.exception.status_code, 429)
        mock_mute.assert_awaited_once_with(123, "b", penalty)

    @patch('Dubsite_tgach.main.apply_regular_mute', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.time.time')
    async def test_file_spam_max_per_window(self, mock_time, mock_mute):
        t_mock = MagicMock()
        base_time = 1000.0

        class MockFile:
            def __init__(self, c):
                self.c = c
            async def seek(self, pos): pass
            async def read(self): return self.c

        max_files = Dubsite_tgach.main.SITE_SPAM_RULES['files']['max_per_window']
        penalty = Dubsite_tgach.main.SITE_SPAM_RULES['files']['penalty_seconds']

        for i in range(max_files - 1):
            mock_time.return_value = base_time + i
            # Using empty string for text so we don't trigger text spam filter
            await check_and_punish_site_spam("b", 123, "", [MockFile(f"content{i}".encode())], t_mock)

        mock_time.return_value = base_time + max_files - 1
        with self.assertRaises(HTTPException) as cm:
            await check_and_punish_site_spam("b", 123, "", [MockFile(f"content{max_files - 1}".encode())], t_mock)

        self.assertEqual(cm.exception.status_code, 429)
        mock_mute.assert_awaited_once_with(123, "b", penalty)

    @patch('Dubsite_tgach.main.apply_regular_mute', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.time.time')
    async def test_file_spam_max_repeats(self, mock_time, mock_mute):
        t_mock = MagicMock()
        base_time = 1000.0

        class MockFile:
            def __init__(self, c):
                self.c = c
            async def seek(self, pos): pass
            async def read(self): return self.c

        max_repeats = Dubsite_tgach.main.SITE_SPAM_RULES['files']['max_repeats']
        penalty = Dubsite_tgach.main.SITE_SPAM_RULES['files']['penalty_seconds']

        for i in range(max_repeats - 1):
            mock_time.return_value = base_time + i
            await check_and_punish_site_spam("b", 123, "", [MockFile(b"same_content")], t_mock)

        mock_time.return_value = base_time + max_repeats - 1
        with self.assertRaises(HTTPException) as cm:
            await check_and_punish_site_spam("b", 123, "", [MockFile(b"same_content")], t_mock)

        self.assertEqual(cm.exception.status_code, 429)
        mock_mute.assert_awaited_once_with(123, "b", penalty)

    @patch('Dubsite_tgach.main.apply_regular_mute', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.time.time')
    async def test_no_spam(self, mock_time, mock_mute):
        t_mock = MagicMock()
        base_time = 1000.0

        class MockFile:
            def __init__(self, c):
                self.c = c
            async def seek(self, pos): pass
            async def read(self): return self.c

        mock_time.return_value = base_time + 1
        await check_and_punish_site_spam("b", 123, "normal text", [MockFile(b"c1")], t_mock)

        mock_time.return_value = base_time + 2
        await check_and_punish_site_spam("b", 123, "another text", [MockFile(b"c2")], t_mock)

        mock_mute.assert_not_called()

if __name__ == '__main__':
    unittest.main()
