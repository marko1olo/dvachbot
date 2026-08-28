# -*- coding: utf-8 -*-
"""Unit tests for work_alerts.py cooldown expiration notification engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from work_alerts import (
    WORK_ALERT_PHRASES, schedule_work_cooldown_alert,
    _work_cooldown_alert_task, _scheduled_work_alerts
)


class TestWorkAlertPhrases:
    def test_phrases_not_empty(self):
        assert len(WORK_ALERT_PHRASES) >= 4
        for p in WORK_ALERT_PHRASES:
            assert "<b>" in p
            assert len(p) > 50


@pytest.mark.asyncio
async def test_work_cooldown_alert_task_fires():
    """Verify that alert task sends banner message when cooldowns are expired."""
    mock_bot = MagicMock()
    user_id = 999111
    board_id = "b"

    with patch("work_alerts.asyncio.sleep", new=AsyncMock()), \
         patch("common.db_pool.get_pool", new=AsyncMock(return_value=MagicMock())), \
         patch("common.bot_helpers._get_user_active_items", new=AsyncMock(return_value={"work_cooldowns": {"bottles": 0}})), \
         patch("banner_manager.send_banner_message", new=AsyncMock()) as mock_send_banner:
        
        await _work_cooldown_alert_task(mock_bot, user_id, board_id, finish_ts=0)
        
        mock_send_banner.assert_called_once()
        args, kwargs = mock_send_banner.call_args
        caption_lower = kwargs["caption"].lower()
        assert any(w in caption_lower for w in ["работ", "завод", "кулдаун", "сыч", "смен", "пахат", "станок", "шекел", "абу", "доширак", "перерыв", "таймер", "батрач", "труда"])


@pytest.mark.asyncio
async def test_work_cooldown_alert_skips_if_active_cooldown_remains():
    """Verify that alert is NOT sent if another cooldown is still running in future."""
    mock_bot = MagicMock()
    user_id = 999222
    board_id = "b"

    with patch("work_alerts.asyncio.sleep", new=AsyncMock()), \
         patch("common.db_pool.get_pool", new=AsyncMock(return_value=MagicMock())), \
         patch("common.bot_helpers._get_user_active_items", new=AsyncMock(return_value={"work_cooldowns": {"factory": 9999999999}})), \
         patch("banner_manager.send_banner_message", new=AsyncMock()) as mock_send_banner:
        
        await _work_cooldown_alert_task(mock_bot, user_id, board_id, finish_ts=0)
        
        mock_send_banner.assert_not_called()
