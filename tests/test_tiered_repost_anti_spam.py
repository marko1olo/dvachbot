# -*- coding: utf-8 -*-
"""
Tests for Tiered Repost Anti-Spam:
- Tier scaling (newbie=4, anon=6, veteran=8, oldfag=10, ancient=12)
- Warning-first policy for regular anons (no immediate shadowmute on first infraction)
- Persistent spam mitigation (short 120s shadowmute upon continuous spam)
- Total shadowmute immunity for oldfags / ancient veterans
- Per-board isolation (reposts on board 'b' do not affect board 'po')
- Media group / album deduplication
"""
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from common.spam_filter import (
    check_repost_spam,
    check_repost_spam_async,
    reset_repost_tracker,
    is_repost_from_public,
    REPOST_FLOOD_RESPONSES,
    REPOST_FLOOD_MUTE_SEC,
)


@pytest.fixture(autouse=True)
def clean_repost_state():
    reset_repost_tracker()
    yield
    reset_repost_tracker()


def make_mock_channel_forward(media_group_id=None):
    msg = MagicMock()
    msg.forward_origin = MagicMock()
    msg.forward_origin.type = "channel"
    msg.forward_from_chat = MagicMock(type="channel")
    msg.media_group_id = media_group_id
    msg.bot = MagicMock(id=999999)
    return msg


@pytest.mark.asyncio
async def test_newbie_repost_limit_and_immediate_spambot_containment():
    """Newbies (< 20 posts) have a limit of 4. 5th is blocked with immediate containment."""
    user_id = 111100
    base_ts = 1000000.0
    mock_msg = make_mock_channel_forward()

    with patch('common.spam_filter.apply_shadow_mute', new=AsyncMock(return_value=base_ts + 120.0)), \
         patch('common.database.apply_shadow_mute', new=AsyncMock(return_value=base_ts + 120.0)):
        # 1 to 4: allowed
        for i in range(4):
            is_blocked, resp = check_repost_spam(
                user_id=user_id,
                message=mock_msg,
                board_id="b",
                now_ts=base_ts + i * 5.0,
                posts_count=0
            )
            assert not is_blocked
            assert resp == ""

        # 5th: blocked and muted immediately for newbie spambot
        is_blocked, resp, exp = await check_repost_spam_async(
            user_id=user_id,
            message=mock_msg,
            board_id="b",
            now_ts=base_ts + 25.0,
            auto_apply_mute=True,
            posts_count=0
        )
        assert is_blocked
        assert resp in REPOST_FLOOD_RESPONSES
        assert exp >= base_ts + 119.0


@pytest.mark.asyncio
async def test_anon_tier_higher_limit_and_warning_first_no_mute():
    """
    Active Anon (e.g. 50 posts) has limit of 6.
    1st to 6th pass.
    7th is blocked and warned, but NOT shadowmuted!
    8th is blocked and warned, but NOT shadowmuted!
    9th (persistent spam) triggers 120s shadowmute.
    """
    user_id = 222200
    base_ts = 1000000.0
    mock_msg = make_mock_channel_forward()

    with patch('common.spam_filter.apply_shadow_mute', new=AsyncMock(return_value=base_ts + 120.0)) as mock_mute, \
         patch('common.database.apply_shadow_mute', new=AsyncMock(return_value=base_ts + 120.0)):
        # 1 to 6: allowed
        for i in range(6):
            is_blocked, resp = check_repost_spam(
                user_id=user_id,
                message=mock_msg,
                board_id="b",
                now_ts=base_ts + i * 5.0,
                posts_count=50
            )
            assert not is_blocked

        # 7th repost (first block): BLOCKED, BUT NO SHADOWMUTE!
        is_blocked, resp, exp = await check_repost_spam_async(
            user_id=user_id,
            message=mock_msg,
            board_id="b",
            now_ts=base_ts + 32.0,
            auto_apply_mute=True,
            posts_count=50
        )
        assert is_blocked
        assert resp in REPOST_FLOOD_RESPONSES
        assert exp == 0.0  # NO MUTE!
        mock_mute.assert_not_called()

        # 8th repost: BLOCKED, STILL NO SHADOWMUTE
        is_blocked, resp, exp = await check_repost_spam_async(
            user_id=user_id,
            message=mock_msg,
            board_id="b",
            now_ts=base_ts + 35.0,
            auto_apply_mute=True,
            posts_count=50
        )
        assert is_blocked
        assert exp == 0.0
        mock_mute.assert_not_called()

        # 9th repost (persistent spam): BLOCKED AND SHORT SHADOWMUTE (120s)
        is_blocked, resp, exp = await check_repost_spam_async(
            user_id=user_id,
            message=mock_msg,
            board_id="b",
            now_ts=base_ts + 38.0,
            auto_apply_mute=True,
            posts_count=50
        )
        assert is_blocked
        assert exp >= base_ts + 119.0
        mock_mute.assert_awaited_once()


