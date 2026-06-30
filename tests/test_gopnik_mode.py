import unittest
from unittest.mock import patch
import sys
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gopnik_mode import gopnik_transform, _gopnik_replacer, _apply_gopnik_phonetics, _apply_wolf_quote

class TestGopnikTransform(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(gopnik_transform(""), ('text', ""))
        self.assertEqual(gopnik_transform(None), ('text', ""))

    @patch("gopnik_mode.random.random")
    @patch("gopnik_mode.create_visual_post")
    def test_visual_post_creation(self, mock_create_visual, mock_random):
        mock_random.return_value = 0.1 # trigger visual post < 0.175
        mock_create_visual.return_value = b'fake_image_bytes'

        content_type, data = gopnik_transform("Hello")

        self.assertEqual(content_type, 'image')
        self.assertEqual(data, b'fake_image_bytes')
        mock_create_visual.assert_called_once()

    @patch("gopnik_mode.random.random")
    @patch("gopnik_mode.create_visual_post")
    def test_visual_post_fallback(self, mock_create_visual, mock_random):
        mock_random.return_value = 0.1 # trigger visual post < 0.175
        mock_create_visual.return_value = None # visual post fails

        content_type, data = gopnik_transform("Hello")

        self.assertEqual(content_type, 'text')
        self.assertTrue(isinstance(data, str))

    @patch("gopnik_mode.random.random")
    def test_text_transform_happy_path(self, mock_random):
        # Prevent any random additions (suffix, prefix, parasite words, wolf quote, physical actions)
        mock_random.return_value = 0.99

        text = "Здравствуйте, как у вас дела?"
        content_type, data = gopnik_transform(text)

        self.assertEqual(content_type, 'text')
        self.assertTrue(isinstance(data, str))
        # Depending on GOPNIK_REPLACEMENTS, it might change words or not
        # Let's verify it successfully completes the function
        self.assertTrue(len(data) > 0)

    def test_gopnik_replacer_caps(self):
        class MockMatch:
            def __init__(self, match_text):
                self.match_text = match_text
            def group(self, index):
                return self.match_text

        with patch("gopnik_mode.random.choice", return_value="здарова"):
            # Mock the replacement dictionary retrieval to test logic
            with patch.dict("gopnik_mode.GOPNIK_REPLACEMENTS", {"привет": ["здарова"]}):
                self.assertEqual(_gopnik_replacer(MockMatch("ПРИВЕТ")), "ЗДАРОВА")
                self.assertEqual(_gopnik_replacer(MockMatch("Привет")), "Здарова")
                self.assertEqual(_gopnik_replacer(MockMatch("привет")), "здарова")

        # Word not in dictionary should return original
        self.assertEqual(_gopnik_replacer(MockMatch("НеизвестноеСлово")), "НеизвестноеСлово")

    @patch("gopnik_mode.random.random")
    @patch("gopnik_mode.random.choice")
    @patch("gopnik_mode.random.randint")
    def test_transform_with_injections(self, mock_randint, mock_choice, mock_random):
        # Force all the random blocks to execute
        mock_random.return_value = 0.05
        # Prevent visual post creation by making text long enough (>=200) or we mock random only for the parts we want

        def random_side_effect():
            # first call is visual post (< 0.175), let's make it 0.5 to bypass
            if not hasattr(random_side_effect, 'calls'):
                random_side_effect.calls = 0
            random_side_effect.calls += 1

            if random_side_effect.calls == 1:
                return 0.5 # bypass visual
            return 0.1 # execute all other text modifications

        mock_random.side_effect = random_side_effect
        mock_choice.return_value = "бля"
        mock_randint.return_value = 1

        text = "Это длинное предложение с большим количеством слов чтобы все сработало."
        content_type, data = gopnik_transform(text)

        self.assertEqual(content_type, 'text')
        self.assertTrue(isinstance(data, str))
        self.assertTrue("бля" in data)

    @patch("gopnik_mode.random.random")
    def test_apply_wolf_quote(self, mock_random):
        mock_random.return_value = 0.1 # Trigger wolf quote

        # Test case: text has enough words and long enough sentences
        text = "Это очень длинное предложение. Оно состоит из более чем пяти слов."
        with patch("gopnik_mode.random.choice", return_value="Альберт Эйнштейн"):
            result = _apply_wolf_quote(text)
            self.assertIn("Брат, запомни", result)
            self.assertIn("Оно состоит из более чем пяти слов", result)
            self.assertIn("Альберт Эйнштейн", result)

        # Test case: not enough words
        short_text = "Короткий текст."
        result2 = _apply_wolf_quote(short_text)
        self.assertEqual(result2, short_text)

        # Test case: no sentences long enough
        many_short_sentences = "А. Б. В. Г. Д. Е. Ж."
        result3 = _apply_wolf_quote(many_short_sentences)
        self.assertEqual(result3, many_short_sentences)

    @patch("gopnik_mode.random.random")
    def test_apply_gopnik_phonetics(self, mock_random):
        mock_random.return_value = 0.99 # bypass actions insertion

        text = "что ты вообще сейчас делаешь"
        result = _apply_gopnik_phonetics(text)
        # Check phonetics map replacements
        self.assertIn("шо", result)
        self.assertIn("ты ёпт", result)
        self.assertIn("ваще", result)
        self.assertIn("ща", result)

        # Check bydlo tags
        result2 = _apply_gopnik_phonetics("Скажи мне")
        self.assertEqual(result2, "Скажи-ка мне")

if __name__ == "__main__":
    unittest.main()
