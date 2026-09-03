import asyncio
import hashlib
import json
import time
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from common.database import db_transaction
from common.db_pool import get_pool
from site_tgach.tagging_worker import (
    get_tasks,
    process_image_cpu,
)


@pytest.mark.asyncio
async def test_secondary_file_id_registration_via_tags_registry(isolated_test_db):
    """Test that processing a secondary file_id with an existing SHA creates a composite record."""
    db = isolated_test_db

    sha_primary = "59d285622f422028b9ea047885346c6d752cca2a3b2b84c778e05d229157a9a3"
    fid_primary = "FID_PRIMARY_001"
    fid_secondary = "FID_SECONDARY_002"
    tags_initial = "megumin, explosion, anime"
    desc_initial = "Megumin casting explosion"
    phash = "1010101010101010"
    b_hash = "L6PZfSi_.AyE_3t7t7R**0o#DgR4"
    file_type = "photo"
    thumb_id = "THUMB_SEC_002"

    # 1. Insert primary row into FileRegistry
    async with db_transaction(db):
        await db.execute(
            """
            INSERT INTO FileRegistry 
            (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash, tags, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sha_primary, phash, fid_primary, None, file_type, time.time(), b_hash, tags_initial, desc_initial),
        )

    # 2. Simulate _save_tags_registry logic for fid_secondary sharing sha_primary
    updated_tags = "megumin, explosion, anime, updated"
    updated_desc = "Megumin casting explosion updated"
    
    async with db_transaction(db):
        async with db.execute(
            """
            UPDATE FileRegistry 
            SET tags = ?, description = COALESCE(?, description), phash = ?, blurhash = ?
            WHERE file_id = ?
            """,
            (updated_tags, updated_desc, phash, b_hash, fid_secondary),
        ) as cursor:
            updated_rows = cursor.rowcount

        if updated_rows == 0:
            async with db.execute(
                "SELECT file_id FROM FileRegistry WHERE sha256 = ?",
                (sha_primary,),
            ) as cursor:
                existing_sha_row = await cursor.fetchone()

            if existing_sha_row:
                await db.execute(
                    """
                    UPDATE FileRegistry 
                    SET tags = ?, description = COALESCE(?, description), phash = ?, blurhash = ?
                    WHERE sha256 = ?
                    """,
                    (updated_tags, updated_desc, phash, b_hash, sha_primary),
                )
                sec_sha = f"{sha_primary}_{fid_secondary}"
                await db.execute(
                    """
                    INSERT OR REPLACE INTO FileRegistry 
                    (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash, tags, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sec_sha,
                        phash,
                        fid_secondary,
                        thumb_id,
                        file_type,
                        time.time(),
                        b_hash,
                        updated_tags,
                        updated_desc,
                    ),
                )

    # 3. Assertions: Both primary and secondary file_ids are now present in FileRegistry
    async with db.execute("SELECT file_id, sha256, tags, description FROM FileRegistry WHERE file_id = ?", (fid_primary,)) as cursor:
        row_prim = await cursor.fetchone()
    assert row_prim is not None
    assert row_prim[0] == fid_primary
    assert row_prim[1] == sha_primary
    assert row_prim[2] == updated_tags

    async with db.execute("SELECT file_id, sha256, tags, description, thumbnail_id FROM FileRegistry WHERE file_id = ?", (fid_secondary,)) as cursor:
        row_sec = await cursor.fetchone()
    assert row_sec is not None
    assert row_sec[0] == fid_secondary
    assert row_sec[1] == f"{sha_primary}_{fid_secondary}"
    assert row_sec[2] == updated_tags
    assert row_sec[4] == thumb_id


