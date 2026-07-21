import unittest
from unittest.mock import patch
import zaputin_mode

class TestZaputinMode(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(zaputin_mode.zaputin_transform(""), "")
        self.assertEqual(zaputin_mode.zaputin_transform(None), None)

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
        self.assertIn("<b>", result)

if __name__ == '__main__':
    unittest.main()
