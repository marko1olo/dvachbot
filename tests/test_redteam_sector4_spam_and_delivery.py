# -*- coding: utf-8 -*-
"""
Red-team inquisition tests for Sector 4:
- Token Pool (Round-Robin, Cooldown, Unban, Load Env, Key Normalization)
- Spam Filter (Cross-Board Spam bypass fix, Memory leak pruning in trackers, Tuple repost keys reset, KeyError resilience)
- Broadcaster (401 Unauthorized FATAL_ERROR_STOP, Real-time Circuit Breaker)
- Delivery Manager (Durable queue post_num validation, Cumulative metrics bounded pruning)
"""
import pytest
import time
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from collections import deque, defaultdict
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from common.token_pool import TokenRotator, _clean_and_dedup_keys, _load_env_keys
from common.spam_filter import (
    _check_cross_board_spam,
    cross_board_spam_tracker,
    _spam_trackers,
    _user_repost_timestamps,
    _seen_repost_media_groups,
    _user_posts_count_cache,
    set_cached_user_posts,
    prune_stale_spam_filter_state,
    apply_shadow_mute,
    _check_repeats,
    reset_repost_tracker,
)
from delivery_manager import (
    _queue_item_can_be_durable,
    cumulative_post_metrics,
    prune_stale_cumulative_post_metrics,
)
from broadcaster import MessageBroadcaster
import shared_state


# ============================================================================
# 1. TOKEN ROTATOR TESTS
# ============================================================================

def test_token_rotator_unban_and_clean():
    rotator = TokenRotator(" tok1 , 'tok2' , \"tok3\" ")
    assert rotator.tokens == ["tok1", "tok2", "tok3"]

    # Ban tok2
    rotator.ban_token("tok2")
    assert "tok2" not in rotator.tokens
    assert "tok2" in rotator.get_banned_tokens()
    assert rotator.get_token() in ["tok1", "tok3"]

    # Unban tok2
    assert rotator.unban_token("tok2") is True
    assert "tok2" not in rotator.get_banned_tokens()
    assert "tok2" in rotator.tokens

    # set_tokens explicitly unbans tokens present in the new set
    rotator.ban_token("tok1")
    assert "tok1" in rotator.get_banned_tokens()
    rotator.set_tokens(["tok1", "tok4"])
    assert "tok1" not in rotator.get_banned_tokens()
    assert rotator.tokens == ["tok1", "tok4"]


def test_token_rotator_penalize_and_sorted_cooling():
    rotator = TokenRotator(["t1", "t2", "t3"])
    now = time.time()
    # Penalize t1 for 100s, t2 for 20s
    rotator.penalize_token("t1", 100.0)
    rotator.penalize_token("t2", 20.0)

    # get_all_active_tokens should have ready (t3) first, then cooling sorted by remaining time (t2, then t1)
    all_toks = rotator.get_all_active_tokens()
    assert all_toks[0] == "t3"
    assert all_toks[1] == "t2"  # expires earlier than t1
    assert all_toks[2] == "t1"

    # When all are cooling
    rotator.penalize_token("t3", 10.0)
    all_cooling = rotator.get_all_active_tokens()
    assert all_cooling[0] == "t3"  # 10s
    assert all_cooling[1] == "t2"  # 20s
    assert all_cooling[2] == "t1"  # 100s


def test_clean_and_dedup_keys_multiline_and_env():
    raw = "key1, key2\nkey3;\r\nkey4, #comment\n'key5'"
    res = _clean_and_dedup_keys(raw)
    assert res == ["key1", "key2", "key3", "key4", "key5"]


# ============================================================================
# 2. SPAM FILTER TESTS
# ============================================================================

