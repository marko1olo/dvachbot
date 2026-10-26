import pytest
import time
import os
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import main


@pytest.mark.asyncio
async def test_auto_summary_state_persistence(tmp_path):
    """Test that auto-summary state persists across calls and restarts."""
    test_state_file = str(tmp_path / "test_auto_summary_state.json")
    with patch.object(main, "_AUTO_SUMMARY_STATE_FILE", test_state_file):
        # Initial empty state
        assert main._get_last_auto_summary_time("b") == 0.0

        # Set time
        now_ts = time.time()
        main._set_last_auto_summary_time("b", now_ts)
        assert main._get_last_auto_summary_time("b") == now_ts

        # Load fresh from file
        loaded = main._load_auto_summary_state()
        assert loaded.get("b") == now_ts


@pytest.mark.asyncio
async def test_check_board_inactivity_cooldown():
    """Test that auto-summary refuses to run if 8h cooldown has not elapsed."""
    now_ts = time.time()
    last_summary_ts = now_ts - (4 * 3600)  # only 4 hours ago

    can_run, reason = await main._check_board_inactivity_for_auto_summary("b", last_summary_ts)
    assert can_run is False
    assert "cooldown_active" in reason


@pytest.mark.asyncio
async def test_check_board_inactivity_active_chat():
    """Test that auto-summary refuses to interrupt when chat is currently active."""
    now_ts = time.time()
    last_summary_ts = now_ts - (10 * 3600)  # 10 hours ago (cooldown ok)

    # Populate messages_storage with recent active posts (< 30m ago)
    test_storage = {}
    for i in range(15):
        test_storage[i] = {
            "board_id": "b",
            "author_id": 12345,
            "timestamp": now_ts - (i * 60),  # posts in the last 15 minutes
            "content": {"text": f"Active chatting message {i}"}
        }

    with patch.object(main, "messages_storage", test_storage):
        can_run, reason = await main._check_board_inactivity_for_auto_summary("b", last_summary_ts)
        assert can_run is False
        assert "chat_currently_active" in reason


@pytest.mark.asyncio
async def test_check_board_inactivity_insufficient_content():
    """Test that auto-summary skips if chat has too few new messages to summarize."""
    now_ts = time.time()
    last_summary_ts = now_ts - (10 * 3600)  # 10 hours ago

    # Quiet chat (last post 2 hours ago), but only 2 messages total
    test_storage = {
        1: {
            "board_id": "b",
            "author_id": 12345,
            "timestamp": now_ts - 7200,
            "content": {"text": "Hello"}
        },
        2: {
            "board_id": "b",
            "author_id": 12345,
            "timestamp": now_ts - 7000,
            "content": {"text": "Bye"}
        }
    }

    with patch.object(main, "messages_storage", test_storage):
        can_run, reason = await main._check_board_inactivity_for_auto_summary("b", last_summary_ts)
        assert can_run is False
        assert "insufficient_new_content" in reason


@pytest.mark.asyncio
async def test_check_board_inactivity_quiet_window_confirmed():
    """Test that auto-summary triggers when chat has been quiet >= 30m and has >= 10 posts."""
    now_ts = time.time()
    last_summary_ts = now_ts - (9 * 3600)  # 9 hours ago

    # Last post 45 minutes ago, and 12 text posts accumulated in the last 9 hours
    test_storage = {}
    for i in range(12):
        test_storage[i] = {
            "board_id": "b",
            "author_id": 1000 + i,
            "timestamp": now_ts - 2700 - (i * 300),  # starts at 45m ago and goes back
            "content": {"text": f"Meaningful discussion point #{i} regarding the topic"}
        }

    with patch.object(main, "messages_storage", test_storage):
        can_run, reason = await main._check_board_inactivity_for_auto_summary("b", last_summary_ts)
        assert can_run is True
        assert "quiet_window_confirmed" in reason


