# -*- coding: utf-8 -*-
from common.debuff_phrases import (
    DEBUFF_SHIT_PHRASES,
    DEBUFF_VOMIT_PHRASES,
    DEBUFF_FLAG_UA_PHRASES,
    DEBUFF_FLAG_RU_PHRASES,
    DEBUFF_CURSE_PHRASES,
    DEBUFF_SCHIZO_PHRASES,
    get_debuff_footer
)


def test_debuff_phrases_counts():
    for name, pool in [
        ("shit", DEBUFF_SHIT_PHRASES),
        ("vomit", DEBUFF_VOMIT_PHRASES),
        ("flag_ua", DEBUFF_FLAG_UA_PHRASES),
        ("flag_ru", DEBUFF_FLAG_RU_PHRASES),
        ("curse", DEBUFF_CURSE_PHRASES),
        ("schizo", DEBUFF_SCHIZO_PHRASES),
    ]:
        assert len(pool) >= 50, f"{name} has only {len(pool)} phrases (expected >= 50)"
        for p in pool:
            assert isinstance(p, str) and len(p) > 5
            assert p.startswith("[") and p.endswith("]")


def test_get_debuff_footer():
    for t in ["shit", "vomit", "flag_ua", "flag_ru", "curse", "schizo"]:
        res = get_debuff_footer(t)
        assert isinstance(res, str) and len(res) > 5
