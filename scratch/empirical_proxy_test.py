import sys
import os
import time
import pytest
from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from site_tgach.main import app, sanitize_header_filename

try:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
except Exception:
    pass

client = TestClient(app, raise_server_exceptions=False)

@pytest.fixture(autouse=True)
def mock_common_dependencies():
    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country, \
         patch("common.database.is_file_permanently_failed", new_callable=AsyncMock) as mock_failed, \
         patch("site_tgach.main.get_cached_file_path", new_callable=AsyncMock) as mock_cached:
        mock_country.return_value = "RU"
        mock_failed.return_value = False
        mock_cached.return_value = None
        yield

def test_route_aliases_consistency():
    routes = [
        "/files/test_alias_123",
        "/file/test_alias_123",
        "/thumb/test_alias_123",
        "/i/test_alias_123",
        "/preview/test_alias_123",
        "/b/src/test_alias_123",
        "/b/thumb/test_alias_123",
    ]
    fake_mirrors = {"r2": "https://r2.cdn.example.com/test_alias_123.png"}
    with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
        mock_mirrors.return_value = fake_mirrors
        for route in routes:
            resp = client.get(route, follow_redirects=False)
            assert resp.status_code == 307, f"Route {route} failed with status {resp.status_code}"
            assert resp.headers.get("location") == fake_mirrors["r2"], f"Route {route} redirected to incorrect URL"
            assert resp.headers.get("access-control-allow-origin") == "*", f"Route {route} missing CORS header"

def test_binary_payload_and_headers_proxying():
    fake_png_binary = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    
    class FakeAiohttpResponse:
        def __init__(self, data, status=200):
            self.data = data
            self.status = status
            self.headers = {
                "Content-Type": "image/png",
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(data)),
                "ETag": '"test-etag-123"'
            }

        def release(self):
            pass

        @property
        def content(self):
            class ContentIter:
                def __init__(self, data):
                    self.data = data
                async def iter_chunked(self, size):
                    yield self.data
            return ContentIter(self.data)

    fake_session = MagicMock()
    fake_response = FakeAiohttpResponse(fake_png_binary, 200)
    fake_session.get = AsyncMock(return_value=fake_response)

    with patch("site_tgach.main._get_shared_aiohttp_session", return_value=fake_session), \
         patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
        mock_mirrors.return_value = {"catbox": "https://catbox.moe/test.png"}

        resp = client.get("/files/test_catbox_proxied.png?skip=r2,telegram,freeimage,imgbb,pixhost", follow_redirects=False)
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "image/png"
        assert "max-age=86400" in resp.headers.get("cache-control", "")
        assert resp.headers.get("access-control-allow-origin") == "*"
        assert resp.content == fake_png_binary

def test_fast_fail_database_permanent_failure():
    with patch("common.database.is_file_permanently_failed", new_callable=AsyncMock) as mock_failed:
        mock_failed.return_value = True
        t0 = time.time()
        resp = client.get("/files/permanently_failed_999", follow_redirects=False)
        dt = time.time() - t0

        assert resp.status_code == 404
        assert dt < 0.2, f"Fast fail took too long: {dt:.4f}s"

def test_fast_fail_redis_dead_file():
    dead_fid = "dead_file_test_id_888"
    
    class FakeBackend:
        async def get(self, key):
            if key == f"dead_file:public:{dead_fid}":
                return "1"
            return None
        async def set(self, key, value, expire=None):
            pass

    with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors, \
         patch("fastapi_cache.FastAPICache.get_backend", return_value=FakeBackend()):
        mock_mirrors.return_value = {}
        t0 = time.time()
        resp = client.get(f"/files/{dead_fid}", follow_redirects=False)
        dt = time.time() - t0

        assert resp.status_code == 404
        assert dt < 0.2, f"Dead file fast fail took too long: {dt:.4f}s"

def test_thumbnail_agac_fallback_to_original():
    thumb_id = "AgAC_test_thumb_111"
    orig_id = "AgAC_test_orig_222"

    def mock_get_db_connection():
        class FakeCursor:
            async def fetchone(self):
                return (orig_id,)
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
        class FakeConn:
            def execute(self, sql, params):
                return FakeCursor()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass

        @asynccontextmanager
        async def _cm():
            yield FakeConn()
        return _cm()

    async def side_effect_mirrors(fid):
        if fid == orig_id:
            return {"r2": f"https://r2.cdn.example.com/{orig_id}.jpg"}
        return {}

    with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors, \
         patch("site_tgach.main.get_db_connection", side_effect=mock_get_db_connection):
        mock_mirrors.side_effect = side_effect_mirrors

        resp = client.get(f"/files/{thumb_id}", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers.get("location") == f"https://r2.cdn.example.com/{orig_id}.jpg"

def test_direct_original_file_request():
    orig_id = "test_orig_direct_file"
    with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
        mock_mirrors.return_value = {"r2": "https://r2.cdn.example.com/orig_direct.jpg"}
        resp = client.get(f"/files/{orig_id}", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers.get("location") == "https://r2.cdn.example.com/orig_direct.jpg"

def test_skip_filtering_and_normalization():
    fake_mirrors = {
        "r2": "https://r2.cdn.example.com/test.jpg",
        "freeimage": "https://freeimage.host/test.jpg",
        "pixhost": "https://img1.pixhost.to/test.jpg",
    }
    with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
        mock_mirrors.return_value = fake_mirrors

        resp1 = client.get("/files/test_skip?skip=r2", follow_redirects=False)
        assert resp1.status_code == 307
        assert resp1.headers.get("location") == "https://freeimage.host/test.jpg"

        resp2 = client.get("/files/test_skip?skip=%20R2%20,%20FreeImage%20", follow_redirects=False)
        assert resp2.status_code == 307
        assert resp2.headers.get("location") == "https://img1.pixhost.to/test.jpg"

def test_direct_url_in_file_id_redirect():
    target_url = "https://external.cdn.org/sample.png"
    resp = client.get(f"/files/{target_url}", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers.get("location") == target_url
    assert resp.headers.get("access-control-allow-origin") == "*"

def test_cache_poisoning_non_dict_mirrors():
    """Adversarial stress test: non-dict JSON stored in cache (e.g. "1") causes AttributeError in main.py line 10540 if not guarded with isinstance(mirrors, dict)."""
    file_id = "poisoned_cache_file_123"
    
    class PoisonedCacheBackend:
        async def get(self, key):
            if key == f"mirrors:{file_id}":
                return "1"  # json.loads("1") -> 1 (int, not dict)
            return None
        async def set(self, key, value, expire=None):
            pass

    with patch("fastapi_cache.FastAPICache.get_backend", return_value=PoisonedCacheBackend()):
        resp = client.get(f"/files/{file_id}", follow_redirects=False)
        # If unguarded, main.py throws 500 AttributeError: 'int' object has no attribute 'get'
        assert resp.status_code != 500, "Uncaught 500 AttributeError when cache contains non-dict JSON"
