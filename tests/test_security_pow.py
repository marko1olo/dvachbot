import hashlib
import unittest
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from site_tgach.security import verify_pow
import site_tgach.security as security

class TestVerifyPow(unittest.TestCase):
    def setUp(self):
        # Clear the cache before each test
        security.POW_CACHE.clear()

    def test_difficulty_zero(self):
        self.assertTrue(verify_pow("chal", "nonce", difficulty=0))

    def test_empty_inputs(self):
        security.POW_CACHE["valid_chal"] = 1234567890

        self.assertFalse(verify_pow("", "nonce", difficulty=2))
        self.assertFalse(verify_pow("valid_chal", "", difficulty=2))
        self.assertFalse(verify_pow("", "", difficulty=2))

        self.assertIn("valid_chal", security.POW_CACHE)

    def test_challenge_not_in_cache(self):
        self.assertFalse(verify_pow("missing_chal", "nonce", difficulty=2))

    def test_invalid_nonce(self):
        chal = "my_challenge"
        security.POW_CACHE[chal] = 1234567890

        # Finding a known invalid nonce
        nonce = "invalid"
        target = "00"
        while hashlib.sha256(f"{chal}{nonce}".encode()).hexdigest().startswith(target):
            nonce += "1"

        self.assertFalse(verify_pow(chal, nonce, difficulty=2))
        # Ensure it remains in cache
        self.assertIn(chal, security.POW_CACHE)

    def test_valid_nonce(self):
        chal = "my_challenge_2"
        security.POW_CACHE[chal] = 1234567890

        difficulty = 2
        target = "0" * difficulty
        nonce = 0
        while not hashlib.sha256(f"{chal}{nonce}".encode()).hexdigest().startswith(target):
            nonce += 1

        nonce_str = str(nonce)
        self.assertTrue(verify_pow(chal, nonce_str, difficulty=difficulty))
        # Ensure it is removed from cache
        self.assertNotIn(chal, security.POW_CACHE)

if __name__ == "__main__":
    unittest.main()
