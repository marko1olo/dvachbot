# -*- coding: utf-8 -*-
import pytest
import time
from unittest import mock
from common.spam_filter import (
    check_flood,
    check_short_gibberish_flood,
    calculate_dynamic_spam_mute_duration,
    reset_short_gibberish_tracker,
    evaluate_message_for_autoshadowmute,
    prune_stale_spam_filter_state,
    _short_gibberish_tracker,
    _user_request_timestamps,
    _seen_media_groups,
    _shadow_mute_applied_ts,
)


@pytest.fixture(autouse=True)
def clean_spam_state():
    reset_short_gibberish_tracker()
    _user_request_timestamps.clear()
    _seen_media_groups.clear()
    _shadow_mute_applied_ts.clear()
    yield
    reset_short_gibberish_tracker()
    _user_request_timestamps.clear()
    _seen_media_groups.clear()
    _shadow_mute_applied_ts.clear()


def test_short_gibberish_flood_triggers_mute():
    """3 быстрых коротких текста (< 25 симв) за 2 секунды вызывают шедоумут."""
    user_id = 90001
    base_ts = 1000.0

    # 1st short message (< 25 chars) at t = 0.0s
    is_flood1, _, dur1 = check_short_gibberish_flood(user_id, "asdfgh", now_ts=base_ts, posts_count=10)
    assert not is_flood1
    assert dur1 == 0

    # 2nd short message at t = 1.0s
    is_flood2, _, dur2 = check_short_gibberish_flood(user_id, "фывпрлдж", now_ts=base_ts + 1.0, posts_count=10)
    assert not is_flood2
    assert dur2 == 0

    # 3rd short message at t = 2.0s -> triggers!
    is_flood3, reason3, dur3 = check_short_gibberish_flood(user_id, "fghj", now_ts=base_ts + 2.0, posts_count=10)
    assert is_flood3 is True
    assert "Спам-флуд короткой рандомной херней/keysmash" in reason3
    assert "(3 за 5.0с)" in reason3
    # Duration: newbie/anon base 1200, length <= 10 -> 3.0, velocity 3 / 2.0 = 1.5 -> 1.8 => 1200 * 3.0 * 1.8 = 6480
    assert dur3 == 6480


def test_short_gibberish_veteran_mute_duration():
    """У ветерана (posts_count >= 100) базовая длительность масштабируется от 600с."""
    user_id = 90002
    base_ts = 2000.0

    check_short_gibberish_flood(user_id, "asdf", now_ts=base_ts, posts_count=150)
    check_short_gibberish_flood(user_id, "fghj", now_ts=base_ts + 1.0, posts_count=150)
    is_flood, reason, dur = check_short_gibberish_flood(user_id, "jklm", now_ts=base_ts + 2.0, posts_count=150)

    assert is_flood is True
    assert "Спам-флуд короткой рандомной херней/keysmash" in reason
    # Duration for veteran: base 600, length <= 10 -> 3.0, velocity 3 / 2.0 = 1.5 -> 1.8 => 600 * 3.0 * 1.8 = 3240
    assert dur == 3240


def test_normal_conversation_does_not_trigger_gibberish_flood():
    """Обычный разговор анонов (1 короткое сообщение раз в 6 секунд) НЕ триггерит мут."""
    user_id = 90003
    base_ts = 3000.0

    messages = [
        "здарова",
        "че как оно?",
        "да пойдет вроде",
        "норм тред",
        "быть добру",
        "ладно, я спать",
    ]

    for idx, msg in enumerate(messages):
        ts = base_ts + (idx * 6.0)  # exactly 1 message every 6 seconds
        is_flood, reason, dur = check_short_gibberish_flood(user_id, msg, now_ts=ts, posts_count=50)
        assert not is_flood, f"Message '{msg}' at step {idx+1} falsely triggered: {reason}"
        assert dur == 0


