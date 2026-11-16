# -*- coding: utf-8 -*-
import pytest
import time
from unittest import mock
import asyncio

import shared_state
from common.spam_filter import (
    is_actual_keysmash_or_gibberish,
    check_short_gibberish_flood,
    check_flood,
    is_bayan,
    check_bayan,
    prune_stale_spam_filter_state,
    reset_short_gibberish_tracker,
    evaluate_message_for_autoshadowmute,
    _short_gibberish_tracker,
    _bayan_tracker,
    _bayan_mute_count,
    _bayan_mute_last_ts,
    _user_request_timestamps,
)
from common.database import update_shadow_mute, is_shadow_muted, get_shadow_mute_info
from handlers.message_router import _last_shadow_echo_ts, handle_message, _is_user_shadow_muted_early


@pytest.fixture(autouse=True)
def clean_spam_state():
    reset_short_gibberish_tracker()
    _bayan_tracker.clear()
    _bayan_mute_count.clear()
    _bayan_mute_last_ts.clear()
    _user_request_timestamps.clear()
    _last_shadow_echo_ts.clear()
    shared_state.shadow_fake_post_counters.clear()
    yield
    reset_short_gibberish_tracker()
    _bayan_tracker.clear()
    _bayan_mute_count.clear()
    _bayan_mute_last_ts.clear()
    _user_request_timestamps.clear()
    _last_shadow_echo_ts.clear()
    shared_state.shadow_fake_post_counters.clear()


# ============================================================================
# 1. FALSE POSITIVES AUDIT: LAUGHING & SHORT RUSSIAN PHRASES
# ============================================================================

def test_laughing_words_not_keysmash():
    """
    Verifies that various natural laughing words are NEVER misclassified as keysmash:
    - 'ахахаха', 'пхаха', 'пхахаха', 'ахахахаха'
    - 'лоооол', 'лооооол' (elongated vowels)
    - 'хддд', 'хдд', 'xd', 'xddd' (laughter emoticon / slang)
    - 'ыыыы', 'ыыы' (Russian chuckling)
    - 'кеееек', 'кек'
    """
    laughing_samples = [
        "ахахаха",
        "пхаха",
        "пхахаха",
        "ахахахаха",
        "лоооол",
        "лооооол",
        "хддд",
        "хдд",
        "xd",
        "xdd",
        "xddd",
        "ыыыы",
        "ыыы",
        "ыыыыы",
        "кеееек",
        "кек",
        "хехехе",
        "хыхыхы",
    ]
    for laugh in laughing_samples:
        assert is_actual_keysmash_or_gibberish(laugh) is False, (
            f"Laughing phrase '{laugh}' was falsely misclassified as keysmash!"
        )


def test_common_short_russian_phrases_not_keysmash():
    """
    Verifies that common short conversational phrases are NEVER misclassified as keysmash:
    - 'да', 'нет', 'го', 'го в доту', 'че', 'где', 'кто'
    - 'даааа', 'неееет', 'мдаааа' (natural elongated vowels)
    - 'чо', 'што', 'ща', 'щас', 'лан', 'пон', 'жиза', 'база', 'кринж', 'рофл'
    """
    common_phrases = [
        "да",
        "нет",
        "го",
        "го в доту",
        "че",
        "где",
        "кто",
        "чо",
        "што",
        "ща",
        "щас",
        "лан",
        "пон",
        "жиза",
        "база",
        "кринж",
        "рофл",
        "даааа",
        "неееет",
        "мдаааа",
    ]
    for phrase in common_phrases:
        assert is_actual_keysmash_or_gibberish(phrase) is False, (
            f"Common Russian phrase '{phrase}' was falsely misclassified as keysmash!"
        )


def test_real_keysmash_is_accurately_detected():
    """
    Verifies that true keysmashes and consonant gibberish ARE correctly flagged:
    - Home row smashes: 'asdfgh', 'фывпрлдж', 'zxcvbnm', 'fghj'
    - Keyboard walks & consonant floods: 'fhgx', 'jkl', 'fgh fgh', 'ываыва'
    - Repetitions: 'aaaa', 'фффф', '))))', '1111'
    """
    real_keysmashes = [
        "asdfgh",
        "фывпрлдж",
        "fgh fgh",
        "fhgx",
        "jkl",
        "фывпр",
        "asdasd",
        "fghfgh",
        "ываыва",
        "aaaa",
        "фффф",
        "qwerqwer",
        "zxcvbnm",
        "sdfghjk",
        "))))",
        "1111",
    ]
    for smash in real_keysmashes:
        assert is_actual_keysmash_or_gibberish(smash) is True, (
            f"Real keysmash '{smash}' failed to be detected!"
        )


