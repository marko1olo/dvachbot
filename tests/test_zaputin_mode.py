import unittest
from unittest.mock import patch
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import zaputin_mode
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

    def test_zv_replacement(self):
        # tests that 'з' and 'в' are replaced by 'Z' and 'V' (preserving case via mapping)
        # However, the code uses uppercase 'Z' and 'V' for both lowercase and uppercase.
        result = zaputin_mode.zaputin_transform("Заяц волк")
        self.assertIn("Z", result)
        self.assertIn("V", result)
    @patch('random.random')
    @patch('random.choice')
    def test_ideological_replacements(self, mock_choice, mock_random):
        mock_choice.side_effect = lambda x: x[0]
        # Без этого тест флакал ~15%: zaputin_mode:1044 делает
        # `word.upper() if random.random() < 0.15`, и «когитатор» иногда
        # превращался в «КОГИТАТОР», роняя assertIn. 0.99 отключает и CAPS,
        # и добавление лозунга — как в соседних тестах этого файла.
        mock_random.return_value = 0.99
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
        self.assertIn("<b>", result)

if __name__ == '__main__':
    unittest.main()
