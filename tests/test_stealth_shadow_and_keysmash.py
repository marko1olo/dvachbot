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
    check_link_or_ad_spam,
    check_stop_words_violation,
    reset_stop_words_tracker,
    reset_short_gibberish_tracker,
    set_spam_filter_words,
    evaluate_message_for_autoshadowmute,
    _short_gibberish_tracker,
    _user_request_timestamps,
    _stop_words_violation_tracker,
)
from handlers.message_router import process_shadow_reject


@pytest.fixture(autouse=True)
def clean_test_state():
    reset_short_gibberish_tracker()
    reset_stop_words_tracker()
    _user_request_timestamps.clear()
    shared_state.shadow_fake_post_counters.clear()
    set_spam_filter_words('b', set())
    set_spam_filter_words('ALL', set())
    yield
    reset_short_gibberish_tracker()
    reset_stop_words_tracker()
    _user_request_timestamps.clear()
    shared_state.shadow_fake_post_counters.clear()
    set_spam_filter_words('b', set())
    set_spam_filter_words('ALL', set())


def test_is_actual_keysmash_or_gibberish():
    """
    Verifies is_actual_keysmash_or_gibberish:
    - Normal conversational Russian phrases (e.g. Zagesi's messages) -> False
    - Actual keyboard home-row smashes and consonant gibberish -> True
    """
    # 1. Zagesi's legitimate conversation phrases -> MUST return False!
    zagesi_phrases = [
        "жаль не нашел",
        "но увидишь кидай",
        "он оч изменился",
        "привет всем",
        "как дела?",
        "до встречи",
        "встреча завтра",
        "взгляд в окно",
        "всплеск эмоций",
        "агентство новостей",
        "все норм",
        "спс",
        "ппц",
        "крч",
        "хаха",
        "ахаха",
    ]
    for phrase in zagesi_phrases:
        assert is_actual_keysmash_or_gibberish(phrase) is False, f"Legitimate phrase '{phrase}' falsely marked as keysmash!"

    # 2. Actual keysmash and consonant gibberish -> MUST return True!
    keysmash_phrases = [
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
    for smash in keysmash_phrases:
        assert is_actual_keysmash_or_gibberish(smash) is True, f"Real keysmash '{smash}' failed to be recognized!"


def test_check_short_gibberish_flood_oldfag_trust_scaling():
    """
    - A user with 100k posts sends 3 short phrases in rapid succession -> NOT muted!
    - A newbie/spammer sends 'asdf' 3 times in 2 seconds -> MUTED!
    """
    base_ts = 1000.0

    # Oldfag with 100,000 posts: sends 3 short conversational phrases
    oldfag_id = 11111
    is_fl1, _, _ = check_short_gibberish_flood(oldfag_id, "жаль не нашел", now_ts=base_ts, posts_count=100000)
    is_fl2, _, _ = check_short_gibberish_flood(oldfag_id, "но увидишь кидай", now_ts=base_ts + 0.5, posts_count=100000)
    is_fl3, _, _ = check_short_gibberish_flood(oldfag_id, "он оч изменился", now_ts=base_ts + 1.0, posts_count=100000)

    assert not is_fl1
    assert not is_fl2
    assert not is_fl3, "Oldfag sending normal short phrases must NEVER be muted!"

    # Even if oldfag sends actual keysmash, their fast limit is raised to 12
    for i in range(11):
        is_fl, _, _ = check_short_gibberish_flood(oldfag_id, "asdf", now_ts=base_ts + 2.0 + (i * 0.1), posts_count=100000)
        assert not is_fl, f"Oldfag with 100k posts should tolerate up to 11 keysmashes, failed at {i+1}"

    # Spammer (newbie, posts_count=5) sending 'asdf' 3 times in 2 seconds -> MUTED!
    spammer_id = 22222
    s_fl1, _, d1 = check_short_gibberish_flood(spammer_id, "asdf", now_ts=base_ts, posts_count=5)
    assert not s_fl1
    assert d1 == 0

    s_fl2, _, d2 = check_short_gibberish_flood(spammer_id, "asdf", now_ts=base_ts + 0.5, posts_count=5)
    assert not s_fl2
    assert d2 == 0

    s_fl3, s_reason3, d3 = check_short_gibberish_flood(spammer_id, "asdf", now_ts=base_ts + 1.0, posts_count=5)
    assert s_fl3 is True, "Spammer sending 3 keysmashes in 1s must be muted!"
    assert "Спам-флуд короткой рандомной херней/keysmash" in s_reason3
    assert d3 > 0


def test_check_flood_unclamped_for_oldfags():
    """
    Verifies that check_flood does not artificially clamp burst_limit to 5 for oldfags (posts_count >= 500).
    For posts_count=500 (oldfag tier), burst_limit is 14 (not 5!).
    """
    oldfag_id = 33333
    board_id = "b"
    base_ts = 2000.0

    # Oldfag sends 10 rapid messages in 3 seconds (under their tier_burst of 14)
    for i in range(10):
        is_fl, reason = check_flood(
            user_id=oldfag_id,
            board_id=board_id,
            now_ts=base_ts + (i * 0.2),
            posts_count=600,
            is_media=False,
            media_group_id=None
        )
        assert not is_fl, f"Message {i+1} falsely blocked for oldfag: {reason}"

    # Meanwhile, newbie (posts_count=0) with burst_limit clamped to 5 is blocked on the 6th message
    newbie_id = 44444
    for i in range(5):
        is_fl, _ = check_flood(
            user_id=newbie_id,
            board_id=board_id,
            now_ts=base_ts + (i * 0.2),
            posts_count=0,
            is_media=False,
            media_group_id=None
        )
        assert not is_fl

    is_fl_newbie_6, reason_6 = check_flood(
        user_id=newbie_id,
        board_id=board_id,
        now_ts=base_ts + 1.2,
        posts_count=0,
        is_media=False,
        media_group_id=None
    )
    assert is_fl_newbie_6 is True, "Newbie must be burst limited at 6th message!"
    assert "Burst флуд" in reason_6


@pytest.mark.asyncio
async def test_process_shadow_reject_stealth_and_increment():
    """
    Verifies process_shadow_reject:
    1. Smooth post numbering increment strictly by +1 (no random jumping holes 1..3).
    2. BroadcastConfig recipients={ctx.user_id} and reply_info=None (author receives formatted post cleanly).
    3. Retains realistic delay (0.5..1.5s).
    """
    user_id = 55555
    board_id = "b"
    mock_bot = mock.AsyncMock()

    shared_state.state['post_counter'] = 100
    ctx = shared_state.ShadowRejectContext(
        bot=mock_bot,
        board_id=board_id,
        user_id=user_id,
        content={"type": "text", "text": "Тестовое теневое сообщение"},
        reply_to_post=None,
        stream='ru',
        reply_to_message_id=98765
    )

    with mock.patch("handlers.message_router.send_message_to_users", mock.AsyncMock()) as mock_send, \
         mock.patch("handlers.message_router.format_header", mock.AsyncMock(side_effect=lambda b, p, u, stream='ru': f"Пост #{p}")) as mock_header, \
         mock.patch("asyncio.sleep", mock.AsyncMock()) as mock_sleep:

        # 1st shadow post
        await process_shadow_reject(ctx)

        key = (board_id, user_id)
        assert shared_state.shadow_fake_post_counters[key] == 101, "First post must increment floor strictly by +1!"
        mock_send.assert_called_once()
        b_config = mock_send.call_args[0][0]
        assert b_config.recipients == {user_id}
        assert b_config.reply_info is None
        assert b_config.content['post_num'] == 101
        assert b_config.content['is_shadow_reject'] is True

        # 2nd shadow post
        mock_send.reset_mock()
        await process_shadow_reject(ctx)
        assert shared_state.shadow_fake_post_counters[key] == 102, "Second post must increment strictly by +1 (102)!"
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0].content['post_num'] == 102

        # 3rd shadow post
        mock_send.reset_mock()
        await process_shadow_reject(ctx)
        assert shared_state.shadow_fake_post_counters[key] == 103, "Third post must increment strictly by +1 (103)!"
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0].content['post_num'] == 103

        # Sleep verification: called with values between 0.5 and 1.5s
        assert mock_sleep.call_count >= 3
        for call_args in mock_sleep.call_args_list:
            slept_time = call_args[0][0]
            assert 0.5 <= slept_time <= 1.5


