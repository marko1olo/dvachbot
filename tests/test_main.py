import sys
import os
import unittest
import types
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


# Setup required env var
os.environ["SECRET_KEY"] = "test-secret-key-12345"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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
    'bs4', 'slowapi', 'slowapi.util', 'slowapi.errors', 'uvicorn',
    'fastapi_cache', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator', 'geoip2', 'geoip2.database', 'aiogram',
    'aiogram.types', 'aiogram.exceptions', 'aiogram.enums', 'aiogram.client',
    'aiogram.client.session', 'aiogram.client.session.aiohttp', 'common.bot_pool',
    'aiogram.webhook', 'aiogram.webhook.aiohttp_server'
]

for dep in mocked_deps:
    mock_module(dep)

# Return MagicMock for any attribute access on our mocked modules
for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        class SiteTgachMock(MagicMock):
            def __await__(self):
                async def dummy(): return self
                return dummy().__await__()
        sys.modules[mod_name].__getattr__ = lambda name: SiteTgachMock()

# Now we can safely import the function under test
from Dubsite_tgach.main import get_real_ip

class StubClient:
    def __init__(self, host):
        self.host = host

class StubRequest:
    def __init__(self, headers=None, client_host=None):
        self.headers = headers or {}
        self.client = StubClient(client_host)

class TestGetRealIp(unittest.TestCase):
    def test_x_real_ip_preferred(self):
        """Test that x-real-ip is used if available."""
        request = StubRequest(
            headers={"x-real-ip": "1.2.3.4", "x-forwarded-for": "5.6.7.8"},
            client_host="9.10.11.12"
        )
        self.assertEqual(get_real_ip(request), "1.2.3.4")

    def test_x_forwarded_for_fallback(self):
        """Test that x-forwarded-for is used if x-real-ip is not available."""
        request = StubRequest(
            headers={"x-forwarded-for": "5.6.7.8"},
            client_host="9.10.11.12"
        )
        self.assertEqual(get_real_ip(request), "5.6.7.8")

    def test_x_forwarded_for_multiple_ips(self):
        """Test that only the first IP from x-forwarded-for is returned."""
        request = StubRequest(
            headers={"x-forwarded-for": "5.6.7.8, 10.0.0.1"},
            client_host="9.10.11.12"
        )
        self.assertEqual(get_real_ip(request), "5.6.7.8")

    def test_client_host_fallback(self):
        """Test that client.host is used if no relevant headers are present."""
        request = StubRequest(
            headers={},
            client_host="9.10.11.12"
        )
        self.assertEqual(get_real_ip(request), "9.10.11.12")

    def test_empty_headers_values(self):
        """Test that empty string header values correctly fall back to client.host."""
        request = StubRequest(
            headers={"x-real-ip": "", "x-forwarded-for": ""},
            client_host="9.10.11.12"
        )
        self.assertEqual(get_real_ip(request), "9.10.11.12")


from Dubsite_tgach.main import clean_title_text

