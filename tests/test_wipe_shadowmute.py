import asyncio
import pytest
import time
from datetime import datetime, timezone, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

from common.database import update_shadow_mute, get_pool
from post_helpers import delete_user_posts
from admin_manager import cmd_wipe, execute_wipe


@pytest.mark.asyncio
async def test_update_shadow_mute_with_duration_and_reason(isolated_test_db):
    test_user_id = 999888777
    test_board = "b"
    duration = 3600
    reason = "wipe"

    # Issue shadowmute for 1 hour
    await update_shadow_mute(
        user_id=test_user_id,
        board_id=test_board,
        duration_seconds=duration,
        reason=reason
    )

    db = await get_pool()
    async with db.execute(
        "SELECT user_id, board_id, mute_type, expires_at, reason FROM Mutes WHERE user_id = ? AND board_id = ?",
        (test_user_id, test_board)
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None, "Shadowmute row should be present in Mutes table"
    assert row[0] == test_user_id
    assert row[1] == test_board
    assert row[2] == "shadow"
    assert row[3] > time.time() + 3500, "Expires at should be at least 3500 seconds in future"
    assert row[4] == "wipe", "Reason should be recorded as 'wipe'"


@pytest.mark.asyncio
async def test_delete_user_posts_with_broadcast_queue(isolated_test_db):
    test_author_id = 888777666
    test_board = "b"
    bot_mock = AsyncMock()
    bot_mock.delete_message = AsyncMock(return_value=True)

    db = await get_pool()
    
    # Insert test post
    now_ts = datetime.now(UTC).timestamp()
    await db.execute(
        """
        INSERT INTO Posts (post_num, board_id, author_id, timestamp, content)
        VALUES (9999991, ?, ?, ?, '{"type": "text", "text": "test spam"}')
        """,
        (test_board, test_author_id, now_ts)
    )
    # Insert PostCopies
    await db.execute(
        """
        INSERT INTO PostCopies (post_num, recipient_id, message_id)
        VALUES (9999991, 111111, 222222)
        """
    )
    # Insert BroadcastQueue
    await db.execute(
        """
        INSERT INTO BroadcastQueue (post_num, created_at, is_sent_to_tg)
        VALUES (9999991, ?, 0)
        """,
        (now_ts,)
    )

    # Call delete_user_posts
    deleted_count = await delete_user_posts(bot_mock, test_author_id, time_period_minutes=60, board_id=test_board)
    assert deleted_count == 1, "Should delete 1 post"

    # Verify deleted from Posts
    async with db.execute("SELECT * FROM Posts WHERE post_num = 9999991") as cursor:
        assert await cursor.fetchone() is None

    # Verify deleted from PostCopies
    async with db.execute("SELECT * FROM PostCopies WHERE post_num = 9999991") as cursor:
        assert await cursor.fetchone() is None

    # Verify deleted from BroadcastQueue
    async with db.execute("SELECT * FROM BroadcastQueue WHERE post_num = 9999991") as cursor:
        assert await cursor.fetchone() is None


@pytest.mark.asyncio
async def test_cmd_wipe_resolution_and_apriori_shadowmute(isolated_test_db):
    test_author_id = 777666555
    test_board = "b"
    admin_id = 7716348189
    
    db = await get_pool()
    now_ts = datetime.now(UTC).timestamp()
    
    # Create test post
    await db.execute(
        """
        INSERT INTO Posts (post_num, board_id, author_id, timestamp, content)
        VALUES (9999992, ?, ?, ?, '{"type": "text", "text": "spam to wipe"}')
        """,
        (test_board, test_author_id, now_ts)
    )

    # Mock admin message: /wipe 9999992 (passing post_num)
    message = AsyncMock()
    message.from_user.id = admin_id
    message.text = "/wipe 9999992"
    message.caption = None
    message.reply_to_message = None
    message.answer = AsyncMock()
    message.delete = AsyncMock()

    with patch("admin_manager.is_admin", return_value=True):
        await cmd_wipe(message, board_id=test_board)

    # Verify author received shadowmute for 1 hour
    async with db.execute(
        "SELECT user_id, board_id, mute_type, expires_at, reason FROM Mutes WHERE user_id = ? AND board_id = ?",
        (test_author_id, test_board)
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None, "Target author should have been shadowmuted immediately upon /wipe"
    assert row[0] == test_author_id
    assert row[2] == "shadow"
    assert row[3] > time.time() + 3500
    assert row[4] == "wipe"

    # Verify bot answered with confirmation prompt
    assert message.answer.called
    answer_text = message.answer.call_args[0][0]
    assert "⚠️" in answer_text
    assert str(test_author_id) in answer_text
    assert "теневой мут на 1ч" in answer_text
