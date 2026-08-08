import pytest
import asyncio
import time
import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from common.database import get_failed_files_batch, is_file_permanently_failed
from site_tgach.main import app, enrich_extra_data, _process_files_list
from site_tgach.tagging_worker import get_tasks, TEMP_FAILED_FILES
from common.db_pool import get_pool, db_lock

try:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache-challenger")
except Exception:
    pass

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def mock_external_deps():
    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country:
        mock_country.return_value = "RU"
        yield mock_country


@pytest.mark.asyncio
async def test_worker_failure_persistence_and_gap_elimination():
    """
    Stress-test: Insert a post with a gap file ID.
    Verify get_tasks returns it.
    Simulate worker fail_cnt >= 3 UPSERT with tags='download_failed'.
    Verify get_tasks NEVER returns it again.
    """
    db = await get_pool()
    ts = int(time.time() * 1000)
    gap_fid = f"stress_gap_fid_{ts}"
    post_num = 999999000 + (ts % 100000)
    dummy_sha = f"failed_{gap_fid}"

    post_content = json.dumps({
        "text": "Stress test gap file post",
        "files": [
            {
                "original_file_id": gap_fid,
                "type": "photo",
                "thumbnail_file_id": None
            }
        ]
    })

    async with db_lock:
        await db.execute(
            "INSERT INTO Posts (post_num, thread_id, board_id, content, created_at) VALUES (?, 1, 'b', ?, ?)",
            (post_num, post_content, time.time())
        )

    try:
        # Step 1: get_tasks MUST include gap_fid
        tasks_before = await get_tasks(db)
        found_before = any(t["fid"] == gap_fid for t in tasks_before)
        assert found_before, f"Expected gap_fid {gap_fid} to be returned by get_tasks before tagging failure"

        # Step 2: Worker UPSERT on fail_cnt >= 3
        async with db_lock:
            async with db.execute(
                "SELECT sha256 FROM FileRegistry WHERE file_id=?", (gap_fid,)
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                await db.execute(
                    "UPDATE FileRegistry SET tags='download_failed' WHERE file_id=?", (gap_fid,)
                )
            else:
                await db.execute(
                    "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, NULL, 'photo', 'download_failed', ?)",
                    (dummy_sha, gap_fid, time.time()),
                )

        # Step 3: Verify get_tasks NEVER returns gap_fid again
        tasks_after = await get_tasks(db)
        found_after = any(t["fid"] == gap_fid for t in tasks_after)
        assert not found_after, f"Failed file {gap_fid} MUST NOT be returned by get_tasks after UPSERT!"

    finally:
        async with db_lock:
            await db.execute("DELETE FROM Posts WHERE post_num = ?", (post_num,))
            await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (gap_fid,))


@pytest.mark.asyncio
async def test_tag_variants_and_thumbnail_failure_batch():
    """
    Stress-test: Insert files with different failed tags ('error_too_large', 'format_unsupported', 'dead', 'error_no_tags')
    and test thumbnail_id failure.
    Verify get_failed_files_batch and is_file_permanently_failed recognize all tag variants.
    """
    db = await get_pool()
    ts = int(time.time() * 1000)
    
    fid_download_failed = f"fid_dl_fail_{ts}"
    fid_error_too_large = f"fid_err_large_{ts}"
    fid_format_unsupported = f"fid_fmt_unsupp_{ts}"
    fid_dead = f"fid_dead_{ts}"
    fid_normal = f"fid_normal_{ts}"

    thumb_fid_failed = f"thumb_fail_{ts}"

    async with db_lock:
        await db.execute(
            "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'photo', 'download_failed', ?)",
            (f"sha_{fid_download_failed}", fid_download_failed, time.time())
        )
        await db.execute(
            "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'video', 'error_too_large', ?)",
            (f"sha_{fid_error_too_large}", fid_error_too_large, time.time())
        )
        await db.execute(
            "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'sticker', 'format_unsupported', ?)",
            (f"sha_{fid_format_unsupported}", fid_format_unsupported, time.time())
        )
        await db.execute(
            "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'photo', 'dead', ?)",
            (f"sha_{fid_dead}", fid_dead, time.time())
        )
        await db.execute(
            "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, 'orig_has_bad_thumb', ?, 'photo', 'download_failed', ?)",
            (f"sha_{thumb_fid_failed}", thumb_fid_failed, time.time())
        )

    try:
        # Check single lookups
        assert await is_file_permanently_failed(fid_download_failed) is True
        assert await is_file_permanently_failed(fid_error_too_large) is True
        assert await is_file_permanently_failed(fid_format_unsupported) is True
        assert await is_file_permanently_failed(fid_dead) is True
        assert await is_file_permanently_failed(thumb_fid_failed) is True
        assert await is_file_permanently_failed(fid_normal) is False

        # Batch lookup
        batch_ids = [
            fid_download_failed,
            fid_error_too_large,
            fid_format_unsupported,
            fid_dead,
            thumb_fid_failed,
            fid_normal
        ]
        failed_set = await get_failed_files_batch(batch_ids)

        assert fid_download_failed in failed_set
        assert fid_error_too_large in failed_set
        assert fid_format_unsupported in failed_set
        assert fid_dead in failed_set
        assert thumb_fid_failed in failed_set
        assert fid_normal not in failed_set

    finally:
        async with db_lock:
            await db.execute(
                "DELETE FROM FileRegistry WHERE file_id IN (?, ?, ?, ?, 'orig_has_bad_thumb')",
                (fid_download_failed, fid_error_too_large, fid_format_unsupported, fid_dead)
            )


