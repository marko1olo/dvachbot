# -*- coding: utf-8 -*-
from common.debuff_phrases import (
    DEBUFF_SHIT_PHRASES,
    DEBUFF_VOMIT_PHRASES,
    DEBUFF_FLAG_UA_PHRASES,
    DEBUFF_FLAG_RU_PHRASES,
    DEBUFF_CURSE_PHRASES,
    DEBUFF_SCHIZO_PHRASES,
    MUTE_WARN_REASONS,
    PARTYVAN_ANNOUNCEMENTS,
    MUTE_GUN_ANNOUNCEMENTS,
    get_debuff_footer,
    get_mute_warn_text,
    get_partyvan_announcement,
    get_mute_gun_announcement
)


def test_debuff_phrases_counts():
    for name, pool in [
        ("shit", DEBUFF_SHIT_PHRASES),
        ("vomit", DEBUFF_VOMIT_PHRASES),
        ("flag_ua", DEBUFF_FLAG_UA_PHRASES),
        ("flag_ru", DEBUFF_FLAG_RU_PHRASES),
        ("curse", DEBUFF_CURSE_PHRASES),
        ("schizo", DEBUFF_SCHIZO_PHRASES),
        ("mute_warn_reasons", MUTE_WARN_REASONS),
    ]:
        assert len(pool) >= 50, f"{name} has only {len(pool)} phrases (expected >= 50)"

    assert len(PARTYVAN_ANNOUNCEMENTS) >= 5
    assert len(MUTE_GUN_ANNOUNCEMENTS) >= 3


def test_get_mute_warn_text():
    text = get_mute_warn_text("10ч 25мин")
    assert "10ч 25мин" in text
    assert "ТЕБЯ ЕБНУЛИ В МУТ" in text
    assert len(text) > 100


def test_announcements():
    assert len(get_partyvan_announcement()) > 30
    assert len(get_mute_gun_announcement()) > 30
