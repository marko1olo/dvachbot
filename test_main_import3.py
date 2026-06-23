import sys
import os
import types
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def mock_module(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod

mocked_deps = [
    'site_tgach', 'site_tgach.mirror_worker', 'site_tgach.tagging_worker',
    'site_tgach.security', 'site_tgach.image_processing', 'site_tgach.catbox',
    'site_tgach.neuro_poster', 'site_tgach.rss', 'site_tgach.backup',
    'site_tgach.importer', 'site_tgach.neuro_scanner', 'site_tgach.admin_config',
    'site_tgach.voice_processing', 'warhammer_mode', 'japanese_translator',
    'bs4', 'slowapi', 'slowapi.util', 'slowapi.errors', 'async_lru', 'uvicorn',
    'fastapi_cache', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator', 'geoip2', 'geoip2.database', 'aiogram',
    'aiogram.types', 'aiogram.exceptions', 'aiogram.enums', 'aiogram.client',
    'aiogram.client.session', 'aiogram.client.session.aiohttp', 'common.bot_pool',
    'aiogram.webhook', 'aiogram.webhook.aiohttp_server', 'psutil',
    'matplotlib', 'matplotlib.pyplot', 'matplotlib.ticker', 'matplotlib.dates',
    'common.db_pool', 'seaborn', 'pandas', 'numpy', 'aiohttp', 'redis', 'redis.asyncio',
    'imagehash', 'PIL', 'tenacity', 'lxml', 'lxml.html', 'dotenv', 'aiosqlite',
    'aiogram.client.default', 'aiogram.fsm', 'aiogram.fsm.storage', 'aiogram.fsm.storage.memory',
    'aiogram.fsm.context', 'aiogram.fsm.state', 'aiogram.filters', 'aiogram.filters.command',
    'aiogram.utils', 'aiogram.utils.media_group', 'aiogram.utils.deep_linking',
    'httpx', 'openai', 'pyrogram', 'pyrogram.client', 'pyrogram.types', 'pyrogram.errors',
    'huggingface_hub', 'huggingface_hub.inference_api', 'TgCrypto', 'orjson', 'itsdangerous',
    'python-multipart', 'uvloop', 'asyncpg', 'fastapi', 'blurhash'
]

for dep in mocked_deps:
    mock_module(dep)

class MockState:
    def __getattr__(self, item):
        return self
    def __call__(self, *args, **kwargs):
        return self

class AiogramMock(MagicMock):
    def middleware(self, *args, **kwargs):
        pass
    def __call__(self, *args, **kwargs):
        return self
    def __getattr__(self, item):
        return MockState()

sys.modules['aiogram'] = AiogramMock()

for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        if mod_name != 'aiogram':
            sys.modules[mod_name].__getattr__ = lambda name: AiogramMock()

try:
    import main
    print(main.sanitize_html('<a href="https://test.com">test</a>'))
except Exception as e:
    import traceback
    traceback.print_exc()
