import os
import sys
import unittest
from unittest.mock import patch

# Standard environment variable mock
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Dubsite_tgach.main import format_bayan_label

class TestFormatBayanLabel(unittest.TestCase):
    def setUp(self):
        self.mock_translations = {
            'ru': {
                'bayan_low': ['Баян (мало)'],
                'bayan_mid': ['Баян (средне)'],
                'bayan_high': ['Баян (много)']
            },
            'en': {
                'bayan_low': ['Repost (low)'],
                'bayan_mid': ['Repost (mid)'],
                'bayan_high': ['Repost (high)']
            }
        }

    def test_count_none_or_less_than_two(self):
        self.assertEqual(format_bayan_label(None), "")
        self.assertEqual(format_bayan_label(0), "")
        self.assertEqual(format_bayan_label(-5), "")
        self.assertEqual(format_bayan_label(1), "")

    @patch('Dubsite_tgach.main.TRANSLATIONS')
    @patch('Dubsite_tgach.main.random.choice')
    def test_count_low(self, mock_choice, mock_translations):
        mock_translations.get.side_effect = lambda k, default: self.mock_translations.get(k, default)
        mock_translations.__getitem__.side_effect = lambda k: self.mock_translations[k]

        # We also need to configure random.choice to return the first element of the list passed to it
        mock_choice.side_effect = lambda seq: seq[0]

        # Count 2, 3 -> low
        for count in [2, 3]:
            with self.subTest(count=count):
                self.assertEqual(format_bayan_label(count), f"♻️ Баян (мало) ({count})")

    @patch('Dubsite_tgach.main.TRANSLATIONS')
    @patch('Dubsite_tgach.main.random.choice')
    def test_count_mid(self, mock_choice, mock_translations):
        mock_translations.get.side_effect = lambda k, default: self.mock_translations.get(k, default)
        mock_translations.__getitem__.side_effect = lambda k: self.mock_translations[k]

        mock_choice.side_effect = lambda seq: seq[0]

        # Count 4..10 -> mid
        for count in [4, 5, 10]:
            with self.subTest(count=count):
                self.assertEqual(format_bayan_label(count), f"♻️ Баян (средне) ({count})")

    @patch('Dubsite_tgach.main.TRANSLATIONS')
    @patch('Dubsite_tgach.main.random.choice')
    def test_count_high(self, mock_choice, mock_translations):
        mock_translations.get.side_effect = lambda k, default: self.mock_translations.get(k, default)
        mock_translations.__getitem__.side_effect = lambda k: self.mock_translations[k]

        mock_choice.side_effect = lambda seq: seq[0]

        # Count > 10 -> high
        for count in [11, 20, 100]:
            with self.subTest(count=count):
                self.assertEqual(format_bayan_label(count), f"♻️ Баян (много) ({count})")

    @patch('Dubsite_tgach.main.TRANSLATIONS')
    @patch('Dubsite_tgach.main.random.choice')
    def test_different_language(self, mock_choice, mock_translations):
        mock_translations.get.side_effect = lambda k, default: self.mock_translations.get(k, default)
        mock_translations.__getitem__.side_effect = lambda k: self.mock_translations[k]

        mock_choice.side_effect = lambda seq: seq[0]

        self.assertEqual(format_bayan_label(5, lang='en'), f"♻️ Repost (mid) (5)")

    @patch('Dubsite_tgach.main.TRANSLATIONS')
    @patch('Dubsite_tgach.main.random.choice')
    def test_missing_language_fallback(self, mock_choice, mock_translations):
        mock_translations.get.side_effect = lambda k, default: self.mock_translations.get(k, default)
        mock_translations.__getitem__.side_effect = lambda k: self.mock_translations[k]

        mock_choice.side_effect = lambda seq: seq[0]

        # 'jp' not in mock_translations, falls back to 'ru' (which is the default argument in get)
        self.assertEqual(format_bayan_label(5, lang='jp'), f"♻️ Баян (средне) (5)")

    @patch('Dubsite_tgach.main.TRANSLATIONS')
    @patch('Dubsite_tgach.main.random.choice')
    def test_missing_key_fallback(self, mock_choice, mock_translations):
        # Return empty dict for any language, triggering default ["Баян"]
        mock_translations.get.return_value = {}
        mock_translations.__getitem__.return_value = {}

        mock_choice.side_effect = lambda seq: seq[0]

        self.assertEqual(format_bayan_label(5), f"♻️ Баян (5)")

if __name__ == '__main__':
    unittest.main()
