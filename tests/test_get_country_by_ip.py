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
    'site_tgach.voice_processing', 'warhammer_mode', 'japanese_translator',
    'slowapi', 'slowapi.util', 'slowapi.errors', 'uvicorn',
    'fastapi_cache', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator', 'aiogram',
    'aiogram.types', 'aiogram.exceptions', 'aiogram.enums', 'aiogram.client',
    'aiogram.client.session', 'aiogram.client.session.aiohttp', 'common.bot_pool',
    'aiogram.webhook', 'aiogram.webhook.aiohttp_server'
]

for dep in mocked_deps:
    mock_module(dep)

# Return MagicMock for any attribute access on our mocked modules
for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        sys.modules[mod_name].__getattr__ = lambda name: MagicMock()

# Instead of MagicMocking async_lru which makes get_country_by_ip non-awaitable, just bypass it
sys.modules['async_lru'] = types.ModuleType('async_lru')
sys.modules['async_lru'].alru_cache = lambda *args, **kwargs: lambda func: func

from Dubsite_tgach.main import get_country_by_ip

class TestGetCountryByIp(unittest.IsolatedAsyncioTestCase):
    async def test_local_ip(self):
        self.assertEqual(await get_country_by_ip("127.0.0.1"), "XX")

    @patch('Dubsite_tgach.main.GEOIP_READER')
    async def test_geoip_reader_raises_exception(self, mock_geoip_reader):
        mock_geoip_reader.country.side_effect = Exception("Test Exception")
        # should fall back to httpx if geoip fails

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'countryCode': 'YY'}
            mock_get.return_value = mock_response

            result = await get_country_by_ip("8.8.8.8")
            self.assertEqual(result, "YY")


    @patch('Dubsite_tgach.main.GEOIP_READER')
    async def test_httpx_raises_exception_both_strategies(self, mock_geoip_reader):
        mock_geoip_reader.country.side_effect = Exception("GeoIP Exception")

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("HTTPX Exception")

            result = await get_country_by_ip("8.8.8.8")
            self.assertEqual(result, "XX")

            # Since there are 2 strategies (Proxy and Direct), it should attempt 2 calls
            self.assertEqual(mock_get.call_count, 2)

    @patch('Dubsite_tgach.main.GEOIP_READER')
    async def test_httpx_first_strategy_fails_second_succeeds(self, mock_geoip_reader):
        mock_geoip_reader.country.side_effect = Exception("GeoIP Exception")

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            # First call raises exception, second returns 200 OK
            mock_success_response = MagicMock()
            mock_success_response.status_code = 200
            mock_success_response.json.return_value = {'countryCode': 'ZZ'}

            mock_get.side_effect = [Exception("Proxy Failed"), mock_success_response]

            result = await get_country_by_ip("8.8.8.8")
            self.assertEqual(result, "ZZ")
            self.assertEqual(mock_get.call_count, 2)
if __name__ == '__main__':
    unittest.main()
