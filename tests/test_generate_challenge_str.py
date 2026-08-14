import unittest
from unittest.mock import patch

import site_tgach.security as security_module

class TestGenerateChallengeStr(unittest.TestCase):
    def setUp(self):
        security_module.POW_CACHE.clear()

    def tearDown(self):
        security_module.POW_CACHE.clear()

    @patch("time.time")
    @patch("random.random")
    def test_basic_generation(self, mock_random, mock_time):
        mock_time.return_value = 1000.0
        mock_random.return_value = 0.5  # No random cleanup

        challenge = security_module.generate_challenge_str()

        self.assertIsInstance(challenge, str)
        self.assertEqual(len(challenge), 32)
        self.assertIn(challenge, security_module.POW_CACHE)
        self.assertEqual(security_module.POW_CACHE[challenge], 1600.0)

    @patch("time.time")
    @patch("random.random")
    def test_expired_cleanup_via_random(self, mock_random, mock_time):
        mock_time.return_value = 2000.0
        mock_random.return_value = 0.05  # Triggers random cleanup (< 0.1)

        security_module.POW_CACHE["expired1"] = 1500.0
        security_module.POW_CACHE["expired2"] = 1999.0
        security_module.POW_CACHE["valid1"] = 2500.0

        challenge = security_module.generate_challenge_str()

        self.assertNotIn("expired1", security_module.POW_CACHE)
        self.assertNotIn("expired2", security_module.POW_CACHE)
        self.assertIn("valid1", security_module.POW_CACHE)
        self.assertIn(challenge, security_module.POW_CACHE)

    @patch("time.time")
    @patch("random.random")
    def test_no_cleanup_when_not_triggered(self, mock_random, mock_time):
        mock_time.return_value = 2000.0
        mock_random.return_value = 0.5  # Does not trigger random cleanup

        security_module.POW_CACHE["expired1"] = 1500.0

        challenge = security_module.generate_challenge_str()

        self.assertIn("expired1", security_module.POW_CACHE)
        self.assertIn(challenge, security_module.POW_CACHE)

    @patch("time.time")
    @patch("random.random")
    @patch("random.sample")
    def test_cleanup_triggered_by_max_size(self, mock_sample, mock_random, mock_time):
        mock_time.return_value = 2000.0
        mock_random.return_value = 0.5

        max_size = security_module.MAX_POW_CACHE_SIZE
        for i in range(max_size + 1):
            security_module.POW_CACHE[f"expired_{i}"] = 1000.0

        mock_sample.side_effect = lambda keys, k: keys[:k]

        challenge = security_module.generate_challenge_str()

        self.assertEqual(len(security_module.POW_CACHE), 1)
        self.assertIn(challenge, security_module.POW_CACHE)
        self.assertTrue(mock_sample.called)

    @patch("time.time")
    @patch("random.random")
    @patch("random.sample")
    def test_aggressive_cleanup(self, mock_sample, mock_random, mock_time):
        mock_time.return_value = 2000.0
        mock_random.return_value = 0.5

        max_size = security_module.MAX_POW_CACHE_SIZE
        for i in range(max_size + 1):
            security_module.POW_CACHE[f"valid_{i}"] = 3000.0

        mock_sample.side_effect = lambda population, k: population[:k]

        challenge = security_module.generate_challenge_str()

        num_removed = (max_size + 1) // 5
        expected_size = (max_size + 1) - num_removed + 1

        self.assertEqual(len(security_module.POW_CACHE), expected_size)
        self.assertIn(challenge, security_module.POW_CACHE)
        self.assertTrue(mock_sample.called)

if __name__ == '__main__':
    unittest.main()