def test_rapid_laughing_does_not_trigger_gibberish_flood():
    """
    A user sending 3 laughing messages in rapid succession (<= 2 seconds)
    must NEVER trigger check_short_gibberish_flood.
    """
    user_id = 77001
    base_ts = 1000.0

    is_fl1, _, _ = check_short_gibberish_flood(user_id, "лоооол", now_ts=base_ts, posts_count=10)
    is_fl2, _, _ = check_short_gibberish_flood(user_id, "хддд", now_ts=base_ts + 0.5, posts_count=10)
    is_fl3, reason3, _ = check_short_gibberish_flood(user_id, "ыыыы", now_ts=base_ts + 1.0, posts_count=10)

    assert not is_fl1
    assert not is_fl2
    assert not is_fl3, f"Rapid laughing falsely triggered keysmash flood: {reason3}"


# ============================================================================
# 2. KEYSMASH FLOOD SCOPE: SINGLE BOARD VS 28 BOARD MUTES
# ============================================================================

@pytest.mark.asyncio
async def test_keysmash_flood_mutes_only_target_board():
    """
    Verifies that when keysmash flood triggers on /b/, it applies a shadowmute
    ONLY to board 'b', and does NOT mute the user across all 27 boards.
    """
    user_id = 77002
    target_board = "b"
    other_board = "po"
    base_ts = time.time()

    # Ensure shared_state has boards initialized in RAM
    for b in shared_state.BOARDS:
        shared_state.board_data.setdefault(b, {})['shadow_mutes'] = {}
    shared_state.board_data.setdefault('ALL', {})['shadow_mutes'] = {}

    mock_db = mock.AsyncMock()
    mock_db.execute = mock.AsyncMock()

    # Mock DB apply_shadow_mute to update board_data in RAM
    async def mock_apply_shadow_mute(uid, bid, duration_seconds=1200.0, reason="", is_exponential=False):
        await update_shadow_mute(uid, bid, expires_at=base_ts + duration_seconds, reason=reason)
        return base_ts + duration_seconds

    with mock.patch("common.database.apply_shadow_mute", side_effect=mock_apply_shadow_mute), \
         mock.patch("common.db_pool.get_pool", mock.AsyncMock(return_value=mock_db)), \
         mock.patch("common.database.get_pool", mock.AsyncMock(return_value=mock_db)):
        # 3 rapid keysmashes on /b/
        for i in range(2):
            await evaluate_message_for_autoshadowmute(
                user_id=user_id,
                board_id=target_board,
                content="asdfgh",
                msg_type="text",
                raw_content_type="text",
                now_ts=base_ts + (i * 0.5),
                posts_count=10
            )

        should_mute, reason, exp = await evaluate_message_for_autoshadowmute(
            user_id=user_id,
            board_id=target_board,
            content="asdfgh",
            msg_type="text",
            raw_content_type="text",
            now_ts=base_ts + 1.0,
            posts_count=10
        )

        assert should_mute is True, "3rd keysmash must trigger shadow mute!"
        assert "keysmash" in reason.lower()
        assert exp > base_ts

        # Verify RAM mute scope:
        # Target board /b/ must be muted
        assert user_id in shared_state.board_data[target_board]['shadow_mutes']
        # Other boards (e.g. /po/, /a/, /sex/) must NOT be muted!
        assert user_id not in shared_state.board_data[other_board]['shadow_mutes']
        assert user_id not in shared_state.board_data['ALL']['shadow_mutes']


@pytest.mark.asyncio
async def test_why_all_board_mute_triggers_28_entries():
    """
    Demonstrates and verifies WHY board_id='ALL' creates exactly 28 shadow mutes in RAM:
    27 individual boards in shared_state.BOARDS + 1 entry in 'ALL' = 28 total entries.
    """
    user_id = 77003
    base_ts = time.time()

    for b in shared_state.BOARDS:
        shared_state.board_data.setdefault(b, {})['shadow_mutes'] = {}
    shared_state.board_data.setdefault('ALL', {})['shadow_mutes'] = {}

    mock_db = mock.AsyncMock()
    mock_db.execute = mock.AsyncMock()

    # When global ban is called with board_id='ALL'
    with mock.patch("common.db_pool.get_pool", mock.AsyncMock(return_value=mock_db)), \
         mock.patch("common.database.get_pool", mock.AsyncMock(return_value=mock_db)):
        await update_shadow_mute(user_id, 'ALL', expires_at=base_ts + 3600.0, reason="test global ban")

    # Count entries across all boards
    muted_boards = [
        b for b in shared_state.BOARDS
        if user_id in shared_state.board_data[b].get('shadow_mutes', {})
    ]
    # Exactly all 27 individual boards
    assert len(muted_boards) == 27
    assert len(shared_state.BOARDS) == 27

    # Plus 1 entry in 'ALL'
    assert user_id in shared_state.board_data['ALL'].get('shadow_mutes', {})
    total_ram_mutes = len(muted_boards) + (1 if user_id in shared_state.board_data['ALL']['shadow_mutes'] else 0)
    assert total_ram_mutes == 28, f"Expected exactly 28 shadow mutes in RAM, got {total_ram_mutes}"


