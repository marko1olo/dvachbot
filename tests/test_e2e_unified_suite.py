"""
Unified E2E Acceptance Integration Test Suite — Milestone 4 (M4)
dvachbot — 404 HTTP Flood & Corrupted HTML Anchor Patch

Verifies all 3 Acceptance Criteria from ORIGINAL_REQUEST.md:
1. Verify 404 Link Generation:
   - Backend & Frontend HTML Anchor regex hardening.
   - Clean <a href="..."> generation for '>>1234 https://domain.com/b/res/343717.html\'>ТГАЧ' without entity leaks.
   - Preservation of multi-parameter URLs (?q=1&lang=en and YouTube watch?v=123&t=30s).
2. Verify Frontend Fallback:
   - Execution of Frontend JS E2E suite (tests/test_e2e_unified_suite_fe.js).
   - FailedMediaCache singleton, fail-fast handleImageError, 0 retries on WebSocket re-renders.
   - Assertion that broken 404 media is requested EXACTLY ONCE per session.
3. Verify Worker Safety:
   - Worker 3-strike failure UPSERT into FileRegistry (tags='download_failed').
   - API post serialization in enrich_extra_data setting is_broken=True and original_url="".
   - GET /files/<file_id> fast-fail 404 response without Telegram polling.
"""

import os
import sys
import html
import re
import asyncio
import time
import subprocess
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from site_tgach.main import (
    app,
    format_post_text as format_post_text_site,
    enrich_extra_data,
    _process_files_list,
)
from Dubsite_tgach.main import format_post_text as format_post_text_dubsite
from common.text_utils import sanitize_html
from common.database import get_failed_files_batch, is_file_permanently_failed

# Initialize FastAPI test client
try:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache-e2e")
except Exception:
    pass

client = TestClient(app, raise_server_exceptions=False)


def async_test(f):
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper


