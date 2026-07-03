import sys
import os
import unittest
import hashlib
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Dubsite_tgach.security import verify_pow

class TestVerifyPow(unittest.TestCase):
    def setUp(self):
        self.challenge = "test_challenge"
        self.nonce = "test_nonce"
        self.difficulty = 4

    def test_difficulty_zero(self):
        self.assertTrue(verify_pow(self.challenge, self.nonce, 0))

    def test_missing_challenge(self):
        self.assertFalse(verify_pow(None, self.nonce, self.difficulty))
        self.assertFalse(verify_pow("", self.nonce, self.difficulty))

    def test_missing_nonce(self):
        self.assertFalse(verify_pow(self.challenge, None, self.difficulty))
        self.assertFalse(verify_pow(self.challenge, "", self.difficulty))

    @patch('Dubsite_tgach.security.POW_CACHE', {})
    def test_challenge_not_in_cache(self):
        self.assertFalse(verify_pow(self.challenge, self.nonce, self.difficulty))

    @patch('Dubsite_tgach.security.POW_CACHE', {"test_challenge": 1234567890})
    def test_invalid_nonce(self):
        self.assertFalse(verify_pow(self.challenge, "wrong_nonce", self.difficulty))

    def test_valid_nonce(self):
        challenge = "test_challenge"
        # Find a valid nonce
        nonce_val = 0
        target = "0" * self.difficulty
        while True:
            nonce = str(nonce_val)
            text = f"{challenge}{nonce}"
            res = hashlib.sha256(text.encode()).hexdigest()
            if res.startswith(target):
                break
            nonce_val += 1

        with patch('Dubsite_tgach.security.POW_CACHE', {challenge: 1234567890}) as mock_cache:
            self.assertTrue(verify_pow(challenge, nonce, self.difficulty))
            self.assertNotIn(challenge, mock_cache) # Verify challenge is removed from cache

if __name__ == "__main__":
    unittest.main()
