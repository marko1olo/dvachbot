import sys
import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.token_pool import TokenRotator

class TestTokenRotator(unittest.TestCase):
    def test_remove_token_until_empty(self):
        pool = TokenRotator("tok1, tok2")
        self.assertEqual(pool.get_token(), "tok1")
        pool.remove_token("tok1")
        self.assertEqual(pool.get_token(), "tok2")
        pool.remove_token("tok2")
        self.assertIsNone(pool.get_token())
        self.assertIsNone(pool.get_random())

    def test_remove_nonexistent_token(self):
        pool = TokenRotator("tok1, tok2")
        pool.remove_token("tok3")
        self.assertEqual(len(pool.tokens), 2)

    def test_remove_token_resets_iterator(self):
        pool = TokenRotator("tok1, tok2, tok3")
        self.assertEqual(pool.get_token(), "tok1")
        pool.remove_token("tok2")
        # Since the iterator is reset, getting the next token should return "tok1" again or "tok3" if we look at the new list ["tok1", "tok3"].
        # Actually, if we reset it with itertools.cycle(self.tokens), next() will return the first element.
        self.assertEqual(pool.get_token(), "tok1")

if __name__ == '__main__':
    unittest.main()
