import asyncio
import time
from datetime import datetime, UTC
from unittest import mock
import pytest

from common.spam_filter import check_flood, _user_request_timestamps, _user_media_burst_tracker
from shared_state import board_data
from post_processor import NewPostProcessor, NewPostContext


@pytest.mark.asyncio
async def test_post_processor_db_retry_success():
    """
    Verifies NewPostProcessor retries create_post if it initially returns None
    (e.g., SQLite locked/timeout) and successfully rescues the post.
    """
    mock_bot = mock.AsyncMock()
    ctx = NewPostContext(
        bot_instance=mock_bot,
        board_id="b",
        user_id=5264555563,
        content={"text": "ned lore"},
        reply_to_post=None,
        is_shadow_muted=False,
        stream="ru",
    )
    processor = NewPostProcessor(ctx)
    processor.final_content = {"text": "ned lore"}

    # Simulate create_post returning None on 1st call, then 551385 on retry
    mock_calls = []
    async def fake_create_post(**kwargs):
        mock_calls.append(kwargs)
        if len(mock_calls) == 1:
            return None
        return 551385

    with mock.patch("post_processor.create_post", side_effect=fake_create_post), \
         mock.patch("post_processor.update_user_verification_stats", return_value=None), \
         mock.patch("asyncio.sleep", new_callable=mock.AsyncMock) as mock_sleep:
        success = await processor._create_post_record(datetime.now(UTC))
        assert success is True
        assert processor.current_post_num == 551385
        assert len(mock_calls) == 2
        mock_sleep.assert_awaited()


@pytest.mark.asyncio
async def test_post_processor_db_exhausted_top_level():
    """
    Verifies that when create_post fails on all retries for a top-level post,
    the user receives an honest 'Database busy' warning rather than silent data loss.
    """
    mock_bot = mock.AsyncMock()
    ctx = NewPostContext(
        bot_instance=mock_bot,
        board_id="b",
        user_id=5264555563,
        content={"text": "ДА ЕБАННЫЙ ТЫ В РОТ"},
        reply_to_post=None,
        is_shadow_muted=False,
        stream="ru",
    )
    processor = NewPostProcessor(ctx)
    processor.final_content = {"text": "ДА ЕБАННЫЙ ТЫ В РОТ"}

    with mock.patch("post_processor.create_post", return_value=None), \
         mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
        success = await processor._create_post_record(datetime.now(UTC))
        assert success is False
        assert processor.current_post_num == None
        mock_bot.send_message.assert_awaited_once()
        msg_text = mock_bot.send_message.call_args[0][1]
        assert "база данных занята" in msg_text or "Database is temporarily busy" in msg_text


@pytest.mark.asyncio
async def test_post_processor_db_exhausted_reply_distinguishes_deleted_vs_busy():
    """
    Verifies that when replying:
    - If parent post exists in DB, user is informed that the DB is busy.
    - If parent post truly does not exist, user is informed that post was deleted.
    """
    mock_bot = mock.AsyncMock()
    ctx = NewPostContext(
        bot_instance=mock_bot,
        board_id="b",
        user_id=5264555563,
        content={"text": "test reply"},
        reply_to_post=551384,
        is_shadow_muted=False,
        stream="ru",
    )
    processor = NewPostProcessor(ctx)
    processor.final_content = {"text": "test reply"}

    # Case A: Parent post exists -> DB busy message
    with mock.patch("post_processor.create_post", return_value=None), \
         mock.patch("common.database.get_post_by_num", return_value={"post_num": 551384}), \
         mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
        success = await processor._create_post_record(datetime.now(UTC))
        assert success is False
        msg_text = mock_bot.send_message.call_args[0][1]
        assert "база данных занята" in msg_text

    mock_bot.reset_mock()

    # Case B: Parent post truly does not exist -> deleted parent post message
    with mock.patch("post_processor.create_post", return_value=None), \
         mock.patch("common.database.get_post_by_num", return_value=None), \
         mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
        success = await processor._create_post_record(datetime.now(UTC))
        assert success is False
        msg_text = mock_bot.send_message.call_args[0][1]
        assert "был удален" in msg_text


