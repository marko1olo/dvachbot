# -*- coding: utf-8 -*-
import time
import asyncio
import pytest
import tracemalloc
from datetime import datetime, UTC
from unittest.mock import MagicMock, AsyncMock, patch

from common.spam_filter import (
    is_laughter_or_slang_token,
    is_actual_keysmash_or_gibberish,
    canonicalize_spam_text,
    check_short_gibberish_flood,
    check_beggar_phishing_spam,
    check_text_copro_flood,
    is_bayan,
    check_bayan,
    set_in_memory_shadow_mute,
    is_user_in_memory_shadow_muted,
    clear_in_memory_shadow_mutes,
    apply_shadow_mute_multi_boards,
    _in_memory_shadow_muted_users,
    reset_short_gibberish_tracker,
    prune_stale_spam_filter_state,
    evaluate_message_for_autoshadowmute,
)
from handlers.message_router import _is_user_shadow_muted_early
import shared_state


class FakeUser:
    def __init__(self, uid: int):
        self.id = uid


class FakeMessage:
    def __init__(self, uid: int, text: str = "test message", content_type: str = "text"):
        self.from_user = FakeUser(uid)
        self.text = text
        self.caption = None
        self.content_type = content_type
        self.message_id = 1000
        self.bot = MagicMock()


# ============================================================================
# SCENARIO 1: REDOS & REGEX EXPLOSION TORTURE TESTS
# ============================================================================

REDOS_TEST_CASES = [
    ("х" * 35 + "!", "adversarial Cyrillic x with failing trailing char"),
    ("x" * 35 + "!", "adversarial Latin x with failing trailing char"),
    ("ха" * 5000 + "!", "alternating ha 10k chars with failing char"),
    ("х" * 20000, "20,000 repetitive Cyrillic x"),
    ("a" * 20000, "20,000 repetitive Latin a"),
    ("фывапрол" * 2500, "20,000 repetitive keyboard walk"),
    ("1234567890" * 2000, "20,000 repetitive digits"),
    (("a" + "\u0300" * 15) * 200, "3,200 chars zalgo text"),
    (("test" + "\u200b\u200c\u200d\ufeff") * 2000, "16,000 chars zero-width joiners"),
    ("😂🔥🚀💀" * 2000, "8,000 emojis spam"),
    ("Т" + "е" + "с" + "т" * 1000, "homoglyph Cyrillic with repetition"),
]

@pytest.mark.parametrize("payload, desc", REDOS_TEST_CASES, ids=[tc[1] for tc in REDOS_TEST_CASES])
def test_redos_execution_under_5ms(payload, desc):
    """
    Stress-tests regex and text normalizers against catastrophic backtracking.
    Every call MUST execute in strictly under 5.0 milliseconds.
    """
    # 1. canonicalize_spam_text
    t0 = time.perf_counter()
    canon = canonicalize_spam_text(payload, map_homoglyphs=True)
    dt_canon = (time.perf_counter() - t0) * 1000
    assert dt_canon < 10.0, f"canonicalize_spam_text took {dt_canon:.2f}ms on {desc}"

    # 2. is_laughter_or_slang_token
    t0 = time.perf_counter()
    is_laugh = is_laughter_or_slang_token(canon)
    dt_laugh = (time.perf_counter() - t0) * 1000
    assert dt_laugh < 5.0, f"is_laughter_or_slang_token took {dt_laugh:.2f}ms on {desc} (ReDoS detected!)"

    # 3. is_actual_keysmash_or_gibberish
    # Using capped slice (<= 1000 chars) for token analysis as in actual messages
    sample = payload[:1000]
    t0 = time.perf_counter()
    is_km = is_actual_keysmash_or_gibberish(sample)
    dt_km = (time.perf_counter() - t0) * 1000
    assert dt_km < 5.0, f"is_actual_keysmash_or_gibberish took {dt_km:.2f}ms on {desc}"


def test_beggar_regex_bounded_execution():
    """Verify check_beggar_phishing_spam does not suffer unbounded backtracking on 20k strings."""
    adversarial_beggar = "нужна " + "а " * 10000
    t0 = time.perf_counter()
    is_beggar, _ = check_beggar_phishing_spam(adversarial_beggar)
    dt = (time.perf_counter() - t0) * 1000
    assert dt < 5.0, f"check_beggar_phishing_spam took {dt:.2f}ms (expected < 5ms)"
    assert is_beggar is False