def test_cross_board_spam_detection_after_prior_benign_history():
    """
    Redteam vulnerability test:
    Verify cross-board spam is detected even when the user previously posted benign messages.
    """
    cross_board_spam_tracker.clear()
    uid = 888123
    t0 = 1000000.0

    # User posts 2 benign messages on different boards
    assert _check_cross_board_spam(uid, "b", "Benign message 1 on /b/", "text", "text", now_ts=t0)
    assert _check_cross_board_spam(uid, "po", "Benign message 2 on /po/", "text", "text", now_ts=t0 + 5.0)

    # Spammer starts flooding identical spam across boards
    spam_text = "BUY CHEAP CRYPTO AIRDROP NOW AT HTTPS://SCAM.EXAMPLE.COM"
    assert _check_cross_board_spam(uid, "b", spam_text, "text", "text", now_ts=t0 + 10.0)
    assert _check_cross_board_spam(uid, "po", spam_text, "text", "text", now_ts=t0 + 15.0)

    # 3rd identical spam post on a 3rd board (/soc/) MUST be blocked!
    is_allowed = _check_cross_board_spam(uid, "soc", spam_text, "text", "text", now_ts=t0 + 20.0)
    assert not is_allowed, "Vulnerability: Cross-board spam was NOT caught due to older benign history!"


def test_spam_filter_prune_trackers_and_cache_bounds():
    now = time.time()
    # 1. Populate _spam_trackers with stale timestamps
    _spam_trackers["b"][99901] = [now - 120.0, now - 90.0]
    _spam_trackers["b"][99902] = [now - 5.0]  # active

    # 2. Populate cross_board_spam_tracker with stale deque
    cross_board_spam_tracker[99901].append((now - 150.0, "b", "old text"))

    # 3. Populate _user_posts_count_cache
    for i in range(5050):
        set_cached_user_posts(100000 + i, i)
    assert len(_user_posts_count_cache) <= 5000

    # Prune
    pruned = prune_stale_spam_filter_state(now_ts=now)
    assert 99901 not in _spam_trackers["b"]
    assert 99902 in _spam_trackers["b"]
    assert 99901 not in cross_board_spam_tracker
    assert pruned["_spam_trackers"] >= 1
    assert pruned["cross_board_spam_tracker"] >= 1


@pytest.mark.asyncio
async def test_apply_shadow_mute_cleans_tuple_repost_trackers():
    uid = 777001
    board_id = "b"
    _user_repost_timestamps[(uid, board_id)].append(time.time())
    _seen_repost_media_groups[(uid, board_id)]["mg1"] = {"first_ts": time.time()}
    cross_board_spam_tracker[uid].append((time.time(), "b", "spam"))
    _spam_trackers[board_id][uid].append(time.time())

    with patch('common.spam_filter._orig_db_apply_shadow_mute', new=AsyncMock(return_value=1200.0)), \
         patch('common.database.get_shadow_mute_info', new=AsyncMock(return_value={'is_muted': False})):
        await apply_shadow_mute(uid, board_id, duration_seconds=1200.0, reason="test")

    # Verifications: all trackers for this user must be completely cleared
    assert (uid, board_id) not in _user_repost_timestamps
    assert uid not in _user_repost_timestamps
    assert (uid, board_id) not in _seen_repost_media_groups
    assert uid not in cross_board_spam_tracker
    assert uid not in _spam_trackers[board_id]


def test_check_repeats_keyerror_resilience():
    empty_bdata = {}
    violations = {'level': 0}
    # Should not raise KeyError: 'last_texts'
    res = _check_repeats(
        user_id=123,
        b_data=empty_bdata,
        msg_info=("Some text", "text"),
        rules={'max_repeats': 3, 'min_length': 4},
        violations=violations,
        posts_count=0
    )
    assert res is True
    assert 'last_texts' in empty_bdata


