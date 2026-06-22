import sys
import types
from unittest.mock import MagicMock

# Setup required env var
import os
os.environ["SECRET_KEY"] = "test-secret-key-12345"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def mock_module(name):
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    mod.__path__ = [] # makes it a package
    sys.modules[name] = mod
    return mod

# Mock heavy/missing dependencies to allow import
mocked_deps = [
'fastapi',
    'starlette',
    'orjson',
    'pydantic',
    'jinja2',
    'httpx',
    'mutagen',
    'aiosqlite',
    'sqlalchemy',
    'aiohttp',
    'PIL',
    'itsdangerous',
    'passlib',
    'jose',
    'psutil',
    'cryptography',
    'msgspec',
    'matplotlib',
    'pandas',
    'numpy',
    'scipy',
    'seaborn',
    'networkx',
    'wordcloud',
    'aiogram',
    'openpyxl',
    'lxml',
    'openai',
    'tiktoken',
    'tenacity',
    'colorama',
    'apscheduler',
    'websockets',
    'watchdog',
    'markdown',
    'fastapi_cache.backends',
    'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator',
    'fastapi.responses',
    'fastapi.requests',
    'starlette.requests',
    'starlette.responses',
    'pydantic.main',
    'fastapi.middleware',
    'fastapi.middleware.trustedhost',
    'fastapi.middleware.cors',
    'fastapi.staticfiles',
    'fastapi.templating',
    'apscheduler.schedulers',
    'apscheduler.schedulers.asyncio',
    'fastapi.concurrency',
    'starlette.middleware',
    'starlette.middleware.base',
    'fastapi.security',
    'watchdog.observers',
    'watchdog.events',
    'markdown.extensions',
    'markdown.extensions.fenced_code',
    'mutagen.mp3',
    'mutagen.oggvorbis',
    'mutagen.mp4',
    'mutagen.flac',
    'fastapi.middleware.gzip',
    'sqlalchemy.ext',
    'sqlalchemy.ext.asyncio',
    'sqlalchemy.orm',
    'sqlalchemy.future',
    'sqlalchemy.pool',
    'starlette.middleware.sessions',
    'PIL.Image',
    'passlib.context',
    'jose.jwt',
    'starlette.types',
    'starlette.datastructures',
    'cryptography.hazmat',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.ciphers',
    'cryptography.hazmat.backends',
    'matplotlib.pyplot',
    'matplotlib.dates',
    'matplotlib.ticker',
    'matplotlib.font_manager',
    'scipy.interpolate',
    'aiogram.client.default',
    'aiogram.fsm',
    'aiogram.fsm.storage',
    'aiogram.fsm.storage.memory',
    'aiogram.fsm.strategy',
    'aiogram.filters',
    'aiogram.filters.command',
    'aiogram.types.message',
    'aiogram.types.inline_query',
    'aiogram.utils',
    'aiogram.utils.media_group',
    'aiogram.utils.keyboard',
    'aiogram.utils.markdown',
    'aiogram.exceptions',
    'aiogram.fsm.state',
    'aiogram.fsm.context',
    'xml.etree.ElementTree',
    'xml.etree',
    'site_tgach',
    'site_tgach.mirror_worker',
    'site_tgach.tagging_worker',
    'site_tgach.security',
    'site_tgach.image_processing',
    'site_tgach.catbox',
    'site_tgach.neuro_poster',
    'site_tgach.rss',
    'site_tgach.backup',
    'site_tgach.importer',
    'site_tgach.neuro_scanner',
    'site_tgach.admin_config',
    'site_tgach.voice_processing',
    'warhammer_mode',
    'japanese_translator',
    'bs4',
    'slowapi',
    'slowapi.util',
    'slowapi.errors',
    'async_lru',
    'uvicorn',
    'fastapi_cache',
    'geoip2',
    'geoip2.database',
    'aiogram.types',
    'aiogram.enums',
    'aiogram.client',
    'aiogram.client.session',
    'aiogram.client.session.aiohttp',
    'common.bot_pool',
    'aiogram.webhook',
    'aiogram.webhook.aiohttp_server'
]

for dep in mocked_deps:
    mock_module(dep)

# Helper to automatically provide SafeMocks and avoid StopIteration/AttributeError
class MockDict(dict):
    def __missing__(self, key):
        self[key] = MagicMock()
        return self[key]

mock_cache = {}

class FakeModule(types.ModuleType):
    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []
        if name not in mock_cache:
            mock_cache[name] = MockDict()

    def __call__(self, *args, **kwargs):
        return MagicMock()

    def __getattr__(self, name):
        fullname = f"{self.__name__}.{name}"
        if fullname in mocked_deps or name.islower():
            if fullname not in sys.modules:
                mod = FakeModule(fullname)
                sys.modules[fullname] = mod
                return mod

        if name == 'BaseMiddleware':
            class FakeBaseMiddleware:
                def __init__(self, *args, **kwargs): pass
                async def __call__(self, handler, event, data): return await handler(event, data)
            return FakeBaseMiddleware
        if name == 'State':
            class FakeState:
                def __init__(self, *args, **kwargs): pass
            return FakeState
        if name == 'StatesGroup':
            class FakeStatesGroup: pass
            return FakeStatesGroup

        return mock_cache[self.__name__][name]

for dep in mocked_deps:
    sys.modules[dep] = FakeModule(dep)

# Now we can safely import the functions under test
from Dubsite_tgach.main import get_real_ip
import importlib.util
spec = importlib.util.spec_from_file_location("root_main", os.path.join(PROJECT_ROOT, "main.py"))
root_main = importlib.util.module_from_spec(spec)
sys.modules["root_main"] = root_main
spec.loader.exec_module(root_main)
add_you_to_my_posts_fast = root_main.add_you_to_my_posts_fast

class StubClient:
    def __init__(self, host):
        self.host = host

class StubRequest:
    def __init__(self, headers=None, client_host=None):
        self.headers = headers or {}
        self.client = StubClient(client_host)

import unittest
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
from unittest.mock import patch

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



class TestAddYouToMyPostsFastFull(unittest.TestCase):
    def test_happy_path(self):
        text = "Hello >>123 world >>456"
        post_authors = {123: 1, 456: 2}
        result = add_you_to_my_posts_fast(text, 1, post_authors)
        self.assertEqual(result, "Hello >>123 (You) world >>456")

    def test_value_error_handling(self):
        # We simulate ValueError during int() cast by passing a string of digits
        # so large that it exceeds the integer string conversion limit (sys.set_int_max_str_digits)
        # default is 4300, so > 4300 digits will cause int() to raise ValueError.
        huge_num = "1" * 4301
        text = f"Test >>{huge_num} and >>456"
        post_authors = {456: 1} # 456 is authored by user 1

        # huge_num will be matched by >>(\d+), but int(huge_num) will raise ValueError
        # and it should continue to process >>456 without crashing
        result = add_you_to_my_posts_fast(text, 1, post_authors)

        # Result should be exactly the original text but with >>456 replaced
        self.assertEqual(result, f"Test >>{huge_num} and >>456 (You)")

    def test_missing_user(self):
        text = "Test >>123"
        post_authors = {123: 2}
        result = add_you_to_my_posts_fast(text, 1, post_authors)
        self.assertEqual(result, "Test >>123")

    def test_no_matches(self):
        text = "Test no matches"
        post_authors = {123: 1}
        result = add_you_to_my_posts_fast(text, 1, post_authors)
        self.assertEqual(result, "Test no matches")

    def test_empty_string(self):
        self.assertEqual(add_you_to_my_posts_fast("", 1, {}), "")