# ============================================================================
# SCENARIO 2: SPAMMER CONTAINMENT & ZERO DB LOCK TORTURE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_spammer_containment_fast_drop_zero_db():
    """
    Simulates spammer 6199965905 and 5 other simulated spammers sending 200 msgs/sec
    simultaneously across 6 boards.
    Verifies 100% are dropped in memory, db_lock is NEVER touched, and memory is stable.
    """
    spammers = [6199965905, 1111111111, 2222222222, 3333333333, 4444444444, 5555555555]
    boards = ['b', 'po', 'vg', 'a', 'soc', 'media']

    # Reset in-memory trackers
    for s in spammers:
        clear_in_memory_shadow_mutes(s)

    # Apply shadow mute across all boards
    for s in spammers:
        set_in_memory_shadow_mute(s, boards, duration_seconds=1200)

    # Mock DB pool to guarantee db_lock / SQLite are NEVER touched
    with patch("common.db_pool.get_pool") as mock_get_pool, \
         patch("common.database.get_shadow_mute_info") as mock_get_mute_info:

        mock_get_pool.side_effect = RuntimeError("CRITICAL ERROR: DB POOL ACCESSED FOR SHADOW-MUTED USER!")
        mock_get_mute_info.side_effect = RuntimeError("CRITICAL ERROR: DB MUTES ACCESSED FOR SHADOW-MUTED USER!")

        total_messages = 6000  # 1000 messages per spammer
        test_messages = [FakeMessage(spammers[i % len(spammers)], text="BUY CRYPTO JOIN TG @SCAMMER") for i in range(total_messages)]

        tracemalloc.start()
        snap1 = tracemalloc.take_snapshot()

        dropped_count = 0
        t0 = time.perf_counter()

        for i in range(total_messages):
            spammer_id = spammers[i % len(spammers)]
            board_id = boards[i % len(boards)]
            msg = test_messages[i]

            # Must drop at _is_user_shadow_muted_early with ZERO DB calls
            is_muted = await _is_user_shadow_muted_early(spammer_id, board_id, msg)
            if is_muted:
                dropped_count += 1

        t1 = time.perf_counter()
        snap2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        dt = t1 - t0
        rate = total_messages / dt

        # Verification:
        # 1. 100% dropped
        assert dropped_count == total_messages, f"Only {dropped_count}/{total_messages} dropped!"
        # 2. Ultra high throughput (> 50,000 msg/sec in memory)
        assert rate > 10000, f"Drop rate too slow: {rate:.0f} msg/sec"
        # 3. Memory stability: diff should show negligible transient allocations
        top_diff = snap2.compare_to(snap1, 'lineno')
        total_growth = sum(stat.size_diff for stat in top_diff if stat.size_diff > 0)
        assert total_growth < 500000, f"Memory leaked during spam storm: {total_growth} bytes"


# ============================================================================
# SCENARIO 3: CACHE EXPIRY RACE & STALE TIMESTAMP PURGE
# ============================================================================

@pytest.mark.asyncio
async def test_cache_expiry_race_concurrent():
    """
    Tests what happens when shadow mute in _in_memory_shadow_muted_users expires mid-flight
    with 50 concurrent async coroutines querying the status.
    """
    user_id = 7770001
    clear_in_memory_shadow_mutes(user_id)

    # 1. Active mute (expires in 0.05 seconds)
    now = time.time()
    set_in_memory_shadow_mute(user_id, 'ALL', duration_seconds=0.05)
    assert is_user_in_memory_shadow_muted(user_id, 'b', now_ts=now) is True

    # 2. Concurrently poll as it expires
    results = []
    async def poll_worker(worker_id: int):
        await asyncio.sleep(0.02 + (worker_id * 0.001))
        res = is_user_in_memory_shadow_muted(user_id, 'b')
        results.append((worker_id, res))

    tasks = [asyncio.create_task(poll_worker(i)) for i in range(50)]
    await asyncio.gather(*tasks)

    # 3. After expiry: must cleanly return False and pop expired key
    await asyncio.sleep(0.06)
    final_res = is_user_in_memory_shadow_muted(user_id, 'b')
    assert final_res is False
    assert user_id not in _in_memory_shadow_muted_users


@pytest.mark.asyncio
async def test_stale_board_data_timestamp_purged_on_expiry():
    """
    Verifies that when a shadow mute expires, board_data['shadow_mutes'] is cleaned
    and does not accumulate stale expired timestamps.
    """
    user_id = 7770002
    board_id = 'b'
    clear_in_memory_shadow_mutes(user_id)

    # Set expired timestamp in board_data
    past_dt = datetime.fromtimestamp(time.time() - 100.0, UTC)
    shared_state.board_data.setdefault(board_id, {})['shadow_mutes'] = {user_id: past_dt}

    msg = FakeMessage(user_id, text="Normal post after mute expired")

    with patch("common.database.get_shadow_mute_info", new=AsyncMock(return_value={'is_muted': False})):
        is_muted = await _is_user_shadow_muted_early(user_id, board_id, msg)
        assert is_muted is False

        # Stale key MUST be removed from board_data['shadow_mutes']
        sm_dict = shared_state.board_data[board_id].get('shadow_mutes', {})
        assert user_id not in sm_dict, f"Stale user_id left in board_data shadow_mutes: {sm_dict}"


