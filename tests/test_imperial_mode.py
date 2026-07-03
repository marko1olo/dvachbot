import unittest
from unittest.mock import patch
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from imperial_mode import yatify_word

class TestYatifyWord(unittest.TestCase):
    @patch('imperial_mode.random.random')
    def test_mir_replacement(self, mock_random):
        """Test that 'мир' is correctly replaced with 'мiръ'."""
        mock_random.return_value = 1.0 # prevent random e replacements
        self.assertEqual(yatify_word('мир'), 'мiръ')
        self.assertEqual(yatify_word('вмире'), 'вмiръе')

    @patch('imperial_mode.random.random')
    def test_e_replacement_with_mocks_lower(self, mock_random):
        """Test replacement of lower 'е' into 'ѣ'."""
        # chance to replace is < 0.4
        # then if replaced, chance to be yat is 0.6 if middle, 0.2 if start/end
        mock_random.side_effect = [0.3, 0.1] # < 0.4, then < 0.2 (i=0, len=1 -> 0.2)
        self.assertEqual(yatify_word('е'), 'ѣ')

        # 'еее'
        # i=0: chance 0.2. r1 < 0.4, r2 < 0.2
        # i=1: chance 0.6. r1 < 0.4, r2 < 0.6
        # i=2: chance 0.2. r1 < 0.4, r2 < 0.2
        mock_random.side_effect = [
            0.3, 0.1, # ѣ
            0.3, 0.5, # ѣ
            0.3, 0.1  # ѣ
        ]
        self.assertEqual(yatify_word('еее'), 'ѣѣѣ')

        # 'место'
        # 'м'
        # 'е' i=1, len=5: chance 0.6.
        mock_random.side_effect = [0.3, 0.5]
        self.assertEqual(yatify_word('место'), 'мѣсто')

    @patch('imperial_mode.random.random')
    def test_e_replacement_with_mocks_upper(self, mock_random):
        """Test replacement of upper 'Е' into 'Ѣ'."""
        mock_random.side_effect = [0.3, 0.1]
        self.assertEqual(yatify_word('Е'), 'Ѣ')

        mock_random.side_effect = [0.3, 0.3] # 0.3 > 0.2 (chance for i=0 len=1)
        self.assertEqual(yatify_word('Е'), 'Е')

        # 'МЕСТО'
        mock_random.side_effect = [0.3, 0.5]
        self.assertEqual(yatify_word('МЕСТО'), 'МѢСТО')

    def test_empty_string(self):
        """Test empty string handling."""
        self.assertEqual(yatify_word(''), '')

    def test_no_e_or_mir(self):
        """Test string with no 'е' or 'мир'."""
        self.assertEqual(yatify_word('слово'), 'слово')
        self.assertEqual(yatify_word('СЛОВО'), 'СЛОВО')
        self.assertEqual(yatify_word('123'), '123')

if __name__ == '__main__':
    unittest.main()