# ============================================================================
# 3. BROADCASTER CIRCUIT BREAKER & FATAL ERROR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_broadcaster_unauthorized_token_stops_immediately():
    """
    401 Unauthorized must halt the broadcast queue immediately via FATAL_ERROR_STOP
    instead of spamming hundreds of useless API calls across subsequent chunks.
    """
    mock_bot = MagicMock()
    # Simulate 401 Unauthorized from Telegram Bot API
    mock_bot.send_message = AsyncMock(
        side_effect=TelegramBadRequest(method="sendMessage", message="Unauthorized: bot token is invalid")
    )
    mock_bot.token = "123456:FAKE_TOKEN"

    # 100 recipients (multiple chunks of 25)
    recipients = {1000 + i for i in range(100)}
    config = shared_state.BroadcastConfig(
        bot_instance=mock_bot,
        board_id="b",
        recipients=recipients,
        content={"type": "text", "text": "Test message", "header": "Test Header", "post_num": 12345},
        verbose=False
    )

    broadcaster = MessageBroadcaster(config)
    broadcaster.b_data = {"users": {"active": set(recipients), "banned": set()}, "user_settings": {}}

    results = await broadcaster.broadcast()
    # It must stop after first chunk (25), not continue through all 100 recipients
    assert mock_bot.send_message.call_count <= 25
    assert mock_bot.send_message.call_count < len(recipients)
    assert broadcaster.stats['errors'] > 0


@pytest.mark.asyncio
async def test_broadcaster_realtime_circuit_breaker_halts_mass_blocks():
    """
    If blocks exceed the threshold in real time, the circuit breaker must trip mid-broadcast
    and halt remaining queue items to protect subscribers.
    """
    mock_bot = MagicMock()
    # Simulate 403 Forbidden (user blocked bot)
    mock_bot.send_message = AsyncMock(
        side_effect=TelegramForbiddenError(method="sendMessage", message="Forbidden: bot was blocked by the user")
    )
    mock_bot.token = "123456:VALID_TOKEN"

    # 100 recipients
    recipients = {2000 + i for i in range(100)}
    config = shared_state.BroadcastConfig(
        bot_instance=mock_bot,
        board_id="b",
        recipients=recipients,
        content={"type": "text", "text": "Hello", "header": "Header", "post_num": 55555},
        verbose=False
    )

    broadcaster = MessageBroadcaster(config)
    broadcaster.b_data = {"users": {"active": set(recipients), "banned": set()}, "user_settings": {}}

    # Patch BOARD_CONFIG token match
    with patch('common.board_config.BOARD_CONFIG', {'b': {'token': '123456:VALID_TOKEN'}}):
        results = await broadcaster.broadcast()

    # Active was 100, threshold is max(25, 10) = 25.
    # The queue must trip when blocked users reach 25, stopping well before 100 calls!
    assert mock_bot.send_message.call_count <= 40
    assert results.interrupted_reason == "circuit_breaker_tripped"


# ============================================================================
# 4. DELIVERY MANAGER TESTS
# ============================================================================

def test_queue_item_can_be_durable_validation():
    # Valid durable item
    valid_item = {
        "delivery_phase": "passive",
        "post_num": 12345,
        "content": {"type": "text", "text": "Hello"},
        "recipients": [101, 102],
    }
    with patch('shared_state.DURABLE_DELIVERY_QUEUE_ENABLED', True):
        assert _queue_item_can_be_durable(valid_item) is True

        # Non-integer string post_num
        invalid_item = valid_item.copy()
        invalid_item["post_num"] = "not_an_int"
        assert _queue_item_can_be_durable(invalid_item) is False

        # None post_num
        invalid_item["post_num"] = None
        assert _queue_item_can_be_durable(invalid_item) is False

        # Zero post_num
        invalid_item["post_num"] = 0
        assert _queue_item_can_be_durable(invalid_item) is False


def test_cumulative_metrics_pruning():
    cumulative_post_metrics.clear()
    now = time.time()

    # Populate 600 metrics items, 100 old (> 3600s)
    for i in range(100):
        cumulative_post_metrics[("b", i)] = {
            'success': 1, 'priority': 1, 'passive': 0, 'errors': 0, 'blocks': 0,
            'start_time': now - 5000.0, 'total': 1
        }
    for i in range(100, 600):
        cumulative_post_metrics[("b", i)] = {
            'success': 1, 'priority': 1, 'passive': 0, 'errors': 0, 'blocks': 0,
            'start_time': now - 10.0, 'total': 1
        }

    assert len(cumulative_post_metrics) == 600
    prune_stale_cumulative_post_metrics(max_age_sec=3600.0, max_keep=500)
    assert len(cumulative_post_metrics) <= 500
    # The old ones must have been pruned
    assert ("b", 0) not in cumulative_post_metrics
