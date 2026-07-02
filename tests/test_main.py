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

# Return MagicMock for any attribute access on our mocked modules
for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        sys.modules[mod_name].__getattr__ = lambda name: MagicMock()

# Now we can safely import the function under test
from Dubsite_tgach.main import get_real_ip, sanitize_html, format_post_text, get_country_by_ip, check_post_cooldown, _resize_image_if_needed
from unittest.mock import MagicMock, AsyncMock, patch
import io

class StubClient:
    def __init__(self, host):
        self.host = host

class StubRequest:
    def __init__(self, headers=None, client_host=None, client_is_none=False):
        self.headers = headers or {}
        self.client = None if client_is_none else StubClient(client_host)

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

    def test_client_none_fallback(self):
        """Test that a missing client correctly falls back to 127.0.0.1."""
        request = StubRequest(
            headers={},
            client_is_none=True
        )
        self.assertEqual(get_real_ip(request), "127.0.0.1")

    def test_empty_headers_values(self):
        """Test that empty string header values correctly fall back to client.host."""
        request = StubRequest(
            headers={"x-real-ip": "", "x-forwarded-for": ""},
            client_host="9.10.11.12"
        )
        self.assertEqual(get_real_ip(request), "9.10.11.12")


from Dubsite_tgach.main import clean_title_text

