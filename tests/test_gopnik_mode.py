import unittest
import re
from unittest.mock import patch, Mock
import sys
import random

# Mock out PIL if it's not available
try:
    import PIL
except ImportError:
    sys.modules['PIL'] = Mock()
    sys.modules['PIL.Image'] = Mock()
    sys.modules['PIL.ImageDraw'] = Mock()
    sys.modules['PIL.ImageFont'] = Mock()
    sys.modules['PIL.ImageFilter'] = Mock()

# Import here to ensure mocks are in place
from gopnik_mode import _gopnik_replacer, GOPNIK_REPLACEMENTS

class TestGopnikReplacer(unittest.TestCase):
    def _create_match(self, word):
        match = Mock(spec=re.Match)
        match.group.return_value = word
        return match

    def test_missing_word(self):
        """Test that words not in dictionary are returned unchanged"""
        match = self._create_match("неизвестноеслово")
        self.assertEqual(_gopnik_replacer(match), "неизвестноеслово")

    @patch('gopnik_mode.random.choice')
    def test_list_replacement_lower(self, mock_choice):
        """Test replacement from a list of options in lowercase"""
        mock_choice.return_value = 'здарова'
        match = self._create_match("привет")
        self.assertEqual(_gopnik_replacer(match), "здарова")
        mock_choice.assert_called_once()

    @patch('gopnik_mode.random.choice')
    def test_list_replacement_title(self, mock_choice):
        """Test replacement from a list of options with initial capital letter"""
        mock_choice.return_value = 'здарова'
        match = self._create_match("Привет")
        self.assertEqual(_gopnik_replacer(match), "Здарова")

    @patch('gopnik_mode.random.choice')
    def test_list_replacement_upper(self, mock_choice):
        """Test replacement from a list of options with full uppercase"""
        mock_choice.return_value = 'здарова'
        match = self._create_match("ПРИВЕТ")
        self.assertEqual(_gopnik_replacer(match), "ЗДАРОВА")

    def test_string_replacement_lower(self):
        """Test replacement from a direct string (not list) in lowercase"""
        # "конечно" maps to "стопудово, бля" in GOPNIK_REPLACEMENTS
        match = self._create_match("конечно")
        self.assertEqual(_gopnik_replacer(match), "стопудово, бля")

    def test_string_replacement_title(self):
        """Test replacement from a direct string with initial capital letter"""
        match = self._create_match("Конечно")
        self.assertEqual(_gopnik_replacer(match), "Стопудово, бля")

    def test_string_replacement_upper(self):
        """Test replacement from a direct string with full uppercase"""
        match = self._create_match("КОНЕЧНО")
        self.assertEqual(_gopnik_replacer(match), "СТОПУДОВО, БЛЯ")

    def test_single_letter_upper(self):
        """Test that a single uppercase letter isn't fully uppercased if replacement is long,
        it should be capitalized (first letter upper) based on logic"""
        # original_word.isupper() and len(original_word) > 1 -> full caps
        # else if original_word and original_word[0].isupper() -> capitalize

        # Temporarily add a single-letter word to dict
        original_val = GOPNIK_REPLACEMENTS.get('я')
        GOPNIK_REPLACEMENTS['я'] = 'братан'

        match = self._create_match("Я")
        self.assertEqual(_gopnik_replacer(match), "Братан")

        # Cleanup
        if original_val is not None:
            GOPNIK_REPLACEMENTS['я'] = original_val
        else:
            del GOPNIK_REPLACEMENTS['я']

    def test_specific_replacements_lower(self):
        """Test specific replacements for ['друг', 'товарищ', 'пацан'] in lowercase"""
        for word in ["друг", "товарищ", "пацан"]:
            match = self._create_match(word)
            self.assertEqual(_gopnik_replacer(match), "братан")

    def test_specific_replacements_title(self):
        """Test specific replacements for ['друг', 'товарищ', 'пацан'] capitalized"""
        for word in ["Друг", "Товарищ", "Пацан"]:
            match = self._create_match(word)
            self.assertEqual(_gopnik_replacer(match), "Братан")

if __name__ == '__main__':
    unittest.main()
