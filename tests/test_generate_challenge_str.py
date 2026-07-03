import pytest
from unittest.mock import patch

import site_tgach.security
import Dubsite_tgach.security

@pytest.mark.parametrize("security_module", [site_tgach.security, Dubsite_tgach.security])
class TestGenerateChallengeStr:
    @pytest.fixture(autouse=True)
    def setup_cache(self, security_module):
        # Reset cache before each test
        security_module.POW_CACHE.clear()
        yield
        security_module.POW_CACHE.clear()

    @patch("time.time")
    @patch("random.random")
    def test_basic_generation(self, mock_random, mock_time, security_module):
        mock_time.return_value = 1000.0
        mock_random.return_value = 0.5  # No random cleanup

        challenge = security_module.generate_challenge_str()

        assert isinstance(challenge, str)
        assert len(challenge) == 32  # token_hex(16) length
        assert challenge in security_module.POW_CACHE
        assert security_module.POW_CACHE[challenge] == 1600.0

    @patch("time.time")
    @patch("random.random")
    def test_expired_cleanup_via_random(self, mock_random, mock_time, security_module):
        mock_time.return_value = 2000.0
        mock_random.return_value = 0.05  # Triggers random cleanup (< 0.1)

        # Add expired and valid items
        security_module.POW_CACHE["expired1"] = 1500.0
        security_module.POW_CACHE["expired2"] = 1999.0
        security_module.POW_CACHE["valid1"] = 2500.0

        challenge = security_module.generate_challenge_str()

        assert "expired1" not in security_module.POW_CACHE
        assert "expired2" not in security_module.POW_CACHE
        assert "valid1" in security_module.POW_CACHE
        assert challenge in security_module.POW_CACHE

    @patch("time.time")
    @patch("random.random")
    def test_no_cleanup_when_not_triggered(self, mock_random, mock_time, security_module):
        mock_time.return_value = 2000.0
        mock_random.return_value = 0.5  # Does not trigger random cleanup

        # Cache is below MAX_POW_CACHE_SIZE
        security_module.POW_CACHE["expired1"] = 1500.0

        challenge = security_module.generate_challenge_str()

        # Expired item should still be there because cleanup wasn't triggered
        assert "expired1" in security_module.POW_CACHE
        assert challenge in security_module.POW_CACHE

    @patch("time.time")
    @patch("random.random")
    @patch("random.sample")
    def test_cleanup_triggered_by_max_size(self, mock_sample, mock_random, mock_time, security_module):
        mock_time.return_value = 2000.0
        mock_random.return_value = 0.5  # Does not trigger random cleanup

        max_size = security_module.MAX_POW_CACHE_SIZE
        # Fill cache to exceed max size with expired items
        for i in range(max_size + 1):
            security_module.POW_CACHE[f"expired_{i}"] = 1000.0

        mock_sample.side_effect = lambda keys, k: keys[:k]

        challenge = security_module.generate_challenge_str()

        # All expired items should be cleared
        # The new challenge is added
        assert len(security_module.POW_CACHE) == 1
        assert challenge in security_module.POW_CACHE
        assert mock_sample.called

    @patch("time.time")
    @patch("random.random")
    @patch("random.sample")
    def test_aggressive_cleanup(self, mock_sample, mock_random, mock_time, security_module):
        mock_time.return_value = 2000.0
        mock_random.return_value = 0.5

        max_size = security_module.MAX_POW_CACHE_SIZE

        # Add valid items to exceed max size
        # We use large values for timestamp to make them not expired
        for i in range(max_size + 1):
            security_module.POW_CACHE[f"valid_{i}"] = 3000.0

        def mock_sample_side_effect(population, k):
            return population[:k]

        mock_sample.side_effect = mock_sample_side_effect

        challenge = security_module.generate_challenge_str()

        # 20% of items should be removed
        num_removed = (max_size + 1) // 5
        expected_size = (max_size + 1) - num_removed + 1 # +1 for the new challenge

        assert len(security_module.POW_CACHE) == expected_size
        assert challenge in security_module.POW_CACHE
        assert mock_sample.called