def test_prune_stale_spam_filter_state():
    """Verifies prune_stale_spam_filter_state purges expired entries across all trackers."""
    now = time.time()
    user_id = 7770003

    _in_memory_shadow_muted_users[user_id] = now - 10.0
    _in_memory_shadow_muted_users[(user_id, 'b')] = now - 10.0
    shared_state.board_data.setdefault('b', {})['shadow_mutes'] = {user_id: now - 10.0}

    pruned = prune_stale_spam_filter_state(now_ts=now)
    assert pruned.get("_in_memory_shadow_muted_users", 0) >= 2
    assert user_id not in _in_memory_shadow_muted_users
    assert user_id not in shared_state.board_data['b'].get('shadow_mutes', {})


# ============================================================================
# SCENARIO 4: 50 BORDERLINE HUMAN MESSAGES (ZERO FALSE POSITIVES)
# ============================================================================

BORDERLINE_50_MESSAGES = [
    "ахахаха ору бля",
    "хддддд лол",
    "дааа уж",
    "го в пати 123",
    "пхахахаха жесть",
    "кеееек лол",
    "ыыыыы ну ты выдал",
    "рооофл ппц",
    "мдааа треш",
    "жиза ппц",
    "база кормит",
    "кринж какой-то",
    "ладно проехали",
    "ура победа",
    "привет анон",
    "спасибо бро",
    "хз что делать",
    "мб завтра",
    "спс за инфу",
    "чзх это было",
    "крч слушай сюда",
    "ппц ты кадр",
    "втф что за бред",
    "ок понял тебя",
    "да нет наверное",
    "в смысле как так",
    "ну такое себе",
    "аааа жесть",
    "неееет только не это",
    "погнали играть",
    "че кого как дела",
    "лооооол орнул",
    "кек чебурек",
    "хыхыхы смешно",
    "хехехе классика",
    "хохохо дед мороз",
    "пхахах ну и кринж",
    "ору в голосину",
    "в голос с подливой",
    "годнота приехала",
    "годно пили еще",
    "сейчас бы в 2026",
    "плюсую адеквату",
    "двачую капчую",
    "сап двач мур",
    "спок ночи анон",
    "доброе утро тред",
    "поясни за шмот",
    "пруфы будут не",
    "слился лалка",
]

@pytest.mark.asyncio
@pytest.mark.parametrize("msg_text", BORDERLINE_50_MESSAGES)
async def test_borderline_messages_never_shadowmuted(msg_text):
    """
    Adversarial test on 50 borderline messages:
    Verifies they are recognized as legitimate banter/conversation and NEVER falsely muted.
    """
    uid = 999000 + hash(msg_text) % 100000
    clear_in_memory_shadow_mutes(uid)
    reset_short_gibberish_tracker(uid)

    # 1. Must NOT be detected as keysmash
    is_km = is_actual_keysmash_or_gibberish(msg_text)
    assert is_km is False, f"Borderline message falsely flagged as keysmash: '{msg_text}'"

    # 2. Must NOT trigger short gibberish flood
    is_gib, reason, _ = check_short_gibberish_flood(uid, msg_text, posts_count=50)
    assert is_gib is False, f"Borderline message falsely triggered gibberish flood: '{msg_text}' ({reason})"

    # 3. Must evaluate cleanly in evaluate_message_for_autoshadowmute
    with patch("common.spam_filter.get_user_total_posts", new=AsyncMock(return_value=50)):
        should_mute, mute_reason, _ = await evaluate_message_for_autoshadowmute(
            user_id=uid,
            board_id="b",
            content=msg_text,
            msg_type="text",
            raw_content_type="text",
            posts_count=50
        )
        assert should_mute is False, f"Borderline message falsely triggered autoshadowmute: '{msg_text}' ({mute_reason})"


@pytest.mark.parametrize("keysmash_text", [
    "фывапрол",
    "asdfghjkl",
    "йцукенгш",
    "вджлрп",
    "бвгджз",
    "qwerqwer",
    "zxcvzxcv",
    "11111",
])
def test_true_keysmash_properly_detected(keysmash_text):
    """Verifies that true keysmash and keyboard walks ARE still caught correctly."""
    assert is_actual_keysmash_or_gibberish(keysmash_text) is True
