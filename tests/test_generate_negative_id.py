import unittest
from common.token_generator import generate_negative_id

class TestGenerateNegativeId(unittest.TestCase):
    def test_consistent_generation(self):
        # The id should be consistently generated for the same input string
        token1 = "test_token_123"
        token2 = "test_token_123"
        self.assertEqual(generate_negative_id(token1), generate_negative_id(token2))

    def test_always_negative(self):
        # The generated id should always be negative
        tokens = ["test", "another_test", "12345", "", "a_very_long_string_to_hash_for_testing_negative_generation"]
        for token in tokens:
            self.assertLess(generate_negative_id(token), 0)

    def test_different_inputs_yield_different_ids(self):
        # Different input strings should yield different ids
        token1 = "input_A"
        token2 = "input_B"
        self.assertNotEqual(generate_negative_id(token1), generate_negative_id(token2))

    def test_bounds_checking(self):
        # The absolute value does not exceed max int32 bounds since it's -(val % 2147483647) - 1
        tokens = ["token1", "token2", "token3", "token4", "token5"]
        for token in tokens:
            val = generate_negative_id(token)
            # The value should be negative and not less than -2147483648
            self.assertTrue(-2147483648 <= val < 0)

if __name__ == "__main__":
    unittest.main()
