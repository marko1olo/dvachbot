import unittest
import os
import asyncio

# Mock environment variables before importing
os.environ['SECRET_KEY'] = 'test_secret_key'
os.environ['BOT_TOKEN'] = 'test_bot_token'
os.environ['OPENAI_API_KEY'] = 'test_openai_api_key'

# Create and set new event loop to avoid Pyrogram/asyncio errors
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from Dubsite_tgach.main import pluralize_russian

class TestPluralizeRussian(unittest.TestCase):
    def setUp(self):
        self.words = ("яблоко", "яблока", "яблок")

    def test_one(self):
        # 1, 21, 31, 101, etc.
        self.assertEqual(pluralize_russian(1, *self.words), "яблоко")
        self.assertEqual(pluralize_russian(21, *self.words), "яблоко")
        self.assertEqual(pluralize_russian(101, *self.words), "яблоко")

    def test_few(self):
        # 2-4, 22-24, 102-104, etc.
        for n in [2, 3, 4, 22, 23, 24, 102, 103, 104]:
            self.assertEqual(pluralize_russian(n, *self.words), "яблока")

    def test_many(self):
        # 0, 5-20, 25-30, 111-114, etc.
        for n in [0, 5, 6, 9, 10, 11, 12, 13, 14, 15, 20, 25, 30, 111, 112, 113, 114]:
            self.assertEqual(pluralize_russian(n, *self.words), "яблок")

    def test_string_inputs(self):
        # Function accepts count as string
        self.assertEqual(pluralize_russian("1", *self.words), "яблоко")
        self.assertEqual(pluralize_russian("2", *self.words), "яблока")
        self.assertEqual(pluralize_russian("5", *self.words), "яблок")

    def test_invalid_inputs(self):
        # Test error handling (ValueError, TypeError) returns "many"
        self.assertEqual(pluralize_russian("invalid", *self.words), "яблок")
        self.assertEqual(pluralize_russian(None, *self.words), "яблок")
        self.assertEqual(pluralize_russian(3.14, *self.words), "яблока") # Note: int(3.14) is 3, which is "few"
        self.assertEqual(pluralize_russian([1], *self.words), "яблок")

if __name__ == '__main__':
    unittest.main()
