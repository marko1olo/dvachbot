import unittest
from common.board_config import parse_channel_id, parse_token, parse_admins

class TestBoardConfig(unittest.TestCase):
    def test_parse_channel_id(self):
        # Happy paths
        self.assertEqual(parse_channel_id("12345"), 12345)
        self.assertEqual(parse_channel_id("-12345"), -12345)

        # Edge cases and error conditions
        self.assertIsNone(parse_channel_id(None))
        self.assertIsNone(parse_channel_id(""))
        self.assertIsNone(parse_channel_id("   "))
        self.assertIsNone(parse_channel_id("abc"))
        self.assertIsNone(parse_channel_id("-abc"))
        self.assertIsNone(parse_channel_id("123a"))

        # Leading/trailing spaces
        self.assertEqual(parse_channel_id(" 12345 "), 12345)
        self.assertEqual(parse_channel_id(" -12345 "), -12345)

    def test_parse_token(self):
        # Happy paths
        self.assertEqual(parse_token("my_token"), "my_token")
        self.assertEqual(parse_token(" my_token "), " my_token ")

        # Edge cases and error conditions
        self.assertIsNone(parse_token(None))
        self.assertIsNone(parse_token(""))
        self.assertIsNone(parse_token("   "))

    def test_parse_admins(self):
        # Happy paths
        self.assertEqual(parse_admins("123,456"), {123, 456})
        self.assertEqual(parse_admins("123, 456"), {123, 456})
        self.assertEqual(parse_admins(" 123 , 456 "), {123, 456})

        # Single admin
        self.assertEqual(parse_admins("123"), {123})

        # Duplicates (should be a set)
        self.assertEqual(parse_admins("123, 123"), {123})

        # Edge cases and error conditions
        self.assertEqual(parse_admins(""), set())
        self.assertEqual(parse_admins("   "), set())

        # Mixed valid and invalid
        self.assertEqual(parse_admins("123,abc,456"), {123, 456})
        self.assertEqual(parse_admins("abc,def"), set())

        # Note: parse_admins expects a string, testing with None might raise an error in real usage since it calls split() directly on raw, but raw.split(",") is used so raw shouldn't be None. We'll stick to string inputs.

if __name__ == "__main__":
    unittest.main()
