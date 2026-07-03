import unittest
import re
from unittest.mock import Mock, patch
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from imperial_mode import _imperial_replacer

class TestImperialReplacer(unittest.TestCase):
    @patch.dict('imperial_mode.WORD_REPLACEMENTS', {'интернет': ['мiровая паутина', 'электро-телеграфная сѣть'], 'сообщение': 'депеша'}, clear=True)
    @patch('imperial_mode.random.choice')
    def test_replacer_list_choice(self, mock_choice):
        mock_choice.return_value = 'мiровая паутина'
        match_mock = Mock(spec=re.Match)
        match_mock.group.return_value = 'интернет'

        result = _imperial_replacer(match_mock)

        self.assertEqual(result, 'мiровая паутина')
        mock_choice.assert_called_once_with(['мiровая паутина', 'электро-телеграфная сѣть'])

    @patch.dict('imperial_mode.WORD_REPLACEMENTS', {'интернет': ['мiровая паутина', 'электро-телеграфная сѣть'], 'сообщение': 'депеша'}, clear=True)
    @patch('imperial_mode.random.choice')
    def test_replacer_string(self, mock_choice):
        match_mock = Mock(spec=re.Match)
        match_mock.group.return_value = 'сообщение'

        result = _imperial_replacer(match_mock)

        self.assertEqual(result, 'депеша')
        mock_choice.assert_not_called()

    @patch.dict('imperial_mode.WORD_REPLACEMENTS', {'интернет': ['мiровая паутина', 'электро-телеграфная сѣть'], 'сообщение': 'депеша'}, clear=True)
    def test_replacer_upper(self):
        match_mock = Mock(spec=re.Match)
        match_mock.group.return_value = 'СООБЩЕНИЕ'

        result = _imperial_replacer(match_mock)

        self.assertEqual(result, 'ДЕПЕША')

    @patch.dict('imperial_mode.WORD_REPLACEMENTS', {'интернет': ['мiровая паутина', 'электро-телеграфная сѣть'], 'сообщение': 'депеша'}, clear=True)
    def test_replacer_title(self):
        match_mock = Mock(spec=re.Match)
        match_mock.group.return_value = 'Сообщение'

        result = _imperial_replacer(match_mock)

        self.assertEqual(result, 'Депеша')

    @patch.dict('imperial_mode.WORD_REPLACEMENTS', {'интернет': ['мiровая паутина', 'электро-телеграфная сѣть'], 'сообщение': 'депеша'}, clear=True)
    @patch('imperial_mode.random.choice')
    def test_replacer_upper_with_list(self, mock_choice):
        mock_choice.return_value = 'мiровая паутина'
        match_mock = Mock(spec=re.Match)
        match_mock.group.return_value = 'ИНТЕРНЕТ'

        result = _imperial_replacer(match_mock)

        self.assertEqual(result, 'МIРОВАЯ ПАУТИНА')
        mock_choice.assert_called_once_with(['мiровая паутина', 'электро-телеграфная сѣть'])

if __name__ == '__main__':
    unittest.main()