# ============================================================================
# 3. MEMORY LEAKS AUDIT & BOUNDED TRACKERS
# ============================================================================

def test_is_bayan_does_not_leak_empty_deques():
    """
    Calling is_bayan on benign users must NOT allocate empty deques in _bayan_tracker.
    Previously, defaultdict access `_bayan_tracker[user_id]` allocated deques for every message.
    """
    initial_tracked = len(_bayan_tracker)

    for uid in range(80000, 80500):
        is_by, _ = is_bayan(user_id=uid, board_id="b", content=f"Hello world unique text {uid}", msg_type="text")
        assert not is_by

    # _bayan_tracker must NOT have 500 empty deques!
    assert len(_bayan_tracker) == initial_tracked, (
        f"is_bayan leaked {len(_bayan_tracker) - initial_tracked} empty deques into _bayan_tracker!"
    )


def test_short_gibberish_tracker_pops_on_mute_and_caps():
    """
    1. When check_short_gibberish_flood triggers a mute, the user must be popped
       from _short_gibberish_tracker rather than leaving an empty deque.
    2. Tracker enforces a capacity ceiling (capped at 5000 users).
    """
    spammer_id = 81001
    base_ts = 4000.0

    # 1. Trigger keysmash mute
    check_short_gibberish_flood(spammer_id, "asdf", now_ts=base_ts, posts_count=0)
    check_short_gibberish_flood(spammer_id, "asdf", now_ts=base_ts + 0.5, posts_count=0)
    is_fl, _, _ = check_short_gibberish_flood(spammer_id, "asdf", now_ts=base_ts + 1.0, posts_count=0)
    assert is_fl is True

    # After mute, spammer_id must NOT remain as an empty deque in _short_gibberish_tracker
    assert spammer_id not in _short_gibberish_tracker, (
        "Muted user was left as an empty deque in _short_gibberish_tracker!"
    )

    # 2. Capacity test: populate > 5000 entries
    for uid in range(1, 5100):
        _short_gibberish_tracker[uid].append(base_ts)

    # Calling check_short_gibberish_flood triggers capacity trim
    check_short_gibberish_flood(99999, "asdf", now_ts=base_ts, posts_count=0)
    assert len(_short_gibberish_tracker) <= 5000, (
        f"_short_gibberish_tracker exceeded 5000 cap: {len(_short_gibberish_tracker)}"
    )


def test_prune_stale_spam_filter_state_cleans_orphaned_bayan_counts():
    """
    prune_stale_spam_filter_state must prune orphaned user IDs from _bayan_mute_count
    that have count <= 0 or are not in _bayan_mute_last_ts.
    """
    orphan_uid = 82001
    active_uid = 82002
    now = 5000.0

    _bayan_mute_count[orphan_uid] = 0
    _bayan_mute_count[active_uid] = 2
    _bayan_mute_last_ts[active_uid] = now  # active

    pruned = prune_stale_spam_filter_state(now_ts=now)
    assert orphan_uid not in _bayan_mute_count, "Orphaned user ID was not pruned from _bayan_mute_count!"
    assert active_uid in _bayan_mute_count


# ============================================================================
# 4. SHADOW EARLY DROP AUDIT: RESILIENCE & CLEAN RESOURCES
# ============================================================================

@pytest.mark.asyncio
async def test_shadow_early_drop_null_from_user_safety():
    """
    Verifies handle_message gracefully drops messages where message.from_user is None
    (e.g. channel posts or system updates) without raising AttributeError.
    """
    mock_msg = mock.AsyncMock()
    mock_msg.from_user = None
    mock_msg.text = "channel post"
    mock_msg.caption = None
    mock_msg.content_type = "text"
    mock_msg.chat.id = 12345
    mock_msg.bot.id = 999

    # Must return cleanly without exception
    res = await handle_message(mock_msg, board_id="b", stream="ru")
    assert res is None


@pytest.mark.asyncio
async def test_last_shadow_echo_ts_bounded():
    """
    Verifies that _last_shadow_echo_ts does not grow unbounded when early shadow drop triggers.
    """
    now = time.time()
    for uid in range(1, 5100):
        _last_shadow_echo_ts[uid] = now - 400.0  # stale (> 300s)

    mock_msg = mock.AsyncMock()
    mock_msg.from_user.id = 99999
    mock_msg.text = "test early drop text"
    mock_msg.caption = None
    mock_msg.content_type = "text"
    mock_msg.chat.id = 12345
    mock_msg.bot.id = 999
    mock_msg.message_id = 54321

    with mock.patch("handlers.message_router._is_user_shadow_muted_early", mock.AsyncMock(return_value=True)), \
         mock.patch("handlers.message_router.process_shadow_reject", mock.AsyncMock()):
        await handle_message(mock_msg, board_id="b", stream="ru")

    assert len(_last_shadow_echo_ts) <= 5000, (
        f"_last_shadow_echo_ts exceeded capacity: {len(_last_shadow_echo_ts)}"
    )