def test_baklop5_spammer_detection():
    """
    Verifies detection of Baklop5 attack patterns:
    - Keysmash words: 'fgh', 'fhgx' -> detected by is_actual_keysmash_or_gibberish
    - Rapid 15 msgs / 2 sec burst -> caught by check_flood at 6th message
    """
    baklop_uid = 6199965905
    board_id = "b"
    base_ts = 3000.0

    # 1. Keysmash detection
    assert is_actual_keysmash_or_gibberish("fgh") is True
    assert is_actual_keysmash_or_gibberish("fhgx") is True

    # 2. Burst flood: 15 messages in 2 seconds
    for i in range(5):
        is_fl, _ = check_flood(baklop_uid, board_id, now_ts=base_ts + (i * 0.1), posts_count=0)
        assert not is_fl

    is_fl_6, reason = check_flood(baklop_uid, board_id, now_ts=base_ts + 0.6, posts_count=0)
    assert is_fl_6 is True
    assert "Burst флуд" in reason


def test_kibana7_spammer_detection():
    """
    Verifies detection of Kibana7 attack patterns:
    - External Telegram channel invite spam: 't.me/govnachh'
    - check_link_or_ad_spam blocks on first attempt for non-whitelisted users
    """
    kibana_uid = 9134685790
    board_id = "b"
    base_ts = 4000.0

    is_spam, reason = check_link_or_ad_spam(
        user_id=kibana_uid,
        board_id=board_id,
        text="Заходите на наш канал https://t.me/govnachh быстрее!",
        now_ts=base_ts
    )
    assert is_spam is True
    assert "Telegram ссылка/паблик" in reason or "Авто-шедоумут" in reason


