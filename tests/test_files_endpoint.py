import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from site_tgach.main import app, _mark_random_dead_file, _is_random_dead_file, sanitize_header_filename

try:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
except Exception:
    pass

client = TestClient(app, raise_server_exceptions=False)

@pytest.fixture(autouse=True)
def mock_external_deps():
    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country:
        mock_country.return_value = "RU"
        yield mock_country

def test_route_aliases_and_r2_redirect():
    fake_mirrors = {"r2": "https://r2.cdn.example.com/test_image.jpg"}
    routes_to_test = [
        "/files/test_file_123",
        "/file/test_file_123",
        "/thumb/test_file_123",
        "/i/test_file_123",
        "/preview/test_file_123",
        "/b/src/test_file_123",
        "/b/thumb/test_file_123",
    ]
    with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
        mock_mirrors.return_value = fake_mirrors
        for route in routes_to_test:
            resp = client.get(route, follow_redirects=False)
            assert resp.status_code == 307, f"Failed on route {route}"
            assert resp.headers.get("location") == "https://r2.cdn.example.com/test_image.jpg"
            assert resp.headers.get("access-control-allow-origin") == "*"

def test_skip_filtering():
    fake_mirrors = {
        "r2": "https://r2.cdn.example.com/test.jpg",
        "freeimage": "https://freeimage.host/test.jpg",
        "pixhost": "https://img1.pixhost.to/images/1/test.jpg",
    }
    with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
        mock_mirrors.return_value = fake_mirrors
        
        # Skip r2 -> falls back to freeimage
        resp1 = client.get("/file/test_skip_1?skip=r2", follow_redirects=False)
        assert resp1.status_code == 307
        assert resp1.headers.get("location") == "https://freeimage.host/test.jpg"
        assert resp1.headers.get("access-control-allow-origin") == "*"

        # Skip r2,freeimage -> falls back to pixhost
        resp2 = client.get("/file/test_skip_1?skip=r2,freeimage", follow_redirects=False)
        assert resp2.status_code == 307
        assert resp2.headers.get("location") == "https://img1.pixhost.to/images/1/test.jpg"
        assert resp2.headers.get("access-control-allow-origin") == "*"

def test_skip_parameter_normalization():
    fake_mirrors = {
        "r2": "https://r2.cdn.example.com/test.jpg",
        "freeimage": "https://freeimage.host/test.jpg",
        "pixhost": "https://img1.pixhost.to/images/1/test.jpg",
    }
    with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
        mock_mirrors.return_value = fake_mirrors
        
        # Test skip with whitespace and uppercase: " R2 , FreeImage "
        resp = client.get("/file/test_skip_norm?skip=%20R2%20,%20FreeImage%20", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers.get("location") == "https://img1.pixhost.to/images/1/test.jpg"

def test_sanitize_header_filename():
    assert sanitize_header_filename('test"file\r\nheader:inject.png') == "testfileheader:inject.png"
    assert sanitize_header_filename('  "quoted_file.jpg"  ') == "quoted_file.jpg"
    assert sanitize_header_filename("bad\x00file\nname.pdf") == "badfilename.pdf"
    assert sanitize_header_filename("") == "file"
    assert sanitize_header_filename(None) == "file"

def test_dead_file_redis_sync():
    dead_fid = "dead_file_test_id_999"
    _mark_random_dead_file(dead_fid)
    assert _is_random_dead_file(dead_fid) is True

    with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
        mock_mirrors.return_value = {}
        resp = client.get(f"/file/{dead_fid}", follow_redirects=False)
        assert resp.status_code == 404

def test_cors_headers_on_direct_link():
    direct_url = "https://external.cdn.example.com/direct_image.png"
    resp = client.get(f"/file/{direct_url}", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers.get("location") == direct_url
    assert resp.headers.get("access-control-allow-origin") == "*"