@pytest.mark.asyncio
async def test_oldfag_immunity_from_shadowmutes():
    """
    Oldfags (> 500 posts) have limit of 10.
    Excess reposts are simply blocked/dropped, but NEVER shadowmuted.
    """
    user_id = 333300
    base_ts = 1000000.0
    mock_msg = make_mock_channel_forward()

    with patch('common.spam_filter.apply_shadow_mute', new=AsyncMock()) as mock_mute, \
         patch('common.database.apply_shadow_mute', new=AsyncMock()):
        # 1 to 10: allowed
        for i in range(10):
            is_blocked, _ = check_repost_spam(
                user_id=user_id,
                message=mock_msg,
                board_id="b",
                now_ts=base_ts + i * 2.0,
                posts_count=800
            )
            assert not is_blocked

        # 11th through 16th reposts: BLOCKED, but NEVER muted
        for i in range(11, 17):
            is_blocked, resp, exp = await check_repost_spam_async(
                user_id=user_id,
                message=mock_msg,
                board_id="b",
                now_ts=base_ts + 20.0 + i,
                auto_apply_mute=True,
                posts_count=800
            )
            assert is_blocked
            assert exp == 0.0

        mock_mute.assert_not_called()


@pytest.mark.asyncio
async def test_per_board_repost_isolation():
    """
    Reposts on board 'b' do not count towards reposts on board 'po'.
    A user posting 3 reposts on /b/ and 3 on /po/ stays within limits on both boards.
    """
    user_id = 444400
    base_ts = 1000000.0
    mock_msg = make_mock_channel_forward()

    # 3 reposts on /b/
    for i in range(3):
        is_blocked, _ = check_repost_spam(
            user_id=user_id,
            message=mock_msg,
            board_id="b",
            now_ts=base_ts + i * 5.0,
            posts_count=0  # Newbie limit = 4
        )
        assert not is_blocked

    # 3 reposts on /po/
    for i in range(3):
        is_blocked, _ = check_repost_spam(
            user_id=user_id,
            message=mock_msg,
            board_id="po",
            now_ts=base_ts + 20.0 + i * 5.0,
            posts_count=0  # Newbie limit = 4
        )
        assert not is_blocked

    # 4th repost on /b/ is still allowed (4th in /b/ bucket)
    is_blocked, _ = check_repost_spam(
        user_id=user_id,
        message=mock_msg,
        board_id="b",
        now_ts=base_ts + 40.0,
        posts_count=0
    )
    assert not is_blocked

    # 5th repost on /b/ triggers block on /b/
    is_blocked, resp = check_repost_spam(
        user_id=user_id,
        message=mock_msg,
        board_id="b",
        now_ts=base_ts + 45.0,
        posts_count=0
    )
    assert is_blocked


@pytest.mark.asyncio
async def test_sex_board_is_exempt_from_repost_limits():
    """Board /sex/ has zero repost restrictions (users forward media/erotica content)."""
    user_id = 999123
    base_ts = 2000000.0
    mock_msg = make_mock_channel_forward()

    # User posts 20 reposts in 30 seconds on /sex/ -> ALL allowed
    for i in range(20):
        is_blocked, resp = check_repost_spam(
            user_id=user_id,
            message=mock_msg,
            board_id="sex",
            now_ts=base_ts + i * 1.5,
            posts_count=0  # Newbie!
        )
        assert not is_blocked
        assert resp == ""

    # Async check also completely exempt
    is_blocked, resp, exp = await check_repost_spam_async(
        user_id=user_id,
        message=mock_msg,
        board_id="sex",
        now_ts=base_ts + 50.0,
        posts_count=0
    )
    assert not is_blocked
    assert resp == ""
    assert exp == 0.0

