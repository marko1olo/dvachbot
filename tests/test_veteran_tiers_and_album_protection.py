# -*- coding: utf-8 -*-
import pytest
import time
from unittest import mock
from common.spam_filter import (
    get_user_tier,
    check_flood,
    record_shadow_mute_applied,
    is_in_mute_grace_period,
    _user_request_timestamps,
    _seen_media_groups,
    _shadow_mute_applied_ts,
    USER_TIERS,
)


@pytest.fixture(autouse=True)
def clean_spam_state():
    _user_request_timestamps.clear()
    _seen_media_groups.clear()
    _shadow_mute_applied_ts.clear()
    yield
    _user_request_timestamps.clear()
    _seen_media_groups.clear()
    _shadow_mute_applied_ts.clear()


def test_veteran_tiers_distribution():
    """Verify get_user_tier returns correct limits for each post tier."""
    # Newbie (< 20)
    t0 = get_user_tier(0)
    assert t0['burst_limit'] == 8
    assert t0['flood_base_mute_sec'] == 300.0

    t10 = get_user_tier(10)
    assert t10['burst_limit'] == 8

    # Anon (20..99)
    t25 = get_user_tier(25)
    assert t25['burst_limit'] == 10
    assert t25['flood_base_mute_sec'] == 240.0

    # Veteran (100..499, like kroleposter with 211 posts)
    t211 = get_user_tier(211)
    assert t211['burst_limit'] == 12
    assert t211['rate_limit'] == 22
    assert t211['minute_limit'] == 45
    assert t211['flood_base_mute_sec'] == 120.0

    # Oldfag (500..1999)
    t500 = get_user_tier(500)
    assert t500['burst_limit'] == 14
    assert t500['rate_limit'] == 26
    assert t500['minute_limit'] == 52
    assert t500['flood_base_mute_sec'] == 90.0

    # Ancient (>= 2000)
    t2500 = get_user_tier(2500)
    assert t2500['burst_limit'] == 16
    assert t2500['rate_limit'] == 30
    assert t2500['minute_limit'] == 60
    assert t2500['flood_base_mute_sec'] == 60.0


def test_kroleposter_batch_with_veteran_limits():
    """
    Kroleposter (posts_count=211) sends a batch of 12 videos.
    With veteran tier (burst=12) and media bonus (+6 = 18),
    all 12 videos MUST pass without triggering burst flood!
    """
    user_id = 400193164
    board_id = "sex"
    base_ts = time.time()

    for i in range(12):
        ts = base_ts + (i * 0.005)  # 5ms apart
        is_fl, reason = check_flood(
            user_id=user_id,
            board_id=board_id,
            now_ts=ts,
            posts_count=211,
            is_media=True
        )
        assert not is_fl, f"Video {i+1} falsely flagged: {reason}"


def test_album_media_group_deduplication():
    """
    An album of 10 photos/videos with the same media_group_id
    must only count the leader; all 9 subsequent items must bypass flood.
    """
    user_id = 999001
    board_id = "b"
    mg_id = "1357924680_album"
    base_ts = time.time()

    # Send 10 photos in album (all within 50ms)
    for i in range(10):
        ts = base_ts + (i * 0.005)
        is_fl, reason = check_flood(
            user_id=user_id,
            board_id=board_id,
            now_ts=ts,
            posts_count=0, # Even for a complete newbie!
            is_media=True,
            media_group_id=mg_id
        )
        assert not is_fl, f"Album element {i+1} flagged: {reason}"

    # Only 1 request recorded in timestamps
    assert len(_user_request_timestamps[user_id]) == 1


def test_mute_grace_period_prevents_compounding():
    """
    When shadow mute is applied, in-flight messages within 4 seconds
    are recognized as in grace period, preventing exponential compounding.
    """
    user_id = 400193164
    now = time.time()

    record_shadow_mute_applied(user_id, now_ts=now)

    # 100ms later (in-flight video) -> in grace period
    assert is_in_mute_grace_period(user_id, now_ts=now + 0.1)

    # 2.5s later -> still in grace period
    assert is_in_mute_grace_period(user_id, now_ts=now + 2.5)

    # 5.0s later -> grace period expired
    assert not is_in_mute_grace_period(user_id, now_ts=now + 5.0)


@pytest.mark.asyncio
async def test_apply_shadow_mute_downgrades_exponential_during_grace_period():
    """
    apply_shadow_mute must force is_exponential=False if within grace period.
    """
    import common.spam_filter
    user_id = 888111
    board_id = "b"
    now = time.time()

    # Initial mute
    record_shadow_mute_applied(user_id, now_ts=now)

    mock_db_mute = mock.AsyncMock(return_value=now + 1200.0)
    with mock.patch.object(common.spam_filter, "_orig_db_apply_shadow_mute", mock_db_mute):
        await common.spam_filter.apply_shadow_mute(user_id, board_id, duration_seconds=1200.0, is_exponential=True)
        
        # Verify is_exponential was downgraded to False
        mock_db_mute.assert_called_once()
        _, kwargs = mock_db_mute.call_args
        assert kwargs.get("is_exponential") is False
