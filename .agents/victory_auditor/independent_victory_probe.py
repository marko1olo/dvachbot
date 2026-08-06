"""
Independent Victory Auditor Verification Probe.
This script performs independent, automated verification of site_tgach media pipeline functionality,
testing all requirements (R1, R2) and acceptance criteria.
"""
import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from site_tgach.main import app, _mark_random_dead_file, _is_random_dead_file, sanitize_header_filename
from site_tgach.pixhost import upload_file_to_pixhost

SAMPLE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc` \x05\x00\x00"
    b"\x04\x00\x01\xdd\x8d\xb4\x1c\x00\x00\x00\x00IEND\xaeB`\x82"
)

async def run_victory_audit():
    print("=" * 70)
    print("INDEPENDENT VICTORY AUDIT PROBE — site_tgach Media Pipeline")
    print("=" * 70)

    try:
        FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
    except Exception:
        import traceback; traceback.print_exc()

    results = []

    def assert_check(condition: bool, desc: str):
        if condition:
            results.append((True, desc))
            print(f"  [PASS] {desc}")
        else:
            results.append((False, desc))
            print(f"  [FAIL] {desc}")
            raise AssertionError(f"Independent Audit Failure: {desc}")

    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country:
        mock_country.return_value = "RU"
        with TestClient(app, raise_server_exceptions=False) as client:

            # Test 1: Route Aliases & R2 CDN Redirect
            print("\n[Audit Test 1] Route Aliases & CORS Headers")
            fake_r2_url = "https://r2.cdn.example.com/auditor_test.png"
            test_routes = [
                "/files/auditor_001",
                "/file/auditor_001",
                "/thumb/auditor_001",
                "/i/auditor_001",
                "/preview/auditor_001",
                "/b/src/auditor_001",
                "/b/thumb/auditor_001",
                "/po/src/auditor_001/custom_name.png",
                "/a/thumb/auditor_001/thumb.jpg",
            ]
            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = {"r2": fake_r2_url}
                for r in test_routes:
                    res = client.get(r, follow_redirects=False)
                    assert_check(res.status_code == 307, f"Route '{r}' status code 307")
                    assert_check(res.headers.get("location") == fake_r2_url, f"Route '{r}' location header match")
                    assert_check(res.headers.get("access-control-allow-origin") == "*", f"Route '{r}' CORS header present")

            # Test 2: Fallback Mirror Cascade & Skip Parameter
            print("\n[Audit Test 2] Fallback Mirror Cascade & Skip Parameter")
            mirrors_data = {
                "r2": "https://r2.cdn.example.com/file.png",
                "freeimage": "https://freeimage.host/file.png",
                "imgbb": "https://i.ibb.co/file.png",
                "pixhost": "https://img1.pixhost.to/images/1/file.png",
                "catbox": "https://files.catbox.moe/file.png",
            }
            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = mirrors_data

                # Default prioritizes R2
                res = client.get("/file/auditor_cascade", follow_redirects=False)
                assert_check(res.status_code == 307 and res.headers.get("location") == mirrors_data["r2"], "Cascade #1: R2 CDN")

                # Skip R2 -> FreeImage
                res = client.get("/file/auditor_cascade?skip=R2", follow_redirects=False)
                assert_check(res.status_code == 307 and res.headers.get("location") == mirrors_data["freeimage"], "Cascade #2: FreeImage (with case normalization)")

                # Skip R2, FreeImage -> ImgBB
                res = client.get("/file/auditor_cascade?skip=r2,%20freeimage%20", follow_redirects=False)
                assert_check(res.status_code == 307 and res.headers.get("location") == mirrors_data["imgbb"], "Cascade #3: ImgBB (with whitespace normalization)")

                # Skip R2, FreeImage, ImgBB -> PixHost
                res = client.get("/file/auditor_cascade?skip=r2,freeimage,imgbb", follow_redirects=False)
                assert_check(res.status_code == 307 and res.headers.get("location") == mirrors_data["pixhost"], "Cascade #4: PixHost")

            # Test 3: Direct Link URL Handling & Header Sanitization
            print("\n[Audit Test 3] Direct Link Redirect & Header Sanitization")
            target_url = "https://cdn.external.site/image.png"
            res = client.get(f"/file/{target_url}", follow_redirects=False)
            assert_check(res.status_code == 301, "Direct URL redirect HTTP 301")
            assert_check(res.headers.get("location") == target_url, "Direct URL location header match")
            assert_check(res.headers.get("access-control-allow-origin") == "*", "Direct URL CORS header present")

            # Header Sanitization
            clean_fn = sanitize_header_filename('attack_file"\r\nX-Injected: true.png')
            assert_check("\r" not in clean_fn and "\n" not in clean_fn and '"' not in clean_fn, "Filename sanitization strips CRLF and quotes")

            # Test 4: Pixhost Direct Image URL Parsing
            print("\n[Audit Test 4] Pixhost Direct Image URL Resolution")
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_response = AsyncMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "show_url": "https://pixhost.to/show/9876/sample_img.png",
                    "th_url": "https://t9876.pixhost.to/thumbs/9876/sample_img.png"
                }
                mock_post.return_value = mock_response

                direct_link = await upload_file_to_pixhost("dummy_path.png")
                assert_check(direct_link == "https://img9876.pixhost.to/images/9876/sample_img.png", "Pixhost direct URL regex conversion")

            # Test 5: Dead File Cache Integration
            print("\n[Audit Test 5] Dead File Synchronization")
            dead_id = "dead_file_auditor_9999"
            _mark_random_dead_file(dead_id)
            assert_check(_is_random_dead_file(dead_id) is True, "Dead file stored in cache")

            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = {}
                res = client.get(f"/file/{dead_id}", follow_redirects=False)
                assert_check(res.status_code == 404, "Dead file request returns 404 immediately")

    print("\n" + "=" * 70)
    print(f"Independent Victory Audit Summary: ALL {len(results)} CHECKS PASSED!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_victory_audit())
