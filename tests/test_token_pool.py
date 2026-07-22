import unittest
from unittest.mock import patch
from common.token_pool import TokenRotator, HfPairRotator

class TestTokenRotator(unittest.TestCase):
    def test_empty_string(self):
        rotator = TokenRotator("")
        self.assertIsNone(rotator.get_token())
        self.assertIsNone(rotator.get_random())

    def test_single_token(self):
        rotator = TokenRotator("tok1")
        self.assertEqual(rotator.get_token(), "tok1")
        self.assertEqual(rotator.get_token(), "tok1")
        self.assertEqual(rotator.get_random(), "tok1")

    def test_multiple_tokens(self):
        rotator = TokenRotator(" tok1 , tok2,  tok3 ")
        self.assertEqual(rotator.get_token(), "tok1")
        self.assertEqual(rotator.get_token(), "tok2")
        self.assertEqual(rotator.get_token(), "tok3")
        self.assertEqual(rotator.get_token(), "tok1")
        self.assertIn(rotator.get_random(), ["tok1", "tok2", "tok3"])

    def test_remove_token(self):
        rotator = TokenRotator("tok1,tok2")
        rotator.remove_token("tok1")
        self.assertEqual(rotator.get_token(), "tok2")
        self.assertEqual(rotator.get_token(), "tok2")
        rotator.remove_token("tok2")
        self.assertIsNone(rotator.get_token())
        self.assertIsNone(rotator.get_random())

    def test_remove_token_not_exist(self):
        rotator = TokenRotator("tok1,tok2")
        rotator.remove_token("tok3")
        self.assertEqual(rotator.get_token(), "tok1")

class TestHfPairRotator(unittest.TestCase):
    @patch.dict('os.environ', {'HF_ACCOUNTS': ''})
    def test_empty_accounts(self):
        rotator = HfPairRotator()
        self.assertEqual(rotator.get_pair(), (None, None))

    @patch.dict('os.environ', {'HF_ACCOUNTS': 'tok1:repo1'})
    def test_single_account(self):
        rotator = HfPairRotator()
        self.assertEqual(rotator.get_pair(), ('tok1', 'repo1'))
        self.assertEqual(rotator.get_pair(), ('tok1', 'repo1'))

    @patch.dict('os.environ', {'HF_ACCOUNTS': 'tok1:repo1, tok2:repo2, tok3:repo1'})
    def test_interleaving_accounts(self):
        rotator = HfPairRotator()
        self.assertEqual(rotator.get_pair(), ('tok1', 'repo1'))
        self.assertEqual(rotator.get_pair(), ('tok2', 'repo2'))
        self.assertEqual(rotator.get_pair(), ('tok3', 'repo1'))
        self.assertEqual(rotator.get_pair(), ('tok1', 'repo1'))

    @patch.dict('os.environ', {'HF_ACCOUNTS': 'invalid, :repo1, tok1:'})
    def test_invalid_accounts(self):
        rotator = HfPairRotator()
        self.assertEqual(rotator.get_pair(), (None, None))

if __name__ == '__main__':
    unittest.main()
