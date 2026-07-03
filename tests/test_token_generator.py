import sys
import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.token_generator import generate_unique_token, WORD_GROUPS

class TestTokenGenerator(unittest.IsolatedAsyncioTestCase):
    async def test_generate_first_try(self):
        # db_check_func returns False immediately
        async def mock_db_check(token):
            return False

        token = await generate_unique_token(mock_db_check)
        self.assertIsInstance(token, str)
        parts = token.split()
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[2].isdigit())
        self.assertTrue(10000 <= int(parts[2]) < 100000)

    async def test_generate_with_retries(self):
        # db_check_func returns True 3 times, then False
        self.attempts = 0
        async def mock_db_check(token):
            self.attempts += 1
            if self.attempts <= 3:
                return True
            return False

        token = await generate_unique_token(mock_db_check)
        self.assertEqual(self.attempts, 4)
        self.assertIsInstance(token, str)
        self.assertEqual(len(token.split()), 3)

    async def test_generate_fallback(self):
        # db_check_func always returns True
        self.attempts = 0
        async def mock_db_check(token):
            self.attempts += 1
            return True

        token = await generate_unique_token(mock_db_check)
        self.assertEqual(self.attempts, 10)
        self.assertIsInstance(token, str)
        # Fallback format: {adjective} {noun} {number}-{hex}
        parts = token.split()
        self.assertEqual(len(parts), 3)
        self.assertIn('-', parts[2])
        num_part, hex_part = parts[2].split('-')
        self.assertTrue(num_part.isdigit())
        self.assertEqual(len(hex_part), 4) # 2 bytes = 4 hex chars

    async def test_grammar_consistency(self):
        async def mock_db_check(token):
            return False

        token = await generate_unique_token(mock_db_check)
        parts = token.split()
        adj = parts[0]
        noun = parts[1]

        found_group = False
        for adj_group, noun_group in WORD_GROUPS:
            if adj in adj_group and noun in noun_group:
                found_group = True
                break
        self.assertTrue(found_group, f"Token '{token}' words not from the same grammar group")

if __name__ == '__main__':
    unittest.main()
