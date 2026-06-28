import unittest
import os
import asyncio

# Mock environment variables before importing
os.environ['SECRET_KEY'] = 'test_secret_key'
os.environ['BOT_TOKEN'] = 'test_bot_token'
os.environ['OPENAI_API_KEY'] = 'test_openai_api_key'

import sys
import types
from unittest.mock import MagicMock

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

from Dubsite_tgach.main import sanitize_html

class TestSanitizeHtml(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(sanitize_html(""), "")

    def test_none(self):
        self.assertEqual(sanitize_html(None), "")

    def test_html_tags(self):
        self.assertEqual(
            sanitize_html("<script>alert('xss')</script>"),
            "&lt;script&gt;alert('xss')&lt;/script&gt;"
        )
        self.assertEqual(
            sanitize_html("A & B"),
            "A &amp; B"
        )

    def test_quotes(self):
        # With quote=False, quotes should remain unescaped
        self.assertEqual(
            sanitize_html('<div class="test" id=\'a\'>'),
            '&lt;div class="test" id=\'a\'&gt;'
        )
        self.assertEqual(
            sanitize_html("\"quotes'"),
            "\"quotes'"
        )

if __name__ == '__main__':
    unittest.main()
