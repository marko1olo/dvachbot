import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock, MagicMock

import witching_hour
from witching_hour import witching_hour_ghost_worker

class StopLoopException(Exception):
    pass


def test_is_witching_hour_active_initial_state():
    # Initial state is usually 0 for both timestamps
    witching_hour.witching_hour_start_ts = 0
    witching_hour.witching_hour_end_ts = 0
    with patch('time.time', return_value=1000):
        # When both are 0, 0 <= 1000 <= 0 is false.
        # But if time.time() happens to return 0, 0 <= 0 <= 0 is true.
        # Let's test non-zero time which is the common case
        assert not witching_hour.is_witching_hour_active()

    with patch('time.time', return_value=0):
        # Edge case: time.time() returns exactly 0
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_before_start():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=999):
        assert not witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_at_start():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=1000):
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_in_middle():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=1500):
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_at_end():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=2000):
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_after_end():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=2001):
        assert not witching_hour.is_witching_hour_active()

@pytest.mark.asyncio
async def test_witching_hour_ghost_worker_inactive():
    bot_instance = MagicMock()
    with patch('witching_hour.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, StopLoopException()]
        with patch('witching_hour.is_witching_hour_active', return_value=False):
            try:
                await witching_hour_ghost_worker(bot_instance)
            except StopLoopException:
                pass

@pytest.mark.asyncio
async def test_witching_hour_ghost_worker_active_no_post():
    bot_instance = MagicMock()
    with patch('witching_hour.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, StopLoopException()]
        with patch('witching_hour.is_witching_hour_active', return_value=True):
            with patch('witching_hour.random.random', return_value=0.5): # 0.5 > 0.1 so it should not post
                try:
                    await witching_hour_ghost_worker(bot_instance)
                except StopLoopException:
                    pass


@pytest.mark.asyncio
async def test_witching_hour_ghost_worker_active_post():
    bot_instance = MagicMock()

    mock_board_data = {'b': {'recipients': {'user1'}}}
    mock_state = {'post_counter': 100}

    with patch('witching_hour.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, StopLoopException()]
        with patch('witching_hour.is_witching_hour_active', return_value=True):
            with patch('witching_hour.random.random', return_value=0.05): # 0.05 < 0.1 so it should post
                with patch.dict('main.board_data', mock_board_data, clear=True):
                    with patch.dict('main.state', mock_state, clear=True):
                        with patch('main.get_board_chunk', new_callable=AsyncMock, return_value="chunk context") as mock_chunk:
                            with patch('summarize.summarize_text_with_hf', new_callable=AsyncMock, return_value="ghost message") as mock_summarize:
                                with patch('main.format_header', new_callable=AsyncMock, return_value="header") as mock_format:
                                    with patch('main.send_message_to_users', new_callable=AsyncMock) as mock_send:
                                        try:
                                            await witching_hour_ghost_worker(bot_instance)
                                        except StopLoopException:
                                            pass

                                        # Verification
                                        mock_chunk.assert_called_once()
                                        mock_summarize.assert_called_once()
                                        mock_format.assert_called_once()
                                        mock_send.assert_called_once()
                                        args, kwargs = mock_send.call_args
                                        assert kwargs['bot_instance'] == bot_instance
                                        assert kwargs['board_id'] == 'b'
                                        assert kwargs['recipients'] == {'user1'}
                                        assert 'text' in kwargs['content']
                                        assert kwargs['content']['header'] == 'header'

@pytest.mark.asyncio
async def test_witching_hour_ghost_worker_no_active_boards():
    bot_instance = MagicMock()
    mock_board_data = {'b': {'recipients': set()}} # Empty recipients = inactive

    with patch('witching_hour.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, StopLoopException()]
        with patch('witching_hour.is_witching_hour_active', return_value=True):
            with patch('witching_hour.random.random', return_value=0.05):
                with patch.dict('main.board_data', mock_board_data, clear=True):
                    with patch('summarize.summarize_text_with_hf', new_callable=AsyncMock) as mock_summarize:
                        try:
                            await witching_hour_ghost_worker(bot_instance)
                        except StopLoopException:
                            pass

                        mock_summarize.assert_not_called()

@pytest.mark.asyncio
async def test_witching_hour_ghost_worker_summarize_failed():
    bot_instance = MagicMock()

    mock_board_data = {'b': {'recipients': {'user1'}}}
    mock_state = {'post_counter': 100}

    with patch('witching_hour.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, StopLoopException()]
        with patch('witching_hour.is_witching_hour_active', return_value=True):
            with patch('witching_hour.random.random', return_value=0.05):
                with patch.dict('main.board_data', mock_board_data, clear=True):
                    with patch.dict('main.state', mock_state, clear=True):
                        with patch('main.get_board_chunk', new_callable=AsyncMock, return_value="chunk context"):
                            # "Нейронка сдохла" means it failed and should skip
                            with patch('summarize.summarize_text_with_hf', new_callable=AsyncMock, return_value="Нейронка сдохла: error"):
                                with patch('main.send_message_to_users', new_callable=AsyncMock) as mock_send:
                                    try:
                                        await witching_hour_ghost_worker(bot_instance)
                                    except StopLoopException:
                                        pass

                                    mock_send.assert_not_called()

@pytest.mark.asyncio
async def test_witching_hour_ghost_worker_exception():
    bot_instance = MagicMock()

    mock_board_data = {'b': {'recipients': {'user1'}}}

    with patch('witching_hour.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = [None, StopLoopException()]
        with patch('witching_hour.is_witching_hour_active', return_value=True):
            with patch('witching_hour.random.random', return_value=0.05):
                with patch.dict('main.board_data', mock_board_data, clear=True):
                    with patch('main.get_board_chunk', new_callable=AsyncMock, side_effect=Exception("Database error")):
                        with patch('builtins.print') as mock_print:
                            try:
                                await witching_hour_ghost_worker(bot_instance)
                            except StopLoopException:
                                pass

                            mock_print.assert_called_with("💀 [WITCHING HOUR] Ghost Error: Database error")