def test_veteran_media_burst_flood_protection():
    """
    Verifies that veteran user (e.g. 3922 posts, mult >= 1.75) posting media items
    does not trigger false-positive burst flood shadow-mute due to MEDIA_BURST_BONUS.
    """
    user_id = 7414244332
    board_id = "b"
    _user_request_timestamps.pop((user_id, board_id), None)
    _user_request_timestamps.pop(user_id, None)
    _user_media_burst_tracker.pop(user_id, None)

    # 3922 posts -> 'oldfag' tier (mult >= 1.75)
    with mock.patch("common.spam_filter.get_cached_user_posts", return_value=3922):
        # 16 media items sent in 2.5 seconds
        now = time.time()
        for i in range(16):
            is_flood, reason = check_flood(
                user_id=user_id,
                board_id=board_id,
                now_ts=now + (i * 0.1),
                record_history=True,
                is_reply=False,
                posts_count=3922,
                is_media=True,
                media_group_id=None,
            )
            # None of the 16 media items should trigger flood
            assert is_flood is False, f"Item {i+1} triggered flood unexpectedly: {reason}"

    _user_request_timestamps.pop((user_id, board_id), None)
    _user_request_timestamps.pop(user_id, None)
    _user_media_burst_tracker.pop(user_id, None)


@pytest.mark.asyncio
async def test_update_shadow_mute_ram_sync_and_rollback(isolated_test_db):
    """
    Verifies update_shadow_mute:
    1. Correctly sets RAM board_data['shadow_mutes'] on success (and does not pop it).
    2. Writes to DB Mutes table.
    3. Rolls back RAM board_data['shadow_mutes'] if the DB transaction raises an error.
    """
    from common.database import update_shadow_mute, is_shadow_muted

    user_id = 99887766
    board_id = "b"
    if board_id not in board_data:
        board_data[board_id] = {}
    board_data[board_id]["shadow_mutes"] = {}

    # 1. Successful application
    await update_shadow_mute(user_id=user_id, board_id=board_id, duration_seconds=600, reason="test_mute")
    assert user_id in board_data[board_id]["shadow_mutes"]
    assert await is_shadow_muted(user_id, board_id) is True

    # 2. Simulate DB failure during update
    with mock.patch.object(isolated_test_db, "execute", side_effect=Exception("Simulated SQLite lock")):
        await update_shadow_mute(user_id=user_id, board_id=board_id, duration_seconds=1200, reason="failed_mute")
        # RAM must have been rolled back so it does not falsely keep the user muted
        assert user_id not in board_data[board_id]["shadow_mutes"]

    # 3. Explicit unmute (expires_at=0)
    # Re-apply first
    await update_shadow_mute(user_id=user_id, board_id=board_id, duration_seconds=600)
    assert user_id in board_data[board_id]["shadow_mutes"]
    assert await is_shadow_muted(user_id, board_id) is True

    # Now lift mute
    await update_shadow_mute(user_id=user_id, board_id=board_id, expires_at=0)
    assert user_id not in board_data[board_id]["shadow_mutes"]
    assert await is_shadow_muted(user_id, board_id) is False


