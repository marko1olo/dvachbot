# -*- coding: utf-8 -*-
"""
tests/test_anti_neuroslop_and_flavor.py — Automated Anti-Neuroslop, HTML Validity & UX Flavor Audit.

Verifies:
1. Zero corporate/HR/soy neuroslop phrases across all player-facing modules.
2. Explicit anti-GPT-slop instructions in neuro_poster.py & mode_punchup_data.py,
   plus deterministic scrubbing via mode_punchup.punch_up_mode_text().
3. 100% balanced Telegram HTML tags (<b>, <i>, <code>, <a>, <pre>) and safe escaping.
4. Preservation of UX clarity (exact REP/work/rest/referral instructions) and economic invariants.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


BANNED_SOY_PHRASES = [
    "к сожалению",
    "извините за неудобства",
    "приносим извинения",
    "уважаемый пользователь",
    "мы рады приветствовать",
    "дружном сообществе",
    "подводя итог",
    "в современном мире",
    "стоит отметить",
    "сделай вдох",
    "доверие сообщества",
    "разложит всё по полочкам",
    "разнообразить общение",
    "попавших в беду",
    "ты дома, анон",
    "добро пожаловать в тгач",
    "добро пожаловать в анонимную борду",
    "добро пожаловать в имиджборду 2.0",
    "честно и абсолютно бесплатно",
    "take a breather",
    "welcome to tgach",
    "we apologize",
    "in today's world",
    "in conclusion",
]


class _TelegramHTMLValidator(HTMLParser):
    SUPPORTED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "tg-spoiler"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t not in self.SUPPORTED_TAGS:
            self.errors.append(f"Unsupported Telegram HTML tag <{tag}>")
        self.stack.append(t)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if not self.stack:
            self.errors.append(f"Unexpected closing tag </{tag}>")
            return
        top = self.stack.pop()
        if top != t:
            self.errors.append(f"Mismatched closing tag </{tag}> (expected </{top}>)")


def assert_valid_telegram_html(text: str, label: str) -> None:
    validator = _TelegramHTMLValidator()
    validator.feed(text)
    validator.close()
    assert not validator.errors, f"HTML errors in {label}: {validator.errors}"
    assert not validator.stack, f"Unclosed HTML tags in {label}: {validator.stack}"
    # Check no stray unescaped '<' outside known tags
    stripped_tags = re.sub(r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|tg-spoiler)(?:\s+[^>]*)?>", "", text)
    assert "<" not in stripped_tags, f"Unescaped '<' in {label}: {stripped_tags!r}"


def _collect_strings(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_collect_strings(v))
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            out.extend(_collect_strings(v))
    return out


# =============================================================================
# 1. ZERO CORPORATE / SOY NEUROSLOP IN PLAYER-FACING TEXTS
# =============================================================================

def test_no_soy_or_neuroslop_in_help_text():
    import help_text

    all_blocks = []
    for attr in [
        "HELP_HUB_PAGES_RU",
        "HELP_HUB_PAGES_EN",
        "HELP_HUB_PAGES_JP",
        "HELP_TEXT_COMMANDS",
        "HELP_TEXT_EN_COMMANDS",
        "HELP_TEXT_JP_COMMANDS",
        "BOARD_LIST_HEADERS_RU",
        "THREAD_PROMO_TEXT_RU",
        "THREAD_PROMO_TEXT_EN",
        "MODE_INFO_TEXT_RU",
        "CHANNEL_PROMO_TEXT_RU",
        "MECHANICS_INFO_TEXT_RU",
    ]:
        all_blocks.extend(_collect_strings(getattr(help_text, attr)))

    for idx, text in enumerate(all_blocks):
        low = text.lower()
        for banned in BANNED_SOY_PHRASES:
            assert banned not in low, f"Found banned slop '{banned}' in help_text block #{idx}: {text[:160]}"


def test_no_soy_or_neuroslop_in_reputation_and_referral():
    import common.reputation_engine as rep_eng
    import common.referral_engine as ref_eng

    samples = []
    samples.extend(_collect_strings(rep_eng.REPUTATION_TIERS))
    samples.extend(_collect_strings(ref_eng.VIRAL_SNIPPETS))

    for stream in ("ru", "en", "jp"):
        samples.append(rep_eng.format_newcomer_onboarding_alert("post", user_rep=0, req_rep=5, stream=stream))
        samples.append(rep_eng.format_how_to_earn_reputation(stream=stream))
        samples.append(rep_eng.format_newcomer_guide(stream=stream))
        _, msg_rescue, _ = rep_eng.rescue_soft_locked_user(123, {"energy": 0.0, "health": 0.0}, 0.0, stream=stream)
        samples.append(msg_rescue)
        _, msg_rest_ok, _ = rep_eng.execute_free_rest(123, {"energy": 10.0, "health": 50.0}, now_ts=10000.0, stream=stream)
        samples.append(msg_rest_ok)
        _, msg_rest_cd, _ = rep_eng.execute_free_rest(123, {"energy": 50.0, "health": 50.0, "last_free_rest_ts": 9990.0}, now_ts=10000.0, stream=stream)
        samples.append(msg_rest_cd)

        dash_text, _ = ref_eng.format_referral_dashboard_message(
            user_id=1234567,
            bot_username="dvach_chatbot",
            ref_code="Sholter5",
            stats={"referrals_count": 2, "total_earned": 44640.0},
            board_id="b",
            stream=stream,
        )
        samples.append(dash_text)

    for text in samples:
        low = text.lower()
        for banned in BANNED_SOY_PHRASES:
            assert banned not in low, f"Found banned slop '{banned}' in onboarding/referral text: {text[:160]}"


def test_no_soy_or_neuroslop_in_work_alerts_troll_and_flavor():
    import work_alerts
    import troll_phrases
    import contextual_flavor
    import common.work_engine as work_eng

    samples = []
    samples.extend(work_alerts.WORK_ALERT_50_PHRASES)
    samples.extend(work_alerts.WORK_ALERT_100_PHRASES)
    samples.extend(troll_phrases.PREFIXES)
    samples.extend(troll_phrases.SUBJECTS)
    samples.extend(troll_phrases.ACTIONS)
    samples.extend(troll_phrases.ADVICES)
    samples.extend(troll_phrases.SHORT_PHRASES)
    samples.extend(troll_phrases.UNIQUE_PHRASES)
    samples.extend(troll_phrases.CHAIN_PHRASES)
    samples.extend(troll_phrases.SPEED_PHRASES)
    samples.extend(troll_phrases.MEDIA_PHRASES)
    for _, replies in contextual_flavor.CONTEXTUAL_REPLY_EXTENSIONS_RU:
        samples.extend(replies)
    samples.extend(_collect_strings(work_eng.WORK_VACANCIES))
    samples.extend(work_eng.UNIVERSAL_WORK_SUCCESS_PHRASES)
    samples.extend(work_eng.UNIVERSAL_WORK_FAIL_PHRASES)
    samples.append(work_eng.execute_job_action("bottles", {"energy": 0})[2])
    samples.append(work_eng.execute_job_action("bottles", {"health": 0})[2])
    samples.append(work_eng.execute_job_action("factory", {"work_shifts": 0})[2])

    for text in samples:
        low = text.lower()
        for banned in BANNED_SOY_PHRASES:
            assert banned not in low, f"Found banned slop '{banned}' in flavor/work text: {text[:160]}"


# =============================================================================
# 2. ANTI-SLOP PROMPT HARDENING & MODE SCRUBBING
# =============================================================================

def test_neuro_poster_prompts_have_hard_anti_slop_rules():
    import site_tgach.neuro_poster as np

    ru_prompt = np.SYSTEM_PROMPTS["ru"]
    assert "В современном мире" in ru_prompt
    assert "Подводя итог" in ru_prompt
    assert "Стоит отметить" in ru_prompt
    assert "К сожалению" in ru_prompt
    assert "нумерованные списки" in ru_prompt.lower()
    assert "морализаторство" in ru_prompt.lower()

    en_prompt = np.SYSTEM_PROMPTS["en"]
    assert "In today's world" in en_prompt
    assert "In conclusion" in en_prompt
    assert "Unfortunately" in en_prompt

    # Normie persona must NOT instruct the LLM to be polite or give life advice
    normie_prompt = np.PERSONAS["normie"]["prompt"].lower()
    assert "вежливо" not in normie_prompt
    assert "давай тупые житейские советы" not in normie_prompt
    assert "без вежливых советов" in normie_prompt


def test_mode_punchup_anti_slop_rules_and_scrubbing():
    import mode_punchup_data as mpd
    import mode_punchup as mp

    assert hasattr(mpd, "ANTI_SLOP_MODE_RULES")
    assert "В современном мире" in mpd.ANTI_SLOP_MODE_RULES
    assert "Подводя итог" in mpd.ANTI_SLOP_MODE_RULES
    assert "Стоит отметить" in mpd.ANTI_SLOP_MODE_RULES

    slop_input = "Уважаемый пользователь, к сожалению, в современном мире, подводя итог, стоит отметить это."
    out = mp.punch_up_mode_text(slop_input, "gopnik_mode")
    low = out.lower()
    for phrase in ("уважаемый пользователь", "к сожалению", "в современном мире", "подводя итог", "стоит отметить"):
        assert phrase not in low, f"GPT-slop '{phrase}' survived mode_punchup: {out}"


# =============================================================================
# 3. TELEGRAM HTML VALIDITY & UX / ECONOMIC INVARIANTS
# =============================================================================

def test_telegram_html_validity_across_modules():
    import help_text
    import work_alerts
    import common.reputation_engine as rep_eng
    import common.referral_engine as ref_eng
    import common.work_engine as work_eng

    for lang, pages in [
        ("RU", help_text.HELP_HUB_PAGES_RU),
        ("EN", help_text.HELP_HUB_PAGES_EN),
        ("JP", help_text.HELP_HUB_PAGES_JP),
    ]:
        for key, text in pages.items():
            assert_valid_telegram_html(text, f"help_text.{lang}.{key}")

    for i, text in enumerate(work_alerts.WORK_ALERT_50_PHRASES):
        assert_valid_telegram_html(text, f"work_alerts.50[{i}]")
    for i, text in enumerate(work_alerts.WORK_ALERT_100_PHRASES):
        assert_valid_telegram_html(text, f"work_alerts.100[{i}]")

    for stream in ("ru", "en", "jp"):
        assert_valid_telegram_html(
            rep_eng.format_newcomer_onboarding_alert("post", 1, 5, stream=stream),
            f"reputation.alert.{stream}",
        )
        assert_valid_telegram_html(rep_eng.format_how_to_earn_reputation(stream=stream), f"reputation.how.{stream}")
        assert_valid_telegram_html(rep_eng.format_newcomer_guide(stream=stream), f"reputation.guide.{stream}")
        dash, _ = ref_eng.format_referral_dashboard_message(
            123456, "dvach_chatbot", "Code5", {"referrals_count": 1, "total_earned": 22320.0}, stream=stream
        )
        assert_valid_telegram_html(dash, f"referral.dash.{stream}")

    for jid, job in work_eng.WORK_VACANCIES.items():
        for bucket in ("phrases", "fail_phrases", "jackpot_phrases"):
            for i, tmpl in enumerate(job.get(bucket, [])):
                rendered = tmpl.format(reward=100, penalty=50)
                assert_valid_telegram_html(rendered, f"work_engine.{jid}.{bucket}[{i}]")
        assert_valid_telegram_html(work_eng.format_vacancy_dossier(jid, user_shifts=0), f"work_dossier.{jid}")


def test_ux_clarity_and_economic_invariants_preserved():
    import common.reputation_engine as rep_eng
    import common.referral_engine as ref_eng
    import common.work_engine as work_eng
    import contextual_flavor as cf

    # Reputation tiers & UX clarity
    assert [t["min_rep"] for t in rep_eng.REPUTATION_TIERS.values()] == [0, 5, 20, 50, 100]
    alert = rep_eng.format_newcomer_onboarding_alert("post", user_rep=2, req_rep=20, stream="ru")
    assert "20 REP" in alert
    assert "2 REP" in alert
    assert "/work" in alert

    # Referral constants & zero raw ID leak
    assert ref_eng.REFERRAL_REWARD_REFERRER == 22320.0
    assert ref_eng.REFERRAL_REWARD_REFEREE == 7500.0
    dash, _ = ref_eng.format_referral_dashboard_message(
        99887766, "dvach_chatbot", "Abc123", {"referrals_count": 1, "total_earned": 22320.0}, stream="ru"
    )
    assert "99887766" not in dash
    assert "<code>https://t.me/dvach_chatbot?start=ref_Abc123</code>" in dash

    # Work invariants
    assert len(work_eng.WORK_VACANCIES) == 26
    assert work_eng.MAX_COMBINED_MULTIPLIER == 2.25
    assert work_eng.MAX_SHIFT_REWARD_CAP == 45000

    # Contextual flavor regex fix for 'вайб'
    assert any(p.search("вайб") for p, _ in cf.CONTEXTUAL_REPLY_EXTENSIONS_RU)
