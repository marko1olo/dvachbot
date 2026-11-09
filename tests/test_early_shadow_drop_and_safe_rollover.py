import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from datetime import datetime, timedelta, UTC

from main import WindowsSafeRotatingFileHandler
from handlers.message_router import (
    _build_shadow_echo_content,
    _is_user_shadow_muted_early,
    _last_shadow_echo_ts,
    handle_message
)
import shared_state


@pytest.mark.asyncio
async def test_safe_rotating_file_handler_cooldown(tmp_path):
    log_file = tmp_path / "test_runtime.log"
    log_file.write_text("A" * 200, encoding="utf-8")

    handler = WindowsSafeRotatingFileHandler(
        str(log_file), maxBytes=100, backupCount=2, encoding="utf-8"
    )

    record = MagicMock()
    record.getMessage.return_value = "Test log"

    # Simulate locked file (WinError 32)
    with patch("logging.handlers.RotatingFileHandler.doRollover", side_effect=PermissionError(32, "File in use")):
        with patch("sys.stderr.write") as mock_stderr:
            # First rollover attempt
            assert handler.shouldRollover(record) == 1
            handler.doRollover()

            # Warning must be emitted
            assert mock_stderr.called
            assert handler._rollover_retry_after > time.time() + 250.0

            # Subsequent shouldRollover calls must return 0 without doing rollover
            assert handler.shouldRollover(record) == 0
            assert handler.shouldRollover(record) == 0

    handler.close()


@pytest.mark.asyncio
async def test_is_user_shadow_muted_early_ram_and_admin():
    board_id = "b"
    user_id = 6199965905
    admin_id = 1234567

    shared_state.board_data[board_id] = {
        'shadow_mutes': {
            user_id: datetime.now(UTC) + timedelta(hours=1)
        },
        'user_settings': {},
        'users': {'active': set(), 'banned': set()}
    }

    mock_msg = MagicMock()
    mock_msg.content_type = "text"
    mock_msg.text = "spam test"

    # Admin is never muted
    with patch("handlers.message_router.is_admin", return_value=True):
        assert await _is_user_shadow_muted_early(admin_id, board_id, mock_msg) is False

    # Shadow muted user is detected immediately via RAM
    with patch("handlers.message_router.is_admin", return_value=False):
        assert await _is_user_shadow_muted_early(user_id, board_id, mock_msg) is True

    # Normal user is not muted
    normal_id = 999999
    with patch("handlers.message_router.is_admin", return_value=False):
        with patch("common.database.is_shadow_muted", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = False
            assert await _is_user_shadow_muted_early(normal_id, board_id, mock_msg) is False


@pytest.mark.asyncio
async def test_handle_message_early_shadow_drop():
    board_id = "b"
    user_id = 6199965905

    shared_state.board_data[board_id] = {
        'shadow_mutes': {
            user_id: datetime.now(UTC) + timedelta(hours=1)
        },
        'user_settings': {},
        'users': {'active': set(), 'banned': set()}
    }

    mock_bot = MagicMock()
    mock_msg = MagicMock()
    mock_msg.from_user.id = user_id
    mock_msg.chat.id = user_id
    mock_msg.bot = mock_bot
    mock_msg.content_type = "text"
    mock_msg.text = "spam attack"
    mock_msg.caption = None
    mock_msg.delete = AsyncMock()

    _last_shadow_echo_ts.clear()

    with patch("handlers.message_router.is_admin", return_value=False), \
         patch("handlers.message_router.spawn_task") as mock_spawn, \
         patch("handlers.message_router.process_new_post", new_callable=AsyncMock) as mock_new_post:

        # First message: dropped, echo spawned
        await handle_message(mock_msg, board_id)

        assert mock_msg.delete.called
        assert mock_spawn.called
        # Crucial: process_new_post must NEVER be called
        assert not mock_new_post.called

        # Second message immediately after (cooldown < 1.5s): deleted, no extra echo spawned
        mock_spawn.reset_mock()
        mock_msg.delete.reset_mock()
        await handle_message(mock_msg, board_id)

        assert mock_msg.delete.called
        assert not mock_spawn.called
        assert not mock_new_post.called
