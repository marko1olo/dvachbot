import unittest
from unittest.mock import patch
import os
import sys

# Ensure import paths work
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from warhammer_mode import orkify, necronify

class TestWarhammerMode(unittest.TestCase):
    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.random.choice')
    def test_orkify_basic_replacement(self, mock_choice, mock_random):
        # We ensure no random vowel replacement or gluing happens
        mock_random.return_value = 0.99
        text = "СЕКРЕТНЫЙ ЧЕЛОВЕК ЕДЕТ НА ЁЖИКЕ"
        # С->З, Ч->Ш, К->Г, Е->Э, Ё->О
        # "ЗЭГРЭТНЫЙ ШЭЛОВЭГ ЭДЭТ НА ОЖИГЭ"
        result = orkify(text)
        self.assertEqual(result, "ЗЭГРЭТНЫЙ ШЭЛОВЭГ ЭДЭТ НА ОЖИГЭ")

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.random.choice')
    def test_orkify_vowel_replacement(self, mock_choice, mock_random):
        # "ИЫЯЮ"
        text = "ИХУ"
        # 1. glue check: False
        # 2. vowel loop: 'И' is in 'ИЫЯЮ'. random.random() < 0.5 -> 0.1. mock_choice returns 'О'
        # 3. -ДАККА check: random.random() < 0.15 -> 0.99 (no append)
        mock_random.side_effect = [0.1, 0.99]
        mock_choice.return_value = 'О'

        result = orkify(text)
        self.assertEqual(result, "ОХУ")

    @patch('warhammer_mode.random.random')
    def test_orkify_dakka_append(self, mock_random):
        text = "ОРК"
        # word = "ОРК" (becomes ОРГ)
        # 1. glue check: False
        # 2. vowel loop: no 'ИЫЯЮ', random.random not called
        # 3. -ДАККА check: random.random() < 0.15 -> 0.1 (append)
        mock_random.side_effect = [0.1]

        result = orkify(text)
        self.assertEqual(result, "ОРГ-ДАККА")

    @patch('warhammer_mode.random.random')
    def test_orkify_gluing(self, mock_random):
        text = "ТО АХ"
        # words = ["ТО", "АХ"]
        # word 1: "ТО"
        # - glue check: orked_words is empty -> False
        # - length > 2: False -> goes to else (append)

        # word 2: "АХ"
        # - glue check: orked_words[-1] is "ТО" (len 2). word is "АХ" (len 2)
        # random.random() < 0.5 -> 0.1 (glue!)

        mock_random.side_effect = [0.1]
        result = orkify(text)
        self.assertEqual(result, "ТОАХ")

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.random.randint')
    def test_necronify_with_injection(self, mock_randint, mock_random):
        text = "Hello world"
        mock_random.side_effect = [0.1, 0.9]
        mock_randint.return_value = 42

        result = necronify(text)
        expected = "++Анализ органической речи: ++0000000000101010++Hello world. ++Протокол выполнен.++"
        self.assertEqual(result, expected)

    @patch('warhammer_mode.random.random')
    def test_necronify_no_injection(self, mock_random):
        text = "Hello world"
        mock_random.return_value = 0.9

        result = necronify(text)
        expected = "++Анализ органической речи: Hello world. ++Протокол выполнен.++"
        self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()
