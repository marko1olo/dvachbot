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

if __name__ == '__main__':
    unittest.main()
