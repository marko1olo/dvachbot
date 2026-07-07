import unittest
from unittest.mock import patch
import os
import sys

# Ensure import paths work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from zaputin_mode import zaputin_transform

class TestZaputinMode(unittest.TestCase):
    def test_empty_string(self):
        """Test that empty string returns empty string."""
        self.assertEqual(zaputin_transform(""), "")

    def test_none_input(self):
        """Test that None returns None."""
        self.assertIsNone(zaputin_transform(None))

    @patch('zaputin_mode.random.choice')
    @patch('zaputin_mode.random.random')
    def test_ideological_replacements(self, mock_random, mock_choice):
        """Test ideological replacement logic."""
        mock_random.return_value = 0.5

        def mock_choice_func(seq):
            if 'бывшая УССР' in seq:
                return 'бывшая УССР'
            return seq[0]

        mock_choice.side_effect = mock_choice_func

        result = zaputin_transform("украина")

        self.assertTrue("быVшая" in result)

    @patch('zaputin_mode.random.random')
    def test_zv_replacements(self, mock_random):
        """Test that Z and V are correctly substituted."""
        mock_random.return_value = 0.5

        result = zaputin_transform("Завтра великий день")
        # 'З' -> 'Z', 'автра' -> 'aVтра', 'великий' -> 'Vеликий'
        self.assertIn("ZаVтра", result)
        self.assertIn("Vеликий", result)

    @patch('zaputin_mode.random.choice')
    @patch('zaputin_mode.random.random')
    def test_patriotic_phrase_added(self, mock_random, mock_choice):
        """Test that a patriotic phrase is added when conditions are met."""
        # Condition: len(text.split()) > 3 and random.random() < 0.25
        mock_random.return_value = 0.1 # trigger capslock occasionally? capslock is < 0.15. So we mock random to return 0.2? Wait, < 0.25 is patriotic phrase.

        # let's make it 0.2, avoiding capslock (< 0.15) but triggering phrase (< 0.25)
        mock_random.return_value = 0.2

        def mock_choice_func(seq):
            if "СЛАВА РОССИИ!" in seq:
                return "СЛАВА РОССИИ!"
            return seq[0]

        mock_choice.side_effect = mock_choice_func

        text = "Раз два три четыре"
        result = zaputin_transform(text)

        self.assertTrue(result.endswith("\n\n<b>СЛАВА РОССИИ!</b>"))

    @patch('zaputin_mode.random.random')
    def test_patriotic_phrase_not_added_short_text(self, mock_random):
        """Test that a patriotic phrase is not added if text is too short."""
        mock_random.return_value = 0.2 # < 0.25, but length <= 3

        text = "Раз два три" # 3 words
        result = zaputin_transform(text)

        self.assertFalse("<b>" in result)

    @patch('zaputin_mode.random.random')
    def test_patriotic_phrase_not_added_probability(self, mock_random):
        """Test that a patriotic phrase is not added if random >= 0.25."""
        mock_random.return_value = 0.5 # >= 0.25

        text = "Раз два три четыре" # > 3 words
        result = zaputin_transform(text)

        self.assertFalse("<b>" in result)

if __name__ == '__main__':
    unittest.main()
