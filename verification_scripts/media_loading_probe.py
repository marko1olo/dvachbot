"""
Media Loading Probe Verification Script for site_tgach.
Probes endpoint routes and verifies 200 OK / 307 responses, correct Content-Type headers,
CORS headers (Access-Control-Allow-Origin: *), and valid image binary data.
"""
import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from site_tgach.main import app, _mark_random_dead_file, _is_random_dead_file

# Sample 1x1 transparent PNG binary data
SAMPLE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc` \x05\x00\x00"
    b"\x04\x00\x01\xdd\x8d\xb4\x1c\x00\x00\x00\x00IEND\xaeB`\x82"
)


def probe_media_endpoints():
    print("=" * 60)
    print("Starting Media Loading Probe...")
    print("=" * 60)

    try:
        FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
    except Exception:
        import traceback; traceback.print_exc()

    passed_checks = 0
    total_checks = 0

    def check(condition: bool, description: str):
        nonlocal passed_checks, total_checks
        total_checks += 1
        if condition:
            passed_checks += 1
            print(f"  [PASS] {description}")
        else:
            print(f"  [FAIL] {description}")
            raise AssertionError(f"Probe failure: {description}")

    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country:
        mock_country.return_value = "RU"
        with TestClient(app) as client:

            # 1. Probe Route Aliases with 307 R2 CDN redirect
            print("\n--- 1. Testing Route Aliases & R2 CDN Redirect ---")
            fake_r2_url = "https://r2.cdn.example.com/test_sample_image.png"
            fake_mirrors = {"r2": fake_r2_url}

            routes = [
                "/files/probe_file_001",
                "/file/probe_file_001",
                "/thumb/probe_file_001",
                "/i/probe_file_001",
                "/preview/probe_file_001",
                "/b/src/probe_file_001",
                "/b/thumb/probe_file_001",
            ]

            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = fake_mirrors
                for route in routes:
                    resp = client.get(route, follow_redirects=False)
                    check(resp.status_code == 307, f"Route '{route}' returned HTTP {resp.status_code} (expected 307)")
                    check(resp.headers.get("location") == fake_r2_url, f"Route '{route}' location is {resp.headers.get('location')}")
                    check(resp.headers.get("access-control-allow-origin") == "*", f"Route '{route}' CORS Access-Control-Allow-Origin is '*'")

            # 2. Probe Skip Filtering (R2 -> FreeImage -> PixHost)
            print("\n--- 2. Testing Skip Filtering ---")
            multi_mirrors = {
                "r2": "https://r2.cdn.example.com/image.png",
                "freeimage": "https://freeimage.host/image.png",
                "pixhost": "https://img1.pixhost.to/images/1/image.png",
            }
            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = multi_mirrors

                # Skip R2
                resp1 = client.get("/file/probe_skip?skip=r2", follow_redirects=False)
                check(resp1.status_code == 307, "Skip r2 returns HTTP 307")
                check(resp1.headers.get("location") == multi_mirrors["freeimage"], f"Location is freeimage: {resp1.headers.get('location')}")
                check(resp1.headers.get("access-control-allow-origin") == "*", "CORS header present")

                # Skip R2 & FreeImage
                resp2 = client.get("/file/probe_skip?skip=r2,freeimage", follow_redirects=False)
                check(resp2.status_code == 307, "Skip r2,freeimage returns HTTP 307")
                check(resp2.headers.get("location") == multi_mirrors["pixhost"], f"Location is pixhost: {resp2.headers.get('location')}")
                check(resp2.headers.get("access-control-allow-origin") == "*", "CORS header present")

            # 3. Probe Proxied Stream & Valid Image Binary Data
            print("\n--- 3. Testing Proxied Stream, CORS & Image Binary Integrity ---")

            class MockAiohttpResponse:
                def __init__(self, status=200, content_type="image/png", data=SAMPLE_PNG_BYTES):
                    self.status = status
                    self.headers = {
                        "Content-Type": content_type,
                        "Content-Length": str(len(data)),
                        "Accept-Ranges": "bytes",
                    }
                    self._data = data

                def release(self):
                    pass

                class ContentIter:
                    def __init__(self, data):
                        self.data = data
                    async def iter_chunked(self, n):
                        yield self.data

                @property
                def content(self):
                    return self.ContentIter(self._data)

            class MockSession:
                async def get(self, url, headers=None):
                    return MockAiohttpResponse()

            with patch("site_tgach.main._get_shared_aiohttp_session", return_value=MockSession()):
                catbox_mirrors = {"catbox": "https://files.catbox.moe/sample.png"}
                with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                    mock_mirrors.return_value = catbox_mirrors
                    resp_stream = client.get("/file/probe_stream?skip=r2,telegram,freeimage,imgbb,pixhost", follow_redirects=False)
                    check(resp_stream.status_code == 200, f"Proxied stream returned HTTP {resp_stream.status_code}")
                    check(resp_stream.headers.get("access-control-allow-origin") == "*", "Proxied CORS Access-Control-Allow-Origin is '*'")
                    check(resp_stream.headers.get("content-type") == "image/png", f"Content-Type is {resp_stream.headers.get('content-type')}")
                    check(resp_stream.content == SAMPLE_PNG_BYTES, "Proxied response contains valid PNG binary data")
                    check(resp_stream.content[:8] == b"\x89PNG\r\n\x1a\n", "PNG magic bytes verified")

            # 4. Probe Dead File Sync
            print("\n--- 4. Testing Dead File Sync ---")
            dead_id = "probe_dead_file_777"
            _mark_random_dead_file(dead_id)
            check(_is_random_dead_file(dead_id) is True, f"Dead file mark registered in memory/cache for {dead_id}")

            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = {}
                resp_dead = client.get(f"/file/{dead_id}", follow_redirects=False)
                check(resp_dead.status_code == 404, "Dead file request returned HTTP 404 immediately")

    print("\n" + "=" * 60)
    print(f"Media Loading Probe Summary: ALL {passed_checks}/{total_checks} CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    probe_media_endpoints()
