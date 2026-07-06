from unittest.mock import patch, MagicMock, AsyncMock
import pytest
import witching_hour


def test_is_witching_hour_active_initial_state():
    witching_hour.witching_hour_start_ts = 0
    witching_hour.witching_hour_end_ts = 0
    with patch("time.time", return_value=1000):
        assert not witching_hour.is_witching_hour_active()

    with patch("time.time", return_value=0):
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
async def test_ghost_worker_exception_handling():
    mock_board_data = {"board1": {"recipients": {"user1"}}}
    mock_state = {"post_counter": 100}

    sleep_call_count = 0

    async def mock_sleep(seconds):
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count > 1:
            raise KeyboardInterrupt("stop loop")

    with (
        patch("witching_hour.asyncio.sleep", new=AsyncMock(side_effect=mock_sleep)),
        patch("witching_hour.is_witching_hour_active", return_value=True),
        patch("witching_hour.random.random", return_value=0.05),
        patch("witching_hour.random.choice", return_value="board1"),
        patch("witching_hour.random.randint", return_value=1),
        patch.dict(
            "sys.modules",
            {
                "main": MagicMock(
                    board_data=mock_board_data,
                    state=mock_state,
                    shadow_fake_post_counters={},
                    format_header=AsyncMock(return_value="header"),
                    send_message_to_users=AsyncMock(
                        side_effect=Exception("Test Ghost Error")
                    ),
                ),
                "common.database": MagicMock(
                    get_board_chunk=AsyncMock(return_value="chunk")
                ),
                "summarize": MagicMock(
                    summarize_text_with_hf=AsyncMock(return_value="creepy text")
                ),
            },
        ),
        patch("builtins.print") as mock_print,
    ):
        try:
            await witching_hour.witching_hour_ghost_worker(bot_instance=MagicMock())
        except KeyboardInterrupt:
            pass

        mock_print.assert_any_call("💀 [WITCHING HOUR] Ghost Error: Test Ghost Error")
