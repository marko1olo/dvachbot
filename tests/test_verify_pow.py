import sys
import os
import unittest
import hashlib
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Dubsite_tgach.security import verify_pow as dubsite_verify_pow
from site_tgach.security import verify_pow as site_verify_pow

class TestVerifyPow(unittest.TestCase):
    def setUp(self):
        self.challenge = "test_challenge"
        self.nonce = "test_nonce"
        self.difficulty = 4

    def test_difficulty_zero(self):
        for module_name, verify_pow_func in [("dubsite", dubsite_verify_pow), ("site", site_verify_pow)]:
            with self.subTest(module=module_name):
                self.assertTrue(verify_pow_func(self.challenge, self.nonce, 0))

    def test_missing_challenge(self):
        for module_name, verify_pow_func in [("dubsite", dubsite_verify_pow), ("site", site_verify_pow)]:
            with self.subTest(module=module_name):
                self.assertFalse(verify_pow_func(None, self.nonce, self.difficulty))
                self.assertFalse(verify_pow_func("", self.nonce, self.difficulty))

    def test_missing_nonce(self):
        for module_name, verify_pow_func in [("dubsite", dubsite_verify_pow), ("site", site_verify_pow)]:
            with self.subTest(module=module_name):
                self.assertFalse(verify_pow_func(self.challenge, None, self.difficulty))
                self.assertFalse(verify_pow_func(self.challenge, "", self.difficulty))

    def test_challenge_not_in_cache(self):
        for module_name, verify_pow_func, cache_path in [
            ("dubsite", dubsite_verify_pow, 'Dubsite_tgach.security.POW_CACHE'),
            ("site", site_verify_pow, 'site_tgach.security.POW_CACHE')
        ]:
            with self.subTest(module=module_name):
                with patch(cache_path, {}):
                    self.assertFalse(verify_pow_func(self.challenge, self.nonce, self.difficulty))

    def test_invalid_nonce(self):
        for module_name, verify_pow_func, cache_path in [
            ("dubsite", dubsite_verify_pow, 'Dubsite_tgach.security.POW_CACHE'),
            ("site", site_verify_pow, 'site_tgach.security.POW_CACHE')
        ]:
            with self.subTest(module=module_name):
                with patch(cache_path, {"test_challenge": 1234567890}):
                    self.assertFalse(verify_pow_func(self.challenge, "wrong_nonce", self.difficulty))

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

        for module_name, verify_pow_func, cache_path in [
            ("dubsite", dubsite_verify_pow, 'Dubsite_tgach.security.POW_CACHE'),
            ("site", site_verify_pow, 'site_tgach.security.POW_CACHE')
        ]:
            with self.subTest(module=module_name):
                mock_cache = {challenge: 1234567890}
                with patch(cache_path, mock_cache):
                    self.assertTrue(verify_pow_func(challenge, nonce, self.difficulty))
                    self.assertNotIn(challenge, mock_cache)

if __name__ == "__main__":
    unittest.main()