class TestCleanTitleText(unittest.TestCase):
    def test_clean_title_text_parameterized(self):
        test_cases = [
            # Edge cases
            (None, ""),
            ("", ""),
            ("No tags here", "No tags here"),

            # HTML tags
            ("<h1>Hello</h1>", "Hello"),
            ("<p>Some <b>bold</b> text</p>", "Some bold text"),
            ("<script>alert(1)</script>", "alert(1)"),

            # Brackets (Removed in the current implementation in Dubsite_tgach/main.py)
            ("This is [some tag] text", "This is text"),
            ("[Prefix] Just the title", "Just the title"),
            ("[Tag1] [Tag2] Title", "Title"),

            # Whitespace
            ("   Too   much   space   ", "Too much space"),
            ("New\nlines\tand\ttabs", "New lines and tabs"),

            # Combined
            ("\n\n [Tag]   <h1>  Super Title  </h1>   [123] \t", "Super Title"),
            ("Title with <a href='https://example.com'>link</a> and [brackets]", "Title with link and")
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                self.assertEqual(clean_title_text(input_text), expected)

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


from Dubsite_tgach.main import vibe_to_icon
class TestVibeToIcon(unittest.TestCase):
    def test_exact_matches(self):
        self.assertEqual(vibe_to_icon("toxic"), "🔥 (Токсично)")
        self.assertEqual(vibe_to_icon("anime"), "🌸 (Аниме)")
        self.assertEqual(vibe_to_icon("schizo"), "🤡 (Шиза)")

    def test_case_and_whitespace(self):
        self.assertEqual(vibe_to_icon("  TOXIC  "), "🔥 (Токсично)")
        self.assertEqual(vibe_to_icon("\tAnImE\n"), "🌸 (Аниме)")

    def test_substring_match(self):
        self.assertEqual(vibe_to_icon("this is a very toxic vibe"), "🔥 (Токсично)")
        self.assertEqual(vibe_to_icon("some tech news"), "💾 (Техно)")

    def test_fallback(self):
        self.assertEqual(vibe_to_icon("unknown"), "❓ (Неясно)")
        self.assertEqual(vibe_to_icon(""), "❓ (Неясно)")
        self.assertEqual(vibe_to_icon("something totally unrelated"), "❓ (Неясно)")

class TestSanitizeHtml(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(sanitize_html(""), "")
        self.assertEqual(sanitize_html(None), "None")

    def test_basic_tags(self):
        self.assertEqual(sanitize_html("<b>bold</b>"), "&lt;b&gt;bold&lt;/b&gt;")
        self.assertEqual(sanitize_html("<script>alert(1)</script>"), "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertEqual(sanitize_html("<h1>heading</h1>"), "&lt;h1&gt;heading&lt;/h1&gt;")

    def test_quotes_preserved(self):
        self.assertEqual(sanitize_html('"double quotes"'), '"double quotes"')
        self.assertEqual(sanitize_html("'single quotes'"), "'single quotes'")
        self.assertEqual(sanitize_html("<div class=\"test\">text</div>"), "&lt;div class=\"test\"&gt;text&lt;/div&gt;")

    def test_error_handling(self):
        self.assertEqual(sanitize_html(123), "123")
        self.assertEqual(sanitize_html(12.34), "12.34")
        self.assertEqual(sanitize_html([1, 2, 3]), "[1, 2, 3]")
        self.assertEqual(sanitize_html({"a": 1}), "{'a': 1}")

    def test_malicious_inputs(self):
        self.assertEqual(sanitize_html("<script>fetch('bad')</script>"), "&lt;script&gt;fetch('bad')&lt;/script&gt;")
        self.assertEqual(sanitize_html("<img src=x onerror=alert(1)>"), "&lt;img src=x onerror=alert(1)&gt;")


from PIL import Image as PilImage

class TestResizeImageIfNeeded(unittest.TestCase):
    def create_image_bytes(self, width, height, format="JPEG", mode="RGB", extra_bytes=b""):
        img = PilImage.new(mode, (width, height), color="red")
        b = io.BytesIO()
        img.save(b, format=format)
        return b.getvalue() + extra_bytes

    def test_empty_bytes(self):
        self.assertEqual(_resize_image_if_needed(b""), b"")

    def test_media_headers(self):
        self.assertEqual(_resize_image_if_needed(b"1234ftyp5678..."), b"1234ftyp5678...")
        self.assertEqual(_resize_image_if_needed(b"\x1A\x45\xDF\xA3_mkv_data"), b"\x1A\x45\xDF\xA3_mkv_data")
        self.assertEqual(_resize_image_if_needed(b"GIF89a_data"), b"GIF89a_data")

    def test_invalid_image_bytes(self):
        invalid_bytes = b"not an image file at all"
        self.assertEqual(_resize_image_if_needed(invalid_bytes), invalid_bytes)

    def test_small_image(self):
        small_img = self.create_image_bytes(100, 100)
        res = _resize_image_if_needed(small_img)
        with PilImage.open(io.BytesIO(res)) as img:
            self.assertEqual(img.size, (100, 100))

    def test_large_dimension(self):
        large_img = self.create_image_bytes(6000, 6000)
        res = _resize_image_if_needed(large_img)
        with PilImage.open(io.BytesIO(res)) as img:
            self.assertEqual(img.size, (5000, 5000))

    def test_large_aspect_ratio_width(self):
        wide_img = self.create_image_bytes(4000, 100)
        res = _resize_image_if_needed(wide_img)
        with PilImage.open(io.BytesIO(res)) as img:
            self.assertEqual(img.size, (2000, 100))

    def test_large_aspect_ratio_height(self):
        tall_img = self.create_image_bytes(100, 4000)
        res = _resize_image_if_needed(tall_img)
        with PilImage.open(io.BytesIO(res)) as img:
            self.assertEqual(img.size, (100, 2000))

    def test_large_file_size(self):
        large_file = self.create_image_bytes(100, 100, extra_bytes=b"0" * (10 * 1024 * 1024))
        res = _resize_image_if_needed(large_file)
        self.assertLess(len(res), 9.5 * 1024 * 1024)
        with PilImage.open(io.BytesIO(res)) as img:
            self.assertLessEqual(img.width, 100)
            self.assertLessEqual(img.height, 100)

    def test_large_png_conversion(self):
        large_png = self.create_image_bytes(100, 100, format="PNG", extra_bytes=b"0" * (6 * 1024 * 1024))
        res = _resize_image_if_needed(large_png)
        with PilImage.open(io.BytesIO(res)) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertEqual(img.size, (100, 100))

    def test_animated_image_fallback(self):
        small_img = self.create_image_bytes(100, 100)
        original_open = PilImage.open
        def mock_open(*args, **kwargs):
            img = original_open(*args, **kwargs)
            img.is_animated = True
            return img

        with patch('PIL.Image.open', side_effect=mock_open):
            res = _resize_image_if_needed(small_img)
            self.assertEqual(res, small_img)


class TestFormatPostText(unittest.TestCase):
    def test_invalid_input(self):
        self.assertEqual(format_post_text(None), "")
        self.assertEqual(format_post_text(123), "")
        self.assertEqual(format_post_text([]), "")

    def test_xss_obfuscation(self):
        self.assertEqual(format_post_text("<script>alert(1)</script>"), "&lt;scrlpt&gt;alert(1)&lt;/scrlpt&gt;")
        self.assertEqual(format_post_text("<iframe src='x'></iframe>"), "&lt;lframe src=&#x27;x&#x27;&gt;&lt;/lframe&gt;")
        self.assertEqual(format_post_text("expression(alert(1))"), "explession(alert(1))")
        self.assertEqual(format_post_text("<style>body{}</style>"), "&lt;sty1e&gt;body{}&lt;/sty1e&gt;")
        self.assertEqual(format_post_text("<STYLE>body{}</STYLE>"), "&lt;STYLe&gt;body{}&lt;/STYLe&gt;")
        self.assertEqual(format_post_text("<img onerror=alert(1)>"), "&lt;img 0nerror=alert(1)&gt;")
        self.assertEqual(format_post_text("<body onload=alert(1)>"), "&lt;body 0nload=alert(1)&gt;")

    def test_html_escaping(self):
        self.assertEqual(format_post_text("a < b > c \" d ' e & f"), "a &lt; b &gt; c &quot; d &#x27; e &amp; f")

    def test_formatting_newlines(self):
        self.assertEqual(format_post_text("line1\nline2"), "line1<br>line2")
        self.assertEqual(format_post_text("line1<br>line2"), "line1<br>line2")
        self.assertEqual(format_post_text("line1<br/>line2"), "line1<br>line2")

    def test_url_autolinking(self):
        self.assertEqual(
            format_post_text("Check http://example.com/test"),
            'Check <a href="http://example.com/test" target="_blank" rel="noopener noreferrer">http://example.com/test</a>'
        )
        self.assertEqual(
            format_post_text("Check https://example.com/test"),
            'Check <a href="https://example.com/test" target="_blank" rel="noopener noreferrer">https://example.com/test</a>'
        )

    def test_greentext(self):
        self.assertEqual(
            format_post_text(">greentext here"),
            '<span class="greentext">&gt;greentext here</span>'
        )
        self.assertEqual(
            format_post_text("&amp;gt;greentext here"),
            '&amp;amp;gt;greentext here'
        )
        self.assertEqual(
            format_post_text("line1\n>line2"),
            'line1<br><span class="greentext">&gt;line2</span>'
        )
        self.assertNotIn('greentext', format_post_text(">>/b/123"))

    def test_post_links(self):
        self.assertEqual(
            format_post_text(">>12345"),
            '<a href="#post-12345" class="post-link" data-post-num="12345">&gt;&gt;12345</a>'
        )
        self.assertEqual(
            format_post_text(">>/b/12345"),
            '<a href="/b/res/0#post-12345" class="post-link cross-board-link" data-board-id="b" data-post-num="12345">&gt;&gt;/b/12345</a>'
        )

    def test_bbcode_tags(self):
        self.assertEqual(format_post_text("[b]bold[/b]"), "<b>bold</b>")
        self.assertEqual(format_post_text("[i]italic[/i]"), "<i>italic</i>")
        self.assertEqual(format_post_text("[s]strike[/s]"), "<s>strike</s>")
        self.assertEqual(format_post_text("[u]underline[/u]"), "<u>underline</u>")
        self.assertEqual(format_post_text("[h1]heading[/h1]"), '<h3 class="post-heading">heading</h3>')
        self.assertEqual(format_post_text("[code]code block[/code]"), "<code>code block</code>")

    def test_effects(self):
        self.assertEqual(format_post_text("[shake]shaking[/shake]"), '<span class="effect-shake">shaking</span>')
        self.assertEqual(format_post_text("[rainbow]colorful[/rainbow]"), '<span class="effect-rainbow">colorful</span>')
        self.assertEqual(format_post_text("[blur]blurred[/blur]"), '<span class="effect-blur">blurred</span>')
        self.assertEqual(
            format_post_text("[glitch]glitching[/glitch]"),
            '<span class="effect-glitch" data-text="glitching">glitching</span>'
        )

    def test_button(self):
        self.assertEqual(
            format_post_text("[btn=http://test.com]Click[/btn]"),
            '[btn=<a href="http://test.com]Click[/btn]" target="_blank" rel="noopener noreferrer">http://test.com]Click[/btn]</a>'
        )
        self.assertEqual(
            format_post_text("[btn=http://test.com?a=1&b=2]Click[/btn]"),
            '[btn=<a href="http://test.com?a=1&amp;b=2]Click[/btn]" target="_blank" rel="noopener noreferrer">http://test.com?a=1&amp;b=2]Click[/btn]</a>'
        )

    def test_size(self):
        self.assertEqual(format_post_text("[size=20]big[/size]"), '<span style="font-size: 20px;">big</span>')
        self.assertEqual(format_post_text("[size=5]small[/size]"), '<span style="font-size: 10px;">small</span>')
        self.assertEqual(format_post_text("[size=50]huge[/size]"), '<span style="font-size: 30px;">huge</span>')
        self.assertEqual(format_post_text("[size=abc]text[/size]"), "[size=abc]text[/size]")

    def test_spoiler(self):
        self.assertEqual(format_post_text("||spoiler text||"), '<span class="spoiler">spoiler text</span>')


class TestGetCountryByIp(unittest.IsolatedAsyncioTestCase):
    async def test_local_ip(self):
        self.assertEqual(await get_country_by_ip("127.0.0.1"), "XX")
        self.assertEqual(await get_country_by_ip("localhost"), "XX")
        self.assertEqual(await get_country_by_ip("::1"), "XX")

    @patch("Dubsite_tgach.main.GEOIP_READER", None)
    @patch("os.path.exists", return_value=False)
    @patch("httpx.AsyncClient")
    async def test_http_fallback_success(self, mock_client_cls, mock_exists):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"countryCode": "US"}
        mock_client.get.return_value = mock_response
        self.assertEqual(await get_country_by_ip("8.8.8.8"), "US")
        self.assertTrue(mock_client.get.called)

    @patch("Dubsite_tgach.main.GEOIP_READER")
    async def test_geoip_success(self, mock_reader):
        mock_response = MagicMock()
        mock_response.country.iso_code = "CA"
        mock_reader.country.return_value = mock_response
        self.assertEqual(await get_country_by_ip("1.1.1.1"), "CA")
        self.assertTrue(mock_reader.country.called)

    @patch("Dubsite_tgach.main.GEOIP_READER")
    @patch("httpx.AsyncClient")
    async def test_geoip_exception_fallback(self, mock_client_cls, mock_reader):
        mock_reader.country.side_effect = Exception("Not found")
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"countryCode": "GB"}
        mock_client.get.return_value = mock_response
        self.assertEqual(await get_country_by_ip("2.2.2.2"), "GB")
        self.assertTrue(mock_reader.country.called)
        self.assertTrue(mock_client.get.called)

    @patch("Dubsite_tgach.main.GEOIP_READER", None)
    @patch("os.path.exists", return_value=False)
    @patch("httpx.AsyncClient")
    async def test_all_fail(self, mock_client_cls, mock_exists):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = Exception("Network error")
        self.assertEqual(await get_country_by_ip("3.3.3.3"), "XX")


class TestCheckPostCooldown(unittest.IsolatedAsyncioTestCase):
    async def test_empty_cache_user(self):
        request = StubRequest(headers={}, client_host="1.1.1.1")
        user = {'id': '123', 'is_guest': False}
        mock_backend = MagicMock()
        mock_backend.get = AsyncMock(return_value=None)
        mock_backend.set = AsyncMock()
        with patch('Dubsite_tgach.main.FastAPICache.get_backend', return_value=mock_backend), \
             patch('time.time', return_value=100.0):
            await check_post_cooldown(request, user)
            mock_backend.get.assert_called_once_with('cooldown_user_123')
            mock_backend.set.assert_called_once_with('cooldown_user_123', '100.0', expire=5)

    async def test_empty_cache_guest(self):
        request = StubRequest(headers={}, client_host="1.1.1.1")
        user = {'id': '456', 'is_guest': True}
        mock_backend = MagicMock()
        mock_backend.get = AsyncMock(return_value=None)
        mock_backend.set = AsyncMock()
        with patch('Dubsite_tgach.main.FastAPICache.get_backend', return_value=mock_backend), \
             patch('time.time', return_value=100.0):
            await check_post_cooldown(request, user)
            mock_backend.get.assert_called_once_with('cooldown_guest_456')
            mock_backend.set.assert_called_once_with('cooldown_guest_456', '100.0', expire=25)

    async def test_recent_post_user_raises_429(self):
        request = StubRequest(headers={}, client_host="1.1.1.1")
        user = {'id': '123', 'is_guest': False}
        mock_backend = MagicMock()
        mock_backend.get = AsyncMock(return_value='98.0')
        mock_backend.set = AsyncMock()
        import starlette.exceptions
        RealHTTPException = starlette.exceptions.HTTPException
        with patch('Dubsite_tgach.main.FastAPICache.get_backend', return_value=mock_backend), \
             patch('time.time', return_value=100.0), \
             patch('Dubsite_tgach.main.HTTPException', RealHTTPException):
            with self.assertRaises(RealHTTPException) as ctx:
                await check_post_cooldown(request, user)
            self.assertEqual(ctx.exception.status_code, 429)
            mock_backend.set.assert_not_called()

    async def test_older_post_user_allows(self):
        request = StubRequest(headers={}, client_host="1.1.1.1")
        user = {'id': '123', 'is_guest': False}
        mock_backend = MagicMock()
        mock_backend.get = AsyncMock(return_value='94.0')
        mock_backend.set = AsyncMock()
        with patch('Dubsite_tgach.main.FastAPICache.get_backend', return_value=mock_backend), \
             patch('time.time', return_value=100.0):
            await check_post_cooldown(request, user)
            mock_backend.set.assert_called_once_with('cooldown_user_123', '100.0', expire=5)

    async def test_invalid_cache_data(self):
        request = StubRequest(headers={}, client_host="1.1.1.1")
        user = {'id': '123', 'is_guest': False}
        mock_backend = MagicMock()
        mock_backend.get = AsyncMock(return_value='invalid_float')
        mock_backend.set = AsyncMock()
        with patch('Dubsite_tgach.main.FastAPICache.get_backend', return_value=mock_backend), \
             patch('time.time', return_value=100.0):
            await check_post_cooldown(request, user)
            mock_backend.set.assert_called_once_with('cooldown_user_123', '100.0', expire=5)

if __name__ == "__main__":
    unittest.main()

from Dubsite_tgach.main import format_poll_for_html

class TestFormatPollForHtml(unittest.TestCase):
    def test_empty_poll(self):
        self.assertEqual(format_poll_for_html({}), "")
        self.assertEqual(format_poll_for_html(None), "")

    def test_missing_question(self):
        self.assertEqual(format_poll_for_html({'options': ['A', 'B']}), "")

    def test_zero_votes(self):
        poll = {
            'question': 'Test?',
            'options': ['Yes', 'No'],
            'votes': {}
        }
        html_out = format_poll_for_html(poll)
        self.assertIn("📊 Test?", html_out)
        self.assertIn("Yes (0)", html_out)
        self.assertIn("No (0)", html_out)
        self.assertIn("width: 0.0%", html_out)

    def test_valid_votes(self):
        poll = {
            'question': 'Color?',
            'options': ['Red', 'Blue', 'Green'],
            'votes': {
                '0': [1, 2],       # Red: 2 votes
                '1': [3],          # Blue: 1 vote
                '2': [4, 5, 6]     # Green: 3 votes
            }
        }
        html_out = format_poll_for_html(poll)
        self.assertIn("📊 Color?", html_out)
        self.assertIn("Red (2)", html_out)
        self.assertIn("Blue (1)", html_out)
        self.assertIn("Green (3)", html_out)
        # Total votes = 6
        # Red = 2/6 = 33.333% -> 33.3%
        self.assertIn("width: 33.3%", html_out)
        # Blue = 1/6 = 16.666% -> 16.7%
        self.assertIn("width: 16.7%", html_out)
        # Green = 3/6 = 50% -> 50.0%
        self.assertIn("width: 50.0%", html_out)

    def test_html_escaping(self):
        poll = {
            'question': '<script>alert(1)</script>',
            'options': ['<img src="x" onerror="alert(1)">', 'Normal'],
            'votes': {'0': [1]}
        }
        html_out = format_poll_for_html(poll)
        self.assertNotIn("<script>", html_out)
        self.assertNotIn("<img", html_out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_out)
        self.assertIn("&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;", html_out)
