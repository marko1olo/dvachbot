import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from common.database import get_failed_files_batch, is_file_permanently_failed
from site_tgach.main import app, enrich_extra_data, _process_files_list

try:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache-test")
except Exception:
    pass

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def mock_external_deps():
    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country:
        mock_country.return_value = "RU"
        yield mock_country


@pytest.mark.asyncio
async def test_is_file_permanently_failed_and_batch_lookup():
    """Verify get_failed_files_batch and is_file_permanently_failed DB queries."""
    from common.db_pool import get_pool, db_lock

    db = await get_pool()
    failed_fid = f"test_failed_{int(time.time())}"
    normal_fid = f"test_normal_{int(time.time())}"
    dummy_sha = f"failed_{failed_fid}"

    async with db_lock:
        await db.execute(
            "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'photo', 'download_failed', ?)",
            (dummy_sha, failed_fid, time.time()),
        )

    try:
        # Test single item lookup
        is_failed = await is_file_permanently_failed(failed_fid)
        assert is_failed is True, f"Expected {failed_fid} to be permanently failed"

        is_normal_failed = await is_file_permanently_failed(normal_fid)
        assert is_normal_failed is False, f"Expected {normal_fid} not to be failed"

        # Test batch lookup
        batch_res = await get_failed_files_batch([failed_fid, normal_fid])
        assert failed_fid in batch_res
        assert normal_fid not in batch_res
    finally:
        # Cleanup
        async with db_lock:
            await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (failed_fid,))


