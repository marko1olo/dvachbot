import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from witching_hour import witching_hour_ghost_worker

class StopLoopException(Exception):
    pass

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