@pytest.mark.asyncio
async def test_enrich_extra_data_multi_file_and_nested_replies():
    """
    Stress-test: Post with multiple files + nested replies containing broken files.
    Verify original_url and thumbnail_url are stripped to "" and is_broken / download_failed set.
    """
    failed_1 = "failed_fid_multi_1"
    failed_2 = "failed_fid_multi_2"
    normal_1 = "normal_fid_multi_3"

    posts = [
        {
            "id": 5001,
            "content": {
                "type": "files",
                "files": [
                    {
                        "type": "image",
                        "original_file_id": failed_1,
                        "thumbnail_file_id": failed_1,
                        "original_url": f"/files/{failed_1}/img1.jpg",
                        "thumbnail_url": f"/files/{failed_1}",
                    },
                    {
                        "type": "image",
                        "original_file_id": normal_1,
                        "thumbnail_file_id": normal_1,
                        "original_url": f"/files/{normal_1}/img2.jpg",
                        "thumbnail_url": f"/files/{normal_1}",
                    },
                ],
            },
            "latest_replies": [
                {
                    "id": 5002,
                    "content": {
                        "type": "files",
                        "files": [
                            {
                                "type": "image",
                                "original_file_id": failed_2,
                                "thumbnail_file_id": failed_2,
                                "original_url": f"/files/{failed_2}/reply.jpg",
                                "thumbnail_url": f"/files/{failed_2}",
                            }
                        ]
                    }
                }
            ]
        }
    ]

    with patch("common.database.get_failed_files_batch", new_callable=AsyncMock) as mock_failed_batch, \
         patch("common.database.get_duplicate_counts", new_callable=AsyncMock) as mock_dupes, \
         patch("common.database.get_blurhashes_batch", new_callable=AsyncMock) as mock_blurs, \
         patch("common.database.get_mirrors_batch", new_callable=AsyncMock) as mock_mirrors:

        mock_failed_batch.return_value = {failed_1, failed_2}
        mock_dupes.return_value = {}
        mock_blurs.return_value = {}
        mock_mirrors.return_value = {}

        await enrich_extra_data(posts, is_ru=True)

        main_files = posts[0]["content"]["files"]
        f1 = main_files[0]
        n1 = main_files[1]

        assert f1["is_broken"] is True
        assert f1["download_failed"] is True
        assert f1["original_url"] == ""
        assert f1["thumbnail_url"] == ""

        assert n1.get("is_broken") is not True
        assert n1["original_url"] != ""

        reply_files = posts[0]["latest_replies"][0]["content"]["files"]
        f2 = reply_files[0]
        assert f2["is_broken"] is True
        assert f2["download_failed"] is True
        assert f2["original_url"] == ""
        assert f2["thumbnail_url"] == ""


def test_files_endpoint_various_routes_fast_fail():
    """
    Stress-test: Verify GET and HEAD requests to /files/<failed_id>, /files/<failed_id>/filename.jpg,
    /thumb/<failed_id>, /b/src/<failed_id> all fast-fail with HTTP 404 immediately.
    """
    failed_fid = "permanently_failed_fid_99"

    with patch("common.database.is_file_permanently_failed", new_callable=AsyncMock) as mock_is_failed:
        mock_is_failed.return_value = True

        # 1. Direct GET /files/<id>
        r1 = client.get(f"/files/{failed_fid}")
        assert r1.status_code == 404

        # 2. GET /files/<id>/image.png (with filename path)
        r2 = client.get(f"/files/{failed_fid}/image.png")
        assert r2.status_code == 404

        # 3. HEAD request /files/<id>
        r3 = client.head(f"/files/{failed_fid}")
        assert r3.status_code == 404

        # 4. GET /thumb/<id>
        r4 = client.get(f"/thumb/{failed_fid}")
        assert r4.status_code == 404

        # 5. GET /b/src/<id>
        r5 = client.get(f"/b/src/{failed_fid}")
        assert r5.status_code == 404


@pytest.mark.asyncio
async def test_large_batch_failed_files_performance():
    """
    Stress-test: Pass 500 file IDs to get_failed_files_batch to verify SQLite query handles large parameters cleanly.
    """
    db = await get_pool()
    ts = int(time.time())
    
    test_fids = [f"bulk_fid_{ts}_{i}" for i in range(500)]
    failed_sample = test_fids[0]
    dummy_sha = f"failed_{failed_sample}"

    async with db_lock:
        await db.execute(
            "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'photo', 'download_failed', ?)",
            (dummy_sha, failed_sample, time.time())
        )

    try:
        t0 = time.monotonic()
        result_set = await get_failed_files_batch(test_fids)
        elapsed = time.monotonic() - t0

        assert failed_sample in result_set
        assert len(result_set) == 1
        assert elapsed < 1.0, f"Query took too long: {elapsed:.3f}s"
    finally:
        async with db_lock:
            await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (failed_sample,))