class TestCleanTitleText(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(clean_title_text(""), "")
        self.assertEqual(clean_title_text(None), "")

    def test_remove_html_tags(self):
        self.assertEqual(clean_title_text("<h1>Hello</h1>"), "Hello")
        self.assertEqual(clean_title_text("<p>Some <b>bold</b> text</p>"), "Some bold text")

    def test_remove_brackets(self):
        self.assertEqual(clean_title_text("This is [some tag] text"), "This is text")
        self.assertEqual(clean_title_text("[Prefix] Just the title"), "Just the title")

    def test_excessive_whitespace(self):
        self.assertEqual(clean_title_text("   Too   much   space   "), "Too much space")
        self.assertEqual(clean_title_text("New\nlines\tand\ttabs"), "New lines and tabs")

    def test_combined(self):
        self.assertEqual(
            clean_title_text("\n\n [Tag]   <h1>  Super Title  </h1>   [123] \t"),
            "Super Title"
        )
        self.assertEqual(
            clean_title_text("Title with <a href='https://example.com'>link</a> and [brackets]"),
            "Title with link and"
        )

if __name__ == "__main__":
    unittest.main()

from Dubsite_tgach.main import format_bayan_label

class TestFormatBayanLabel(unittest.TestCase):
    @patch('Dubsite_tgach.main.random.choice')
    def test_bayan_low(self, mock_choice):
        mock_choice.return_value = "Mocked_Low"
        # 2 and 3 should be 'low'
        self.assertEqual(format_bayan_label(2), "♻️ Mocked_Low (2)")
        self.assertEqual(format_bayan_label(3), "♻️ Mocked_Low (3)")
        # Make sure the phrases are chosen properly by looking at what was passed
        self.assertEqual(len(mock_choice.call_args[0][0]), 3) # "bayan_low" array in RU has 3 items

    @patch('Dubsite_tgach.main.random.choice')
    def test_bayan_mid(self, mock_choice):
        mock_choice.return_value = "Mocked_Mid"
        # 4 to 10 should be 'mid'
        self.assertEqual(format_bayan_label(4), "♻️ Mocked_Mid (4)")
        self.assertEqual(format_bayan_label(10), "♻️ Mocked_Mid (10)")

    @patch('Dubsite_tgach.main.random.choice')
    def test_bayan_high(self, mock_choice):
        mock_choice.return_value = "Mocked_High"
        # > 10 should be 'high'
        self.assertEqual(format_bayan_label(11), "♻️ Mocked_High (11)")
        self.assertEqual(format_bayan_label(100), "♻️ Mocked_High (100)")

    def test_bayan_count_zero_or_one(self):
        # 0 or 1 should return empty string
        self.assertEqual(format_bayan_label(0), "")
        self.assertEqual(format_bayan_label(1), "")
        self.assertEqual(format_bayan_label(-1), "")

    @patch('Dubsite_tgach.main.random.choice')
    def test_bayan_language_fallback(self, mock_choice):
        mock_choice.return_value = "Mocked_Eng"
        # English translations are present
        res = format_bayan_label(5, lang='en')
        self.assertEqual(res, "♻️ Mocked_Eng (5)")
        # Assuming the fallback logic works for a missing lang
        res = format_bayan_label(5, lang='missing_lang')
        self.assertEqual(res, "♻️ Mocked_Eng (5)")

from Dubsite_tgach.main import get_country_by_ip

class TestGetCountryByIp(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        asyncio.set_event_loop(asyncio.new_event_loop())

    async def asyncSetUp(self):
        if hasattr(get_country_by_ip, 'cache_clear'):
            get_country_by_ip.cache_clear()

    @patch('Dubsite_tgach.main.GEOIP_READER')
    @patch('Dubsite_tgach.main.AsyncHTTPTransport')
    async def test_get_country_by_ip_httpx_fallback(self, mock_transport, mock_geoip):
        mock_geoip.country.side_effect = Exception("GeoIP Error")

        with patch('Dubsite_tgach.main.httpx.AsyncClient', autospec=True) as mock_async_client_class:
            mock_client_instance = mock_async_client_class.return_value.__aenter__.return_value

            # 1. Test Exception raising during HTTP request
            # Needs side_effect to be called twice due to multiple proxies failing
            mock_client_instance.get = AsyncMock(side_effect=Exception("HTTPX Error"))
            country = await get_country_by_ip("8.8.8.8")
            self.assertEqual(country, "XX")
            if hasattr(get_country_by_ip, 'cache_clear'):
                get_country_by_ip.cache_clear()

            # 2. Test 200 response
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'countryCode': 'US'}
            # We want it to just return this value
            mock_client_instance.get = AsyncMock(return_value=mock_resp)

            country = await get_country_by_ip("8.8.8.8")
            self.assertEqual(country, "US")
            if hasattr(get_country_by_ip, 'cache_clear'):
                get_country_by_ip.cache_clear()

            # 3. Test non-200 response
            mock_resp_500 = MagicMock()
            mock_resp_500.status_code = 500
            # Needs to return 500 twice for proxy and direct
            mock_client_instance.get = AsyncMock(return_value=mock_resp_500)

            country = await get_country_by_ip("8.8.8.8")
            self.assertEqual(country, "XX")