@pytest.mark.asyncio
async def test_motivation_worker_no_longer_requires_high_activity():
    """Test that _board_motivation_worker sends invite when active users are present without being blocked by activity < 10."""
    fixed_now = 1700046000.0  # 11:00 UTC / 14:00 MSK (active daytime)

    # Board has active users but 0 recent activity (quiet board that needs invites)
    test_board_data = {
        "b": {
            "users": {
                "active": {111, 222},
                "banned": set()
            }
        }
    }

    send_mock = AsyncMock()

    with patch.object(main, "board_data", test_board_data), \
         patch("time.time", return_value=fixed_now), \
         patch.object(main, "_get_last_motivation_time", return_value=fixed_now - (7 * 3600)), \
         patch.object(main, "_set_last_motivation_time") as set_time_mock, \
         patch.object(main, "_send_motivation_message", send_mock), \
         patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError]):

        try:
            await main._board_motivation_worker("b")
        except asyncio.CancelledError:
            pass

        # Verify that _send_motivation_message was called despite 0 activity
        assert send_mock.called
        assert set_time_mock.called


@pytest.mark.asyncio
async def test_board_motivation_eligibility():
    """Verify that only core active boards or boards with >= 15 posts are eligible."""
    assert await main._is_board_eligible_for_motivation("b") is True
    assert await main._is_board_eligible_for_motivation("sex") is True
    assert await main._is_board_eligible_for_motivation("thread") is True
    assert await main._is_board_eligible_for_motivation("test") is False
    assert await main._is_board_eligible_for_motivation("bunker") is False

    # Mock aiosqlite connection returned by get_pool()
    from unittest.mock import MagicMock
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=[5])
    mock_cursor.__aenter__.return_value = mock_cursor
    mock_cursor.__aexit__.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = MagicMock(return_value=mock_cursor)

    with patch("common.db_pool.get_pool", return_value=mock_db):
        # 5 posts < 15 -> False
        assert await main._is_board_eligible_for_motivation("x") is False

        # 20 posts >= 15 -> True
        mock_cursor.fetchone = AsyncMock(return_value=[20])
        assert await main._is_board_eligible_for_motivation("x") is True


def test_invite_image_branding_zero_2ch():
    """Verify that invite image slogans, watermarks and captions contain zero '2ch' or 'двач' references."""
    import re
    from invite_image_generator import IMAGE_SLOGANS, AUTO_POST_COMPANION_TEXTS

    for i, slogan in enumerate(IMAGE_SLOGANS):
        for k, v in slogan.items():
            assert not re.search(r'2ch|двач', v, re.IGNORECASE), f"Found 2ch/двач in slogan {i} [{k}]: {v}"

    for i, caption in enumerate(AUTO_POST_COMPANION_TEXTS):
        assert not re.search(r'2ch|двач', caption, re.IGNORECASE), f"Found 2ch/двач in caption {i}: {caption}"


@pytest.mark.asyncio
async def test_broadcaster_delivers_from_file_path(tmp_path):
    """Verify that broadcaster loads image from disk file_path if file_id is missing and image_bytes is not bytes."""
    from broadcaster import MessageBroadcaster
    from shared_state import BroadcastConfig

    test_file = tmp_path / "test_invite.jpg"
    test_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100) # Fake JPEG header

    bot_mock = AsyncMock()
    photo_res = AsyncMock()
    photo_res.photo = [AsyncMock(file_id="new_cached_fid_123")]
    bot_mock.send_photo = AsyncMock(return_value=photo_res)
    bot_mock.id = 999999

    content = {
        "type": "photo",
        "file_id": None,
        "image_bytes": "<бинарные данные: 104 байт>", # String as in DB
        "file_path": str(test_file),
        "caption": "Test invite caption",
        "text": "Test invite caption",
        "header": ""
    }

    config = BroadcastConfig(
        bot_instance=bot_mock,
        board_id="b",
        recipients={111222},
        content=content
    )

    broadcaster = MessageBroadcaster(config)
    broadcaster.users_settings = {}
    broadcaster.common_formatted_body = "Test invite caption"
    res = await broadcaster._send_one(111222, 10)

    # Broadcaster should call send_photo with BufferedInputFile read from file_path
    assert bot_mock.send_photo.called
    kwargs = bot_mock.send_photo.call_args[1]
    assert "Test invite caption" in kwargs.get("caption", "")
    assert hasattr(kwargs.get("photo"), "read")  # BufferedInputFile

    # And file_id should be cached in content
    assert content.get("file_id") == "new_cached_fid_123"

