import os
import sys
import unittest
import asyncio
from unittest.mock import MagicMock

# Ensure PROJECT_ROOT is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Setup event loop for async imports if not present
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# Mock required environment variables
os.environ["SECRET_KEY"] = "test_secret"
os.environ["BOT_TOKEN"] = "123:test_bot_token"
os.environ["OPENAI_API_KEY"] = "sk-test_openai_api_key"

# Mock problematic dependencies globally just for this test file
mocked_deps = [
    'pyrogram',
    'site_tgach.mtproto_client',
    'imagehash',
    'site_tgach.neuro_poster'
]
for mod in mocked_deps:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

try:
    from Dubsite_tgach.main import generate_negative_id as generate_negative_id_dub
    from site_tgach.main import generate_negative_id as generate_negative_id_site
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

class TestGenerateNegativeId(unittest.TestCase):
    def test_deterministic_output(self):
        token = "test_token"
        # The prompt says MD5 is used, but the codebase actually uses SHA-256 and modulo operations.
        # For "test_token", SHA-256 is cc0af972..., [:8] is cc0af972 = 3423271282
        # -(3423271282 % 2147483647) - 1 = -1275787636
        expected = -1275787636

        res1 = generate_negative_id_dub(token)
        self.assertEqual(res1, expected)

        res2 = generate_negative_id_dub(token)
        self.assertEqual(res1, res2)

        res3 = generate_negative_id_site(token)
        self.assertEqual(res3, expected)

        res4 = generate_negative_id_site(token)
        self.assertEqual(res3, res4)

    def test_negative_value(self):
        token = "test_token_2"
        # For "test_token_2", SHA-256 is 70d7e87e..., [:8] is 70d7e87e = 1893197950
        # -(1893197950 % 2147483647) - 1 = -1893197951
        expected = -1893197951

        res = generate_negative_id_dub(token)
        self.assertTrue(res < 0)
        self.assertEqual(res, expected)

        res2 = generate_negative_id_site(token)
        self.assertTrue(res2 < 0)
        self.assertEqual(res2, expected)

    def test_different_tokens(self):
        token1 = "test_token_1"
        token2 = "test_token_2"
        self.assertNotEqual(generate_negative_id_dub(token1), generate_negative_id_dub(token2))

    def test_empty_string(self):
        # Empty string SHA-256 is e3b0c442... = 3820012610
        # -(3820012610 % 2147483647) - 1 = -1672528964
        expected = -1672528964
        res = generate_negative_id_dub("")
        self.assertTrue(res < 0)
        self.assertEqual(res, expected)

    def test_unicode_string(self):
        token = "токена_тест_😊"
        res = generate_negative_id_dub(token)
        self.assertTrue(res < 0)
        self.assertIsInstance(res, int)

if __name__ == '__main__':
    unittest.main()