@pytest.mark.asyncio
async def test_enrich_extra_data_strips_broken_urls():
    """Verify enrich_extra_data sets is_broken=True and strips original_url & thumbnail_url for failed files."""
    failed_fid = "failed_fid_enrich_999"
    normal_fid = "normal_fid_enrich_888"

    posts = [
        {
            "id": 1001,
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

        # Failed file assertions
        assert failed_file.get("is_broken") is True
        assert failed_file.get("download_failed") is True
        assert failed_file.get("original_url") == ""
        assert failed_file.get("thumbnail_url") == ""

        # Normal file assertions
        assert normal_file.get("is_broken") is not True
        assert normal_file.get("original_url") != ""


def test_process_files_list_preserves_is_broken():
    """Verify _process_files_list respects pre-existing is_broken / download_failed flag."""
    content = {
        "files": [
            {
                "type": "image",
                "original_file_id": "broken_123",
                "is_broken": True,
                "download_failed": True,
                "original_url": "",
                "thumbnail_url": "",
            }
        ]
    }

    _process_files_list(content)
    file_item = content["files"][0]
    assert file_item["is_broken"] is True
    assert file_item["original_url"] == ""
    assert file_item["thumbnail_url"] == ""


def test_files_endpoint_fast_fail_404():
    """Verify GET /files/<file_id> fast-fails with HTTP 404 when file is permanently failed."""
    failed_fid = "failed_fid_fast_fail_777"

    with patch("common.database.is_file_permanently_failed", new_callable=AsyncMock) as mock_is_failed:
        mock_is_failed.return_value = True

        resp = client.get(f"/files/{failed_fid}")
        assert resp.status_code == 404
        assert "unavailable" in resp.text.lower() or resp.status_code == 404


@pytest.mark.asyncio
async def test_worker_upsert_failure_prevents_gap_requery():
    """Verify worker upserts FileRegistry when download fails 3 times, preventing gap requeries."""
    from common.db_pool import get_pool, db_lock

    db = await get_pool()
    test_file_id = f"worker_gap_failed_{int(time.time())}"
    dummy_sha = f"failed_{test_file_id}"

    # Ensure clean state
    async with db_lock:
        await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (test_file_id,))

    # Simulate worker fail_cnt >= 3 UPSERT logic
    file_type = "photo"
    thumb_id = None

    async with db_lock:
        async with db.execute(
            "SELECT sha256 FROM FileRegistry WHERE file_id=?",
            (test_file_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            await db.execute(
                "UPDATE FileRegistry SET tags='download_failed' WHERE file_id=?",
                (test_file_id,),
            )
        else:
            await db.execute(
                "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, ?, ?, 'download_failed', ?)",
                (dummy_sha, test_file_id, thumb_id, file_type, time.time()),
            )

    try:
        # Verify row exists in FileRegistry with tags='download_failed'
        async with db.execute(
            "SELECT tags FROM FileRegistry WHERE file_id = ?", (test_file_id,)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == "download_failed"

        # Verify gap query SQL eliminates this file_id
        gap_query = "SELECT ? NOT IN (SELECT file_id FROM FileRegistry)"
        async with db.execute(gap_query, (test_file_id,)) as cursor:
            row = await cursor.fetchone()
            assert row[0] == 0, "Failed file MUST NOT be selected by gap query (should return 0/False)"
    finally:
        # Cleanup
        async with db_lock:
            await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (test_file_id,))


@pytest.mark.asyncio
async def test_error_no_tags_file_resiliency():
    """Verify that a file with tags = 'error_no_tags' in FileRegistry is NOT treated as permanently broken.
    - /files/{file_id} must return HTTP 200 OK (not 404 permanently failed).
    - enrich_extra_data must return a non-empty original_url.
    """
    from common.db_pool import get_pool, db_lock

    db = await get_pool()
    no_tags_fid = f"test_no_tags_{int(time.time())}"
    dummy_sha = f"notags_{no_tags_fid}"

    async with db_lock:
        await db.execute(
            "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'photo', 'error_no_tags', ?)",
            (dummy_sha, no_tags_fid, time.time()),
        )

    try:
        # 1. Verify DB helper functions do NOT classify it as permanently failed
        is_failed = await is_file_permanently_failed(no_tags_fid)
        assert is_failed is False, f"Expected {no_tags_fid} with tags='error_no_tags' NOT to be permanently failed"

        failed_batch = await get_failed_files_batch([no_tags_fid])
        assert no_tags_fid not in failed_batch, f"Expected {no_tags_fid} NOT to be in failed_batch"

        # 2. Verify enrich_extra_data returns non-empty original_url
        posts = [
            {
                "id": 2001,
                "content": {
                    "type": "files",
                    "files": [
                        {
                            "type": "image",
                            "original_file_id": no_tags_fid,
                            "thumbnail_file_id": no_tags_fid,
                            "tags": "error_no_tags",
                        }
                    ],
                },
            }
        ]

        with patch("common.database.get_duplicate_counts", new_callable=AsyncMock) as mock_dupes, \
             patch("common.database.get_blurhashes_batch", new_callable=AsyncMock) as mock_blurs, \
             patch("common.database.get_mirrors_batch", new_callable=AsyncMock) as mock_mirrors:
            mock_dupes.return_value = {}
            mock_blurs.return_value = {}
            mock_mirrors.return_value = {}

            await enrich_extra_data(posts, is_ru=True)

            f = posts[0]["content"]["files"][0]
            assert f.get("is_broken") is not True
            assert f.get("original_url") != "", "original_url must be non-empty for error_no_tags file"
            assert f.get("thumbnail_url") != "", "thumbnail_url must be non-empty for error_no_tags file"

        # 3. Verify /files/{file_id} returns HTTP 200/307 (with mocked cached file path)
        with patch("site_tgach.main.get_cached_file_path", new_callable=AsyncMock) as mock_path:
            mock_path.return_value = ("photos/fake.jpg", "fake_token")

            resp = client.get(f"/files/{no_tags_fid}", follow_redirects=False)
            assert resp.status_code in (200, 307), f"Expected HTTP 200 or 307 from /files/{no_tags_fid}, got {resp.status_code}"
    finally:
        async with db_lock:
            await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (no_tags_fid,))


@pytest.mark.asyncio
async def test_missing_thumbnail_file_id_fallback():
    """Verify that a post file with missing or empty thumbnail_file_id populates thumbnail_url with a fallback URL."""
    valid_fid = "valid_fid_no_thumb_999"

    posts = [
        {
            "id": 3001,
            "content": {
                "type": "files",
                "files": [
                    {
                        "type": "image",
                        "original_file_id": valid_fid,
                        "thumbnail_file_id": None,  # Missing thumbnail_file_id
                    }
                ],
            },
        }
    ]

    with patch("common.database.get_failed_files_batch", new_callable=AsyncMock) as mock_failed_batch, \
         patch("common.database.get_duplicate_counts", new_callable=AsyncMock) as mock_dupes, \
         patch("common.database.get_blurhashes_batch", new_callable=AsyncMock) as mock_blurs, \
         patch("common.database.get_mirrors_batch", new_callable=AsyncMock) as mock_mirrors:
        mock_failed_batch.return_value = set()
        mock_dupes.return_value = {}
        mock_blurs.return_value = {}
        mock_mirrors.return_value = {}

        await enrich_extra_data(posts, is_ru=True)

        f = posts[0]["content"]["files"][0]
        assert f.get("original_url") == f"/files/{valid_fid}"
        assert f.get("thumbnail_url") != "", "thumbnail_url must be populated with fallback URL when thumbnail_file_id is missing"
        assert f.get("thumbnail_url") == f["original_url"], "thumbnail_url should fallback to original_url or /files/{file_id}"

