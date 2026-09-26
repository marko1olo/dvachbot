import pytest
import time
import json
from common.database import (
    get_post_info_by_copy,
    get_post_author_by_copy,
    delete_post_by_num,
    add_post_copies,
    add_channel_copy,
    _THREAD_CACHE,
    _VIDEO_CACHE,
    _IMAGE_CACHE
)
import common.config as config
import shared_state


@pytest.mark.asyncio
async def test_copy_resolution_no_cross_chat_false_positives(isolated_test_db):
    """
    Vulnerability check:
    Telegram message_id is an autoincrement integer scoped ONLY to a single chat/channel.
    If a user in DM receives message_id=42, and an arbitrary post in a channel had message_id=42,
    get_post_info_by_copy(user_dm_chat_id, 42) MUST NOT return that channel's post!
    """
    db = isolated_test_db
    now = time.time()

    # Post 1 by Author 99999 (Innocent user), copied to a channel with message_id=42
    channel_id = -1001999999999
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (101, 'b', 99999, '{}', ?)",
        (now,)
    )
    await add_channel_copy(101, channel_id, 42)

    # Post 2 by Author 66666 (Spammer), copied to user DM (chat_id=11111) with message_id=105
    user_id = 11111
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (102, 'b', 66666, '{}', ?)",
        (now,)
    )
    await add_post_copies(102, [(user_id, 105)])

    # 1. User DM lookup for message_id=42 (does NOT exist in PostCopies for this user):
    # Must return None, NOT Post 101!
    res_dm = await get_post_info_by_copy(user_id, 42)
    assert res_dm is None, "User DM copy query MUST NOT match unrelated ChannelCopies row!"

    author_dm = await get_post_author_by_copy(user_id, 42)
    assert author_dm is None, "User DM author query MUST NOT match unrelated ChannelCopies row!"

    # 2. Channel lookup with exact channel_id and message_id:
    # Must return Post 101
    res_chan = await get_post_info_by_copy(channel_id, 42)
    assert res_chan == (101, 99999), "Exact channel_id match must return (post_num, author_id)"

    author_chan = await get_post_author_by_copy(channel_id, 42)
    assert author_chan == 99999, "Channel author query must return correct author_id"

    # 3. User DM lookup with exact PostCopies match:
    # Must return Post 102
    res_dm_exact = await get_post_info_by_copy(user_id, 105)
    assert res_dm_exact == (102, 66666), "Exact PostCopies match must return (post_num, author_id)"

    author_dm_exact = await get_post_author_by_copy(user_id, 105)
    assert author_dm_exact == 66666, "Exact PostCopies author query must return correct author_id"


@pytest.mark.asyncio
async def test_copy_resolution_storage_cluster_fallback(isolated_test_db, monkeypatch):
    """
    Verifies that known storage channels fall back to cluster channels or Posts.channel_message_id.
    """
    db = isolated_test_db
    now = time.time()

    storage_ch1 = -1001111111111
    storage_ch2 = -1002222222222
    monkeypatch.setattr(config, "STORAGE_CHANNELS", {"ru": storage_ch1, "en": storage_ch2})

    # Post with channel_message_id=777
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp, channel_message_id) VALUES (201, 'b', 77777, '{}', ?, 777)",
        (now,)
    )

    # Query from storage_ch1 for message_id 777:
    res = await get_post_info_by_copy(storage_ch1, 777)
    assert res == (201, 77777), "Storage channel query must resolve via channel_message_id"

    # Post copied to storage_ch2
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (202, 'b', 88888, '{}', ?)",
        (now,)
    )
    await add_channel_copy(202, storage_ch2, 888)

    # Query from storage_ch1 for message_id 888 (cluster sibling fallback):
    res_cluster = await get_post_info_by_copy(storage_ch1, 888)
    assert res_cluster == (202, 88888), "Storage cluster sibling lookup must resolve across known cluster channels"


