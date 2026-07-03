import unittest
from unittest.mock import patch
import os
import sys
from pathlib import Path
import asyncio

# Setup env variables before importing main modules
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"
os.environ['ADMIN_CHAT_ID'] = '123456789'
os.environ['API_ID'] = '123'
os.environ['API_HASH'] = 'test_hash'
os.environ['BASE_URL'] = 'http://test.com'

try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import the module to test
from gopnik_mode import _apply_gopnik_phonetics

class TestGopnikMode(unittest.TestCase):
    @patch('random.random')
    def test_phonetic_replacements_ch(self, mock_random):
        """Test replacing 'ч' and 'Ч' with 'щ' and 'Щ' when random < 0.3"""
        # Ensure random is less than 0.3 to trigger replacement, but also
        # make sure to pass a value to prevent actions from triggering if possible,
        # but mock_random affects ALL random.random() calls.
        mock_random.return_value = 0.1

        # We need to mock random.randint and choice because random < 0.25 will trigger the actions
        with patch('random.choice', return_value=""), patch('random.randint', return_value=0):
            # Because action insertion modifies the string if words > 3, we'll keep tests short
            self.assertEqual(_apply_gopnik_phonetics("чё"), "щё")
            self.assertEqual(_apply_gopnik_phonetics("Чё"), "Щё")
            self.assertEqual(_apply_gopnik_phonetics("чаща"), "щаща")
            self.assertEqual(_apply_gopnik_phonetics("ЧАЩА"), "ЩАЩА")
            self.assertEqual(_apply_gopnik_phonetics("чч"), "щщ")

    @patch('random.random')
    def test_phonetic_replacements_ch_no_trigger(self, mock_random):
        """Test 'ч' and 'Ч' are NOT replaced when random >= 0.3"""
        mock_random.return_value = 0.5  # Prevents replacement AND action insertion

        self.assertEqual(_apply_gopnik_phonetics("чё"), "чё")
        self.assertEqual(_apply_gopnik_phonetics("Чё"), "Чё")
        self.assertEqual(_apply_gopnik_phonetics("чаща"), "чаща")

    @patch('random.random')
    def test_phonetic_replacements(self, mock_random):
        """Test phonetic replacements from _COMPILED_PHONETIC_MAP"""
        mock_random.return_value = 0.5  # Prevent random actions from being inserted

        # "что" -> "шо"
        self.assertEqual(_apply_gopnik_phonetics("а что это было?"), "а шо это было?")
        self.assertEqual(_apply_gopnik_phonetics("Что ты хочешь?"), "шо ты ёпт хочешь?") # Since regex replace overrides capitalization

        # "вообще" -> "ваще"
        self.assertEqual(_apply_gopnik_phonetics("вообще не понимаю"), "ваще не понимаю")
        self.assertEqual(_apply_gopnik_phonetics("Вообще нет"), "ваще нет")

        # "как бы" -> "кагбы"
        self.assertEqual(_apply_gopnik_phonetics("ну я как бы тут"), "ну я кагбы тут")

        # "сейчас" -> "ща"
        self.assertEqual(_apply_gopnik_phonetics("я сейчас приду"), "я ща приду")

        # "ты" -> "ты ёпт", "тебя" -> "тебя ебать"
        self.assertEqual(_apply_gopnik_phonetics("ты меня понял?"), "ты ёпт меня понял?")
        self.assertEqual(_apply_gopnik_phonetics("я тебя не звал"), "я тебя ебать не звал")

    @patch('random.random')
    def test_bydlo_tags(self, mock_random):
        """Test the addition of -ка to imperative verbs"""
        mock_random.return_value = 0.5  # Prevent random actions from being inserted

        self.assertEqual(_apply_gopnik_phonetics("скажи мне"), "скажи-ка мне")
        self.assertEqual(_apply_gopnik_phonetics("дай сюда"), "дай-ка сюда")
        self.assertEqual(_apply_gopnik_phonetics("смотри туда"), "смотри-ка туда")
        self.assertEqual(_apply_gopnik_phonetics("послушай внимательно"), "послушай-ка внимательно")

        self.assertEqual(_apply_gopnik_phonetics("Скажи мне"), "Скажи-ка мне")
        self.assertEqual(_apply_gopnik_phonetics("Дай сюда"), "Дай-ка сюда")
        self.assertEqual(_apply_gopnik_phonetics("Смотри туда"), "Смотри-ка туда")
        self.assertEqual(_apply_gopnik_phonetics("Послушай внимательно"), "Послушай-ка внимательно")

    @patch('random.random')
    @patch('random.randint')
    @patch('random.choice')
    def test_action_insertion_short_text(self, mock_choice, mock_randint, mock_random):
        """Test that actions are NOT inserted if word count is 3 or less"""
        mock_random.return_value = 0.1  # Less than 0.25, so it triggers the chance

        # 3 words -> len(words) is not > 3, should not insert
        result = _apply_gopnik_phonetics("один два три")
        self.assertEqual(result, "один два три")
        mock_randint.assert_not_called()
        mock_choice.assert_not_called()

    @patch('random.random')
    @patch('random.randint')
    @patch('random.choice')
    def test_action_insertion_long_text(self, mock_choice, mock_randint, mock_random):
        """Test that actions ARE inserted if word count is > 3 and random < 0.25"""
        mock_random.return_value = 0.1  # Chance triggers, meaning 'ч' in 'четыре' gets replaced too
        mock_choice.return_value = " *сплюнул семку*"
        mock_randint.return_value = 2  # Insert at index 2

        # 4 words -> len(words) > 3, should insert
        text = "один два три четыре"
        result = _apply_gopnik_phonetics(text)

        # Expected to insert action at index 2 (after "два")
        # 'четыре' becomes 'щетыре' because random.random() is 0.1 which is < 0.3
        expected = "один два  *сплюнул семку* три щетыре"
        self.assertEqual(result, expected)

    @patch('random.random')
    def test_action_insertion_no_chance(self, mock_random):
        """Test that actions are NOT inserted if random >= 0.25"""
        mock_random.return_value = 0.3  # Greater than 0.25, 'ч' -> 'щ' will NOT be triggered

        result = _apply_gopnik_phonetics("один два три четыре пять")
        self.assertEqual(result, "один два три четыре пять")

if __name__ == '__main__':
    unittest.main()