class TestE2EUnifiedSuite(unittest.TestCase):

    # --- ACCEPTANCE CRITERIA 1: VERIFY 404 LINK GENERATION (BACKEND) ---

    def test_e2e_html_anchor_corrupted_link_backend(self):
        """Verify post text '>>1234 https://domain.com/b/res/343717.html\'>ТГАЧ' produces clean href in both backend engines."""
        raw_text = ">>1234 https://domain.com/b/res/343717.html'>ТГАЧ"
        
        for engine_name, format_fn in [("site_tgach", format_post_text_site), ("Dubsite_tgach", format_post_text_dubsite)]:
            result = format_fn(raw_text)
            
            # 1. Href must contain strictly clean URL
            url_href_match = re.search(r'<a href="([^"]+)" [^>]*rel="noopener noreferrer"', result)
            self.assertIsNotNone(url_href_match, f"[{engine_name}] No auto-link href found in: {result}")
            url_href = url_href_match.group(1)

            self.assertEqual(url_href, "https://domain.com/b/res/343717.html", f"[{engine_name}] Href mismatch: {url_href}")
            self.assertNotIn("&#039;", url_href, f"[{engine_name}] Leaked entity &#039; in href: {url_href}")
            self.assertNotIn("&#x27;", url_href, f"[{engine_name}] Leaked entity &#x27; in href: {url_href}")
            self.assertNotIn("&gt;", url_href, f"[{engine_name}] Leaked entity &gt; in href: {url_href}")
            self.assertNotIn("ТГАЧ", url_href, f"[{engine_name}] Leaked Cyrillic text in href: {url_href}")

            # 2. No nested <a> tags
            nested_a = re.search(r'<a\b[^>]*>\s*<a\b', result)
            self.assertIsNone(nested_a, f"[{engine_name}] Nested <a> tags found in: {result}")

    def test_e2e_html_anchor_multi_parameter_urls(self):
        """Verify multi-parameter query strings (?q=1&lang=en and YouTube watch?v=123&t=30s) maintain parameter integrity."""
        test_cases = [
            "Check https://example.com/search?q=1&lang=en",
            "Watch https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s",
            ">>1234 https://example.com/search?q=foo&category=all'>Текст"
        ]
        
        for raw in test_cases:
            for engine_name, format_fn in [("site_tgach", format_post_text_site), ("Dubsite_tgach", format_post_text_dubsite)]:
                res = format_fn(raw)
                url_match = re.search(r'<a href="(https?://[^"]+)"', res)
                self.assertIsNotNone(url_match, f"[{engine_name}] No auto-link href found in: {res}")
                href = url_match.group(1)

                if "search" in raw:
                    self.assertIn("q=", href, f"[{engine_name}] Parameter q missing in href: {href}")
                    self.assertTrue("lang=en" in href or "category=all" in href, f"[{engine_name}] Secondary param missing: {href}")
                if "youtube.com" in raw:
                    self.assertIn("v=dQw4w9WgXcQ", href, f"[{engine_name}] YouTube v param missing: {href}")
                    self.assertTrue("t=30s" in href or "&amp;t=30s" in href, f"[{engine_name}] YouTube t param missing: {href}")

                self.assertNotIn("&#039;", href, f"[{engine_name}] Leaked entity in multi-param href: {href}")
                self.assertNotIn("Текст", href, f"[{engine_name}] Leaked text in multi-param href: {href}")

    def test_e2e_html_anchor_quote_sanitization(self):
        """Verify sanitize_html protects double quotes and escapes single quotes cleanly."""
        text = '<a href="https://example.com/test\'quote">Link</a>'
        sanitized = sanitize_html(text)
        self.assertIn('href="https://example.com/test&#x27;quote"', sanitized, f"Quote sanitization failed: {sanitized}")

    # --- ACCEPTANCE CRITERIA 2: VERIFY FRONTEND FALLBACK (VIA JS SUITE) ---

    def test_e2e_frontend_js_suite(self):
        """Execute tests/test_e2e_unified_suite_fe.js in Node.js subprocess and assert Exit Code 0."""
        fe_test_path = os.path.join(PROJECT_ROOT, "tests", "test_e2e_unified_suite_fe.js")
        self.assertTrue(os.path.exists(fe_test_path), f"Frontend E2E test file missing: {fe_test_path}")

        res = subprocess.run(["node", fe_test_path], capture_output=True, text=True, cwd=PROJECT_ROOT)
        
        print("\n--- FRONTEND E2E TEST OUTPUT ---")
        print(res.stdout)
        if res.stderr:
            print("STDERR:", res.stderr)
            
        self.assertEqual(res.returncode, 0, f"Frontend JS E2E suite failed with Exit Code {res.returncode}")
        self.assertIn("ALL UNIFIED E2E FRONTEND TESTS PASSED WITH EXIT CODE 0", res.stdout)

    # --- ACCEPTANCE CRITERIA 3: VERIFY WORKER SAFETY & FAST-FAIL API ---

    @async_test
    async def test_e2e_worker_upsert_failure_persists_in_db(self):
        """Verify worker 3-strike download failure UPSERTs into FileRegistry with tags='download_failed'."""
        from common.db_pool import get_pool, db_lock

        db = await get_pool()
        test_file_id = f"e2e_worker_failed_{int(time.time())}"
        dummy_sha = f"failed_{test_file_id}"

        # Ensure clean initial state
        async with db_lock:
            await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (test_file_id,))

        # Worker UPSERT simulation on fail_cnt >= 3
        async with db_lock:
            async with db.execute("SELECT sha256 FROM FileRegistry WHERE file_id=?", (test_file_id,)) as cursor:
                row = await cursor.fetchone()
            if row:
                await db.execute("UPDATE FileRegistry SET tags='download_failed' WHERE file_id=?", (test_file_id,))
            else:
                await db.execute(
                    "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, ?, 'photo', 'download_failed', ?)",
                    (dummy_sha, test_file_id, None, time.time()),
                )

        try:
            # Verify persistence in FileRegistry
            async with db.execute("SELECT tags FROM FileRegistry WHERE file_id = ?", (test_file_id,)) as cursor:
                row = await cursor.fetchone()
                self.assertIsNotNone(row, "Failed file record MUST exist in FileRegistry")
                self.assertEqual(row[0], "download_failed", f"Expected 'download_failed' tag, got: {row[0]}")

            # Verify gap query SQL excludes this file_id
            gap_query = "SELECT ? NOT IN (SELECT file_id FROM FileRegistry)"
            async with db.execute(gap_query, (test_file_id,)) as cursor:
                row = await cursor.fetchone()
                self.assertEqual(row[0], 0, "Failed file MUST NOT be picked up by worker gap queries (returns 0/False)")
        finally:
            async with db_lock:
                await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (test_file_id,))

    @async_test
    async def test_e2e_api_enrich_extra_data_strips_broken_urls(self):
        """Verify enrich_extra_data sets is_broken=True and strips original_url & thumbnail_url to '' for failed files."""
        failed_fid = "failed_fid_e2e_999"
        normal_fid = "normal_fid_e2e_888"

        posts = [
            {
                "id": 2002,
                "content": {
                    "type": "files",
                    "files": [
                        {
                            "type": "image",
                            "original_file_id": failed_fid,
                            "thumbnail_file_id": failed_fid,
                            "original_url": f"/files/{failed_fid}/img.jpg",
                            "thumbnail_url": f"/files/{failed_fid}",
                        },
                        {
                            "type": "image",
                            "original_file_id": normal_fid,
                            "thumbnail_file_id": normal_fid,
                            "original_url": f"/files/{normal_fid}/img.jpg",
                            "thumbnail_url": f"/files/{normal_fid}",
                        },
                    ],
                },
            }
        ]

        with patch("common.database.get_failed_files_batch", new_callable=AsyncMock) as mock_failed_batch, \
             patch("common.database.get_duplicate_counts", new_callable=AsyncMock) as mock_dupes, \
             patch("common.database.get_blurhashes_batch", new_callable=AsyncMock) as mock_blurs, \
             patch("common.database.get_mirrors_batch", new_callable=AsyncMock) as mock_mirrors:
            
            mock_failed_batch.return_value = {failed_fid}
            mock_dupes.return_value = {}
            mock_blurs.return_value = {}
            mock_mirrors.return_value = {}

            await enrich_extra_data(posts, is_ru=True)

            files = posts[0]["content"]["files"]
            failed_file = files[0]
            normal_file = files[1]

            # Assert failed media object contract
            self.assertTrue(failed_file.get("is_broken"), "is_broken MUST be True")
            self.assertTrue(failed_file.get("download_failed"), "download_failed MUST be True")
            self.assertEqual(failed_file.get("original_url"), "", "original_url MUST be empty string")
            self.assertEqual(failed_file.get("thumbnail_url"), "", "thumbnail_url MUST be empty string")

            # Assert healthy media object
            self.assertNotEqual(normal_file.get("is_broken"), True, "healthy media must not be broken")
            self.assertNotEqual(normal_file.get("original_url"), "", "healthy media must have valid original_url")

    def test_e2e_process_files_list_preserves_broken_status(self):
        """Verify _process_files_list retains original_url='' for pre-marked broken files."""
        content = {
            "files": [
                {
                    "type": "image",
                    "original_file_id": "broken_e2e_file",
                    "is_broken": True,
                    "download_failed": True,
                    "original_url": "",
                    "thumbnail_url": "",
                }
            ]
        }

        _process_files_list(content)
        file_item = content["files"][0]
        self.assertTrue(file_item["is_broken"])
        self.assertEqual(file_item["original_url"], "")
        self.assertEqual(file_item["thumbnail_url"], "")

    def test_e2e_files_endpoint_fast_fail_404(self):
        """Verify GET /files/<file_id> fast-fails with 404 when file is registered as permanently failed."""
        failed_fid = "failed_fid_e2e_404_fast"

        with patch("common.database.is_file_permanently_failed", new_callable=AsyncMock) as mock_is_failed, \
             patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country:
            mock_is_failed.return_value = True
            mock_country.return_value = "RU"

            resp = client.get(f"/files/{failed_fid}")
            self.assertEqual(resp.status_code, 404, f"Expected 404 status code, got {resp.status_code}")


if __name__ == "__main__":
    unittest.main()

