# -*- coding: utf-8 -*-
"""
Automated unit and integration tests for:
1. Casino News Filter (strictly >= 4.0x multiplier required).
2. Night Shift Multiplier (x1.5 payout between 00:00 and 07:00 MSK).
3. Expanded Side Hustles (bottles, dumpster, flyers, microloan, overtime).
4. Daily Work Quests Engine (generation, progress, Abu rewards).
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import common.daily_quests_engine as qe
from common.work_engine import is_night_shift_active, execute_job_action, WORK_VACANCIES
from news_channel_publisher import publish_casino_jackpot_news


# ==========================================
# 1. CASINO NEWS FILTER TESTS
# ==========================================

@pytest.mark.asyncio
async def test_casino_news_filter_rejects_sub_4x():
    """Verify that any casino win with multiplier < 4.0x is rejected from news."""
    mock_bot = AsyncMock()
    mock_bot.get_me.return_value = MagicMock(username="test_bot")

    with patch("news_channel_publisher.get_target_channels", return_value=(-100123456, -100123456)), \
         patch("news_channel_publisher.send_channel_content", new_callable=AsyncMock) as mock_send:

        # 1.8x win on massive bet (100k -> 180k) MUST BE REJECTED
        res1 = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=123, game_type="slots",
            bet_amount=100000, win_amount=180000, multiplier=1.8
        )
        assert res1 is False
        mock_send.assert_not_called()

        # 2.0x win MUST BE REJECTED
        res2 = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=123, game_type="slots",
            bet_amount=50000, win_amount=100000, multiplier=2.0
        )
        assert res2 is False
        mock_send.assert_not_called()

        # 3.99x win MUST BE REJECTED
        res3 = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=123, game_type="slots",
            bet_amount=10000, win_amount=39900, multiplier=3.99
        )
        assert res3 is False
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_casino_news_filter_accepts_4x_and_above():
    """Verify that casino wins with multiplier >= 4.0x are accepted and sent to news channel."""
    mock_bot = AsyncMock()
    mock_bot.get_me.return_value = MagicMock(username="test_bot")

    with patch("news_channel_publisher.get_target_channels", return_value=(-100123456, -100123456)), \
         patch("news_channel_publisher.send_channel_content", new_callable=AsyncMock, return_value=99999) as mock_send:

        # 4.0x win
        res = await publish_casino_jackpot_news(
            bot=mock_bot, user_id=123, game_type="slots",
            bet_amount=1000, win_amount=4000, multiplier=4.0, symbols="[🍋 | 🍋 | 🍋]"
        )
        assert res is True
        mock_send.assert_called_once()


# ==========================================
# 2. NIGHT SHIFT MULTIPLIER TESTS
# ==========================================

def test_night_shift_active_hours():
    """Night shift is active 00:00 to 07:00 MSK (UTC+3, which is 21:00 to 04:00 UTC)."""
    # 03:00 MSK (00:00 UTC) -> Active
    ts_night = 1788739200  # Exactly 00:00 UTC = 03:00 MSK
    assert is_night_shift_active(ts_night) is True

    # 15:00 MSK (12:00 UTC) -> Inactive
    ts_day = ts_night + 12 * 3600
    assert is_night_shift_active(ts_day) is False


def test_night_shift_payout_boost():
    """Verify that job payouts are boosted by 1.5x during night shift."""
    ts_night = 1788739200  # 03:00 MSK
    items = {"work_shifts": 10}

    with patch("time.time", return_value=ts_night):
        ok, reward, msg, drop = execute_job_action("bottles", items)
        assert ok is True
        assert "Ночной тариф x1.5" in msg
        # Bottles base range is (15, 30). With 1.5x, minimum possible is int(15*1.5) = 22
        assert reward >= 22


# ==========================================
# 3. DAILY WORK QUESTS TESTS
# ==========================================

def test_daily_quests_generation_and_rollover():
    """Verify daily quests generation, structure, and day rollover."""
    items = {}
    ts1 = 1788700000
    dq = qe.get_or_create_daily_quests(items, now=ts1)

    assert "date" in dq
    assert len(dq["quests"]) == 3
    assert dq["claimed"] is False
    assert dq["reward_cash"] == 7500

    # Simulate next day rollover
    ts2 = ts1 + 90000
    dq2 = qe.get_or_create_daily_quests(items, now=ts2)
    assert dq2["date"] != dq["date"]


def test_daily_quests_progress_and_reward_claim():
    """Verify progress tracking and reward claim with lootbox."""
    items = {}
    ts = 1788700000
    qe.get_or_create_daily_quests(items, now=ts)

    # Initial state: not completed
    assert qe.are_all_quests_completed(items, now=ts) is False
    ok, cash, msg, item = qe.claim_daily_quests_reward(items, now=ts)
    assert ok is False

    # Progress 1: work shifts (target=2)
    qe.record_quest_progress(items, "work", count=1, now=ts)
    assert qe.are_all_quests_completed(items, now=ts) is False
    qe.record_quest_progress(items, "work", count=1, now=ts)

    # Progress 2: side hustle (target=1)
    qe.record_quest_progress(items, "side_hustle", count=1, now=ts)

    # Progress 3: risk action (target=1)
    qe.record_quest_progress(items, "risk_action", count=1, now=ts)

    # Now all quests must be completed
    assert qe.are_all_quests_completed(items, now=ts) is True

    # Claim reward
    ok, cash, msg, item = qe.claim_daily_quests_reward(items, now=ts)
    assert ok is True
    assert cash == 7500
    assert item == "trash_lootbox"
    assert "ПРЕМИЯ ОТ АБУ ПОЛУЧЕНА" in msg

    # Second claim must be rejected
    ok2, _, _, _ = qe.claim_daily_quests_reward(items, now=ts)
    assert ok2 is False


def test_daily_quests_render():
    """Verify human-readable rendering of daily quests."""
    items = {}
    text, can_claim = qe.render_quests_text(items)
    assert "ЕЖЕДНЕВНЫЙ НАPЯД" in text.upper() or "НАРЯД" in text
    assert can_claim is False
