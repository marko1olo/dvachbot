# -*- coding: utf-8 -*-
import asyncio
import time
import pytest
from unittest.mock import patch
from common.database import register_media_repost, create_post

@pytest.mark.asyncio
async def test_register_media_repost_basic(isolated_test_db):
    """Verifies basic first-seen and repost counts."""
    # Empty inputs return 1
    assert await register_media_repost("", "some_uid") == 1
    assert await register_media_repost("b", "") == 1

    # First time seen -> 1
    c1 = await register_media_repost("b", "unique_photo_aaa")
    assert c1 == 1

    # Second time seen -> 2
    c2 = await register_media_repost("b", "unique_photo_aaa")
    assert c2 == 2

    # Third time seen -> 3
    c3 = await register_media_repost("b", "unique_photo_aaa")
    assert c3 == 3

    # Different board has separate counter
    c_other = await register_media_repost("sex", "unique_photo_aaa")
    assert c_other == 1


@pytest.mark.asyncio
async def test_register_media_repost_concurrent_with_create_post(isolated_test_db):
    """
    Verifies that concurrent register_media_repost and create_post
    do not conflict, deadlock, or drop posts.
    """
    db = isolated_test_db

    # Ensure board exists
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('b', 'Бред')")

    create_results = []
    repost_results = []

    async def do_post(i):
        p_num = await create_post(
            author_id=5000 + i,
            board_id="b",
            content={"type": "text", "text": f"Concurrent test post {i}"},
            timestamp=time.time(),
        )
        create_results.append(p_num)

    async def do_repost(i, fuid):
        count = await register_media_repost("b", fuid)
        repost_results.append((fuid, count))

    tasks = []
    # 15 concurrent create_posts
    for i in range(15):
        tasks.append(do_post(i))

    # 30 concurrent reposts with 3 repeating keys
    for i in range(30):
        tasks.append(do_repost(i, f"concurrent_media_{i % 3}"))

    await asyncio.gather(*tasks)

    # Every post succeeded
    assert len(create_results) == 15
    assert all(p is not None for p in create_results)

    # All repost calls succeeded
    assert len(repost_results) == 30

    # Counts for each key reached 10
    async with db.execute("SELECT file_unique_id, times FROM MediaReposts ORDER BY file_unique_id") as cursor:
        rows = await cursor.fetchall()
        assert len(rows) == 3
        for r in rows:
            assert r[1] == 10


@pytest.mark.asyncio
async def test_register_media_repost_silent_fallback_on_error(isolated_test_db, caplog):
    """
    Verifies that on database errors or timeouts, register_media_repost
    gracefully and silently returns 1 without noisy warnings.
    """
    with patch("common.db_pool.get_pool", side_effect=RuntimeError("Simulated DB connection failure")):
        res = await register_media_repost("b", "test_file_error")
        assert res == 1

    # Ensure no WARNING or ERROR was logged
    for record in caplog.records:
        assert record.levelname not in ("WARNING", "ERROR"), f"Unexpected noisy log: {record.message}"
