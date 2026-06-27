import pytest
from stats_generator import generate_schizo_name, NICK_PREFIXES, NICK_SUFFIXES

def test_generate_schizo_name_deterministic():
    """Test that the generated name is deterministic for a given user_id."""
    user_id = 123456789
    name1 = generate_schizo_name(user_id)
    name2 = generate_schizo_name(user_id)
    assert name1 == name2

def test_generate_schizo_name_format():
    """Test that the format of the generated name is correct."""
    user_id = 9876543210
    name = generate_schizo_name(user_id)
    assert name.endswith("(#3210)")

    parts = name.split(" ")
    assert len(parts) == 2
    prefix_suffix = parts[0].split("-")
    assert len(prefix_suffix) == 2
    assert prefix_suffix[0] in NICK_PREFIXES
    assert prefix_suffix[1] in NICK_SUFFIXES

def test_generate_schizo_name_short_id():
    """Test when user_id is shorter than 4 digits."""
    user_id = 42
    name = generate_schizo_name(user_id)
    assert name.endswith("(#42)")

def test_generate_schizo_name_string_id():
    """Test when user_id is string."""
    user_id = "42"
    name = generate_schizo_name(user_id)
    assert name.endswith("(#42)")

def test_generate_schizo_name_empty():
    """Test when user_id is 0 or None or empty string."""
    assert generate_schizo_name(0) == "Анонимус"
    assert generate_schizo_name(None) == "Анонимус"
    assert generate_schizo_name("") == "Анонимус"