def test_long_messages_exempt_from_gibberish_flood():
    """Сообщения длиннее 25 символов не учитываются в счетчике короткого флуда."""
    user_id = 90004
    base_ts = 4000.0

    long_msg = "Это длинное осмысленное сообщение больше двадцати пяти символов"
    for i in range(5):
        ts = base_ts + (i * 0.5)
        is_flood, _, dur = check_short_gibberish_flood(user_id, long_msg, now_ts=ts, posts_count=10)
        assert not is_flood
        assert dur == 0

    assert len(_short_gibberish_tracker[user_id]) == 0


def test_text_burst_flood_blocks_at_6th_message():
    """Текстовый burst флуд (7 быстрых текстовых сообщений) блокируется на 6-м сообщении."""
    user_id = 90005
    board_id = "b"
    base_ts = 5000.0

    # First 5 text messages pass (burst_limit = 5)
    for i in range(5):
        ts = base_ts + (i * 0.2)
        is_fl, reason = check_flood(
            user_id=user_id,
            board_id=board_id,
            now_ts=ts,
            posts_count=200,  # even for a veteran!
            is_media=False,
            media_group_id=None
        )
        assert not is_fl, f"Message {i+1} should pass, but failed: {reason}"
        assert reason == ""

    # 6th message triggers burst limit (> 5 messages in 4.0s)
    is_fl_6, reason_6 = check_flood(
        user_id=user_id,
        board_id=board_id,
        now_ts=base_ts + 1.0,
        posts_count=200,
        is_media=False,
        media_group_id=None
    )
    assert is_fl_6 is True, "6th message must trigger burst flood!"
    assert "Burst флуд" in reason_6
    assert "6 сообщений за 4.0с" in reason_6

    # 7th message also blocked
    is_fl_7, reason_7 = check_flood(
        user_id=user_id,
        board_id=board_id,
        now_ts=base_ts + 1.2,
        posts_count=200,
        is_media=False,
        media_group_id=None
    )
    assert is_fl_7 is True


def test_veteran_media_batch_12_files_passes():
    """Пакет из 12 медиа-файлов (видео/фото) у ветерана проходит без ошибок (не ломает медиа)."""
    user_id = 90006
    board_id = "sex"
    base_ts = 6000.0

    for i in range(12):
        ts = base_ts + (i * 0.01)  # rapid 10ms burst of media files
        is_fl, reason = check_flood(
            user_id=user_id,
            board_id=board_id,
            now_ts=ts,
            posts_count=211,  # veteran
            is_media=True,
            media_group_id=None
        )
        assert not is_fl, f"Media file {i+1}/12 was falsely blocked: {reason}"


