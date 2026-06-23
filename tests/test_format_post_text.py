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
    'site_tgach.mirror_worker', 'site_tgach.tagging_worker',
    'site_tgach.security', 'site_tgach.image_processing', 'site_tgach.catbox',
    'site_tgach.neuro_poster', 'site_tgach.rss', 'site_tgach.backup',
    'site_tgach.importer', 'site_tgach.neuro_scanner', 'site_tgach.admin_config',
    'site_tgach.voice_processing', 'warhammer_mode', 'japanese_translator',
    'bs4', 'slowapi', 'slowapi.util', 'slowapi.errors', 'async_lru', 'uvicorn',
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
    if mod_name in mocked_deps:
        sys.modules[mod_name].__getattr__ = lambda name: MagicMock()

import pytest
from Dubsite_tgach.main import format_post_text as format_post_text_dubsite
from site_tgach.main import format_post_text as format_post_text_site

@pytest.mark.parametrize("format_post_text", [format_post_text_dubsite, format_post_text_site])
def test_format_post_text_xss_protection(format_post_text):
    assert format_post_text("script") == "scrlpt"
    assert format_post_text("iframe") == "lframe"
    assert format_post_text("expression") == "explession"
    assert format_post_text("style") == "sty1e"
    assert format_post_text("javascript:") == "javascrlpt:"
    assert format_post_text("onload") == "0nload"
    assert format_post_text("onerror") == "0nerror"

@pytest.mark.parametrize("format_post_text", [format_post_text_dubsite, format_post_text_site])
def test_format_post_text_html_escaping(format_post_text):
    assert format_post_text("<script>") == "&lt;scrlpt&gt;"
    assert format_post_text("some & text") == "some &amp; text"
    assert format_post_text('"quotes"') == "&quot;quotes&quot;"
    assert format_post_text("'quotes'") == "&#x27;quotes&#x27;"

@pytest.mark.parametrize("format_post_text", [format_post_text_dubsite, format_post_text_site])
def test_format_post_text_greentext(format_post_text):
    assert format_post_text(">greentext") == '<span class="greentext">&gt;greentext</span>'
    assert format_post_text("normal text\n>greentext") == 'normal text<br><span class="greentext">&gt;greentext</span>'

@pytest.mark.parametrize("format_post_text", [format_post_text_dubsite, format_post_text_site])
def test_format_post_text_post_links(format_post_text):
    assert format_post_text(">>123") == '<a href="#post-123" class="post-link" data-post-num="123">&gt;&gt;123</a>'
    assert format_post_text(">>/b/123") == '<a href="/b/res/0#post-123" class="post-link cross-board-link" data-board-id="b" data-post-num="123">&gt;&gt;/b/123</a>'

@pytest.mark.parametrize("format_post_text", [format_post_text_dubsite, format_post_text_site])
def test_format_post_text_bbcode(format_post_text):
    assert format_post_text("[b]bold[/b]") == "<b>bold</b>"
    assert format_post_text("[i]italic[/i]") == "<i>italic</i>"
    assert format_post_text("[u]underline[/u]") == "<u>underline</u>"
    assert format_post_text("[s]strike[/s]") == "<s>strike</s>"
    assert format_post_text("[code]code[/code]") == "<code>code</code>"
    assert format_post_text("[h1]heading[/h1]") == '<h3 class="post-heading">heading</h3>'

@pytest.mark.parametrize("format_post_text", [format_post_text_dubsite, format_post_text_site])
def test_format_post_text_effects(format_post_text):
    assert format_post_text("[shake]shake[/shake]") == '<span class="effect-shake">shake</span>'
    assert format_post_text("[rainbow]rainbow[/rainbow]") == '<span class="effect-rainbow">rainbow</span>'
    assert format_post_text("[blur]blur[/blur]") == '<span class="effect-blur">blur</span>'
    assert format_post_text("[glitch]glitch[/glitch]") == '<span class="effect-glitch" data-text="glitch">glitch</span>'
    assert format_post_text("||spoiler||") == '<span class="spoiler">spoiler</span>'

@pytest.mark.parametrize("format_post_text", [format_post_text_dubsite, format_post_text_site])
def test_format_post_text_buttons(format_post_text):
    assert format_post_text("[btn=https://example.com]Click me[/btn]") == '<a href="https://example.com" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-small post-btn">Click me</a>'

@pytest.mark.parametrize("format_post_text", [format_post_text_dubsite, format_post_text_site])
def test_format_post_text_size(format_post_text):
    assert format_post_text("[size=20]Big text[/size]") == '<span style="font-size: 20px;">Big text</span>'
    assert format_post_text("[size=50]Huge text[/size]") == '<span style="font-size: 30px;">Huge text</span>' # capped at 30
    assert format_post_text("[size=5]Tiny text[/size]") == '<span style="font-size: 10px;">Tiny text</span>' # capped at 10

@pytest.mark.parametrize("format_post_text", [format_post_text_dubsite, format_post_text_site])
def test_format_post_text_url(format_post_text):
    assert format_post_text("https://example.com") == '<a href="https://example.com" target="_blank" rel="noopener noreferrer">https://example.com</a>'

@pytest.mark.parametrize("format_post_text", [format_post_text_dubsite, format_post_text_site])
def test_format_post_text_invalid_input(format_post_text):
    assert format_post_text(None) == ""
    assert format_post_text(123) == ""
