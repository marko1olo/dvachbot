import os
import sys
import unittest
import asyncio
from unittest.mock import MagicMock

# Mock required environment variables
os.environ["SECRET_KEY"] = "test_secret"
os.environ["BOT_TOKEN"] = "123:test_bot_token"
os.environ["OPENAI_API_KEY"] = "sk-test_openai_api_key"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Setup event loop for async imports if not present
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# Mock problematic dependencies globally just for this test file
mocked_deps = [
    'pyrogram',
    'site_tgach.mtproto_client',
    'imagehash',
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
    def test_generate_negative_id_various_cases(self):
        cases = [
            ("test_token",),
            ("",),
            ("токена_тест_😊",),
            ("a" * 1000,),
            ("!@#$%^&*()_+",),
            ("    ",)
        ]

        previous_results = set()
        for (token,) in cases:
            with self.subTest(token=token):
                # Test determinism
                res1 = generate_negative_id_dub(token)
                res2 = generate_negative_id_dub(token)
                self.assertEqual(res1, res2)

                res3 = generate_negative_id_site(token)
                res4 = generate_negative_id_site(token)
                self.assertEqual(res3, res4)

                self.assertEqual(res1, res3)

                # Test bounds
                self.assertTrue(res1 < 0)
                self.assertTrue(res1 >= -2147483648)
                self.assertIsInstance(res1, int)

                # Test uniqueness
                self.assertNotIn(res1, previous_results)
                previous_results.add(res1)

    def test_generate_negative_id_invalid_input(self):
        cases = [None, 123, [], {}]
        for invalid_input in cases:
            with self.subTest(invalid_input=invalid_input):
                with self.assertRaises(AttributeError):
                    generate_negative_id_dub(invalid_input)
                with self.assertRaises(AttributeError):
                    generate_negative_id_site(invalid_input)

if __name__ == '__main__':
    unittest.main()
