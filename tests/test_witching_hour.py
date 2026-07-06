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

def test_apply_zalgo_empty():
    assert witching_hour.apply_zalgo("") == ""
    assert witching_hour.apply_zalgo(None) is None

def test_apply_zalgo_whitespace():
    assert witching_hour.apply_zalgo(" \t\n ") == " \t\n "

def test_apply_zalgo_deterministic():
    with patch('witching_hour.random.randint') as mock_randint, \
         patch('witching_hour.random.choice') as mock_choice:
        # 1 up, 1 mid, 1 down per character
        mock_randint.return_value = 1
        # Return predictable characters
        mock_choice.side_effect = ['\u030d', '\u0315', '\u0316'] * 10

        result = witching_hour.apply_zalgo("a")
        # 'a' + 1 up + 1 mid + 1 down
        assert result == "a\u030d\u0315\u0316"

        # Test with multiple characters and spaces
        mock_choice.side_effect = ['\u030d', '\u0315', '\u0316'] * 10
        result = witching_hour.apply_zalgo("a b")
        assert result == "a\u030d\u0315\u0316 b\u030d\u0315\u0316"

def test_apply_zalgo_randomness():
    text = "hello world"
    result = witching_hour.apply_zalgo(text)

    assert len(result) >= len(text)
    assert " " in result
    for char in "helloworld":
        assert char in result

    # Since it's random, it's highly likely to be longer, but we check >= just in case.
    # To be more robust, we can just ensure it doesn't crash and returns string.
    assert isinstance(result, str)
