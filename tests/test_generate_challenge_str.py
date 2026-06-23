import sys
import os
from unittest import mock
import time
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import Dubsite_tgach.security
import site_tgach.security

modules_to_test = [Dubsite_tgach.security, site_tgach.security]

@pytest.mark.parametrize("sec_module", modules_to_test)
def test_generate_challenge_str_basic(sec_module):
    """Test standard behavior without cache cleanup"""
    # Reset cache
    sec_module.POW_CACHE.clear()

    with mock.patch("time.time", return_value=1000.0):
        with mock.patch("random.random", return_value=0.5): # Avoid probabilistic cleanup
            challenge = sec_module.generate_challenge_str()

            assert len(challenge) == 32 # 16 bytes hex string
            assert challenge in sec_module.POW_CACHE
            assert sec_module.POW_CACHE[challenge] == 1600.0 # 1000.0 + 600

@pytest.mark.parametrize("sec_module", modules_to_test)
def test_generate_challenge_str_probabilistic_cleanup(sec_module):
    """Test probabilistic cache cleanup of expired elements"""
    sec_module.POW_CACHE.clear()

    # Add an expired element and a non-expired element
    sec_module.POW_CACHE["expired"] = 900.0
    sec_module.POW_CACHE["valid"] = 1100.0

    with mock.patch("time.time", return_value=1000.0):
        # random.random() < 0.1 triggers probabilistic cleanup
        with mock.patch("random.random", return_value=0.05):
            challenge = sec_module.generate_challenge_str()

            assert "expired" not in sec_module.POW_CACHE
            assert "valid" in sec_module.POW_CACHE
            assert challenge in sec_module.POW_CACHE

@pytest.mark.parametrize("sec_module", modules_to_test)
def test_generate_challenge_str_max_size_cleanup(sec_module):
    """Test aggressive cleanup when MAX_POW_CACHE_SIZE is exceeded"""
    sec_module.POW_CACHE.clear()
    max_size = sec_module.MAX_POW_CACHE_SIZE

    # Fill the cache to exactly max_size
    for i in range(max_size):
        # make all elements valid (not expired)
        sec_module.POW_CACHE[f"valid_{i}"] = 2000.0

    # Now adding one more will trigger the len > MAX_POW_CACHE_SIZE condition
    # Add one expired so we can see if it's removed, and then check 20% deletion
    sec_module.POW_CACHE["expired"] = 900.0

    assert len(sec_module.POW_CACHE) == max_size + 1

    with mock.patch("time.time", return_value=1000.0):
        with mock.patch("random.random", return_value=0.5): # don't trigger prob cleanup
            with mock.patch("random.sample", side_effect=lambda keys, k: keys[:k]) as mock_sample:
                challenge = sec_module.generate_challenge_str()

                # It should have removed the expired one
                assert "expired" not in sec_module.POW_CACHE

                # It should have removed 20% of the entries (since even without "expired", len > max_size)
                # Note: after removing 'expired', length was still max_size (5000) which is NOT > max_size
                # Wait, the check is `if len(POW_CACHE) > MAX_POW_CACHE_SIZE: ... to_del.extend(...)`
                # And the first IF is `if len(POW_CACHE) > MAX_POW_CACHE_SIZE ...` which is TRUE initially.
                pass

@pytest.mark.parametrize("sec_module", modules_to_test)
def test_generate_challenge_str_max_size_aggressive(sec_module):
    """Test the aggressive 20% cleanup specifically"""
    sec_module.POW_CACHE.clear()
    max_size = sec_module.MAX_POW_CACHE_SIZE

    # Fill with 5001 valid elements
    for i in range(max_size + 1):
        sec_module.POW_CACHE[f"valid_{i}"] = 2000.0

    assert len(sec_module.POW_CACHE) == max_size + 1

    with mock.patch("time.time", return_value=1000.0):
        with mock.patch("random.random", return_value=0.5):
            # We mock random.sample to just return the first K elements
            with mock.patch("random.sample", side_effect=lambda keys, k: keys[:k]):
                challenge = sec_module.generate_challenge_str()

                # Start: 5001 elements.
                # Expired: 0. Length is still 5001 > 5000.
                # 20% to delete: 5001 // 5 = 1000.
                # So 1000 elements removed + 1 new added.
                # End size: 5001 - 1000 + 1 = 4002
                expected_size = (max_size + 1) - ((max_size + 1) // 5) + 1
                assert len(sec_module.POW_CACHE) == expected_size
