import sys
import os
import unittest
import time
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
    'site_tgach.html_sanitizer',
    'site_tgach.voice_processing', 'warhammer_mode', 'japanese_translator',
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

from Dubsite_tgach.main import custom_access_log_middleware, KNOWN_IPS

for _dep, _previous in _SAVED_MODULES.items():
    if _previous is None:
        sys.modules.pop(_dep, None)
    else:
        sys.modules[_dep] = _previous
del _dep, _previous

class TestCustomAccessLogMiddleware(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        KNOWN_IPS.clear()

    def create_mock_request(self, path, method="GET", headers=None):
        req = MagicMock()
        req.url.path = path
        req.method = method
        req.headers.get.side_effect = lambda k: (headers or {}).get(k)
        return req

    @patch('Dubsite_tgach.main.get_real_ip', return_value="1.2.3.4")
    async def test_ignored_prefix(self, mock_get_ip):
        req = self.create_mock_request("/api/server/pulse")
        call_next = AsyncMock()

        await custom_access_log_middleware(req, call_next)

        call_next.assert_awaited_once_with(req)
        mock_get_ip.assert_not_called()

    @patch('Dubsite_tgach.main.get_real_ip', return_value="1.2.3.4")
    async def test_ignored_substring(self, mock_get_ip):
        req = self.create_mock_request("/some/path/wp-admin")
        call_next = AsyncMock()

        await custom_access_log_middleware(req, call_next)

        call_next.assert_awaited_once_with(req)
        mock_get_ip.assert_not_called()

    @patch('Dubsite_tgach.main.get_real_ip', return_value="1.2.3.4")
    @patch('Dubsite_tgach.main.get_country_by_ip', new_callable=AsyncMock, return_value="US")
    @patch('Dubsite_tgach.main.v_logger.info')
    @patch('Dubsite_tgach.main.time.time', side_effect=[1000.0, 1000.5])
    @patch('builtins.print')
    async def test_new_ip_logging(self, mock_print, mock_time, mock_v_logger_info, mock_get_country, mock_get_ip):
        req = self.create_mock_request("/")
        call_next = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        call_next.return_value = mock_response

        await custom_access_log_middleware(req, call_next)

        self.assertIn("1.2.3.4", KNOWN_IPS)
        mock_get_country.assert_awaited_once_with("1.2.3.4")
        mock_v_logger_info.assert_any_call("[ENTER] 1.2.3.4 (US)")
        mock_v_logger_info.assert_any_call("[DO] 1.2.3.4 | Main page")

    @patch('Dubsite_tgach.main.get_real_ip', return_value="1.2.3.4")
    @patch('Dubsite_tgach.main.get_country_by_ip', new_callable=AsyncMock)
    @patch('Dubsite_tgach.main.v_logger.info')
    @patch('Dubsite_tgach.main.time.time', side_effect=[1000.0, 1000.5])
    @patch('builtins.print')
    async def test_known_ip_no_enter_log(self, mock_print, mock_time, mock_v_logger_info, mock_get_country, mock_get_ip):
        KNOWN_IPS.add("1.2.3.4")

        req = self.create_mock_request("/")
        call_next = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        call_next.return_value = mock_response

        await custom_access_log_middleware(req, call_next)

        mock_get_country.assert_not_called()

    @patch('Dubsite_tgach.main.get_real_ip', return_value="1.2.3.4")
    @patch('Dubsite_tgach.main.v_logger.info')
    @patch('builtins.print')
    async def test_action_parsing(self, mock_print, mock_v_logger_info, mock_get_ip):
        KNOWN_IPS.add("1.2.3.4")

        cases = [
            ("/", "Main page"),
            ("/b/res/123", "Reading /b/ #123"),
            ("/b/threads/", "Browsing /b/"),
            ("/overboard/abc", "Overboard"),
            ("/api/post/b", "POSTING to /b/"),
            ("/some/other", "GET /some/other")
        ]

        for path, expected_action in cases:
            req = self.create_mock_request(path)
            call_next = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {}
            call_next.return_value = mock_response

            await custom_access_log_middleware(req, call_next)

            mock_v_logger_info.assert_called_with(f"[DO] 1.2.3.4 | {expected_action}")

    @patch('Dubsite_tgach.main.get_real_ip', return_value="1.2.3.4")
    @patch('Dubsite_tgach.main.logger.warning')
    @patch('builtins.print')
    async def test_403_logging(self, mock_print, mock_logger_warning, mock_get_ip):
        KNOWN_IPS.add("1.2.3.4")

        req = self.create_mock_request("/test", headers={"user-agent": "test-agent"})
        call_next = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {}
        call_next.return_value = mock_response

        await custom_access_log_middleware(req, call_next)

        mock_logger_warning.assert_called_once_with("🚫 403 FORBIDDEN: IP=1.2.3.4 Path=/test UA=test-agent")

    @patch('Dubsite_tgach.main.get_real_ip', return_value="1.2.3.4")
    @patch('builtins.print')
    async def test_redirect_tag(self, mock_print, mock_get_ip):
        KNOWN_IPS.add("1.2.3.4")

        cases = [
            (302, {"location": "https://huggingface.co/model"}, "-> [HF]"),
            (301, {"location": "https://catbox.moe/file"}, "-> [CB]"),
            (307, {"location": "https://api.telegram.org/bot"}, "-> [TG]"),
            (302, {"location": "https://example.com"}, "-> [OTHER]"),
            (200, {}, "")
        ]

        for status, headers, expected_tag in cases:
            req = self.create_mock_request("/test")
            call_next = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = status
            mock_response.headers = headers
            call_next.return_value = mock_response

            await custom_access_log_middleware(req, call_next)

            # Check print args
            print_args = mock_print.call_args[0][0]
            if expected_tag:
                self.assertIn(expected_tag, print_args)

    @patch('Dubsite_tgach.main.get_real_ip', return_value="1.2.3.4")
    @patch('builtins.print')
    async def test_files_path_print(self, mock_print, mock_get_ip):
        KNOWN_IPS.add("1.2.3.4")

        req = self.create_mock_request("/files/test.jpg")
        call_next = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        call_next.return_value = mock_response

        await custom_access_log_middleware(req, call_next)

        print_args = mock_print.call_args[0][0]
        self.assertIn("file accepted", print_args)

if __name__ == '__main__':
    unittest.main()