@pytest.mark.asyncio
async def test_handle_message_drops_banned_user():
    """
    Verifies that a message from a banned user is deleted and dropped immediately
    with structured logging.
    """
    from handlers.message_router import handle_message
    from aiogram import types

    user_id = 11223344
    board_id = "b"
    board_data.setdefault(board_id, {})
    board_data[board_id].setdefault("users", {"active": set(), "banned": set()})
    board_data[board_id].setdefault("mutes", {})
    board_data[board_id].setdefault("shadow_mutes", {})
    board_data[board_id].setdefault("single_photo_counter", {})
    board_data[board_id].setdefault("last_activity", {})
    board_data[board_id].setdefault("user_settings", {})
    board_data[board_id]["users"]["banned"].add(user_id)

    msg = mock.MagicMock(spec=types.Message)
    msg.message_id = 1001
    msg.content_type = "text"
    msg.text = "Hello from banned user"
    msg.caption = None
    msg.from_user = mock.MagicMock(spec=types.User)
    msg.from_user.id = user_id
    msg.from_user.is_bot = False
    msg.chat = mock.MagicMock(spec=types.Chat)
    msg.chat.id = user_id
    msg.reply_to_message = None
    msg.forward_from = None
    msg.forward_from_chat = None
    msg.sticker = None
    msg.bot = mock.MagicMock(id=999999999)
    msg.delete = mock.AsyncMock()

    with mock.patch("handlers.message_router.is_admin", return_value=False), \
         mock.patch("handlers.message_router.logger.warning") as mock_log_warn:
        await handle_message(msg, board_id=board_id)
        msg.delete.assert_awaited_once()
        # Verify drop log
        assert any("MSG DROPPED: BANNED_USER" in str(c) for c in mock_log_warn.call_args_list)

    board_data[board_id]["users"]["banned"].discard(user_id)


@pytest.mark.asyncio
async def test_handle_message_drops_active_mute():
    """
    Verifies that a message from an actively muted user in RAM is deleted
    and dropped with structured logging.
    """
    from handlers.message_router import handle_message
    from aiogram import types
    from datetime import timedelta

    user_id = 55667788
    board_id = "b"
    board_data.setdefault(board_id, {})
    board_data[board_id].setdefault("users", {"active": set(), "banned": set()})
    board_data[board_id].setdefault("mutes", {})
    board_data[board_id].setdefault("shadow_mutes", {})
    board_data[board_id].setdefault("single_photo_counter", {})
    board_data[board_id].setdefault("last_activity", {})
    board_data[board_id].setdefault("user_settings", {})
    board_data[board_id]["mutes"][user_id] = datetime.now(UTC) + timedelta(minutes=15)

    msg = mock.MagicMock(spec=types.Message)
    msg.message_id = 1002
    msg.content_type = "text"
    msg.text = "Hello from muted user"
    msg.caption = None
    msg.from_user = mock.MagicMock(spec=types.User)
    msg.from_user.id = user_id
    msg.from_user.is_bot = False
    msg.chat = mock.MagicMock(spec=types.Chat)
    msg.chat.id = user_id
    msg.reply_to_message = None
    msg.forward_from = None
    msg.forward_from_chat = None
    msg.sticker = None
    msg.bot = mock.MagicMock(id=999999999)
    msg.delete = mock.AsyncMock()
    msg.answer = mock.AsyncMock()

    with mock.patch("handlers.message_router.is_admin", return_value=False), \
         mock.patch("handlers.message_router.logger.warning") as mock_log_warn:
        await handle_message(msg, board_id=board_id)
        msg.delete.assert_awaited_once()
        assert any("MSG DROPPED: MUTE_ACTIVE" in str(c) for c in mock_log_warn.call_args_list)

    board_data[board_id]["mutes"].pop(user_id, None)


