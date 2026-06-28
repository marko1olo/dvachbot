import pytest
from japanese_translator import _normalize_tag_token

def test_normalize_tag_token_underscores():
    assert _normalize_tag_token("hello_world") == "hello world"

def test_normalize_tag_token_dashes():
    assert _normalize_tag_token("hello-world") == "hello world"

def test_normalize_tag_token_strip_whitespace():
    assert _normalize_tag_token("  hello world  ") == "hello world"

def test_normalize_tag_token_lowercase():
    assert _normalize_tag_token("Hello WORLD") == "hello world"

def test_normalize_tag_token_empty_string():
    assert _normalize_tag_token("") == ""

def test_normalize_tag_token_combination():
    assert _normalize_tag_token("  HELLO_world-TAG  ") == "hello world tag"

def test_normalize_tag_token_multiple_replacements():
    assert _normalize_tag_token("a_b-c_d-e") == "a b c d e"