def test_dynamic_spam_mute_duration_calculation_directive():
    """
    Верификация формулы динамического масштабирования срока теневого мута по директиве владельца:
    - Фактор длины (length_factor): <= 10 (3.0), 11..25 (2.0), 26..60 (1.2), > 60 (1.0).
    - Фактор скорости (frequency_factor): velocity >= 2.0 (2.5), >= 1.0 (1.8), < 1.0 (1.0).
    - Базовая длительность: 600с для ветеранов/олдфагов (posts >= 100), 1200с для новичков/анонов.
    - Итоговая длительность = int(base_sec * length_factor * frequency_factor), кап 86400 (24ч).
    """
    # 1. Пример из директивы: ультра-короткий макрос (<= 10 симв на скорости >= 2 сообщ/сек)
    # Олдфаг (posts >= 100): 600 * 3.0 * 2.5 = 4500с (75 минут)
    dur_oldfag_macro = calculate_dynamic_spam_mute_duration(
        text="п", count=4, window=1.5, posts_count=500  # velocity = 4 / 1.5 = 2.67 >= 2.0
    )
    assert dur_oldfag_macro == 4500

    # Новичок (posts < 100): 1200 * 3.0 * 2.5 = 9000с (2.5 часа)
    dur_newbie_macro = calculate_dynamic_spam_mute_duration(
        text="хуйня", count=4, window=1.5, posts_count=10
    )
    assert dur_newbie_macro == 9000

    # 2. Пример из директивы: Обычный текст (> 60 симв) на скорости < 1 сообщ/сек
    # Дает базовые 600с для олдфага
    long_text = "Это длинный нормальный осмысленный текст сообщения на борде, длина которого превышает шестьдесят символов"
    dur_normal_text = calculate_dynamic_spam_mute_duration(
        text=long_text, count=2, window=4.0, posts_count=150  # velocity = 2 / 4.0 = 0.5 < 1.0
    )
    assert dur_normal_text == 600

    # Базовые 1200с для новичка
    dur_normal_newbie = calculate_dynamic_spam_mute_duration(
        text=long_text, count=2, window=4.0, posts_count=5
    )
    assert dur_normal_newbie == 1200

    # 3. Средний текст (11..25 симв) на скорости >= 1.0 сообщ/сек (множители 2.0 и 1.8)
    # Ветеран: 600 * 2.0 * 1.8 = 2160
    dur_mid = calculate_dynamic_spam_mute_duration(
        text="короткий текст!", count=3, window=2.0, posts_count=100  # len = 15, vel = 1.5
    )
    assert dur_mid == 2160

    # 4. Текст 26..60 симв (множитель 1.2) на скорости >= 2.0 сообщ/сек (множитель 2.5)
    # Новичок: 1200 * 1.2 * 2.5 = 3600
    mid2_text = "Текст средней длины от двадцати шести до шестидесяти"
    dur_mid2 = calculate_dynamic_spam_mute_duration(
        text=mid2_text, count=6, window=2.0, posts_count=0  # len = 52, vel = 3.0
    )
    assert dur_mid2 == 3600

    # 5. Кап 86400с (24ч)
    dur_capped = calculate_dynamic_spam_mute_duration(
        text="а", count=100, window=0.5, posts_count=0
    )
    assert dur_capped <= 86400


@pytest.mark.asyncio
async def test_evaluate_message_for_autoshadowmute_short_gibberish():
    """evaluate_message_for_autoshadowmute triggers autoshadowmute on short gibberish flood."""
    user_id = 90007
    board_id = "b"
    base_ts = 7000.0

    mock_db_mute = mock.AsyncMock(return_value=base_ts + 3240.0)
    with mock.patch("common.database.apply_shadow_mute", mock_db_mute), \
         mock.patch("common.database.is_shadow_muted", mock.AsyncMock(return_value=False)):

        # Msg 1
        res1, reason1, exp1 = await evaluate_message_for_autoshadowmute(
            user_id=user_id,
            board_id=board_id,
            content="asdf",
            msg_type="text",
            raw_content_type="text",
            now_ts=base_ts,
            posts_count=150
        )
        assert not res1
        assert exp1 == 0.0

        # Msg 2
        res2, reason2, exp2 = await evaluate_message_for_autoshadowmute(
            user_id=user_id,
            board_id=board_id,
            content="fghj",
            msg_type="text",
            raw_content_type="text",
            now_ts=base_ts + 1.0,
            posts_count=150
        )
        assert not res2
        assert exp2 == 0.0

        # Msg 3 (within 2s) -> triggers!
        res3, reason3, exp3 = await evaluate_message_for_autoshadowmute(
            user_id=user_id,
            board_id=board_id,
            content="jklm",
            msg_type="text",
            raw_content_type="text",
            now_ts=base_ts + 2.0,
            posts_count=150
        )
        assert res3 is True
        assert "Спам-флуд короткой рандомной херней/keysmash" in reason3
        assert exp3 > 0.0
        mock_db_mute.assert_called_once()


def test_prune_stale_spam_filter_state_cleans_short_gibberish():
    """prune_stale_spam_filter_state clears expired entries from _short_gibberish_tracker."""
    now = 8000.0
    uid_stale = 90008
    uid_active = 90009

    _short_gibberish_tracker[uid_stale].append(now - 15.0)  # > 10.0s old -> expired
    _short_gibberish_tracker[uid_active].append(now - 2.0)   # 2.0s old -> active

    pruned = prune_stale_spam_filter_state(now_ts=now)
    assert uid_stale not in _short_gibberish_tracker
    assert uid_active in _short_gibberish_tracker
    assert pruned.get("_short_gibberish_tracker", 0) >= 1
