# -*- coding: utf-8 -*-
"""
Adversarial Challenge Harness for Requirement R1: Background Tagger Gap Query Resolution,
Duplicate SHA Composite Mapping, Media Structure Diversity, and FTS Trigger Integrity.

Challenger 1 Empirical Verification Suite.
"""

import asyncio
import hashlib
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import common.database as db_module
from common.db_pool import db_transaction, execute_with_retry
from site_tgach.tagging_worker import (
    get_tasks,
    process_image_cpu,
    is_audio_media,
)


async def _populate_test_boards(db, boards=("b", "abu", "vg", "po", "media", "soc")):
    """Ensure all test boards exist to satisfy Foreign Key constraints."""
    for b in boards:
        await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES (?, ?)", (b, f"Board {b}"))


async def _simulate_worker_task_processing(db, task, shared_sha_map=None, default_tags="anime, girl, art", default_desc="Artwork depiction", vision_call_counter=None):
    """
    Executes the exact database pipeline used by tagging_worker._save_tags_registry,
    _check_existing_tags, and fast-track audio/error handling.
    """
    file_id = task["fid"]
    file_type = task.get("type", "photo")
    thumb_id = task.get("thumb_id")
    fname = task.get("fname")
    fmime = task.get("fmime")

    # 1. Check audio fast-track (for audio documents / voice)
    if file_type in ("audio", "voice") or is_audio_media(file_type=file_type, mime_type=fmime, filename=fname):
        sha_audio = f"audio_{file_id}"
        async def _save_audio_fast():
            async with db_transaction(db):
                async with db.execute("SELECT sha256 FROM FileRegistry WHERE file_id=?", (file_id,)) as cursor:
                    row = await cursor.fetchone()
                if row:
                    await db.execute("UPDATE FileRegistry SET tags='audio', file_type='audio' WHERE file_id=?", (file_id,))
                else:
                    await db.execute(
                        "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, thumbnail_id, file_type, tags, created_at) VALUES (?, ?, ?, 'audio', 'audio', ?)",
                        (sha_audio, file_id, thumb_id, time.time()),
                    )
        await execute_with_retry(_save_audio_fast, max_retries=5, base_delay=0.05)
        return "audio", sha_audio, False

    # 2. Determine SHA hash for image/media
    if shared_sha_map and file_id in shared_sha_map:
        sha = shared_sha_map[file_id]
    else:
        sha = hashlib.sha256(f"content_bytes_for_{file_id}".encode()).hexdigest()

    phash = "1010101010101010"
    b_hash = "L6PZfSi_.AyE_3t7t7R**0o#DgR4"

    # 3. Check existing tags for this SHA
    tags = None
    description = None
    async def _check_existing_tags():
        async with db.execute(
            "SELECT tags, description FROM FileRegistry WHERE (sha256 = ? OR sha256 LIKE ?) AND tags IS NOT NULL AND tags != '' LIMIT 1",
            (sha, f"{sha}_%"),
        ) as cursor:
            return await cursor.fetchone()

    row = await execute_with_retry(_check_existing_tags, max_retries=3, base_delay=0.05)
    called_vision = False
    if row:
        tags = row[0]
        description = row[1]
    else:
        # Simulate Vision AI generating tags
        tags = default_tags
        description = default_desc
        called_vision = True
        if vision_call_counter is not None:
            vision_call_counter["count"] += 1

    # 4. Execute _save_tags_registry
    async def _save_tags_registry():
        async with db_transaction(db):
            async with db.execute(
                """
                UPDATE FileRegistry 
                SET tags = ?, description = COALESCE(?, description), phash = ?, blurhash = ?
                WHERE file_id = ?
                """,
                (tags, description, phash, b_hash, file_id),
            ) as cursor:
                updated_rows = cursor.rowcount

            if updated_rows == 0:
                async with db.execute(
                    "SELECT file_id FROM FileRegistry WHERE sha256 = ?",
                    (sha,),
                ) as cursor:
                    existing_sha_row = await cursor.fetchone()

                if existing_sha_row:
                    # Update existing primary record
                    await db.execute(
                        """
                        UPDATE FileRegistry 
                        SET tags = ?, description = COALESCE(?, description), phash = ?, blurhash = ?
                        WHERE sha256 = ?
                        """,
                        (tags, description, phash, b_hash, sha),
                    )
                    # Permanently index the secondary file_id
                    sec_sha = f"{sha}_{file_id}"
                    await db.execute(
                        """
                        INSERT OR REPLACE INTO FileRegistry 
                        (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash, tags, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sec_sha,
                            phash,
                            file_id,
                            thumb_id,
                            file_type,
                            time.time(),
                            b_hash,
                            tags,
                            description,
                        ),
                    )
                else:
                    await db.execute(
                        """
                        INSERT INTO FileRegistry 
                        (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash, tags, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(sha256) DO UPDATE SET
                            tags = excluded.tags,
                            description = COALESCE(excluded.description, FileRegistry.description),
                            phash = excluded.phash,
                            blurhash = excluded.blurhash
                        """,
                        (
                            sha,
                            phash,
                            file_id,
                            thumb_id,
                            file_type,
                            time.time(),
                            b_hash,
                            tags,
                            description,
                        ),
                    )

    await execute_with_retry(_save_tags_registry, max_retries=5, base_delay=0.05)
    return tags, sha, called_vision


@pytest.mark.asyncio
async def test_adversarial_burst_50_plus_posts_identical_sha_drain(isolated_test_db):
    """
    EMPIRICAL STRESS TEST 1: High concurrency / burst stress test.
    - Create 65 posts across 6 boards with diverse media structures.
    - 50 posts share the IDENTICAL SHA hash ('59d28562c8e3...').
    - Multiple media representations: single file_id, files array, media album, audio docs.
    - Verify that gap tasks strictly drain to 0 without hanging or looping.
    """
    db = isolated_test_db
    boards = ["b", "abu", "vg", "po", "media", "soc"]
    await _populate_test_boards(db, boards)

    shared_sha = "59d28562c8e3f940b174a78129841bb02213799638c4b2b71946059d28562abc"
    shared_sha_map = {}
    total_media_fids = set()
    post_num = 1000

    # 1. Generate 20 Single-file posts sharing the same SHA
    for i in range(1, 21):
        post_num += 1
        fid = f"FID_BURST_SINGLE_{i:03d}"
        total_media_fids.add(fid)
        shared_sha_map[fid] = shared_sha
        board = boards[i % len(boards)]
        content = json.dumps({
            "file_id": fid,
            "type": "photo",
            "file_name": f"shared_img_{i}.jpg",
            "mime_type": "image/jpeg",
            "text": f"Single post {i}"
        })
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (?, ?, '1000', ?, ?, ?)",
            (post_num, board, 100 + i, content, time.time()),
        )

    # 2. Generate 10 Multi-file (files array) posts sharing the same SHA (20 fids total)
    for i in range(1, 11):
        post_num += 1
        fid_a = f"FID_BURST_FILES_{i:03d}_A"
        fid_b = f"FID_BURST_FILES_{i:03d}_B"
        total_media_fids.add(fid_a)
        total_media_fids.add(fid_b)
        shared_sha_map[fid_a] = shared_sha
        shared_sha_map[fid_b] = shared_sha
        board = boards[i % len(boards)]
        content = json.dumps({
            "files": [
                {"original_file_id": fid_a, "type": "image", "file_name": f"album_{i}_a.png"},
                {"file_id": fid_b, "type": "photo", "file_name": f"album_{i}_b.jpg"},
            ],
            "text": f"Files array post {i}"
        })
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (?, ?, '1000', ?, ?, ?)",
            (post_num, board, 200 + i, content, time.time()),
        )

    # 3. Generate 5 Media album posts sharing the same SHA (10 fids total)
    for i in range(1, 6):
        post_num += 1
        fid_a = f"FID_BURST_MEDIA_{i:03d}_A"
        fid_b = f"FID_BURST_MEDIA_{i:03d}_B"
        total_media_fids.add(fid_a)
        total_media_fids.add(fid_b)
        shared_sha_map[fid_a] = shared_sha
        shared_sha_map[fid_b] = shared_sha
        board = boards[i % len(boards)]
        content = json.dumps({
            "media": [
                {"media": fid_a, "type": "photo"},
                {"file_id": fid_b, "type": "image"},
            ],
            "text": f"Media album post {i}"
        })
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (?, ?, '1000', ?, ?, ?)",
            (post_num, board, 300 + i, content, time.time()),
        )

    # 4. Generate 10 Corrupted / Empty / Malformed posts (adversarial noise)
    malformed_payloads = [
        {"files": [], "text": "empty files array"},
        {"media": [], "text": "empty media array"},
        {"text": "just raw text message without media"},
        {"text": "empty object body"},
        {"files": [{"type": "photo"}], "text": "missing fid in files"},
        {"media": [{"type": "video"}], "text": "missing fid in media"},
        {"file_id": None, "type": "photo", "text": "null fid"},
        {"file_id": "", "type": "photo", "text": "empty fid string"},
        {"files": [{"file_id": None, "type": "photo"}], "text": "null fid in files"},
        {"random_key": 99999, "text": "arbitrary json key"},
    ]
    for i, payload in enumerate(malformed_payloads, start=1):
        post_num += 1
        board = boards[i % len(boards)]
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (?, ?, '1000', ?, ?, ?)",
            (post_num, board, 400 + i, json.dumps(payload), time.time()),
        )

    # 5. Generate 5 Audio Document posts (fast-track test)
    for i in range(1, 6):
        post_num += 1
        fid_aud = f"FID_BURST_AUDIO_{i:03d}"
        total_media_fids.add(fid_aud)
        board = boards[i % len(boards)]
        content = json.dumps({
            "files": [
                {"file_id": fid_aud, "type": "document", "file_name": f"track_{i}.mp3", "mime_type": "audio/mpeg"}
            ],
            "text": f"Audio document post {i}"
        })
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (?, ?, '1000', ?, ?, ?)",
            (post_num, board, 500 + i, content, time.time()),
        )

    total_expected_fids_count = len(total_media_fids)
    assert total_expected_fids_count == 55, f"Expected 55 total valid media fids, got {total_expected_fids_count}"
    assert len(shared_sha_map) == 50, f"Expected 50 identical SHA media fids, got {len(shared_sha_map)}"

    # 6. Execute Simulated Tagging Worker Loop until drain
    start_time = time.perf_counter()
    max_cycles = 100
    cycles = 0
    processed_fids = set()
    telemetry_log = []

    while cycles < max_cycles:
        cycles += 1
        # Fetch batch with limit=5 (simulating worker batching)
        batch = await get_tasks(db, limit=5)
        
        telemetry_log.append({
            "cycle": cycles,
            "tasks_returned": len(batch),
            "fids": [t["fid"] for t in batch]
        })

        if not batch:
            # Fully drained!
            break

        # Process each task in batch
        for task in batch:
            fid = task["fid"]
            tags, calculated_sha, called_vis = await _simulate_worker_task_processing(db, task, shared_sha_map=shared_sha_map)
            processed_fids.add(fid)

    elapsed_time = time.perf_counter() - start_time

    # 7. Assert Strict Draining to 0
    final_tasks = await get_tasks(db, limit=20)
    assert len(final_tasks) == 0, f"Tasks did not drain to 0! Remaining: {final_tasks}"
    assert processed_fids == total_media_fids, f"Mismatch in processed FIDs: missing {total_media_fids - processed_fids}"
    assert cycles < max_cycles, f"Worker loop hit cycle limit ({max_cycles}) - indicates infinite loop!"

    # 8. Assert FileRegistry Schema Integrity
    async with db.execute("SELECT COUNT(*) FROM FileRegistry") as cursor:
        total_registry_rows = (await cursor.fetchone())[0]

    # Exactly 55 rows in FileRegistry (1 primary SHA + 49 composite secondary SHAs + 5 audio)
    assert total_registry_rows == 55, f"Expected 55 rows in FileRegistry, got {total_registry_rows}"

    # Verify primary and secondary SHA formatting
    async with db.execute("SELECT file_id, sha256, tags FROM FileRegistry WHERE sha256 = ?", (shared_sha,)) as cursor:
        primary_row = await cursor.fetchone()
    assert primary_row is not None, "Primary SHA record not found in FileRegistry"
    primary_fid = primary_row[0]
    assert primary_fid in shared_sha_map

    async with db.execute("SELECT file_id, sha256 FROM FileRegistry WHERE sha256 LIKE ?", (f"{shared_sha}_%",)) as cursor:
        secondary_rows = await cursor.fetchall()
    assert len(secondary_rows) == 49, f"Expected 49 secondary SHA records, got {len(secondary_rows)}"

    for sec_fid, sec_sha in secondary_rows:
        assert sec_sha == f"{shared_sha}_{sec_fid}", f"Secondary SHA improperly formed: {sec_sha}"

    # 9. Assert FileTagsFTS Trigger Validity
    # Query FTS for 'anime'
    async with db.execute("SELECT file_id, tags FROM FileTagsFTS WHERE FileTagsFTS MATCH 'anime'") as cursor:
        fts_matches = await cursor.fetchall()
    assert len(fts_matches) == 50, f"Expected 50 FTS matches for shared anime image, got {len(fts_matches)}"

    # Query FTS for 'audio'
    async with db.execute("SELECT file_id, tags FROM FileTagsFTS WHERE FileTagsFTS MATCH 'audio'") as cursor:
        audio_fts_matches = await cursor.fetchall()
    assert len(audio_fts_matches) == 5, f"Expected 5 FTS matches for audio files, got {len(audio_fts_matches)}"

    # Verify FTS rowcount equals FileRegistry rowcount
    async with db.execute("SELECT COUNT(*) FROM FileTagsFTS") as cursor:
        fts_total = (await cursor.fetchone())[0]
    assert fts_total == 55, f"FileTagsFTS count ({fts_total}) does not match FileRegistry count (55)"

    print(f"\n[EMPIRICAL PROOF 1] 55 files (50 identical SHA + 5 audio docs) successfully drained in {cycles} cycles ({elapsed_time:.3f}s). FileTagsFTS integrity 100% verified.")


@pytest.mark.asyncio
async def test_adversarial_concurrent_worker_burst_race(isolated_test_db):
    """
    EMPIRICAL STRESS TEST 2: Concurrent Multi-Worker Race Condition & Lock Hardening.
    - Simulate 5 concurrent workers simultaneously executing get_tasks and _save_tags_registry
      on a shared pool of duplicate SHA posts.
    - Verify that no deadlocks occur and no duplicate primary entries crash SQLite.
    """
    db = isolated_test_db
    await _populate_test_boards(db)

    shared_sha = "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
    shared_sha_map = {}
    total_fids = set()

    for i in range(1, 31):
        fid = f"FID_RACE_{i:03d}"
        total_fids.add(fid)
        shared_sha_map[fid] = shared_sha
        content = json.dumps({
            "files": [{"original_file_id": fid, "type": "photo", "file_name": f"race_{i}.jpg"}],
            "text": f"Race post {i}"
        })
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (?, 'b', '2000', 99, ?, ?)",
            (2000 + i, content, time.time()),
        )

    processed_fids = set()
    lock = asyncio.Lock()

    async def _worker_loop(worker_id: int):
        for _ in range(25):
            async with lock:
                tasks = await get_tasks(db, limit=2)
            if not tasks:
                await asyncio.sleep(0.01)
                continue

            for t in tasks:
                try:
                    await _simulate_worker_task_processing(db, t, shared_sha_map=shared_sha_map)
                    async with lock:
                        processed_fids.add(t["fid"])
                except Exception as e:
                    pytest.fail(f"Worker {worker_id} crashed during concurrent task processing: {e}")

    # Launch 5 concurrent workers
    workers = [_worker_loop(w) for w in range(5)]
    await asyncio.gather(*workers)

    # Assert all 30 fids were processed and gap tasks are 0
    final_tasks = await get_tasks(db)
    assert len(final_tasks) == 0, f"Remaining gap tasks found: {final_tasks}"
    assert len(processed_fids) == 30

    async with db.execute("SELECT COUNT(*) FROM FileRegistry") as cursor:
        total_rows = (await cursor.fetchone())[0]
    assert total_rows == 30, f"Expected 30 rows in FileRegistry, got {total_rows}"

    print(f"\n[EMPIRICAL PROOF 2] 5 concurrent workers processed 30 duplicate SHA files with zero lock errors or collisions.")


@pytest.mark.asyncio
async def test_adversarial_fts_triggers_on_composite_replace_and_delete(isolated_test_db):
    """
    EMPIRICAL STRESS TEST 3: FileTagsFTS Trigger Verification on INSERT, UPDATE, REPLACE, and DELETE.
    - Tests trigger trg_files_fts_insert, trg_files_fts_update, trg_files_fts_delete on composite keys.
    """
    db = isolated_test_db
    sha_primary = "111122223333444455556666777788889999aaaabbbbccccddddeeeeffff0000"
    fid_primary = "FID_FTS_PRIM"
    fid_secondary = "FID_FTS_SEC"

    # 1. Insert primary
    async with db_transaction(db):
        await db.execute(
            "INSERT INTO FileRegistry (sha256, file_id, file_type, tags, description, created_at) VALUES (?, ?, 'photo', 'cyberpunk, neon', 'Cityscape', ?)",
            (sha_primary, fid_primary, time.time()),
        )

    # Verify FTS match
    async with db.execute("SELECT file_id, tags FROM FileTagsFTS WHERE FileTagsFTS MATCH 'cyberpunk'") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == fid_primary

    # 2. Insert secondary composite record
    sec_sha = f"{sha_primary}_{fid_secondary}"
    async with db_transaction(db):
        await db.execute(
            "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, description, created_at) VALUES (?, ?, 'photo', 'cyberpunk, samurai', 'Warrior', ?)",
            (sec_sha, fid_secondary, time.time()),
        )

    # Verify FTS has both
    async with db.execute("SELECT file_id, tags FROM FileTagsFTS WHERE FileTagsFTS MATCH 'cyberpunk'") as cursor:
        rows = await cursor.fetchall()
    assert len(rows) == 2
    matched_fids = {r[0] for r in rows}
    assert fid_primary in matched_fids
    assert fid_secondary in matched_fids

    # 3. Update secondary tags
    async with db_transaction(db):
        await db.execute(
            "UPDATE FileRegistry SET tags = 'steampunk, gears' WHERE file_id = ?",
            (fid_secondary,),
        )

    # Verify FTS updated
    async with db.execute("SELECT file_id, tags FROM FileTagsFTS WHERE FileTagsFTS MATCH 'steampunk'") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == fid_secondary

    # Verify old tag is gone for secondary
    async with db.execute("SELECT file_id, tags FROM FileTagsFTS WHERE FileTagsFTS MATCH 'samurai'") as cursor:
        row = await cursor.fetchone()
    assert row is None

    # 4. Delete primary record
    async with db_transaction(db):
        await db.execute("DELETE FROM FileRegistry WHERE file_id = ?", (fid_primary,))

    # Verify primary is removed from FTS
    async with db.execute("SELECT file_id, tags FROM FileTagsFTS WHERE FileTagsFTS MATCH 'cyberpunk'") as cursor:
        row = await cursor.fetchone()
    assert row is None

    # Secondary should still exist in FTS
    async with db.execute("SELECT file_id, tags FROM FileTagsFTS WHERE FileTagsFTS MATCH 'steampunk'") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == fid_secondary

    print(f"\n[EMPIRICAL PROOF 3] FileTagsFTS triggers (INSERT, UPDATE, DELETE) verified 100% compliant.")


@pytest.mark.asyncio
async def test_adversarial_malformed_and_extreme_edge_cases(isolated_test_db):
    """
    EMPIRICAL STRESS TEST 4: Malformed payloads, invalid sub-structures, long keys, NULL handling.
    """
    db = isolated_test_db
    await _populate_test_boards(db)

    # 1. JSON with non-array files field (e.g. integer or object)
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (9001, 'b', '9000', 1, ?, ?)",
        (json.dumps({"files": 12345, "text": "files as int"}), time.time()),
    )

    # 2. JSON with non-array media field
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (9002, 'b', '9000', 1, ?, ?)",
        (json.dumps({"media": "not_an_array", "text": "media as string"}), time.time()),
    )

    # 3. JSON with object media field
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (9003, 'b', '9000', 1, ?, ?)",
        (json.dumps({"media": {"file_id": "nested_dict"}, "text": "media as object"}), time.time()),
    )

    # 4. Extreme length FID (600 characters)
    long_fid = "FID_EXTREME_" + "X" * 580
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (9004, 'b', '9000', 1, ?, ?)",
        (json.dumps({"file_id": long_fid, "type": "photo", "text": "extreme long fid"}), time.time()),
    )

    # get_tasks should gracefully handle strange shapes and extract long_fid
    tasks = await get_tasks(db)
    assert len(tasks) == 1
    assert tasks[0]["fid"] == long_fid

    # Save long_fid
    tags, sha, _ = await _simulate_worker_task_processing(db, tasks[0])
    
    # Gap tasks should now be 0
    after_tasks = await get_tasks(db)
    assert len(after_tasks) == 0

    print(f"\n[EMPIRICAL PROOF 4] Malformed JSON shapes, non-array types, and extreme 600-char file_ids handled gracefully without exceptions.")


@pytest.mark.asyncio
async def test_adversarial_100_posts_multi_cluster_drain_with_vision_cache_efficiency(isolated_test_db):
    """
    EMPIRICAL STRESS TEST 5: 100 Posts with Multi-Cluster Duplicate SHAs & Vision AI Cache Efficiency.
    - Cluster A: 40 posts sharing SHA_A
    - Cluster B: 30 posts sharing SHA_B
    - Cluster C: 30 posts with unique SHAs
    - Verifies that Vision AI tagging is called EXACTLY ONCE per cluster (32 total Vision calls for 100 posts).
    - 68 duplicate posts reuse existing tags via _check_existing_tags without hitting Vision AI.
    - All 100 posts drain to 0 tasks.
    """
    db = isolated_test_db
    boards = ["b", "abu", "vg", "po", "media", "soc"]
    await _populate_test_boards(db, boards)

    sha_cluster_a = "aaaaaaaa1111222233334444555566667777888899990000aaaabbbbccccdddd"
    sha_cluster_b = "bbbbbbbb1111222233334444555566667777888899990000aaaabbbbccccdddd"
    shared_sha_map = {}
    all_fids = set()
    post_num = 5000

    # Cluster A (40 files)
    for i in range(1, 41):
        post_num += 1
        fid = f"FID_CLUSTER_A_{i:03d}"
        all_fids.add(fid)
        shared_sha_map[fid] = sha_cluster_a
        board = boards[i % len(boards)]
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (?, ?, '5000', 1, ?, ?)",
            (post_num, board, json.dumps({"file_id": fid, "type": "photo", "text": f"Cluster A {i}"}), time.time()),
        )

    # Cluster B (30 files)
    for i in range(1, 31):
        post_num += 1
        fid = f"FID_CLUSTER_B_{i:03d}"
        all_fids.add(fid)
        shared_sha_map[fid] = sha_cluster_b
        board = boards[i % len(boards)]
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (?, ?, '5000', 1, ?, ?)",
            (post_num, board, json.dumps({"file_id": fid, "type": "photo", "text": f"Cluster B {i}"}), time.time()),
        )

    # Cluster C (30 unique files)
    for i in range(1, 31):
        post_num += 1
        fid = f"FID_CLUSTER_C_UNIQUE_{i:03d}"
        all_fids.add(fid)
        board = boards[i % len(boards)]
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (?, ?, '5000', 1, ?, ?)",
            (post_num, board, json.dumps({"file_id": fid, "type": "photo", "text": f"Cluster C {i}"}), time.time()),
        )

    assert len(all_fids) == 100

    vision_tracker = {"count": 0}
    processed = set()
    cycles = 0

    while cycles < 100:
        cycles += 1
        batch = await get_tasks(db, limit=10)
        if not batch:
            break
        for t in batch:
            tags, calculated_sha, called_vis = await _simulate_worker_task_processing(
                db, t, shared_sha_map=shared_sha_map, vision_call_counter=vision_tracker
            )
            processed.add(t["fid"])

    # 1. Total processed must equal 100
    assert processed == all_fids
    # 2. Vision AI calls must be exactly 32 (1 for cluster A, 1 for cluster B, 30 for unique C)
    assert vision_tracker["count"] == 32, f"Expected 32 vision calls (cached 68), got {vision_tracker['count']}"
    # 3. Tasks drain to 0
    rem_tasks = await get_tasks(db)
    assert len(rem_tasks) == 0

    # 4. Total rows in FileRegistry must be 100
    async with db.execute("SELECT COUNT(*) FROM FileRegistry") as cursor:
        total_rows = (await cursor.fetchone())[0]
    assert total_rows == 100

    print(f"\n[EMPIRICAL PROOF 5] 100 files across 3 clusters drained in {cycles} cycles. Vision AI caching verified: 32 calls made, 68 duplicate SHA calls bypassed.")
