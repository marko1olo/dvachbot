import sys
import os
import unittest
import types
from unittest.mock import MagicMock

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
    'bs4', 'slowapi', 'slowapi.util', 'slowapi.errors', 'async_lru', 'uvicorn',
    'fastapi', 'fastapi.responses', 'fastapi.middleware', 'fastapi.middleware.cors',
    'fastapi.middleware.trustedhost', 'fastapi.middleware.gzip',
    'fastapi.staticfiles', 'fastapi.templating', 'fastapi.exceptions',
    'fastapi_cache', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator', 'geoip2', 'geoip2.database', 'aiogram',
    'aiogram.types', 'aiogram.exceptions', 'aiogram.enums', 'aiogram.client',
    'aiogram.client.default', 'aiogram.client.session', 'aiogram.client.session.aiohttp', 'common.bot_pool',
    'aiogram.filters', 'aiogram.fsm', 'aiogram.fsm.context', 'aiogram.fsm.state', 'aiogram.fsm.storage', 'aiogram.fsm.storage.memory',
    'aiogram.webhook', 'aiogram.webhook.aiohttp_server', 'orjson', 'pydantic',
    'aiogram.utils', 'aiogram.utils.media_group', 'aiogram.utils.keyboard',
    'openai', 'pyrogram', 'pyrogram.errors', 'pyrogram.types'
]

for dep in mocked_deps:
    mock_module(dep)

# Return MagicMock for any attribute access on our mocked modules
for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        sys.modules[mod_name].__getattr__ = lambda name: MagicMock()

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

import ast

def get_clean_html_function():
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    # Extract the function dynamically to avoid importing main.py's side effects
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'clean_html_for_tg':
            # compile and eval
            code = compile(ast.Module(body=[node], type_ignores=[]), filename="<ast>", mode="exec")
            namespace = {'re': __import__('re')}
            exec(code, namespace)
            return namespace['clean_html_for_tg']
    return None

clean_html_for_tg = get_clean_html_function()

class TestCleanHtmlForTg(unittest.TestCase):
    def test_balanced_tags(self):
        self.assertEqual(clean_html_for_tg("hello <b>world</b>"), "hello <b>world</b>")
        self.assertEqual(clean_html_for_tg("<b><i>test</i></b>"), "<b><i>test</i></b>")
        self.assertEqual(clean_html_for_tg("<a href='test'>link</a>"), "<a href='test'>link</a>")

    def test_unclosed_tags(self):
        self.assertEqual(clean_html_for_tg("hello <b>world"), "hello <b>world</b>")
        self.assertEqual(clean_html_for_tg("hello <b><i>world</b>"), "hello <b><i>world</i></b>")

    def test_stray_closing_tags(self):
        self.assertEqual(clean_html_for_tg("hello <b>world</i>"), "hello <b>world&lt;/i&gt;</b>")
        self.assertEqual(clean_html_for_tg("hello </b>world"), "hello &lt;/b&gt;world")

    def test_invalid_tags(self):
        self.assertEqual(clean_html_for_tg("hello <script>world</script>"), "hello &lt;script>world&lt;/script>")
        self.assertEqual(clean_html_for_tg("hello <unknown>world"), "hello &lt;unknown>world")
