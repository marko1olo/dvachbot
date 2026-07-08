import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "123:test"

import types
def mock_module(name):
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    mod.__path__ = []
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
    'openai', 'pyrogram', 'pyrogram.errors', 'pyrogram.types'
]

for dep in mocked_deps:
    mock_module(dep)

# Return MagicMock for any attribute access on our mocked modules
for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        if not hasattr(sys.modules[mod_name], '__getattr__'):
            sys.modules[mod_name].__getattr__ = lambda name: MagicMock()

import async_lru
def dummy_alru_cache(*args, **kwargs):
    def decorator(func):
        return func
    return decorator
async_lru.alru_cache = dummy_alru_cache

# Bypass StopIteration error when aiogram unpacks MagicMocks during import
# This is explicitly requested in Memory.

import unittest.mock


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# Re-apply patch right before importing main
import unittest.mock
def infinite_iter(self):
    while True:
        yield unittest.mock.MagicMock()
unittest.mock.MagicMock.__iter__ = infinite_iter
import main

import common.db_pool

class TestCmdShoot(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = main
        cls.db_pool = common.db_pool

    def setUp(self):
        self.message = AsyncMock()
        self.message.from_user.id = 123
        self.board_id = "test_board"

    async def test_no_board_id(self):
        await self.main.cmd_shoot(self.message, board_id=None)
        self.message.answer.assert_not_called()

    async def test_no_reply(self):
        self.message.reply_to_message = None
        await self.main.cmd_shoot(self.message, board_id=self.board_id)
        self.message.answer.assert_called_with("⚠️ Сделай Reply на пост жертвы с командой /shoot!")

    @patch('common.db_pool.get_pool', new_callable=AsyncMock)
    @patch('main._get_user_active_items')
    async def test_no_mute_gun(self, mock_get_items, mock_get_pool):
        self.message.reply_to_message = MagicMock()
        mock_get_pool.return_value = AsyncMock()
        mock_get_items.return_value = {} # No mute_gun

        await self.main.cmd_shoot(self.message, board_id=self.board_id)
        self.message.answer.assert_called_with("У тебя нет Мут-Гана! Купи его в магазине: /shop")

    @patch('common.db_pool.get_pool', new_callable=AsyncMock)
    @patch('main._get_user_active_items')
    @patch('main.get_author_id_by_reply')
    async def test_no_target_id(self, mock_get_author, mock_get_items, mock_get_pool):
        self.message.reply_to_message = MagicMock()
        mock_get_pool.return_value = AsyncMock()
        mock_get_items.return_value = {"mute_gun": True}
        mock_get_author.return_value = 0 # Cannot find author

        await self.main.cmd_shoot(self.message, board_id=self.board_id)
        self.message.answer.assert_called_with("🚫 Не удалось найти автора поста...")

    @patch('common.db_pool.get_pool', new_callable=AsyncMock)
    @patch('main._get_user_active_items')
    @patch('main.get_author_id_by_reply')
    async def test_shoot_self(self, mock_get_author, mock_get_items, mock_get_pool):
        self.message.reply_to_message = MagicMock()
        mock_get_pool.return_value = AsyncMock()
        mock_get_items.return_value = {"mute_gun": True}
        mock_get_author.return_value = 123 # Target == User

        await self.main.cmd_shoot(self.message, board_id=self.board_id)
        self.message.answer.assert_called_with("Ты пытаешься выстрелить в самого себя? Идиот.")

    @patch('common.db_pool.get_pool', new_callable=AsyncMock)
    @patch('main._get_user_active_items')
    @patch('main.get_author_id_by_reply')
    @patch('main._handle_shoot_bounce')
    @patch('main.time.time')
    async def test_shoot_bounce(self, mock_time, mock_handle_bounce, mock_get_author, mock_get_items, mock_get_pool):
        self.message.reply_to_message = MagicMock()
        db_mock = AsyncMock()
        mock_get_pool.return_value = db_mock

        user_items = {"mute_gun": True}
        target_items = {"reflect_shield_until": 2000}

        # mock_get_items is called twice: first for user, then for target
        mock_get_items.side_effect = [user_items, target_items]

        mock_get_author.return_value = 456
        mock_time.return_value = 1000 # reflect_shield_until > current_time

        await self.main.cmd_shoot(self.message, board_id=self.board_id)

        mock_handle_bounce.assert_called_once_with(
            self.message, db_mock, self.db_pool.db_lock, self.board_id, 123, 456, user_items, target_items
        )

    @patch('common.db_pool.get_pool', new_callable=AsyncMock)
    @patch('main._get_user_active_items')
    @patch('main.get_author_id_by_reply')
    @patch('main._handle_shoot_success')
    @patch('main.time.time')
    async def test_shoot_success(self, mock_time, mock_handle_success, mock_get_author, mock_get_items, mock_get_pool):
        self.message.reply_to_message = MagicMock()
        db_mock = AsyncMock()
        mock_get_pool.return_value = db_mock

        user_items = {"mute_gun": True}
        target_items = {"reflect_shield_until": 500}

        # mock_get_items is called twice: first for user, then for target
        mock_get_items.side_effect = [user_items, target_items]

        mock_get_author.return_value = 456
        mock_time.return_value = 1000 # reflect_shield_until < current_time (no shield)

        await self.main.cmd_shoot(self.message, board_id=self.board_id)

        mock_handle_success.assert_called_once_with(
            self.message, db_mock, self.db_pool.db_lock, self.board_id, 123, 456, user_items
        )
