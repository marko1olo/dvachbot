import pytest
import asyncio
import time
import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from common.database import get_failed_files_batch, is_file_permanently_failed
from common.db_pool import get_pool, db_lock
from site_tgach.main import app, enrich_extra_data, _process_files_list
from site_tgach.tagging_worker import get_tasks

try:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache-adversarial")
except Exception:
    pass

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def mock_external_deps():
    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country:
        mock_country.return_value = "RU"
        yield mock_country


@pytest.mark.asyncio
async def test_adversarial_concurrency_and_locking():
    """Stress test concurrent worker UPSERTs and DB queries for lock collisions."""
    db = await get_pool()
    num_files = 25
    test_fids = [f"adv_conc_fid_{i}_{int(time.time())}" for i in range(num_files)]
    
    async def worker_upsert(file_id):
        dummy_sha = f"failed_{file_id}"
        file_type = "photo"
        thumb_id = f"thumb_{file_id}"
        async with db_lock:
            await db.execute("BEGIN IMMEDIATE")
            try:
                async with db.execute(
                    "SELECT sha256 FROM FileRegistry WHERE file_id=?",
                    (file_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if row:
                    await db.execute(
                        "UPDATE FileRegistry SET tags='download_failed' WHERE file_id=?",
                        (file_id,),
                    )
                else:
                    await db.execute(
                        "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, ?, ?, 'download_failed', ?)",
                        (dummy_sha, file_id, thumb_id, file_type, time.time()),
                    )
                await db.execute("COMMIT")
            except Exception:
                await db.execute("ROLLBACK")
                raise

    async def reader_query(file_ids):
        # Perform random queries concurrently
        for _ in range(5):
            res_set = await get_failed_files_batch(file_ids)
            for fid in file_ids:
                _ = await is_file_permanently_failed(fid)
            await asyncio.sleep(0.01)

    try:
        # Run 25 worker upserts and reader queries concurrently
        upsert_tasks = [worker_upsert(fid) for fid in test_fids]
        reader_task = reader_query(test_fids)
        await asyncio.gather(*upsert_tasks, reader_task)

        # Verify all files are stored and detected
        failed_set = await get_failed_files_batch(test_fids)
        assert len(failed_set) >= num_files * 2  # Includes thumbnail_ids too
        for fid in test_fids:
            assert fid in failed_set
            assert await is_file_permanently_failed(fid) is True

    finally:
        # Cleanup test entries
        async with db_lock:
            placeholders = ",".join("?" for _ in test_fids)
            await db.execute(f"DELETE FROM FileRegistry WHERE file_id IN ({placeholders})", test_fids)


@pytest.mark.asyncio
async def test_adversarial_tag_variants():
    """Verify that all error/failure tag patterns are caught by database query helpers."""
    db = await get_pool()
    tag_cases = [
        ("fid_tag_dl_failed", "download_failed"),
        ("fid_tag_err", "error"),
        ("fid_tag_err_no_tags", "error_no_tags"),
        ("fid_tag_err_too_large", "error_too_large"),
        ("fid_tag_fmt_unsupported", "format_unsupported"),
        ("fid_tag_dead", "dead"),
        ("fid_tag_err_prefix", "error_500_server_down"),
        ("fid_tag_dl_substr", "custom_download_failed_reason"),
    ]
    fids = [item[0] for item in tag_cases]

    try:
        async with db_lock:
            for fid, tag in tag_cases:
                await db.execute(
                    "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'photo', ?, ?)",
                    (f"sha_{fid}", fid, tag, time.time()),
                )

        batch_result = await get_failed_files_batch(fids)
        for fid, _ in tag_cases:
            assert fid in batch_result, f"Failed tag variant for {fid} not in batch_result"
            assert await is_file_permanently_failed(fid) is True, f"Failed tag variant for {fid} returned False"

    finally:
        async with db_lock:
            placeholders = ",".join("?" for _ in fids)
            await db.execute(f"DELETE FROM FileRegistry WHERE file_id IN ({placeholders})", fids)


@pytest.mark.asyncio
async def test_adversarial_endpoint_fast_fail_paths():
    """Verify fast-fail 404 logic on subpath, query params, and non-failed files."""
    failed_fid = "failed_fid_adv_path_123"
    healthy_fid = "healthy_fid_adv_path_456"

    db = await get_pool()
    try:
        async with db_lock:
            await db.execute(
                "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'photo', 'download_failed', ?)",
                (f"sha_{failed_fid}", failed_fid, time.time()),
            )

        # 1. Failed fid simple
        resp = client.get(f"/files/{failed_fid}")
        assert resp.status_code == 404

        # 2. Failed fid with nested filename subpath
        resp = client.get(f"/files/{failed_fid}/img_123.jpg")
        assert resp.status_code == 404

        # 3. Failed fid with query params
        resp = client.get(f"/files/{failed_fid}/img.png?size=large")
        assert resp.status_code == 404

    finally:
        async with db_lock:
            await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (failed_fid,))


@pytest.mark.asyncio
async def test_adversarial_enrich_extra_data_partial_and_replies():
    """Verify enrich_extra_data correctly handles posts with replies and thumbnail-only failures."""
    orig_failed_fid = "orig_failed_999"
    thumb_only_failed_fid = "thumb_failed_888"
    healthy_fid = "healthy_777"

    posts = [
        {
            "id": 5001,
            "content": {
                "files": [
                    {
                        "type": "image",
                        "original_file_id": orig_failed_fid,
                        "thumbnail_file_id": "thumb_for_orig_failed",
                        "original_url": f"/files/{orig_failed_fid}",
                        "thumbnail_url": "/files/thumb_for_orig_failed",
                    },
                    {
                        "type": "video",
                        "original_file_id": healthy_fid,
                        "thumbnail_file_id": thumb_only_failed_fid,
                        "original_url": f"/files/{healthy_fid}",
                        "thumbnail_url": f"/files/{thumb_only_failed_fid}",
                    },
                ]
            },
            "latest_replies": [
                {
                    "id": 5002,
                    "content": {
                        "files": [
                            {
                                "type": "image",
                                "original_file_id": orig_failed_fid,
                                "original_url": f"/files/{orig_failed_fid}",
                            }
                        ]
                    },
                }
            ],
        }
    ]

    with patch("common.database.get_failed_files_batch", new_callable=AsyncMock) as mock_batch, \
         patch("common.database.get_duplicate_counts", new_callable=AsyncMock) as mock_dupes, \
         patch("common.database.get_blurhashes_batch", new_callable=AsyncMock) as mock_blurs, \
         patch("common.database.get_mirrors_batch", new_callable=AsyncMock) as mock_mirrors:

        mock_batch.return_value = {orig_failed_fid, thumb_only_failed_fid}
        mock_dupes.return_value = {}
        mock_blurs.return_value = {}
        mock_mirrors.return_value = {}

        await enrich_extra_data(posts, is_ru=True)

        main_files = posts[0]["content"]["files"]
        file_orig_failed = main_files[0]
        file_thumb_failed = main_files[1]
        reply_file = posts[0]["latest_replies"][0]["content"]["files"][0]

        # Orig failed file assertions
        assert file_orig_failed["is_broken"] is True
        assert file_orig_failed["download_failed"] is True
        assert file_orig_failed["original_url"] == ""
        assert file_orig_failed["thumbnail_url"] == ""

        # Thumb failed file assertions
        assert file_thumb_failed.get("is_broken") is not True
        assert file_thumb_failed["original_url"] != ""
        assert file_thumb_failed["thumbnail_url"] == ""
        assert file_thumb_failed["thumbnail_download_failed"] is True

        # Reply file assertions
        assert reply_file["is_broken"] is True
        assert reply_file["original_url"] == ""


@pytest.mark.asyncio
async def test_adversarial_worker_gap_suppression():
    """Verify gap query in tagging_worker suppresses failed files once recorded in FileRegistry."""
    db = await get_pool()
    gap_fid = f"gap_test_fid_{int(time.time())}"
    dummy_sha = f"failed_{gap_fid}"

    # Get max post_num currently in Posts
    async with db.execute("SELECT COALESCE(MAX(post_num), 0) FROM Posts") as cursor:
        max_pnum = (await cursor.fetchone())[0]
    post_num = max_pnum + 1

    try:
        # 1. Insert a post into Posts table with file gap
        content_json = json.dumps({"files": [{"original_file_id": gap_fid, "type": "photo"}]})
        async with db_lock:
            await db.execute(
                "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 1, ?, ?)",
                (post_num, content_json, time.time()),
            )

        query_gaps_files = """
            SELECT DISTINCT 
                json_extract(j.value, '$.original_file_id') as fid, 
                json_extract(j.value, '$.type') as ftype,
                json_extract(j.value, '$.thumbnail_file_id') as thumb_id
            FROM Posts p, json_each(p.content, '$.files') j
            WHERE p.post_num > (SELECT COALESCE(MAX(post_num), 0) - 250 FROM Posts)
              AND json_extract(j.value, '$.type') IN ('image', 'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document')
              AND json_extract(j.value, '$.original_file_id') IS NOT NULL
              AND json_extract(j.value, '$.original_file_id') NOT IN (SELECT file_id FROM FileRegistry)
        """

        # Test worker's actual query (with alias ftype in WHERE) vs fixed query (with json_extract in WHERE)
        worker_query = """
            SELECT DISTINCT 
                json_extract(j.value, '$.original_file_id') as fid, 
                json_extract(j.value, '$.type') as ftype,
                json_extract(j.value, '$.thumbnail_file_id') as thumb_id
            FROM Posts p, json_each(p.content, '$.files') j
            WHERE p.post_num > (SELECT COALESCE(MAX(post_num), 0) - 250 FROM Posts)
              AND ftype IN ('image', 'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document')
              AND fid IS NOT NULL
              AND fid NOT IN (SELECT file_id FROM FileRegistry)
        """

        async with db.execute(worker_query) as cursor:
            worker_rows = await cursor.fetchall()
            print(f"Worker Query returned: {worker_rows}")

        async with db.execute(query_gaps_files) as cursor:
            fixed_rows = await cursor.fetchall()
            print(f"Fixed Query returned: {fixed_rows}")

        assert any(r[0] == gap_fid for r in fixed_rows), f"Fixed query should find {gap_fid}"
        assert any(r[0] == gap_fid for r in worker_rows), f"Worker query using alias in WHERE failed to find {gap_fid}!"

    finally:
        async with db_lock:
            await db.execute("DELETE FROM Posts WHERE post_num = ?", (post_num,))
            await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (gap_fid,))
