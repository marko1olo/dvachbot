from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# We need to mock os.getenv to avoid the ValueError when SECRET_KEY is missing
with mock.patch.dict(os.environ, {"SECRET_KEY": "test_secret"}):
    from Dubsite_tgach.main import get_user_hash


class GetUserHashTests(unittest.TestCase):
    def setUp(self):
        self.secret = "test_secret"
        import Dubsite_tgach.main
        Dubsite_tgach.main.SECRET_KEY = self.secret

    def test_get_user_hash_with_integer(self):
        user_id = 12345
        expected_hash = hashlib.sha256((str(user_id) + self.secret).encode()).hexdigest()[:12]
        self.assertEqual(get_user_hash(user_id), expected_hash)

    def test_get_user_hash_with_string(self):
        user_id = "user123"
        expected_hash = hashlib.sha256((str(user_id) + self.secret).encode()).hexdigest()[:12]
        self.assertEqual(get_user_hash(user_id), expected_hash)

    def test_get_user_hash_with_empty_string(self):
        self.assertEqual(get_user_hash(""), "system")

    def test_get_user_hash_with_none(self):
        self.assertEqual(get_user_hash(None), "system")

    def test_get_user_hash_with_zero(self):
        self.assertEqual(get_user_hash(0), "system")

    def test_get_user_hash_length(self):
        self.assertEqual(len(get_user_hash(123)), 12)

if __name__ == "__main__":
    unittest.main()
