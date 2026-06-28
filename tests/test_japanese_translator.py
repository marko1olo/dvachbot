import pytest
from japanese_translator import (
    _tag_token_is_blocked,
    ANIME_HARD_BLOCKED_TAGS,
    ANIME_HARD_BLOCKED_PREFIXES,
)


def test_tag_token_is_blocked_exact_match():
    # Test tags that are exactly in the blocked list
    for tag in ANIME_HARD_BLOCKED_TAGS:
        assert _tag_token_is_blocked(tag) is True


def test_tag_token_is_blocked_prefix():
    # Test tags that start with the blocked prefix
    assert _tag_token_is_blocked("shotacon_something") is True
    assert _tag_token_is_blocked("shota_boy") is True


def test_tag_token_is_blocked_negative():
    # Negative tags should be stripped of the leading dash
    assert _tag_token_is_blocked("-shota") is True
    assert _tag_token_is_blocked("-baby") is True


def test_tag_token_is_blocked_normalization():
    # Token normalization (strips, lowercases, replaces spaces with underscores)
    assert _tag_token_is_blocked(" Shota ") is True
    assert _tag_token_is_blocked("LITTLE GIRL") is True
    assert _tag_token_is_blocked("-CUB") is True


def test_tag_token_is_not_blocked():
    # Test benign tags
    assert _tag_token_is_blocked("1girl") is False
    assert _tag_token_is_blocked("safe") is False
    assert _tag_token_is_blocked("-safe") is False
    assert (
        _tag_token_is_blocked("not_shota") is False
    )  # contains 'shota' but doesn't start with it
