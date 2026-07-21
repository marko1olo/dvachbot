import unittest
from unittest.mock import patch
import os
import sys

# Ensure import paths work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from zaputin_mode import zaputin_transform

class TestZaputinMode(unittest.TestCase):
    def test_zaputin_transform_empty_text(self):
        """Test that empty or None text returns appropriately."""
        self.assertEqual(zaputin_transform(""), "")
        self.assertEqual(zaputin_transform(None), None)

    @patch('zaputin_mode.random.choice')
    @patch('zaputin_mode.random.random')
    def test_ideological_replacements(self, mock_random, mock_choice):
        """Test that ideological replacements apply correctly and preserve case."""
        # Ensure random effects like kancelarit caps and slogans don't interfere
        mock_random.return_value = 0.99

        # We need to control the output of random.choice for ideological replacement
        def mock_choice_func(seq):
            if isinstance(seq, list) and len(seq) > 0:
                return seq[0]
            return seq

        mock_choice.side_effect = mock_choice_func

        # 'устали' -> 'героически переутомились'
        result = zaputin_transform("устали")
        self.assertEqual(result, "героически переутомились")

        # Uppercase replacement
        # 'УСТАЛИ' -> 'ГЕРОИЧЕСКИ ПЕРЕУТОМИЛИСЬ'
        result = zaputin_transform("УСТАЛИ")
        self.assertEqual(result, "ГЕРОИЧЕСКИ ПЕРЕУТОМИЛИСЬ")

        # Capitalized replacement
        # 'Устали' -> 'Героически переутомились'
        result = zaputin_transform("Устали")
        self.assertEqual(result, "Героически переутомились")

    @patch('zaputin_mode.random.random')
    def test_zv_replacements(self, mock_random):
        """Test that З/з and В/в are replaced with Z/V."""
        mock_random.return_value = 0.99

        # Avoid words in the ideological dictionary to isolate this test
        text = "завтра ветер"
        result = zaputin_transform(text)
        self.assertEqual(result, "ZаVтра Vетер")

    @patch('zaputin_mode.random.choice')
    @patch('zaputin_mode.random.random')
    def test_kancelarit_english(self, mock_random, mock_choice):
        """Test that English words are wrapped with prefixes."""
        mock_random.return_value = 0.99

        def mock_choice_func(seq):
            # If it's the prefix list for english
            if isinstance(seq, list) and any("чужд" in s or "т.н." in s for s in seq):
                return "т.н."
            if isinstance(seq, list) and len(seq) > 0:
                return seq[0]
            return seq

        mock_choice.side_effect = mock_choice_func

        text = "apple is good"
        result = zaputin_transform(text)

        self.assertIn("т.н. «apple»", result)
        self.assertIn("т.н. «is»", result)
        self.assertIn("т.н. «good»", result)

    @patch('zaputin_mode.random.random')
    def test_kancelarit_map(self, mock_random):
        """Test static regex replacements from _KANCELARIT_MAP_COMPILED."""
        mock_random.return_value = 0.99

        # 'ошибка' -> 'отрицательный результат'
        # In `zaputin_transform`, `_apply_kancelarit` is called after the Z/V replacement.
        # This means the "з" in "результат" is not transformed to "Z", because the word
        # is injected in the _apply_kancelarit step!
        text = "ошибка"
        result = zaputin_transform(text)
        self.assertEqual(result, "отрицательный результат")

        # 'купил' -> 'произвел импортозамещение'
        # "проиZVел импортоZамещение" is WRONG. The replacement adds "произвел импортозамещение"
        # at the _apply_kancelarit step, which is AFTER Z/V replacement.
        text = "купил"
        result = zaputin_transform(text)
        self.assertEqual(result, "произвел импортозамещение")

    @patch('zaputin_mode.random.choice')
    @patch('zaputin_mode.random.random')
    def test_slogan_addition(self, mock_random, mock_choice):
        """Test that a patriotic slogan is added when text has > 3 words and random < 0.25."""
        # Set random to trigger slogan (e.g., 0.1 < 0.25)
        # Also triggers uppercase in _CAPS_IMPORTANT_PATTERN (0.1 < 0.15) for some words
        mock_random.return_value = 0.1
        mock_choice.return_value = "TEST SLOGAN!"

        # 4 words
        text = "один два три четыре"
        result = zaputin_transform(text)

        self.assertTrue(result.endswith("\n\n<b>TEST SLOGAN!</b>"))

        # Less than 4 words -> no slogan
        text_short = "один два три"
        result_short = zaputin_transform(text_short)
        self.assertFalse(result_short.endswith("\n\n<b>TEST SLOGAN!</b>"))

if __name__ == '__main__':
    unittest.main()
