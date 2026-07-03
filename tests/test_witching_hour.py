import pytest
from witching_hour import apply_zalgo

def test_apply_zalgo_empty_string():
    """Test that applying zalgo to an empty string or None returns the input unchanged."""
    assert apply_zalgo("") == ""
    assert apply_zalgo(None) is None

def test_apply_zalgo_whitespace():
    """Test that applying zalgo to a whitespace string returns the input unchanged."""
    text = " \t\n "
    assert apply_zalgo(text) == text

def test_apply_zalgo_normal_text():
    """Test that applying zalgo to normal text modifies it appropriately."""
    text = "Hello"
    result = apply_zalgo(text)

    assert result != text
    assert len(result) > len(text)

    # Check original characters are still present in order
    base_chars = [c for c in result if not (0x0300 <= ord(c) <= 0x036F)]
    assert ''.join(base_chars) == text

def test_apply_zalgo_preserves_spaces():
    """Test that spaces are preserved and not corrupted."""
    text = "H e l l o"
    result = apply_zalgo(text)

    assert result.count(" ") == text.count(" ")
