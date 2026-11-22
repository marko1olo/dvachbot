# -*- coding: utf-8 -*-
"""
tests/test_reaction_mimicry_economy.py — Comprehensive Unit & Integration tests
for reaction mimicry economy, anti-exploit limits, soft overdraft protection,
and bank/work resilience.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from handlers.message_router import (
    apply_mimic_reaction_to_post,
    _daily_mimic_author_rewards,
    MAX_MIMIC_PAID_REACTIONS_PER_DAY,
)
from shared_state import messages_storage, storage_lock
from common.work_engine import execute_job_action, get_user_daily_fatigue_info
from bank_engine import create_bank_deposit, calculate_deposit_state, withdraw_bank_deposit


@pytest.fixture(autouse=True)
def clean_mimic_economy_state():
    _daily_mimic_author_rewards.clear()
    messages_storage.clear()
    yield
    _daily_mimic_author_rewards.clear()
    messages_storage.clear()


def make_mock_db(balance: float = 0.0):
    """Creates a mock DB connection with clean async context manager for execute()."""
    mock_db = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone.return_value = (balance,)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_cursor
    mock_cm.__aexit__.return_value = None
    mock_db.execute = MagicMock(return_value=mock_cm)
    return mock_db


@pytest.mark.asyncio
async def test_mimic_like_awards_shekels_within_daily_limit():
    """Verify that a positive mimic reaction awards shekels when under daily limit."""
    author_id = 112233
    post_num = 1001
    post_data = {
        "author_id": author_id,
        "board_id": "b",
        "timestamp": time.time() - 100,
        "content": {"text": "Годный хентай тред", "type": "text"},
        "reactions": {"users": {}},
    }
    async with storage_lock:
        messages_storage[post_num] = post_data

    mock_db = make_mock_db(100.0)

    with patch("handlers.message_router.get_pool", return_value=mock_db), \
         patch("handlers.message_router.update_post_content", new_callable=AsyncMock):

        ok = await apply_mimic_reaction_to_post(
            post_num=post_num,
            virtual_user_id=770100001,
            emojis=["❤️", "🔥"],
            board_id="b"
        )

        assert ok is True
        assert len(_daily_mimic_author_rewards[author_id]) == 1
        # Check that db.execute was called to insert/update balance
        assert any("INSERT INTO Users" in str(call) for call in mock_db.execute.call_args_list)


@pytest.mark.asyncio
async def test_mimic_like_capped_at_daily_limit_no_extra_emission():
    """Verify that after 3 rewards in 24h, further mimic likes do NOT mint shekels."""
    author_id = 445566
    now = time.time()
    # Pre-fill 3 rewards (cap reached)
    _daily_mimic_author_rewards[author_id] = [now - 1000, now - 500, now - 100]

    post_num = 1002
    post_data = {
        "author_id": author_id,
        "board_id": "b",
        "timestamp": time.time() - 200,
        "content": {"text": "Четвертый пост для фарма", "type": "text"},
        "reactions": {"users": {}},
    }
    async with storage_lock:
        messages_storage[post_num] = post_data

    mock_db = make_mock_db(500.0)

    with patch("handlers.message_router.get_pool", return_value=mock_db), \
         patch("handlers.message_router.update_post_content", new_callable=AsyncMock):

        ok = await apply_mimic_reaction_to_post(
            post_num=post_num,
            virtual_user_id=770100002,
            emojis=["❤️"],
            board_id="b"
        )

        assert ok is True
        # Visual reaction IS applied
        assert post_data["reactions"]["users"][770100002] == ["❤️"]
        # Rewards count remains 3 (cap maintained)
        assert len(_daily_mimic_author_rewards[author_id]) == 3
        # DB balance update was NOT executed
        assert not any("INSERT INTO Users" in str(call) for call in mock_db.execute.call_args_list)


@pytest.mark.asyncio
async def test_mimic_dislike_soft_overdraft_protection_zero_balance():
    """Verify that mimic dislikes do not push a user with 0 balance into negative numbers."""
    author_id = 778899
    post_num = 1003
    post_data = {
        "author_id": author_id,
        "board_id": "b",
        "timestamp": time.time() - 150,
        "content": {"text": "Кринж нытье", "type": "text"},
        "reactions": {"users": {}},
    }
    async with storage_lock:
        messages_storage[post_num] = post_data

    mock_db = make_mock_db(0.0)

    with patch("handlers.message_router.get_pool", return_value=mock_db), \
         patch("handlers.message_router.update_post_content", new_callable=AsyncMock), \
         patch("handlers.message_router.deduct_user_global_balance", new_callable=AsyncMock) as mock_deduct:

        ok = await apply_mimic_reaction_to_post(
            post_num=post_num,
            virtual_user_id=770100003,
            emojis=["💩"],
            board_id="b"
        )

        assert ok is True
        # Reaction visually applied
        assert post_data["reactions"]["users"][770100003] == ["💩"]
        # Deduct was NOT called because balance was 0 (soft overdraft protection)
        mock_deduct.assert_not_called()


@pytest.mark.asyncio
async def test_mimic_dislike_partial_deduction_soft_overdraft():
    """Verify that when user has positive balance less than penalty, only current balance is deducted."""
    author_id = 334455
    post_num = 1004
    post_data = {
        "author_id": author_id,
        "board_id": "b",
        "timestamp": time.time() - 120,
        "content": {"text": "Шитпост", "type": "text"},
        "reactions": {"users": {}},
    }
    async with storage_lock:
        messages_storage[post_num] = post_data

    # User balance is 30 ₪ (penalty is 50..100 ₪)
    mock_db = make_mock_db(30.0)

    with patch("handlers.message_router.get_pool", return_value=mock_db), \
         patch("handlers.message_router.update_post_content", new_callable=AsyncMock), \
         patch("handlers.message_router.deduct_user_global_balance", new_callable=AsyncMock) as mock_deduct:

        ok = await apply_mimic_reaction_to_post(
            post_num=post_num,
            virtual_user_id=770100004,
            emojis=["🤮"],
            board_id="b"
        )

        assert ok is True
        # Deduct was called with at most 30 ₪
        assert mock_deduct.called
        deducted_amount = mock_deduct.call_args[0][3]
        assert deducted_amount <= 30.0
        assert deducted_amount > 0


@pytest.mark.asyncio
async def test_bank_zero_balance_deposit_handling(isolated_test_db):
    """Verify bank rejects deposit when user has zero balance cleanly without exception."""
    ok, dep, err = await create_bank_deposit(
        db=isolated_test_db,
        user_id=999999,
        board_id="b",
        tier_id="sych",
        amount=50.0
    )

    assert ok is False
    assert dep is None
    assert "Недостаточно шекелей" in err


@pytest.mark.asyncio
async def test_bank_deposit_state_calculation_zero_principal():
    """Verify calculate_deposit_state handles zero principal deposits safely."""
    raw_dep = {
        "id": 156,
        "user_id": 5536235634,
        "tier_id": "mmm_abu",
        "principal": 0.0,
        "daily_rate": 0.06,
        "created_at": 1789548142.0,
        "locked_until": 1789634542.0,
        "last_accrual_at": 1795309201.0,
        "accrued_interest": 4229189.75,
        "status": "active"
    }
    state = calculate_deposit_state(raw_dep, current_ts=1795309300.0)
    assert state["principal"] == 0.0
    assert state["accrued_interest"] == 4229189.75
    assert state["total_value"] == 4229189.75
    assert state["is_locked"] is False


def test_work_engine_fatigue_and_zero_balance_safety():
    """Verify work engine handles extreme fatigue gracefully and maintains minimum payout."""
    # Simulate a user who has worked 25 shifts in the last 24h (heavy fatigue)
    now = time.time()
    recent_shifts = [now - (i * 1800) for i in range(25)]
    fatigue_info = get_user_daily_fatigue_info(recent_shifts, now=now)

    assert fatigue_info["shifts_today"] == 25
    assert fatigue_info["efficiency_pct"] == 20  # 20% floor
    assert fatigue_info["recovery_sec"] > 0

    # Execute shift with high fatigue
    items = {
        "work_shifts": 50,
        "recent_shifts": recent_shifts,
        "work_cooldowns": {}
    }
    result = execute_job_action("bottles", items, user_id=123456)
    is_success, amount, msg, dropped = result
    if is_success:
        assert amount >= 1  # Minimum reward floor is always at least 1 ₪
        assert "Эффективность: 20%" in msg or "Усталость" in msg
