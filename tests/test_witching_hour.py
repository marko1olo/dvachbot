import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

import witching_hour


def test_is_witching_hour_active_initial_state():
    # Initial state is usually 0 for both timestamps
    witching_hour.witching_hour_start_ts = 0
    witching_hour.witching_hour_end_ts = 0
    with patch("time.time", return_value=1000):
        # When both are 0, 0 <= 1000 <= 0 is false.
        # But if time.time() happens to return 0, 0 <= 0 <= 0 is true.
        # Let's test non-zero time which is the common case
        assert not witching_hour.is_witching_hour_active()

    with patch("time.time", return_value=0):
        # Edge case: time.time() returns exactly 0
        assert witching_hour.is_witching_hour_active()


def test_is_witching_hour_active_before_start():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch("time.time", return_value=999):
        assert not witching_hour.is_witching_hour_active()


def test_is_witching_hour_active_at_start():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch("time.time", return_value=1000):
        assert witching_hour.is_witching_hour_active()


def test_is_witching_hour_active_in_middle():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch("time.time", return_value=1500):
        assert witching_hour.is_witching_hour_active()


def test_is_witching_hour_active_at_end():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch("time.time", return_value=2000):
        assert witching_hour.is_witching_hour_active()


def test_is_witching_hour_active_after_end():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch("time.time", return_value=2001):
        assert not witching_hour.is_witching_hour_active()


@pytest.mark.asyncio
async def test_witching_hour_ghost_worker_error_path(capsys):
    bot_instance = MagicMock()

    mock_main = MagicMock()
    mock_main.board_data = {"b": {"recipients": {"user1"}}}
    mock_main.state = {"post_counter": 100}
    mock_main.format_header = AsyncMock(return_value="Header")
    mock_main.send_message_to_users = AsyncMock(
        side_effect=Exception("Simulated ghost error")
    )
    mock_main.shadow_fake_post_counters = {}

    mock_summarize = MagicMock()
    mock_summarize.summarize_text_with_hf = AsyncMock(return_value="Scary message")

    mock_db = MagicMock()
    mock_db.get_board_chunk = AsyncMock(return_value="Some chunk")

    with (
        patch.dict(
            "sys.modules",
            {
                "main": mock_main,
                "summarize": mock_summarize,
                "common.database": mock_db,
            },
        ),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("witching_hour.is_witching_hour_active", return_value=True),
        patch("random.random", return_value=0.05),
        patch("random.choice", return_value="b"),
    ):
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        with pytest.raises(asyncio.CancelledError):
            await witching_hour.witching_hour_ghost_worker(bot_instance)

        captured = capsys.readouterr()
        assert "Ghost Error: Simulated ghost error" in captured.out
        assert mock_main.send_message_to_users.call_count == 1
