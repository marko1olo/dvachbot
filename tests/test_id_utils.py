import unittest

from common.id_utils import generate_negative_id

class TestIdUtils(unittest.TestCase):
    def test_generate_negative_id_deterministic(self):
        """Test that the same input produces the same output."""
        token = "test_token_123"
        result1 = generate_negative_id(token)
        result2 = generate_negative_id(token)
        self.assertEqual(result1, result2)

    def test_generate_negative_id_is_negative(self):
        """Test that the output is always strictly negative."""
        tokens = ["test1", "token", "another_test", "", "1234567890", "a" * 100]
        for token in tokens:
            with self.subTest(token=token):
                result = generate_negative_id(token)
                self.assertLess(result, 0)

    def test_generate_negative_id_bounds(self):
        """Test that the output is within the bounds of a 32-bit signed integer."""
        # The lowest possible value is -(2147483647 - 1) - 1 = -2147483647
        # The highest possible value is -(0) - 1 = -1
        tokens = ["test1", "token", "another_test", "", "1234567890", "a" * 100]
        for token in tokens:
            with self.subTest(token=token):
                result = generate_negative_id(token)
                self.assertGreaterEqual(result, -2147483647)
                self.assertLessEqual(result, -1)

    def test_generate_negative_id_distinct(self):
        """Test that different inputs produce different outputs."""
        token1 = "test_token_1"
        token2 = "test_token_2"
        token3 = "completely_different_token"

        result1 = generate_negative_id(token1)
        result2 = generate_negative_id(token2)
        result3 = generate_negative_id(token3)

        self.assertNotEqual(result1, result2)
        self.assertNotEqual(result1, result3)
        self.assertNotEqual(result2, result3)

if __name__ == '__main__':
    unittest.main()
