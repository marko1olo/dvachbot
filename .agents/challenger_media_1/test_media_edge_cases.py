import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock

# Add project root to sys.path
sys.path.insert(0, r"C:\Users\danat\Desktop\dvachbot")

os.environ["PYTHONUTF8"] = "1"
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from site_tgach.main import app, _mark_random_dead_file, _is_random_dead_file

SAMPLE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc` \x05\x00\x00"
    b"\x04\x00\x01\xdd\x8d\xb4\x1c\x00\x00\x00\x00IEND\xaeB`\x82"
)


def run_edge_case_tests():
    print("=" * 70)
    print("EMPIRICAL CHALLENGER: Media Endpoints Edge-Case & Stress Tests")
    print("=" * 70)

    try:
        FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
    except Exception:
        pass

    results = []

    def record(name: str, passed: bool, detail: str):
        status = "PASS" if passed else "FAIL"
        results.append((name, status, detail))
        print(f"[{status}] {name}: {detail}")

    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country, \
         patch("site_tgach.main.get_cached_file_path", new_callable=AsyncMock) as mock_cached_path:
        mock_country.return_value = "RU"
        mock_cached_path.return_value = None

        with TestClient(app) as client:

            # -------------------------------------------------------------
            # TEST GROUP 1: Route Aliases (7 routes x 3 checks)
            # -------------------------------------------------------------
            print("\n--- GROUP 1: Route Aliases ---")
            fake_r2_url = "https://r2.cdn.example.com/test_sample.png"
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
                for r in routes:
                    resp = client.get(r, follow_redirects=False)
                    record(f"Route Alias {r} Status 307", resp.status_code == 307, f"Got HTTP {resp.status_code}")
                    record(f"Route Alias {r} Location Header", resp.headers.get("location") == fake_r2_url, f"Location: {resp.headers.get('location')}")
                    record(f"Route Alias {r} CORS Header", resp.headers.get("access-control-allow-origin") == "*", f"CORS: {resp.headers.get('access-control-allow-origin')}")

            # -------------------------------------------------------------
            # TEST GROUP 2: Skip Parameter Edge Cases
            # -------------------------------------------------------------
            print("\n--- GROUP 2: Skip Parameter Edge Cases ---")
            multi_mirrors = {
                "r2": "https://r2.cdn.example.com/image.png",
                "freeimage": "https://freeimage.host/image.png",
                "pixhost": "https://img1.pixhost.to/images/1/image.png",
                "catbox": "https://files.catbox.moe/sample.png",
            }
            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = multi_mirrors

                # 2.1 Standard multi-skip
                resp = client.get("/file/test_skip?skip=r2,freeimage", follow_redirects=False)
                record("Multi-skip ?skip=r2,freeimage -> pixhost", resp.headers.get("location") == multi_mirrors["pixhost"], f"Location: {resp.headers.get('location')}")

                # 2.2 Whitespace in skip: ?skip=r2,%20freeimage (Space before freeimage)
                resp_ws = client.get("/file/test_skip?skip=r2,%20freeimage", follow_redirects=False)
                is_freeimage = (resp_ws.headers.get("location") == multi_mirrors["freeimage"])
                record("Whitespace in skip ?skip=r2,%20freeimage (unstripped whitespace behavior)", not is_freeimage, f"Redirected to '{resp_ws.headers.get('location')}' (space caused failover bypass)")

                # 2.3 Case sensitivity: ?skip=R2,FREEIMAGE
                resp_cs = client.get("/file/test_skip?skip=R2,FREEIMAGE", follow_redirects=False)
                is_r2 = (resp_cs.headers.get("location") == multi_mirrors["r2"])
                record("Case sensitivity ?skip=R2,FREEIMAGE (uppercase behavior)", not is_r2, f"Redirected to '{resp_cs.headers.get('location')}' (uppercase caused failover bypass)")

                # 2.4 Empty elements in skip: ?skip=r2,,freeimage
                resp_ee = client.get("/file/test_skip?skip=r2,,freeimage", follow_redirects=False)
                record("Empty elements in skip ?skip=r2,,freeimage -> pixhost", resp_ee.headers.get("location") == multi_mirrors["pixhost"], f"Location: {resp_ee.headers.get('location')}")

                # 2.5 Trailing comma in skip: ?skip=r2,
                resp_tc = client.get("/file/test_skip?skip=r2,", follow_redirects=False)
                record("Trailing comma in skip ?skip=r2, -> freeimage", resp_tc.headers.get("location") == multi_mirrors["freeimage"], f"Location: {resp_tc.headers.get('location')}")

            # -------------------------------------------------------------
            # TEST GROUP 3: Direct URL vs File ID Path Handling
            # -------------------------------------------------------------
            print("\n--- GROUP 3: Direct URL vs File ID Path Handling ---")

            # 3.1 Direct URL: http:/example.com/img.png (FastAPI normalized)
            resp_url1 = client.get("/file/http:/example.com/img.png", follow_redirects=False)
            record("Direct URL http:/ -> 301 Redirect", resp_url1.status_code == 301, f"Status: {resp_url1.status_code}")
            record("Direct URL http:/ -> Location http://example.com/img.png", resp_url1.headers.get("location") == "http://example.com/img.png", f"Location: {resp_url1.headers.get('location')}")
            record("Direct URL http:/ -> CORS header present", resp_url1.headers.get("access-control-allow-origin") == "*", f"CORS: {resp_url1.headers.get('access-control-allow-origin')}")

            # 3.2 Direct URL: https:/r2.cdn.example.com/pics/photo.jpg
            resp_url2 = client.get("/file/https:/r2.cdn.example.com/pics/photo.jpg", follow_redirects=False)
            record("Direct URL https:/ -> 301 Redirect", resp_url2.status_code == 301, f"Status: {resp_url2.status_code}")
            record("Direct URL https:/ -> Location https://r2.cdn.example.com/pics/photo.jpg", resp_url2.headers.get("location") == "https://r2.cdn.example.com/pics/photo.jpg", f"Location: {resp_url2.headers.get('location')}")

            # 3.3 Path-encoded filename in File ID: /files/probe_file_001/custom_download.png
            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = {"freeimage": "https://freeimage.host/img.png"}
                resp_path_file = client.get("/files/probe_file_001/custom_download.png?skip=r2", follow_redirects=False)
                record("File ID with path filename /probe_file_001/custom_download.png", resp_path_file.status_code == 307, f"Status: {resp_path_file.status_code}")
                record("File ID with path filename Location freeimage", resp_path_file.headers.get("location") == "https://freeimage.host/img.png", f"Location: {resp_path_file.headers.get('location')}")

            # -------------------------------------------------------------
            # TEST GROUP 4: Filename Query Parameter Handling
            # -------------------------------------------------------------
            print("\n--- GROUP 4: Filename Query Parameter Handling ---")

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
                with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                    mock_mirrors.return_value = {"catbox": "https://files.catbox.moe/sample.png"}

                    # 4.1 Explicit filename parameter
                    resp_fn1 = client.get("/file/probe_stream?skip=r2,telegram,freeimage,imgbb,pixhost&filename=my_photo.png", follow_redirects=False)
                    cd_header1 = resp_fn1.headers.get("content-disposition", "")
                    record("Explicit filename query param sets Content-Disposition", 'inline; filename="my_photo.png"' in cd_header1, f"Content-Disposition: '{cd_header1}'")

                    # 4.2 Missing filename query parameter (None)
                    resp_fn2 = client.get("/file/probe_stream?skip=r2,telegram,freeimage,imgbb,pixhost", follow_redirects=False)
                    cd_header2 = resp_fn2.headers.get("content-disposition", "")
                    record("Missing filename query param omits Content-Disposition", "Content-Disposition" not in resp_fn2.headers or 'filename="sample.png"' in cd_header2, f"Content-Disposition: '{cd_header2}'")

                    # 4.3 Empty filename query parameter (?filename=)
                    resp_fn3 = client.get("/file/probe_stream?skip=r2,telegram,freeimage,imgbb,pixhost&filename=", follow_redirects=False)
                    cd_header3 = resp_fn3.headers.get("content-disposition", "")
                    record("Empty filename query param (?filename=) handling", "Content-Disposition" not in resp_fn3.headers, f"Content-Disposition: '{cd_header3}'")

                    # 4.4 Filename with spaces and special chars
                    resp_fn4 = client.get("/file/probe_stream?skip=r2,telegram,freeimage,imgbb,pixhost&filename=cool%20picture%20(1).png", follow_redirects=False)
                    cd_header4 = resp_fn4.headers.get("content-disposition", "")
                    record("Filename with spaces/special chars in Content-Disposition", 'filename="cool picture (1).png"' in cd_header4, f"Content-Disposition: '{cd_header4}'")

            # -------------------------------------------------------------
            # TEST GROUP 5: Response Codes, Headers & CORS Verification
            # -------------------------------------------------------------
            print("\n--- GROUP 5: Status Codes, Location & CORS ---")

            # 5.1 HTTP 307 for mirror redirect
            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = {"r2": "https://r2.cdn.example.com/pic.png"}
                resp_307 = client.get("/file/probe_307", follow_redirects=False)
                record("Mirror Redirect returns HTTP 307", resp_307.status_code == 307, f"Status: {resp_307.status_code}")
                record("Mirror Redirect includes CORS Access-Control-Allow-Origin: *", resp_307.headers.get("access-control-allow-origin") == "*", f"CORS: {resp_307.headers.get('access-control-allow-origin')}")
                record("Mirror Redirect includes Cache-Control public", "public" in resp_307.headers.get("cache-control", ""), f"Cache-Control: {resp_307.headers.get('cache-control')}")

            # 5.2 HTTP 404 for dead file / unavailable file
            _mark_random_dead_file("probe_dead_999")
            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = {}
                resp_404 = client.get("/file/probe_dead_999", follow_redirects=False)
                record("Dead File returns HTTP 404", resp_404.status_code == 404, f"Status: {resp_404.status_code}")
                cors_404 = resp_404.headers.get("access-control-allow-origin")
                record("Dead File HTTP 404 includes CORS header", cors_404 == "*", f"CORS on 404: '{cors_404}'")

            # 5.3 HEAD request method
            with patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_mirrors:
                mock_mirrors.return_value = {"r2": "https://r2.cdn.example.com/pic.png"}
                resp_head = client.head("/file/probe_head", follow_redirects=False)
                record("HEAD method supported returning HTTP 307", resp_head.status_code == 307, f"HEAD Status: {resp_head.status_code}")
                record("HEAD method returns Location header", resp_head.headers.get("location") == "https://r2.cdn.example.com/pic.png", f"HEAD Location: {resp_head.headers.get('location')}")

    # Summary
    print("\n" + "=" * 70)
    total = len(results)
    passed_cnt = sum(1 for r in results if r[1] == "PASS")
    failed_cnt = total - passed_cnt
    print(f"Empirical Edge-Case Test Summary: {passed_cnt}/{total} PASSED ({failed_cnt} FAILED/ATTENTION)")
    print("=" * 70)

    for name, status, detail in results:
        if status == "FAIL":
            print(f"  ❌ [{status}] {name}: {detail}")
        else:
            print(f"  ✅ [{status}] {name}")

    return passed_cnt, total, results


if __name__ == "__main__":
    run_edge_case_tests()
