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

class MockModule(types.ModuleType):
    def __getattr__(self, name):
        return MagicMock()

def mock_module(name):
    mod = MockModule(name)
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
    'aiogram.types', 'aiogram.exceptions', 'aiogram.enums', 'aiogram.client',
    'aiogram.client.session', 'aiogram.client.session.aiohttp', 'aiogram.client.default',
    'passlib', 'passlib.context', 'pendulum',
]

for dep in mocked_deps:
    if dep not in sys.modules:
        mock_module(dep)

from Dubsite_tgach.main import get_user_id_from_session

class MockClient:
    def __init__(self, host):
        self.host = host

class MockRequest:
    def __init__(self, session=None, headers=None, client_host="127.0.0.1"):
        self.session = session or {}
        self.headers = headers or {}
        self.client = MockClient(client_host)

class TestGetUserIdFromSession(unittest.TestCase):
    def test_user_id_in_session(self):
        req = MockRequest(session={'user': {'id': 12345}})
        self.assertEqual(get_user_id_from_session(req), "12345")

    def test_user_in_session_but_no_id(self):
        req = MockRequest(session={'user': {'name': 'test'}}, client_host="192.168.1.1")
        self.assertEqual(get_user_id_from_session(req), "192.168.1.1")

    def test_no_user_in_session(self):
        req = MockRequest(session={}, client_host="10.0.0.1")
        self.assertEqual(get_user_id_from_session(req), "10.0.0.1")

    def test_fallback_to_real_ip(self):
        req = MockRequest(session={}, headers={"x-real-ip": "203.0.113.1"}, client_host="10.0.0.1")
        self.assertEqual(get_user_id_from_session(req), "203.0.113.1")

    def test_fallback_to_forwarded_for(self):
        req = MockRequest(session={}, headers={"x-forwarded-for": "198.51.100.1, 192.168.0.1"}, client_host="10.0.0.1")
        self.assertEqual(get_user_id_from_session(req), "198.51.100.1")

if __name__ == '__main__':
    unittest.main()
