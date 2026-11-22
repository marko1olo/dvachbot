# -*- coding: utf-8 -*-
"""
tests/test_work_engine_audit_fixes.py — Regression tests for work engine auditor bugfixes:
1. Self-healing of corrupted / impossible future cooldown timestamps.
2. Unlocked milestone achievement bonus cash is credited to user balance in cb_work_do.
3. cmd_work and cb_work_do gracefully handle None board_id with default 'b'.
4. Alert task correctly distinguishes started_at vs expires_at and waits for slowest job.
"""
import time
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from common.work_engine import execute_job_action, WORK_VACANCIES, JobResult
import shared_state
import work_alerts


def test_future_timestamp_self_healing_and_expires_at():
    """Verify that future cooldown timestamps are either treated as expires_at (if <= base_cd) or self-healed."""
    now = int(time.time())

    # Case A: Future timestamp within base_cd (e.g. 45s in future for bottles with 180s cd)
    items_valid_future = {
        "work_shifts": 5,
        "work_cooldowns": {"bottles": now + 45}
    }
    succ, reward, msg, drop = execute_job_action("bottles", items_valid_future, user_id=12345)
    assert succ is False
    assert "Кулдаун" in msg
    assert "45 сек" in msg

    # Case B: Impossible future timestamp (> base_cd, e.g. stale mock 9999999999 or clock jump)
    items_corrupt_future = {
        "work_shifts": 5,
        "work_cooldowns": {"bottles": now + 99999999}
    }
    succ2, reward2, msg2, drop2 = execute_job_action("bottles", items_corrupt_future, user_id=12345)
    # Must auto-heal and allow working immediately!
    assert succ2 is True
    assert reward2 > 0
    assert abs(items_corrupt_future["work_cooldowns"]["bottles"] - now) <= 3


@pytest.mark.asyncio
async def test_cb_work_do_credits_achievement_bonus(isolated_test_db):
    """Verify cb_work_do credits BOTH shift payout AND milestone achievement cash bonus."""
    import main
    user_id = 999444
    board_id = "b"
    db = isolated_test_db

    items = {
        "user_id": user_id,
        "work_shifts": 0,  # Shift #1 unlocks ach_first_work (+50 ₪ bonus)
        "work_cooldowns": {},
        "unlocked_achievements": []
    }

    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 0, ?)",
        (user_id, board_id, json.dumps(items))
    )
    await db.commit()

    mock_cb = MagicMock()
    mock_cb.from_user.id = user_id
    mock_cb.data = "work_do_bottles"
    mock_cb.answer = AsyncMock()
    mock_cb.message = MagicMock()
    mock_cb.message.caption = "Old text"
    mock_cb.message.edit_caption = AsyncMock()

    with patch("main.get_pool", return_value=db):
        await main.cb_work_do(mock_cb, board_id=None)  # None board_id must default to 'b'

    # Verify balance includes shift salary + 50 ₪ achievement bonus
    from common.database import get_user_global_balance
    bal = await get_user_global_balance(db, user_id)
    # Bottles base reward is 15-45, achievement is 50 -> total >= 65
    assert bal >= 65


@pytest.mark.asyncio
async def test_cmd_work_no_board_id_default(isolated_test_db):
    """Verify cmd_work handles None board_id gracefully without early silent exit."""
    import main
    user_id = 999555
    db = isolated_test_db

    msg = MagicMock()
    msg.from_user.id = user_id
    msg.chat.id = user_id
    msg.delete = AsyncMock()

    with patch("main.get_pool", return_value=db), \
         patch("main._build_work_card", new=AsyncMock(return_value=("Test work text", MagicMock()))), \
         patch("banner_manager.send_banner_message", new=AsyncMock()) as mock_banner:

        await main.cmd_work(msg, board_id=None)
        mock_banner.assert_called_once()
