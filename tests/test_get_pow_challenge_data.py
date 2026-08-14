import unittest
from unittest.mock import patch
import site_tgach.security as site_security

class TestGetPowChallengeData(unittest.TestCase):
    def test_get_pow_challenge_data_default(self):
        with patch.object(site_security, 'generate_challenge_str', return_value="mocked_challenge"):
            result = site_security.get_pow_challenge_data()
            self.assertEqual(result, {
                "challenge": "mocked_challenge",
                "difficulty": site_security.DEFAULT_POW_DIFFICULTY
            })

    def test_get_pow_challenge_data_custom_difficulty(self):
        with patch.object(site_security, 'generate_challenge_str', return_value="mocked_challenge_2"):
            result = site_security.get_pow_challenge_data(10)
            self.assertEqual(result, {
                "challenge": "mocked_challenge_2",
                "difficulty": 10
            })

if __name__ == '__main__':
    unittest.main()