def test_stop_words_consecutive_violation_triggers_one_hour_shadowmute():
    """
    Verifies requirement 6:
    If a user sends >2 messages containing stop words in a 180s sliding window,
    triggers a 1-hour (3600s) shadowmute.
    """
    user_id = 77777
    board_id = "b"
    base_ts = 5000.0

    # Configure a test stop word
    set_spam_filter_words(board_id, {"запрещенка_тест", "скам_крипта"})

    # 1st message with stop word -> tracked, not yet muted
    fl1, _, dur1 = check_stop_words_violation(user_id, board_id, "привет запрещенка_тест тут", now_ts=base_ts)
    assert not fl1
    assert dur1 == 0

    # 2nd message with stop word -> tracked, not yet muted
    fl2, _, dur2 = check_stop_words_violation(user_id, board_id, "еще одна запрещенка_тест здесь", now_ts=base_ts + 10.0)
    assert not fl2
    assert dur2 == 0

    # Normal message without stop word -> not tracked in stop word counter
    fl_norm, _, _ = check_stop_words_violation(user_id, board_id, "просто обычный текст", now_ts=base_ts + 20.0)
    assert not fl_norm

    # 3rd message with stop word (>2 messages in 180s) -> TRIGGERS 1 HOUR SHADOWMUTE!
    fl3, reason3, dur3 = check_stop_words_violation(user_id, board_id, "скам_крипта налетайте", now_ts=base_ts + 30.0)
    assert fl3 is True
    assert "Спам запрещенными словами из стоп-листа" in reason3
    assert dur3 == 3600