@pytest.mark.asyncio
async def test_get_tasks_gap_filtering_for_secondary_file_id(isolated_test_db):
    """Test that get_tasks properly extracts missing fids and excludes already-registered secondary fids."""
    db = isolated_test_db

    sha_banner = "9befce4af38d63fc8f8dced4619f79f910ce23fd3a5d414ed13979bd78f941a6"
    fid_primary = "FID_BANNER_PRIMARY"
    fid_secondary_1 = "FID_BANNER_SEC_1"
    fid_secondary_2 = "FID_BANNER_SEC_2"
    fid_album_item = "FID_ALBUM_ITEM_3"

    # Insert primary in FileRegistry
    async with db_transaction(db):
        await db.execute(
            """
            INSERT INTO FileRegistry (sha256, file_id, file_type, tags, created_at)
            VALUES (?, ?, 'photo', 'banner, newspaper', ?)
            """,
            (sha_banner, fid_primary, time.time()),
        )

        # Insert Posts referencing fid_secondary_1 (in files), fid_secondary_2 (single content), fid_album_item (in media)
        await db.execute(
            """
            INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp)
            VALUES (1001, 'b', '1000', 123, ?, ?)
            """,
            (
                json.dumps({
                    "files": [
                        {"original_file_id": fid_secondary_1, "type": "photo", "file_name": "banner1.jpg"}
                    ]
                }),
                time.time(),
            ),
        )
        await db.execute(
            """
            INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp)
            VALUES (1002, 'b', '1000', 123, ?, ?)
            """,
            (
                json.dumps({
                    "file_id": fid_secondary_2,
                    "type": "photo",
                    "file_name": "banner2.jpg"
                }),
                time.time(),
            ),
        )
        await db.execute(
            """
            INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp)
            VALUES (1003, 'b', '1000', 123, ?, ?)
            """,
            (
                json.dumps({
                    "media": [
                        {"media": fid_album_item, "type": "photo"}
                    ]
                }),
                time.time(),
            ),
        )

    # 1. Before recording secondary IDs, get_tasks should return them as gap tasks
    tasks = await get_tasks(db, limit=10)
    task_fids = [t["fid"] for t in tasks]
    assert fid_secondary_1 in task_fids
    assert fid_secondary_2 in task_fids
    assert fid_album_item in task_fids
    assert fid_primary not in task_fids  # primary already in FileRegistry

    # 2. Record secondary IDs in FileRegistry with composite keys
    async with db_transaction(db):
        for fid in (fid_secondary_1, fid_secondary_2, fid_album_item):
            sec_sha = f"{sha_banner}_{fid}"
            await db.execute(
                """
                INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at)
                VALUES (?, ?, 'photo', 'banner, newspaper', ?)
                """,
                (sec_sha, fid, time.time()),
            )

    # 3. After recording, get_tasks gap query must NOT return any of the secondary IDs
    tasks_after = await get_tasks(db)
    task_fids_after = [t["fid"] for t in tasks_after]
    assert fid_secondary_1 not in task_fids_after
    assert fid_secondary_2 not in task_fids_after
    assert fid_album_item not in task_fids_after
    assert len(tasks_after) == 0


@pytest.mark.asyncio
async def test_no_infinite_redownload_or_skip_spam(isolated_test_db):
    """Test that end-to-end task retrieval and saving prevents infinite re-download loops for duplicate SHA media."""
    db = isolated_test_db

    sha_const = "ce09c38680bc7ccde75f63f43cd1306c3e8649f52d2e75c14a0c963b1e9336d7"
    fid_1 = "FID_POST_508024_A"
    fid_2 = "FID_POST_508024_B"

    # Create post 508024 with fid_1
    async with db_transaction(db):
        await db.execute(
            """
            INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp)
            VALUES (508024, 'b', '508000', 999, ?, ?)
            """,
            (
                json.dumps({
                    "files": [{"original_file_id": fid_1, "type": "photo"}]
                }),
                time.time(),
            ),
        )

    # Fetch initial tasks
    tasks = await get_tasks(db)
    assert len(tasks) == 1
    assert tasks[0]["fid"] == fid_1

    # Simulate worker processing fid_1
    async with db_transaction(db):
        await db.execute(
            """
            INSERT INTO FileRegistry (sha256, phash, file_id, file_type, tags, description, created_at)
            VALUES (?, 'phash1', ?, 'photo', 'gigachad, banner', 'Abu Gigachad', ?)
            """,
            (sha_const, fid_1, time.time()),
        )

    # Create post 508025 with fid_2 (same underlying image)
    async with db_transaction(db):
        await db.execute(
            """
            INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp)
            VALUES (508025, 'b', '508000', 999, ?, ?)
            """,
            (
                json.dumps({
                    "files": [{"original_file_id": fid_2, "type": "photo"}]
                }),
                time.time(),
            ),
        )

    # get_tasks returns fid_2
    tasks = await get_tasks(db)
    assert len(tasks) == 1
    assert tasks[0]["fid"] == fid_2

    # Worker detects existing tags for SHA ce09c386... and executes _save_tags_registry logic
    tags = "gigachad, banner"
    description = "Abu Gigachad"
    phash = "phash1"
    b_hash = "bhash1"

    async with db_transaction(db):
        async with db.execute(
            """
            UPDATE FileRegistry 
            SET tags = ?, description = COALESCE(?, description), phash = ?, blurhash = ?
            WHERE file_id = ?
            """,
            (tags, description, phash, b_hash, fid_2),
        ) as cursor:
            updated_rows = cursor.rowcount

        if updated_rows == 0:
            async with db.execute(
                "SELECT file_id FROM FileRegistry WHERE sha256 = ?",
                (sha_const,),
            ) as cursor:
                existing_sha_row = await cursor.fetchone()

            if existing_sha_row:
                sec_sha = f"{sha_const}_{fid_2}"
                await db.execute(
                    """
                    INSERT OR REPLACE INTO FileRegistry 
                    (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash, tags, description)
                    VALUES (?, ?, ?, ?, 'photo', ?, ?, ?, ?)
                    """,
                    (sec_sha, phash, fid_2, None, time.time(), b_hash, tags, description),
                )

    # Assert get_tasks on subsequent cycle returns 0 tasks (no infinite loop)
    tasks_next_cycle = await get_tasks(db)
    assert len(tasks_next_cycle) == 0


