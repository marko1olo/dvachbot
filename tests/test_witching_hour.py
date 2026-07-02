<<<<<<< HEAD
import time
from unittest.mock import patch
import witching_hour

def test_is_witching_hour_active_initial_state():
    # Initial state is usually 0 for both timestamps
    witching_hour.witching_hour_start_ts = 0
    witching_hour.witching_hour_end_ts = 0
    with patch('time.time', return_value=1000):
        # When both are 0, 0 <= 1000 <= 0 is false.
        # But if time.time() happens to return 0, 0 <= 0 <= 0 is true.
        # Let's test non-zero time which is the common case
        assert not witching_hour.is_witching_hour_active()

    with patch('time.time', return_value=0):
        # Edge case: time.time() returns exactly 0
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_before_start():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=999):
        assert not witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_at_start():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=1000):
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_in_middle():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=1500):
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_at_end():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=2000):
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_after_end():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=2001):
        assert not witching_hour.is_witching_hour_active()
=======
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
>>>>>>> 20e4f1e (🧪 [Add tests for apply_zalgo in witching_hour.py])
