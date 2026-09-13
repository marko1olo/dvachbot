# -*- coding: utf-8 -*-
"""
tests/test_caption_guard.py
Verifies safe_tg_caption shielding against TelegramBadRequest 'Bad Request: MESSAGE_TOO_LONG'.
"""

import re
import pytest
from common.text_utils import safe_tg_caption, clean_html_tags, clean_html_for_tg
from leaderboard_card import LeaderboardData, LeaderboardEntry, format_leaderboard_text
from stats_generator import UserStatsCardData, _format_text_report


def assert_tags_balanced(html_text: str):
    """
    Verifies that all allowed Telegram HTML tags in html_text are properly closed and nested.
    """
    # Allowed tags in Telegram HTML
    allowed = {'b', 'i', 'u', 's', 'code', 'pre', 'a', 'tg-spoiler', 'tg-emoji', 'blockquote', 'strong', 'em'}
    tags = re.findall(r'<(/?)([a-zA-Z0-9_-]+)(?:\s+[^>]*)?>', html_text)
    stack = []
    for closing, tag_name in tags:
        tag_name = tag_name.lower()
        if tag_name not in allowed:
            continue
        if not closing:
            stack.append(tag_name)
        else:
            assert len(stack) > 0, f"Unmatched closing tag </{tag_name}> in:\n{html_text}"
            last_tag = stack.pop()
            assert last_tag == tag_name, f"Mismatched tag: expected </{last_tag}>, got </{tag_name}> in:\n{html_text}"
    assert len(stack) == 0, f"Unclosed tags remaining: {stack} in:\n{html_text}"


def test_safe_tg_caption_empty_and_falsy():
    assert safe_tg_caption("") == ""
    assert safe_tg_caption(None) == ""


def test_safe_tg_caption_normal_short_strings():
    text = "Hello, world! This is a simple caption."
    assert safe_tg_caption(text) == text
    assert len(safe_tg_caption(text)) <= 1024

    html_text = "<b>Bold</b>, <i>italic</i>, <code>code</code>."
    assert safe_tg_caption(html_text) == html_text
    assert_tags_balanced(safe_tg_caption(html_text))


def test_safe_tg_caption_exact_max_len():
    text_1024 = "x" * 1024
    assert safe_tg_caption(text_1024, max_len=1024) == text_1024


def test_safe_tg_caption_2000_char_plain_string():
    long_text = "A" * 2000
    res = safe_tg_caption(long_text, max_len=1024)
    assert len(res) <= 1024
    assert res.endswith("...")
    assert_tags_balanced(res)


def test_safe_tg_caption_with_bold_tag():
    text = "<b>" + "X" * 2000 + "</b>"
    res = safe_tg_caption(text, max_len=1024)
    assert len(res) <= 1024
    assert res.endswith("...</b>")
    assert_tags_balanced(res)


def test_safe_tg_caption_with_code_tag():
    text = "<code>" + "print('hello world')\n" * 150 + "</code>"
    res = safe_tg_caption(text, max_len=1024)
    assert len(res) <= 1024
    assert_tags_balanced(res)


def test_safe_tg_caption_with_nested_complex_tags():
    text = "<b><i><u><code>" + "Nested text here! " * 150 + "</code></u></i></b>"
    res = safe_tg_caption(text, max_len=1024)
    assert len(res) <= 1024
    assert_tags_balanced(res)


def test_safe_tg_caption_many_repeated_inline_tags():
    text = ("<b>User</b> posted <i>italic comment</i> with `snippet` and <code>code</code>! " * 40)
    res = safe_tg_caption(text, max_len=1024)
    assert len(res) <= 1024
    assert_tags_balanced(res)


def test_safe_tg_caption_tag_cut_at_boundary():
    # Construct a string where the tag starts right around the cut-off boundary
    prefix = "x" * 1002
    text = prefix + "<b>important bold text</b>" + "y" * 500
    res = safe_tg_caption(text, max_len=1024)
    assert len(res) <= 1024
    assert_tags_balanced(res)


def test_safe_tg_caption_fallback_on_tag_overflow():
    # If the text has many nested open tags, closing them in clean_html_for_tg would exceed max_len,
    # triggering the fallback to clean_html_tags.
    text = ("<b>" * 60) + ("A" * 1500) + ("</b>" * 60)
    res = safe_tg_caption(text, max_len=1024)
    assert len(res) <= 1024
    assert_tags_balanced(res)


def test_safe_tg_caption_custom_small_max_len():
    text = "<b>Super long title text</b> that exceeds short limit"
    res = safe_tg_caption(text, max_len=30)
    assert len(res) <= 30
    assert_tags_balanced(res)

    res_tiny = safe_tg_caption("Hello world", max_len=5)
    assert len(res_tiny) <= 5


def test_leaderboard_card_format_leaderboard_text_shielding():
    # Create LeaderboardData with very long anon tags / prefixes to force length > 1024
    entries = []
    for i in range(1, 11):
        entries.append(LeaderboardEntry(
            user_id=1000 + i,
            rank=i,
            anon_tag=f"Анон [{get_long_hash(i)}]" + "X" * 100,
            custom_prefix="Супер-длинный-титул-" * 10,
            value=1000000 - i * 1000,
            is_caller=(i == 1)
        ))

    data = LeaderboardData(
        board_id="b",
        mode="balance",
        mode_title="ТОП БОГАЧЕЙ " + "★" * 50,
        unit="RUB",
        entries=entries,
        caller_id=1001,
        caller_rank=1,
        caller_value=999000,
        total_users=50000,
        total_metric=100000000
    )

    caption = format_leaderboard_text(data)
    assert len(caption) <= 1024
    assert_tags_balanced(caption)


def test_stats_generator_format_text_report_shielding():
    # Create UserStatsCardData with an extremely long slang_comment to force length > 1024
    card_data = UserStatsCardData(
        schizo_name="Анонимус " * 20,
        role_name="Повелитель Тред-Вайпа",
        custom_prefix="Оверлорд " * 15,
        rank=1,
        total_users=9999,
        posts_count=4242,
        rx_received=8888,
        approval_pct=99.9,
        rx_given=7777,
        balance=12345678,
        mutes_count=0,
        cringe_factor=13.37,
        chronotype="Сыч полуночный",
        slang_comment="База кормит, но тред тонет в шитпосте " * 50,
        board_id="b",
        active_items=[]
    )

    report = _format_text_report(card_data)
    assert len(report) <= 1024
    assert_tags_balanced(report)


def get_long_hash(i: int) -> str:
    return f"hash_{i:04d}_" + "abcdef1234567890" * 4