@pytest.mark.asyncio
async def test_secondary_file_id_bad_file_handling(isolated_test_db):
    """Test that corrupted files with duplicate hashes record secondary file_ids and avoid re-fetch loops."""
    db = isolated_test_db

    sha_corrupt = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    fid_bad_1 = "FID_BAD_001"
    fid_bad_2 = "FID_BAD_002"

    async with db_transaction(db):
        # Insert post with fid_bad_1 and post with fid_bad_2
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (2001, 'b', '2000', 1, ?, ?)",
            (json.dumps({"file_id": fid_bad_1, "type": "photo"}), time.time()),
        )
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (2002, 'b', '2000', 1, ?, ?)",
            (json.dumps({"file_id": fid_bad_2, "type": "photo"}), time.time()),
        )

        # Primary bad file save
        await db.execute(
            "INSERT INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'photo', 'error', ?)",
            (sha_corrupt, fid_bad_1, time.time()),
        )

    # Save secondary bad file
    async with db_transaction(db):
        async with db.execute("UPDATE FileRegistry SET tags='error' WHERE file_id=?", (fid_bad_2,)) as cursor:
            updated_rows = cursor.rowcount
        if updated_rows == 0:
            async with db.execute("SELECT file_id FROM FileRegistry WHERE sha256 = ?", (sha_corrupt,)) as cursor:
                existing_sha_row = await cursor.fetchone()
            if existing_sha_row:
                sec_sha = f"{sha_corrupt}_{fid_bad_2}"
                await db.execute(
                    "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, NULL, 'photo', 'error', ?)",
                    (sec_sha, fid_bad_2, time.time()),
                )

    # Verify both exist with error tag
    async with db.execute("SELECT file_id, tags FROM FileRegistry WHERE file_id IN (?, ?)", (fid_bad_1, fid_bad_2)) as cursor:
        rows = await cursor.fetchall()
    assert len(rows) == 2
    assert all(r[1] == "error" for r in rows)

    # Verify gap query returns 0 tasks
    tasks = await get_tasks(db)
    assert len(tasks) == 0


@pytest.mark.asyncio
async def test_secondary_file_id_audio_doc_handling(isolated_test_db):
    """Test that duplicate audio documents preserve both file_ids in FileRegistry."""
    db = isolated_test_db

    sha_audio = "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0"
    fid_aud_1 = "FID_AUDIO_001"
    fid_aud_2 = "FID_AUDIO_002"

    async with db_transaction(db):
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (3001, 'b', '3000', 1, ?, ?)",
            (json.dumps({"file_id": fid_aud_1, "type": "audio"}), time.time()),
        )
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (3002, 'b', '3000', 1, ?, ?)",
            (json.dumps({"file_id": fid_aud_2, "type": "audio"}), time.time()),
        )

        # Primary audio save
        await db.execute(
            "INSERT INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, ?, 'audio', 'audio', ?)",
            (sha_audio, fid_aud_1, time.time()),
        )

    # Secondary audio save
    async with db_transaction(db):
        async with db.execute("UPDATE FileRegistry SET tags='audio', file_type='audio' WHERE file_id=?", (fid_aud_2,)) as cursor:
            updated_rows = cursor.rowcount
        if updated_rows == 0:
            async with db.execute("SELECT file_id FROM FileRegistry WHERE sha256 = ?", (sha_audio,)) as cursor:
                existing_sha_row = await cursor.fetchone()
            if existing_sha_row:
                sec_sha = f"{sha_audio}_{fid_aud_2}"
                await db.execute(
                    "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, NULL, 'audio', 'audio', ?)",
                    (sec_sha, fid_aud_2, time.time()),
                )

    # Verify both primary and secondary audio files are stored
    async with db.execute("SELECT file_id, sha256, tags FROM FileRegistry WHERE file_id IN (?, ?)", (fid_aud_1, fid_aud_2)) as cursor:
        rows = await cursor.fetchall()
    assert len(rows) == 2
    fids = {r[0] for r in rows}
    assert fid_aud_1 in fids
    assert fid_aud_2 in fids

    # Verify gap query returns 0 tasks
    tasks = await get_tasks(db)
    assert len(tasks) == 0


@pytest.mark.asyncio
async def test_gap_queries_robustness_on_malformed_and_empty_posts(isolated_test_db):
    """Test that get_tasks handles non-media content, empty content, and various media types gracefully."""
    db = isolated_test_db

    async with db_transaction(db):
        # Post with text only (no media fields)
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (4001, 'b', '4000', 1, ?, ?)",
            (json.dumps({"text": "just plain text post"}), time.time()),
        )
        # Post with empty JSON object
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (4002, 'b', '4000', 1, '{}', ?)",
            (time.time(),),
        )
        # Post with arbitrary non-media JSON
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (4003, 'b', '4000', 1, ?, ?)",
            (json.dumps({"custom_field": 12345}), time.time()),
        )
        # Post with valid document
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (4004, 'b', '4000', 1, ?, ?)",
            (json.dumps({"file_id": "FID_DOC_VALID", "type": "document", "file_name": "test.pdf", "mime_type": "application/pdf"}), time.time()),
        )

    tasks = await get_tasks(db)
    assert len(tasks) == 1
    assert tasks[0]["fid"] == "FID_DOC_VALID"
    assert tasks[0]["fname"] == "test.pdf"
    assert tasks[0]["fmime"] == "application/pdf"
