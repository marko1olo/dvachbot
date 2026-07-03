import sys
import os
import unittest
import hashlib
from unittest.mock import patch
import importlib.util

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(PROJECT_ROOT, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class TestVerifyPow(unittest.TestCase):
    def setUp(self):
        self.challenge = "test_challenge"
        self.nonce = "test_nonce"
        self.difficulty = 4
        self.modules = [
            ("dubsite", _load_module("Dubsite_tgach_security_isolated", "Dubsite_tgach/security.py")),
            ("site", _load_module("site_tgach_security_isolated", "site_tgach/security.py"))
        ]

    def test_difficulty_zero(self):
        for module_name, module in self.modules:
            with self.subTest(module=module_name):
                self.assertTrue(module.verify_pow(self.challenge, self.nonce, 0))

    def test_missing_challenge(self):
        for module_name, module in self.modules:
            with self.subTest(module=module_name):
                self.assertFalse(module.verify_pow(None, self.nonce, self.difficulty))
                self.assertFalse(module.verify_pow("", self.nonce, self.difficulty))

    def test_missing_nonce(self):
        for module_name, module in self.modules:
            with self.subTest(module=module_name):
                self.assertFalse(module.verify_pow(self.challenge, None, self.difficulty))
                self.assertFalse(module.verify_pow(self.challenge, "", self.difficulty))

    def test_challenge_not_in_cache(self):
        for module_name, module in self.modules:
            with self.subTest(module=module_name):
                with patch.dict(module.POW_CACHE, {}, clear=True):
                    self.assertFalse(module.verify_pow(self.challenge, self.nonce, self.difficulty))

    def test_invalid_nonce(self):
        for module_name, module in self.modules:
            with self.subTest(module=module_name):
                with patch.dict(module.POW_CACHE, {"test_challenge": 1234567890}, clear=True):
                    self.assertFalse(module.verify_pow(self.challenge, "wrong_nonce", self.difficulty))

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

        for module_name, module in self.modules:
            with self.subTest(module=module_name):
                with patch.dict(module.POW_CACHE, {challenge: 1234567890}, clear=True):
                    self.assertTrue(module.verify_pow(challenge, nonce, self.difficulty))
                    self.assertNotIn(challenge, module.POW_CACHE)

if __name__ == "__main__":
    unittest.main()
