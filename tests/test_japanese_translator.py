import pytest
from japanese_translator import _tag_token_is_blocked, _normalize_tag_token
import japanese_translator

def test_normalize_tag_token():
    assert _normalize_tag_token(" SHOTA ") == "shota"
    assert _normalize_tag_token("little boy") == "little_boy"
    assert _normalize_tag_token("-SHOTA") == "-shota"

def test_tag_token_is_blocked():
    # Exact matches from ANIME_HARD_BLOCKED_TAGS
    assert _tag_token_is_blocked("shota") is True
    assert _tag_token_is_blocked("cub") is True
    assert _tag_token_is_blocked("little_girl") is True
    assert _tag_token_is_blocked("underage") is True

    # Prefix matches from ANIME_HARD_BLOCKED_PREFIXES
    assert _tag_token_is_blocked("shotacon") is True
    assert _tag_token_is_blocked("shotacontent") is True

    # Case insensitive and space handling (handled by normalize)
    assert _tag_token_is_blocked(" SHOTA ") is True
    assert _tag_token_is_blocked("Little Girl") is True

    # Negative tags handling (should strip leading '-')
    assert _tag_token_is_blocked("-shota") is True
    assert _tag_token_is_blocked("-cub") is True

    # Unblocked tags
    assert _tag_token_is_blocked("1girl") is False
    assert _tag_token_is_blocked("cat") is False
    assert _tag_token_is_blocked("dog") is False
    assert _tag_token_is_blocked("safe") is False
    assert _tag_token_is_blocked("") is False

def test_tag_token_is_blocked_custom_globals(monkeypatch):
    monkeypatch.setattr(japanese_translator, 'ANIME_HARD_BLOCKED_TAGS', {"test_blocked"})
    monkeypatch.setattr(japanese_translator, 'ANIME_HARD_BLOCKED_PREFIXES', ("test_prefix_",))

    assert _tag_token_is_blocked("test_blocked") is True
    assert _tag_token_is_blocked("test_prefix_something") is True
    assert _tag_token_is_blocked("other_tag") is False
