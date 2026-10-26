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
    now_ts = time.time()

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
         patch.object(main, "_get_last_motivation_time", return_value=now_ts - (5 * 3600)), \
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
