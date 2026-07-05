import unittest
from common.text_utils import add_you_to_my_posts_fast

class TestAddYouToMyPostsFast(unittest.TestCase):
    def test_add_you_when_user_is_author(self):
        text = "Hello >>123, how are you?"
        user_id = 42
        post_authors = {123: 42}

        result = add_you_to_my_posts_fast(text, user_id, post_authors)
        self.assertEqual(result, "Hello >>123 (You), how are you?")

    def test_no_change_when_user_not_author(self):
        text = "Hello >>123, how are you?"
        user_id = 42
        post_authors = {123: 99}

        result = add_you_to_my_posts_fast(text, user_id, post_authors)
        self.assertEqual(result, "Hello >>123, how are you?")

    def test_multiple_mentions(self):
        text = "Check out >>123 and >>456 and >>789"
        user_id = 42
        post_authors = {
            123: 42,
            456: 99,
            789: 42
        }

        result = add_you_to_my_posts_fast(text, user_id, post_authors)
        self.assertEqual(result, "Check out >>123 (You) and >>456 and >>789 (You)")

    def test_no_double_you(self):
        text = "Hello >>123 (You), what's up?"
        user_id = 42
        post_authors = {123: 42}

        result = add_you_to_my_posts_fast(text, user_id, post_authors)
        # Should remain the same, avoiding ">>123 (You) (You)"
        self.assertEqual(result, "Hello >>123 (You), what's up?")

    def test_fast_return_on_missing_pattern(self):
        text = "Hello world, no mentions here."
        user_id = 42
        post_authors = {123: 42}

        result = add_you_to_my_posts_fast(text, user_id, post_authors)
        self.assertEqual(result, "Hello world, no mentions here.")

    def test_fast_return_on_missing_text(self):
        text = ""
        user_id = 42
        post_authors = {123: 42}

        result = add_you_to_my_posts_fast(text, user_id, post_authors)
        self.assertEqual(result, "")

    def test_invalid_integer_in_pattern(self):
        # Though \d+ should only match digits, we test the try-except logic
        # if somehow non-integers are matched. We'll use a standard match.
        text = ">>99999999999999999999999999999999999999"
        user_id = 42
        post_authors = {99999999999999999999999999999999999999: 42}

        result = add_you_to_my_posts_fast(text, user_id, post_authors)
        self.assertEqual(result, ">>99999999999999999999999999999999999999 (You)")

if __name__ == '__main__':
    unittest.main()
