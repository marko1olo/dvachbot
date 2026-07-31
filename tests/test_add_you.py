import unittest
from main import add_you_to_my_posts_fast

class TestAddYouToMyPostsFast(unittest.TestCase):
    def test_basic_replacement(self):
        text = "Hello >>123"
        user_id = 5
        authors = {123: 5}
        result = add_you_to_my_posts_fast(text, user_id, authors)
        self.assertEqual(result, "Hello >>123 (You)")

    def test_no_text(self):
        self.assertEqual(add_you_to_my_posts_fast("", 5, {123: 5}), "")
        self.assertEqual(add_you_to_my_posts_fast(None, 5, {123: 5}), None)

    def test_no_arrows(self):
        self.assertEqual(add_you_to_my_posts_fast("Hello 123", 5, {123: 5}), "Hello 123")

    def test_not_author(self):
        self.assertEqual(add_you_to_my_posts_fast("Hello >>123", 5, {123: 6}), "Hello >>123")
        self.assertEqual(add_you_to_my_posts_fast("Hello >>123", 5, {}), "Hello >>123")

    def test_multiple_replacements(self):
        text = "Hello >>123 and >>456"
        user_id = 5
        authors = {123: 5, 456: 5}
        result = add_you_to_my_posts_fast(text, user_id, authors)
        self.assertEqual(result, "Hello >>123 (You) and >>456 (You)")

    def test_multiple_replacements_mixed_authors(self):
        text = "Hello >>123 and >>456"
        user_id = 5
        authors = {123: 5, 456: 6}
        result = add_you_to_my_posts_fast(text, user_id, authors)
        self.assertEqual(result, "Hello >>123 (You) and >>456")

    def test_already_replaced(self):
        text = "Hello >>123 (You)"
        user_id = 5
        authors = {123: 5}
        result = add_you_to_my_posts_fast(text, user_id, authors)
        self.assertEqual(result, "Hello >>123 (You)")

    def test_negative_user_id(self):
        text = "Hello >>123"
        user_id = -1
        authors = {123: -1}
        result = add_you_to_my_posts_fast(text, user_id, authors)
        self.assertEqual(result, "Hello >>123")

    def test_value_error_fallback(self):
        text = "Hello >>abc"
        user_id = 5
        authors = {}
        result = add_you_to_my_posts_fast(text, user_id, authors)
        self.assertEqual(result, "Hello >>abc")

if __name__ == "__main__":
    unittest.main()
