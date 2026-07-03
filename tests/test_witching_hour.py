import time
from unittest.mock import patch
import witching_hour
import unittest

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


class TestWitchingHour(unittest.TestCase):
    def test_apply_zalgo_empty_string(self):
        """Test that apply_zalgo returns empty string when given an empty string."""
        self.assertEqual(witching_hour.apply_zalgo(""), "")

    def test_apply_zalgo_none(self):
        """Test that apply_zalgo returns None when given None."""
        self.assertEqual(witching_hour.apply_zalgo(None), None)

    def test_apply_zalgo_normal_string(self):
        """Test that apply_zalgo modifies a normal string."""
        original = "Hello World"
        result = witching_hour.apply_zalgo(original)
        self.assertNotEqual(original, result)
        self.assertTrue(len(result) >= len(original))

if __name__ == '__main__':
    unittest.main()
