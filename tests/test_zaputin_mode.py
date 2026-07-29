import unittest
from unittest.mock import patch
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from zaputin_mode import zaputin_transform, IDEOLOGICAL_REPLACEMENTS, PATRIOTIC_PHRASES

class TestZaputinMode(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(zaputin_transform(""), "")
        self.assertEqual(zaputin_transform(None), None)

    def test_zv_substitution(self):
        # 'ваза' has both в and з, but is not in IDEOLOGICAL_REPLACEMENTS
        text = "ваза"
        result = zaputin_transform(text)

        # 'в' -> 'V', 'а' -> 'а', 'з' -> 'Z', 'а' -> 'а' -> 'VаZа'
        self.assertIn("VаZа", result)

    @patch('zaputin_mode.random.choice')
    def test_ideological_replacement(self, mock_choice):
        # We need to mock random.choice so that ideological replacer returns a predictable string
        mock_choice.return_value = "США"

        result = zaputin_transform("Америка")

        # 'Америка' gets replaced by 'Сша' because of _zaputin_ideological_replacer capitalization rules
        # original is Title case, so replacement will be Title case
        self.assertIn("Сша", result)

        mock_choice.return_value = "наши западные непартнёры"
        result2 = zaputin_transform("запад") # lowercase
        # Z/V replacer will run after ideological: "наши Zападные непартнёры"
        self.assertIn("Zападные", result2)

    @patch('zaputin_mode.random.random')
    @patch('zaputin_mode.random.choice')
    def test_slogan_addition(self, mock_choice, mock_random):
        # For slogan addition, len(transformed_text.split()) > 3 and random.random() < 0.25
        mock_random.return_value = 0.1 # trigger slogan
        mock_choice.return_value = "СЛАВА РОССИИ!"

        # Needs to be at least 4 words
        text = "один два три четыре пять"

        result = zaputin_transform(text)
        self.assertIn("<b>СЛАВА РОССИИ!</b>", result)

    @patch('zaputin_mode.random.random')
    def test_kancelarit_application(self, mock_random):
        mock_random.return_value = 0.99 # Prevent slogan

        # "купил" -> "произвел импортозамещение"
        text = "Я купил машину"
        result = zaputin_transform(text)

        self.assertIn("произвел", result)
        self.assertIn("импортозамещение", result)
    def test_empty_string(self):
        self.assertEqual(zaputin_transform(""), "")
        self.assertEqual(zaputin_transform(None), None)
    def test_zv_replacement(self):
        # tests that 'з' and 'в' are replaced by 'Z' and 'V' (preserving case via mapping)
        # However, the code uses uppercase 'Z' and 'V' for both lowercase and uppercase.
        result = zaputin_mode.zaputin_transform("Заяц волк")
        self.assertIn("Z", result)
        self.assertIn("V", result)
    @patch('random.choice')
    def test_ideological_replacements(self, mock_choice):
        mock_choice.side_effect = lambda x: x[0]
        # Let's check IDEOLOGICAL_REPLACEMENTS for something like 'ноутбук' -> 'отечественный мобильный когитатор'
        result = zaputin_mode.zaputin_transform("ноутбук")
        # 'отечественный мобильный когитатор' -> 'отечестVенный мобильный когитатор' due to V replacement!
        self.assertIn("когитатор", result)
    @patch('random.random')
    @patch('random.choice')
    def test_kancelarit_and_caps(self, mock_choice, mock_random):
        mock_choice.side_effect = lambda x: x[0]
        # Always return 0.1 so it consistently triggers CAPS logic and slogans without StopIteration
        mock_random.return_value = 0.1
        # 'ошибка' -> 'отрицательный результат'
        result = zaputin_mode.zaputin_transform("ошибка")
        self.assertTrue(result.isupper() or "ОТРИЦАТЕЛЬНЫЙ" in result)
    @patch('random.choice')
    def test_english_words(self, mock_choice):
        mock_choice.side_effect = lambda x: x[0] # "т.н."
        result = zaputin_mode.zaputin_transform("hello world")
        self.assertIn("т.н. «hello»", result)
        self.assertIn("т.н. «world»", result)
    @patch('random.random')
    @patch('random.choice')
    def test_slogan(self, mock_choice, mock_random):
        mock_choice.side_effect = lambda x: x[0]
        mock_random.return_value = 0.1 # trigger slogan (0.1 < 0.25)
        # Needs > 3 words for slogan
        result = zaputin_mode.zaputin_transform("раз два три четыре")
        # Slogan is in PATRIOTIC_PHRASES
    def test_zaputin_transform_empty_text(self):
        """Test that empty or None text returns appropriately."""
        self.assertEqual(zaputin_mode.zaputin_transform(""), "")
        self.assertEqual(zaputin_mode.zaputin_transform(None), None)
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
    def test_zv_replacements(self, mock_random):
        """Test that З/з and В/в are replaced with Z/V."""
        mock_random.return_value = 0.99
        # Avoid words in the ideological dictionary to isolate this test
        text = "завтра ветер"
        self.assertEqual(result, "ZаVтра Vетер")
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
        self.assertIn("т.н. «apple»", result)
        self.assertIn("т.н. «is»", result)
        self.assertIn("т.н. «good»", result)
    def test_kancelarit_map(self, mock_random):
        """Test static regex replacements from _KANCELARIT_MAP_COMPILED."""
        mock_random.return_value = 0.99
        # In `zaputin_transform`, `_apply_kancelarit` is called after the Z/V replacement.
        # This means the "з" in "результат" is not transformed to "Z", because the word
        # is injected in the _apply_kancelarit step!
        text = "ошибка"
        self.assertEqual(result, "отрицательный результат")
        # 'купил' -> 'произвел импортозамещение'
        # "проиZVел импортоZамещение" is WRONG. The replacement adds "произвел импортозамещение"
        # at the _apply_kancelarit step, which is AFTER Z/V replacement.
        text = "купил"
        self.assertEqual(result, "произвел импортозамещение")
    def test_slogan_addition(self, mock_random, mock_choice):
        """Test that a patriotic slogan is added when text has > 3 words and random < 0.25."""
        # Set random to trigger slogan (e.g., 0.1 < 0.25)
        # Also triggers uppercase in _CAPS_IMPORTANT_PATTERN (0.1 < 0.15) for some words
        mock_choice.return_value = "TEST SLOGAN!"
        # 4 words
        text = "один два три четыре"
        self.assertTrue(result.endswith("\n\n<b>TEST SLOGAN!</b>"))
        # Less than 4 words -> no slogan
        text_short = "один два три"
        result_short = zaputin_transform(text_short)
        self.assertFalse(result_short.endswith("\n\n<b>TEST SLOGAN!</b>"))

if __name__ == '__main__':
    unittest.main()
