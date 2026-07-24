import unittest
from unittest.mock import patch

from main import check_post_numerals


class TestCheckPostNumerals(unittest.TestCase):
    def setUp(self):
        # We patch SPECIAL_NUMERALS_CONFIG to make the tests robust against
        # changes in the main configuration. We define a few levels here.
        self.mock_config = {
            3: {'label': 'Тройня', 'emojis': ('3',)},
            4: {'label': 'Квадрипл', 'emojis': ('4',)},
            5: {'label': 'Пентипл', 'emojis': ('5',)},
        }
        self.patcher = patch('main.SPECIAL_NUMERALS_CONFIG', self.mock_config)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_matched_numerals(self):
        """Test post numbers with a sufficient sequence of repeating identical trailing digits."""
        # Ends with 444 (length 3, matched)
        self.assertEqual(check_post_numerals(123444), 3)
        # Ends with 0000 (length 4, matched)
        self.assertEqual(check_post_numerals(50000), 4)
        # Ends with 11111 (length 5, matched)
        self.assertEqual(check_post_numerals(11111), 5)
        # The whole number is matching and it is 3 digits long (doesn't get evaluated because len < 4)
        self.assertIsNone(check_post_numerals(111))

    def test_unmatched_repeats(self):
        """Test repeating trailing digits that are not in the SPECIAL_NUMERALS_CONFIG keys."""
        # Only 2 repeating digits, config only has 3, 4, 5
        self.assertIsNone(check_post_numerals(12344))
        # 6 repeating digits, config only has 3, 4, 5
        self.assertIsNone(check_post_numerals(222222))

    def test_edge_cases(self):
        """Test short inputs, single digits, zero, and strings with no trailing repetitions."""
        # Less than 4 digits overall
        self.assertIsNone(check_post_numerals(0))
        self.assertIsNone(check_post_numerals(1))
        self.assertIsNone(check_post_numerals(99))
        self.assertIsNone(check_post_numerals(999))

        # 4 digits, but no repeats
        self.assertIsNone(check_post_numerals(1234))
        # 4 digits, repeats at start, not end
        self.assertIsNone(check_post_numerals(4412))
        # Repeats in middle
        self.assertIsNone(check_post_numerals(14442))


if __name__ == '__main__':
    unittest.main()