@pytest.mark.asyncio
async def test_delete_post_by_num_thread_and_op_post(isolated_test_db):
    """
    Verifies delete_post_by_num:
    - OP post with thread_id = NULL is fully deleted from Posts.
    - All replies in thread are deleted.
    - PostFiles, PostCopies, ChannelCopies, NotificationQueue are cleaned.
    - Caches (_THREAD_CACHE, _VIDEO_CACHE, _IMAGE_CACHE) are cleaned for ALL posts of the thread.
    """
    db = isolated_test_db
    now = time.time()

    # OP post (thread_id IS NULL)
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (500, 'b', NULL, 1000, '{}', ?)",
        (now,)
    )
    await db.execute(
        "INSERT INTO Threads (thread_id, thread_num, board_id, op_id, title, created_at, last_updated_at) VALUES ('500', 500, 'b', 1000, 'Test Thread', ?, ?)",
        (now, now)
    )

    # Replies 501, 502
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, thread_id, author_id, reply_to_post_num, content, timestamp) VALUES (501, 'b', '500', 1001, 500, '{}', ?)",
        (now,)
    )
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, thread_id, author_id, reply_to_post_num, content, timestamp) VALUES (502, 'b', '500', 1002, 501, '{}', ?)",
        (now,)
    )

    # Copies & notifications
    await add_post_copies(500, [(10, 1001)])
    await add_post_copies(501, [(10, 1002)])
    await add_post_copies(502, [(10, 1003)])
    await add_channel_copy(500, -1001234, 5001)

    await db.execute("INSERT INTO NotificationQueue (board_id, source_post_num, reply_post_num, recipient_id, created_at) VALUES ('b', 501, 500, 10, ?)", (now,))
    await db.execute("INSERT INTO UserReplies (board_id, user_id, post_num, parent_num, thread_id, created_at) VALUES ('b', 10, 501, 500, '500', ?)", (now,))

    # Set up in-memory caches
    _THREAD_CACHE["b"] = ["500", "500"]  # duplicate string safety test
    _VIDEO_CACHE["b"] = [(500, "vid1"), (501, "vid2"), (999, "vid999")]
    _IMAGE_CACHE["b"] = [(502, "img1"), (999, "img999")]

    # Delete thread
    deleted = await delete_post_by_num(500)
    assert deleted is True, "delete_post_by_num must return True"

    # Verify Posts table: BOTH OP post (500) and replies (501, 502) must be gone!
    async with db.execute("SELECT post_num FROM Posts WHERE post_num IN (500, 501, 502)") as c:
        remaining_posts = await c.fetchall()
    assert remaining_posts == [], f"All posts must be deleted, but found: {remaining_posts}"

    # Verify Threads table
    async with db.execute("SELECT 1 FROM Threads WHERE thread_id = '500'") as c:
        assert await c.fetchone() is None

    # Verify dependent tables
    async with db.execute("SELECT COUNT(*) FROM PostCopies WHERE post_num IN (500, 501, 502)") as c:
        assert (await c.fetchone())[0] == 0

    async with db.execute("SELECT COUNT(*) FROM ChannelCopies WHERE post_num = 500") as c:
        assert (await c.fetchone())[0] == 0

    async with db.execute("SELECT COUNT(*) FROM NotificationQueue WHERE source_post_num = 501 OR reply_post_num = 500") as c:
        assert (await c.fetchone())[0] == 0

    # Verify cache cleanup
    assert "500" not in _THREAD_CACHE["b"]
    # 500 and 501 must be removed, 999 must remain
    assert _VIDEO_CACHE["b"] == [(999, "vid999")]
    # 502 must be removed, 999 must remain
    assert _IMAGE_CACHE["b"] == [(999, "img999")]


@pytest.mark.asyncio
async def test_delete_post_by_num_single_post(isolated_test_db):
    """
    Verifies delete_post_by_num on a single reply post (not a thread):
    - Deletes post 601.
    - Sets reply_to_post_num = NULL on post 602 that replied to 601.
    """
    db = isolated_test_db
    now = time.time()

    await db.execute(
        "INSERT INTO Posts (post_num, board_id, thread_id, author_id, content, timestamp) VALUES (600, 'b', '10', 1000, '{}', ?)",
        (now,)
    )
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, thread_id, author_id, reply_to_post_num, content, timestamp) VALUES (601, 'b', '10', 1001, 600, '{}', ?)",
        (now,)
    )
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, thread_id, author_id, reply_to_post_num, content, timestamp) VALUES (602, 'b', '10', 1002, 601, '{}', ?)",
        (now,)
    )
    await add_post_copies(601, [(10, 6011)])

    deleted = await delete_post_by_num(601)
    assert deleted is True

    # Post 601 deleted
    async with db.execute("SELECT post_num FROM Posts WHERE post_num = 601") as c:
        assert await c.fetchone() is None

    # Post 602 remains, but reply_to_post_num is NULL
    async with db.execute("SELECT post_num, reply_to_post_num FROM Posts WHERE post_num = 602") as c:
        row = await c.fetchone()
        assert row == (602, None)
