import sys
import os
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

# Setup required env var
os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import types
def mock_module(name):
    mod = types.ModuleType(name)
    mod.__path__ = [] # makes it a package
    sys.modules[name] = mod
    return mod

# Mock heavy/missing dependencies to allow import
mocked_deps = [
    'site_tgach', 'site_tgach.mirror_worker', 'site_tgach.tagging_worker',
    'site_tgach.security', 'site_tgach.image_processing', 'site_tgach.catbox',
    'site_tgach.neuro_poster', 'site_tgach.rss', 'site_tgach.backup',
    'site_tgach.importer', 'site_tgach.neuro_scanner', 'site_tgach.admin_config',
    'site_tgach.voice_processing', 'site_tgach.html_sanitizer', 'warhammer_mode', 'japanese_translator',
    'slowapi', 'slowapi.util', 'slowapi.errors', 'uvicorn',
    'fastapi_cache', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator', 'aiogram',
    'aiogram.types', 'aiogram.exceptions', 'aiogram.enums', 'aiogram.client',
    'aiogram.client.session', 'aiogram.client.session.aiohttp', 'common.bot_pool',
    'aiogram.webhook', 'aiogram.webhook.aiohttp_server'
]

_SAVED_MODULES = {dep: sys.modules.get(dep) for dep in mocked_deps + ['async_lru']}

for dep in mocked_deps:
    mock_module(dep)

# Return MagicMock for any attribute access on our mocked modules
for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        sys.modules[mod_name].__getattr__ = lambda name: MagicMock()

sys.modules['async_lru'] = types.ModuleType('async_lru')
sys.modules['async_lru'].alru_cache = lambda *args, **kwargs: lambda func: func

from Dubsite_tgach.main import is_request_from_ru

for _dep, _previous in _SAVED_MODULES.items():
    if _previous is None:
        sys.modules.pop(_dep, None)
    else:
        sys.modules[_dep] = _previous
del _dep, _previous

class TestIsRequestFromRu(unittest.IsolatedAsyncioTestCase):
    @patch('Dubsite_tgach.main.get_real_ip')
    @patch('Dubsite_tgach.main.get_country_by_ip')
    async def test_request_from_ru(self, mock_get_country, mock_get_ip):
        mock_get_ip.return_value = "8.8.8.8"
        mock_get_country.return_value = "RU"
        mock_request = MagicMock()

        result = await is_request_from_ru(mock_request)
        self.assertTrue(result)
        mock_get_ip.assert_called_once_with(mock_request)
        mock_get_country.assert_called_once_with("8.8.8.8")

    @patch('Dubsite_tgach.main.get_real_ip')
    @patch('Dubsite_tgach.main.get_country_by_ip')
    async def test_request_not_from_ru(self, mock_get_country, mock_get_ip):
        mock_get_ip.return_value = "8.8.8.8"
        mock_get_country.return_value = "US"
        mock_request = MagicMock()

        result = await is_request_from_ru(mock_request)
        self.assertFalse(result)
        mock_get_ip.assert_called_once_with(mock_request)
        mock_get_country.assert_called_once_with("8.8.8.8")

    @patch('Dubsite_tgach.main.get_real_ip')
    @patch('Dubsite_tgach.main.get_country_by_ip')
    async def test_request_local(self, mock_get_country, mock_get_ip):
        mock_get_ip.return_value = "127.0.0.1"
        mock_get_country.return_value = "XX"
        mock_request = MagicMock()

        result = await is_request_from_ru(mock_request)
        self.assertFalse(result)
        mock_get_ip.assert_called_once_with(mock_request)
        mock_get_country.assert_called_once_with("127.0.0.1")

if __name__ == '__main__':
    unittest.main()
