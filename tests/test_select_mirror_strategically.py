import sys
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "123:test"

sys.path.insert(0, os.path.abspath('Dubsite_tgach'))

import types

class MockModule(object):
    def __init__(self, name):
        self.__name__ = name
        self.__path__ = []

    def __getattr__(self, name):
        if name in ('__file__', '__path__'):
            return None
        return MagicMock()

class SafeMagicMock(MagicMock):
    # Only make it iterable if absolutely requested by aiogram, but limit to 1 item to avoid infinite loop OOM
    def __iter__(self):
        yield MagicMock()

def patch_sys_modules():
    # Use a catch-all finder to mock any module that isn't standard library
    # But for safety, we explicitly mock the heavy ones we know are failing.
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
        'fastapi.encoders', 'fastapi_cache', 'fastapi_cache.coder', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
        'fastapi_cache.decorator',
        'fastapi_limiter', 'fastapi_limiter.depends', 'fastapi_limiter.depends.RateLimiter',
        'starlette.requests', 'starlette.responses', 'starlette.middleware.base',
        'pyrogram', 'pyrogram.errors', 'pyrogram.raw.types',
        'aiogram', 'aiogram.client', 'aiogram.client.session', 'aiogram.client.session.aiohttp', 'aiogram.client.default', 'aiogram.types', 'aiogram.filters', 'aiogram.utils.keyboard',
        'aiogram.exceptions', 'periodic_publisher', 'bot_pool', 'check_large_tables'
    ]

    for dep in mocked_deps:
        sys.modules[dep] = MockModule(dep)

patch_sys_modules()

import asyncio

# Setup a dummy loop instead of relying on uvloop since it might not be available
try:
    asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Import main using standard import
from main import _select_mirror_strategically

class TestSelectMirrorStrategically(unittest.TestCase):

    def test_basic_image_no_mirrors(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        orig, thumb = _select_mirror_strategically(file_info, {}, {}, is_ru=True)
        self.assertEqual(orig, 'http://base.com/img.jpg')
        self.assertEqual(thumb, 'http://base.com/thumb.jpg')

    def test_video_with_huggingface(self):
        file_info = {'original_url': 'http://base.com/vid.mp4', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'video'}
        mirrors = {'huggingface': 'http://hf.co/vid.mp4'}
        orig, thumb = _select_mirror_strategically(file_info, mirrors, {}, is_ru=True)
        self.assertEqual(orig, 'http://hf.co/vid.mp4')
        self.assertEqual(thumb, 'http://base.com/thumb.jpg')

    def test_video_no_huggingface(self):
        file_info = {'original_url': 'http://base.com/vid.mp4', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'video'}
        mirrors = {'telegram': 'http://tg.co/vid.mp4'}
        orig, thumb = _select_mirror_strategically(file_info, mirrors, {}, is_ru=True)
        self.assertEqual(orig, 'http://base.com/vid.mp4')
        self.assertEqual(thumb, 'http://base.com/thumb.jpg')

    def test_image_with_huggingface_selected(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        mirrors = {'huggingface': 'http://hf.co/img.jpg'}

        with patch('main.random.choice', return_value='huggingface'):
            orig, thumb = _select_mirror_strategically(file_info, mirrors, {}, is_ru=True)
        self.assertEqual(orig, 'http://hf.co/img.jpg')

    def test_image_with_huggingface_not_selected(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        mirrors = {'huggingface': 'http://hf.co/img.jpg'}

        with patch('main.random.choice', return_value='telegram'):
            orig, thumb = _select_mirror_strategically(file_info, mirrors, {}, is_ru=True)
        self.assertEqual(orig, 'http://base.com/img.jpg')

    def test_thumb_with_huggingface(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        thumb_mirrors = {'huggingface': 'http://hf.co/thumb.jpg', 'catbox': 'http://catbox.moe/thumb.jpg'}
        orig, thumb = _select_mirror_strategically(file_info, {}, thumb_mirrors, is_ru=True)
        self.assertEqual(thumb, 'http://hf.co/thumb.jpg')

    def test_thumb_catbox_not_ru(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        thumb_mirrors = {'catbox': 'http://catbox.moe/thumb.jpg'}
        orig, thumb = _select_mirror_strategically(file_info, {}, thumb_mirrors, is_ru=False)
        self.assertEqual(thumb, 'http://catbox.moe/thumb.jpg')

    def test_thumb_catbox_is_ru(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        thumb_mirrors = {'catbox': 'http://catbox.moe/thumb.jpg'}
        orig, thumb = _select_mirror_strategically(file_info, {}, thumb_mirrors, is_ru=True)
        self.assertEqual(thumb, 'http://base.com/thumb.jpg')

if __name__ == '__main__':
    unittest.main()
