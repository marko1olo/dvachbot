import re
import pytest
from unittest.mock import MagicMock
from aiogram import F

from main import (
    ANIME_COMMAND_MAP,
    _ANIME_KEYS_SORTED,
    _ANIME_CMDS_PATTERN,
    RE_ANIME_STACK,
    RE_ANIME_CMD,
)
import site_tgach.main as site_main


def test_anime_keys_ordering():
    """Ensure longer command variants appear before shorter prefixes."""
    assert _ANIME_KEYS_SORTED.index("hentai") < _ANIME_KEYS_SORTED.index("hent")
    assert _ANIME_KEYS_SORTED.index("lolicon") < _ANIME_KEYS_SORTED.index("loli")
    assert _ANIME_KEYS_SORTED.index("лоликон") < _ANIME_KEYS_SORTED.index("лоли")


@pytest.mark.parametrize(
    "text,expected_cmd,expected_count,expected_caption",
    [
        ("/hent", "hent", 1, ""),
        ("/hent 5", "hent", 5, ""),
        ("/hent5", "hent", 5, ""),
        ("/hentai", "hentai", 1, ""),
        ("/hentai 5", "hentai", 5, ""),
        ("/hentai5", "hentai", 5, ""),
        ("/HENTAI", "HENTAI", 1, ""),
        ("/HENTAI 5", "HENTAI", 5, ""),
        ("/hentai@my_bot 5", "hentai", 5, ""),
        ("/hent@my_bot 5", "hent", 5, ""),
        ("/hentai 5 cool art", "hentai", 5, "cool art"),
        ("/hentai cool art", "hentai", 1, "cool art"),
        ("/hent 3 cool art", "hent", 3, "cool art"),
        ("/lolicon 5", "lolicon", 5, ""),
        ("/loli 5", "loli", 5, ""),
        ("/лоликон 2", "лоликон", 2, ""),
    ],
)
def test_main_anime_stack_matching_and_caption(text, expected_cmd, expected_count, expected_caption):
    matches = RE_ANIME_STACK.findall(text)
    assert matches, f"Failed to match command in {text!r}"
    cmd_name, num1, num2 = matches[0]
    count = int(num1 or num2 or 1)

    assert cmd_name.lower() == expected_cmd.lower()
    assert count == expected_count

    caption = RE_ANIME_STACK.sub("", text).strip()
    assert caption == expected_caption, f"Expected caption {expected_caption!r}, got {caption!r}"


@pytest.mark.parametrize(
    "text,expected_cmd,expected_count,expected_caption",
    [
        ("/hentai 5", "hentai", 5, ""),
        ("/hent 5", "hent", 5, ""),
        ("/hentai@bot 5", "hentai", 5, ""),
        ("/hentai 5 web post", "hentai", 5, "web post"),
    ],
)
def test_site_tgach_anime_stack(text, expected_cmd, expected_count, expected_caption):
    matches = site_main.RE_ANIME_STACK.findall(text)
    assert matches, f"Failed to match command in site_tgach for {text!r}"
    cmd_name, num1, num2 = matches[0]
    count = int(num1 or num2 or 1)

    assert cmd_name.lower() == expected_cmd.lower()
    assert count == expected_count

    caption = site_main.RE_ANIME_STACK.sub("", text).strip()
    assert caption == expected_caption


@pytest.mark.parametrize(
    "text,should_match",
    [
        ("/hent", True),
        ("/hent 5", True),
        ("/hentai", True),
        ("/hentai 5", True),
        ("/HENTAI", True),
        ("/HENTAI 5", True),
        ("/hentai@bot 5", True),
        ("/hent@bot 5", True),
        ("/hentaicool", False),
        ("just a message", False),
    ],
)
def test_aiogram_filter_routing(text, should_match):
    filter_obj = F.text.regexp(rf"(?i)^/({_ANIME_CMDS_PATTERN})(?:@\w+)?(?=\s|\d|$)")
    msg = MagicMock(text=text)
    res = bool(filter_obj.resolve(msg))
    assert res == should_match, f"Routing check failed for {text!r}, got {res}, expected {should_match}"
