import pytest
import time
from common.spam_filter import (
    check_beggar_phishing_spam,
    check_text_copro_flood,
    check_sybil_and_wall_of_text_raid,
    _board_recent_wall_of_texts,
    evaluate_message_for_autoshadowmute,
    _content_fingerprint,
    TEXT_BAYAN_MIN_LEN,
)

@pytest.fixture(autouse=True)
def clean_spam_state():
    _board_recent_wall_of_texts.clear()
    yield
    _board_recent_wall_of_texts.clear()


def test_casual_banter_immune_from_fingerprint():
    """Short casual banter (< 80 chars) must return empty fingerprint and be completely immune from bayan tracking."""
    short_phrases = [
        "ору",
        "быть добру",
        "ебало завали",
        "база",
        "соси хуй быдло",
        "лол кек чебурек",
        "пошел нахуй",
        "да ладно тебе",
    ]
    for phrase in short_phrases:
        fp = _content_fingerprint(phrase, "text")
        assert fp == "", f"Phrase '{phrase}' ({len(phrase)} chars) must not have a bayan fingerprint!"
        assert len(phrase) < TEXT_BAYAN_MIN_LEN


def test_beggar_phishing_spam_detection():
    """Beggar & phishing templates with contacts must be accurately detected, while innocent requests are safe."""
    # Real Sybil scam template with unicode mathematical italic characters
    sybil_text = (
        "🍞 𝘼𝙣𝙤𝙣𝙮, 𝙣𝙪𝙯𝙝𝙣𝙖 𝙥𝙤𝙢𝙤𝙨𝙝𝙘𝙝 𝙨 𝙚𝙙𝙤𝙮...\n"
        "𝘚𝘦𝘺𝘤𝘩𝘢𝘴 𝘷 𝘰𝘤𝘩𝘦𝘯 𝘵𝘺𝘢𝘻𝘩𝘦𝘭𝘰𝘮 𝘱𝘰𝘭𝘰𝘻𝘩𝘦𝘯𝘪𝘪. 𝘕𝘦𝘵 𝘥𝘢𝘻𝘩𝘦 𝘬𝘩𝘭𝘦𝘣𝘢.\n"
        "𝘒𝘵𝘰 𝘮𝘰𝘻𝘩𝘦𝘵 𝘱𝘰𝘮𝘰𝘤𝘩 — 𝘯𝘢𝘱𝘪𝘴𝘩𝘪𝘵𝘦: @Waouty"
    )
    is_spam, reason = check_beggar_phishing_spam(sybil_text)
    assert is_spam is True
    assert "попрошайки" in reason

    # Cyrillic beggar template with card
    cyrillic_beg = "Ребята, прошу помочь на еду, выжить в непростой период, скиньте на хлеб 2202 2000 1234 5678"
    is_spam, reason = check_beggar_phishing_spam(cyrillic_beg)
    assert is_spam is True

    # Crypto beggar template
    crypto_beg = "Сбор средств на еду и выживание, буду искренне благодарен поддержке: 0x71C841803731887F775E26514b8c3B38382d68e3"
    is_spam, reason = check_beggar_phishing_spam(crypto_beg)
    assert is_spam is True

    # Innocent conversational messages MUST NOT trigger
    innocent_1 = "Помогите найти трек из видео плиз @username"
    assert check_beggar_phishing_spam(innocent_1)[0] is False

    innocent_2 = "Кто может помочь с питоном и телетоном, напишите в лс @coder"
    assert check_beggar_phishing_spam(innocent_2)[0] is False

    innocent_3 = "скиньте смешных мемов в тред"
    assert check_beggar_phishing_spam(innocent_3)[0] is False


def test_text_copro_flood_detection():
    """Text copro flood (3+ fecal roots) triggers, casual 1-word swearing does not."""
    flood_text = "ПОНОС КАЛЛ ГОВНО ПОЛИТИЧЕСКИЙ ПОНОС ГОВНОНА"
    is_copro, reason = check_text_copro_flood(flood_text)
    assert is_copro is True
    assert "фекальных корней" in reason

    # Casual single vulgarity MUST NOT trigger
    casual_swearing = "Ну это полное говно, мне не понравилось вообще."
    is_copro, _ = check_text_copro_flood(casual_swearing)
    assert is_copro is False

    casual_two = "У меня сегодня понос мыслей от этой новости."
    is_copro, _ = check_text_copro_flood(casual_two)
    assert is_copro is False


def test_network_lag_double_tap_drop():
    """Identical message from same user within <= 3s is flagged as double_tap_drop with 0 duration."""
    t0 = 1000.0
    wall = (
        "Это очень длинный аналитический текст про текущую ситуацию на имиджборде. "
        "Мы анализируем сетевую активность и поведение пользователей, чтобы предотвратить вайпы и спам. "
        "Тестируем двойной клик из-за лага мобильного интернета."
    )
    # First send
    res1, reason1, mute1 = check_sybil_and_wall_of_text_raid(111, "b", wall, now_ts=t0)
    assert res1 is False

    # Second send 1.5 seconds later (network retry)
    res2, reason2, mute2 = check_sybil_and_wall_of_text_raid(111, "b", wall, now_ts=t0 + 1.5)
    assert res2 is True
    assert reason2 == "double_tap_drop"
    assert mute2 == 0


def test_sybil_raid_detection():
    """Same wall of text posted by account A then account B within 30 min triggers 24h shadowmute on account B."""
    t0 = 2000.0
    wall = (
        "Внимание всем участникам конференции! Сегодня проводится уникальное закрытое мероприятие. "
        "Регистрация строго ограничена по количеству мест, успейте занять свое место в закрытом комьюнити. "
        "Ссылка для доступа и вся информация находятся у координатора."
    )
    # Account A posts
    res_a, _, _ = check_sybil_and_wall_of_text_raid(1001, "b", wall, now_ts=t0)
    assert res_a is False

    # Account B posts the same wall 2 minutes later
    res_b, reason_b, mute_b = check_sybil_and_wall_of_text_raid(1002, "b", wall, now_ts=t0 + 120.0)
    assert res_b is True
    assert "Sybil Raid" in reason_b
    assert "1001" in reason_b
    assert mute_b == 86400


def test_cross_board_fast_blast():
    """Same user posting same wall of text across different boards within 5 minutes triggers 1h shadowmute."""
    t0 = 3000.0
    wall = (
        "Срочный анонс для всех досок проекта! Просим обратить внимание на обновление правил модерации. "
        "Все доски теперь работают по единому стандарту безопасности и чистоты контента без исключений."
    )
    # Post on /b/
    res1, _, _ = check_sybil_and_wall_of_text_raid(2001, "b", wall, now_ts=t0)
    assert res1 is False

    # Post same text on /vg/ 30 seconds later
    res2, reason2, mute2 = check_sybil_and_wall_of_text_raid(2001, "vg", wall, now_ts=t0 + 30.0)
    assert res2 is True
    assert "Веерный спам" in reason2
    assert mute2 == 3600
