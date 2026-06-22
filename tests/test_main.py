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
    'fastapi_cache', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator', 'geoip2', 'geoip2.database', 'aiogram',
    'aiogram.types', 'aiogram.exceptions', 'aiogram.enums', 'aiogram.client', 'aiogram.filters', 'aiogram.utils', 'aiogram.utils.media_group', 'aiogram.fsm', 'aiogram.fsm.state', 'aiogram.fsm.context',
    'aiogram.client.session', 'aiogram.client.session.aiohttp', 'aiogram.client.default', 'common.bot_pool',
    'aiogram.webhook', 'aiogram.webhook.aiohttp_server'
]

for dep in mocked_deps:
    mock_module(dep)

# Return MagicMock for any attribute access on our mocked modules
for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        if 'aiogram' in mod_name:
            class DummyClass(object):
                pass
            class FallbackMock(MagicMock):
                def __mro_entries__(self, bases):
                    return (DummyClass,)
                def __call__(self, *args, **kwargs):
                    return FallbackMock()
                def __getattr__(self, name):
                    if name in ['_mock_methods', '_mock_unsafe', '__class__', '__mro_entries__']:
                        return super().__getattr__(name)
                    return FallbackMock()
            sys.modules[mod_name].__getattr__ = lambda name: FallbackMock()
        else:
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

from main import format_board_statistics

class TestFormatBoardStatistics(unittest.TestCase):
    def setUp(self):
        self.posts_per_hour = {"b1": 10, "b2": 5}
        self.board_data = {
            "b1": {"board_post_count": 100},
            "b2": {"board_post_count": 50}
        }
        self.board_config = {
            "b1": {"username": "@board_1", "name": "Board 1"},
            "b2": {"username": "board_2", "name": "Board 2"}
        }

    @patch('main.random.random')
    def test_happy_path_en(self, mock_random):
        mock_random.return_value = 0.9 # skip caption
        text, title = format_board_statistics('en', self.posts_per_hour, self.board_data, self.board_config)
        self.assertEqual(title, "### Statistics ###")
        self.assertIn('<a href="https://t.me/board_1">Board 1</a> - 10 pst/hr, total: 100', text)
        self.assertIn('<a href="https://t.me/board_2">Board 2</a> - 5 pst/hr, total: 50', text)

    @patch('main.random.random')
    def test_happy_path_jp(self, mock_random):
        mock_random.return_value = 0.9
        text, title = format_board_statistics('jp', self.posts_per_hour, self.board_data, self.board_config)
        self.assertEqual(title, "### 統計 ###")
        self.assertIn('<a href="https://t.me/board_1">Board 1</a> - 10 レス/時, 合計: 100', text)

    @patch('main.random.random')
    def test_happy_path_ru(self, mock_random):
        mock_random.return_value = 0.9
        text, title = format_board_statistics('ru', self.posts_per_hour, self.board_data, self.board_config)
        self.assertEqual(title, "### Статистика ###")
        self.assertIn('<a href="https://t.me/board_1">Board 1</a> - 10 пст/час, всего: 100', text)

    @patch('main.random.random')
    def test_skip_test_board(self, mock_random):
        mock_random.return_value = 0.9
        board_config_with_test = self.board_config.copy()
        board_config_with_test['test'] = {"username": "@test_board", "name": "Test Board"}
        text, title = format_board_statistics('en', self.posts_per_hour, self.board_data, board_config_with_test)
        self.assertNotIn("Test Board", text)
        self.assertNotIn("test_board", text)

    @patch('main.random.random')
    def test_missing_username(self, mock_random):
        mock_random.return_value = 0.9
        board_config_missing_username = {
            "b1": {"name": "Board 1"} # missing username
        }
        text, title = format_board_statistics('en', self.posts_per_hour, self.board_data, board_config_missing_username)
        self.assertNotIn("Board 1", text)

    @patch('main.random.random')
    def test_empty_username(self, mock_random):
        mock_random.return_value = 0.9
        board_config_empty_username = {
            "b1": {"username": "", "name": "Board 1"}
        }
        text, title = format_board_statistics('en', self.posts_per_hour, self.board_data, board_config_empty_username)
        self.assertNotIn("Board 1", text)

    @patch('main.random.random')
    def test_strange_username(self, mock_random):
        mock_random.return_value = 0.9
        board_config_strange_username = {
            "b1": {"username": "@@strange_name@@", "name": "Strange Board"}
        }
        text, title = format_board_statistics('en', self.posts_per_hour, self.board_data, board_config_strange_username)
        self.assertIn('<a href="https://t.me/strange_name">Strange Board</a>', text)

    @patch('main.random.random')
    def test_missing_stats(self, mock_random):
        mock_random.return_value = 0.9
        # No stats in posts_per_hour or board_data, should default to 0 (if key exists but no post count)
        text, title = format_board_statistics('en', {}, {"b1": {}, "b2": {}}, self.board_config)
        self.assertIn('<a href="https://t.me/board_1">Board 1</a> - 0 pst/hr, total: 0', text)

    @patch('main.random.random')
    def test_missing_board_data_entry(self, mock_random):
        mock_random.return_value = 0.9
        # If the board_data completely misses the board ID, we expect it to raise KeyError initially.
        # But wait, my task is to ensure no KeyError is raised during string interpolation?
        # Actually my task is just adding tests.
        with self.assertRaises(KeyError):
            format_board_statistics('en', {}, {}, self.board_config)

    @patch('main.random.random')
    def test_missing_name_key(self, mock_random):
        mock_random.return_value = 0.9
        board_config_missing_name = {
            "b1": {"username": "board_1"} # missing name
        }
        with self.assertRaises(KeyError):
            format_board_statistics('en', self.posts_per_hour, self.board_data, board_config_missing_name)