@pytest.mark.asyncio
async def test_handle_message_repost_spam_shadowmutes_and_drops():
    """
    Verifies that handle_message drops the 5th repost from a public channel,
    replies with toxic Dvach response, and deletes the offending message.
    """
    from handlers.message_router import handle_message
    from aiogram import types

    user_id = 99887766
    board_id = "b"
    board_data.setdefault(board_id, {})
    board_data[board_id].setdefault("users", {"active": set(), "banned": set()})
    board_data[board_id].setdefault("mutes", {})
    board_data[board_id].setdefault("shadow_mutes", {})
    board_data[board_id].setdefault("single_photo_counter", {})
    board_data[board_id].setdefault("last_activity", {})
    board_data[board_id].setdefault("user_settings", {})

    msg = mock.MagicMock(spec=types.Message)
    msg.message_id = 2001
    msg.content_type = "text"
    msg.text = "Forwarded message from public channel"
    msg.caption = None
    msg.forward_origin = mock.MagicMock()
    msg.forward_origin.type = "channel"
    msg.from_user = mock.MagicMock(spec=types.User)
    msg.from_user.id = user_id
    msg.from_user.is_bot = False
    msg.chat = mock.MagicMock(spec=types.Chat)
    msg.chat.id = user_id
    msg.reply_to_message = None
    msg.forward_from = None
    msg.forward_from_chat = None
    msg.sticker = None
    msg.bot = mock.MagicMock(id=999999999)
    msg.delete = mock.AsyncMock()
    warn_reply_mock = mock.MagicMock()
    msg.answer = mock.AsyncMock(return_value=warn_reply_mock)

    with mock.patch("handlers.message_router.is_admin", return_value=False), \
         mock.patch("common.spam_filter.check_repost_spam_async", new=mock.AsyncMock(return_value=(True, "Хватит форвардить этот кал, шизоид.", 1001200.0))), \
         mock.patch("handlers.message_router.logger.warning") as mock_log_warn, \
         mock.patch("common.bot_helpers.process_new_post", new=mock.AsyncMock()) as mock_proc:
        await handle_message(msg, board_id=board_id)
        msg.answer.assert_awaited_once_with("Хватит форвардить этот кал, шизоид.")
        msg.delete.assert_awaited_once()
        mock_proc.assert_not_called()
        assert any("MSG DROPPED: REPOST_SPAM" in str(c) for c in mock_log_warn.call_args_list)


@pytest.mark.asyncio
async def test_handle_media_group_init_db_failure_resilience():
    """
    Verifies that handle_media_group_init gracefully survives DB errors during
    shadowmute check and continues using RAM fallback.
    """
    from handlers.message_router import handle_media_group_init
    from aiogram import types

    user_id = 44556677
    board_id = "b"
    board_data.setdefault(board_id, {})
    board_data[board_id].setdefault("users", {"active": set(), "banned": set()})
    board_data[board_id].setdefault("mutes", {})
    board_data[board_id].setdefault("shadow_mutes", {})
    board_data[board_id].setdefault("single_photo_counter", {})
    board_data[board_id].setdefault("last_activity", {})
    board_data[board_id].setdefault("user_settings", {})

    msg = mock.MagicMock(spec=types.Message)
    msg.message_id = 3001
    msg.media_group_id = "mg_resilience_test_123"
    msg.content_type = "photo"
    msg.photo = [mock.MagicMock(file_id="ph_123", file_size=1024)]
    msg.caption = "Test album resilience"
    msg.from_user = mock.MagicMock(spec=types.User)
    msg.from_user.id = user_id
    msg.from_user.is_bot = False
    msg.chat = mock.MagicMock(spec=types.Chat)
    msg.chat.id = user_id
    msg.reply_to_message = None
    msg.forward_from = None
    msg.forward_from_chat = None
    msg.bot = mock.MagicMock(id=999999999)
    msg.delete = mock.AsyncMock()

    with mock.patch("handlers.message_router.is_admin", return_value=False), \
         mock.patch("common.database.is_shadow_muted", new=mock.AsyncMock(side_effect=RuntimeError("DB locked / pool failure"))), \
         mock.patch("common.spam_filter.check_flood", return_value=(False, 0.0)), \
         mock.patch("common.spam_filter.check_repost_spam_async", new=mock.AsyncMock(return_value=(False, "", 0.0))):
        # Should not raise exception despite DB failure
        res = await handle_media_group_init(msg, board_id=board_id)
        assert res is None


