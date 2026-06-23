import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Add project root to sys.path to allow importing from Dubsite_tgach
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gopnik_mode import gopnik_transform

class TestGopnikMode(unittest.TestCase):
    def test_empty_string(self):
        """Test that an empty string returns an empty text tuple."""
        self.assertEqual(gopnik_transform(""), ('text', ""))
        self.assertEqual(gopnik_transform(None), ('text', ""))

    @patch('gopnik_mode.random.random')
    @patch('gopnik_mode.random.choice')
    @patch('gopnik_mode.random.randint')
    def test_basic_replacement(self, mock_randint, mock_choice, mock_random):
        # Prevent any random blocks from executing (image, replacements, etc.)
        mock_random.return_value = 0.99
        # Mock choice to return the first option, for example, for 'привет' it is 'здарова'
        # Since random.choice is used in multiple places, we define a side_effect
        def choice_side_effect(seq):
            if isinstance(seq, list) or isinstance(seq, tuple):
                return seq[0]
            return seq
        mock_choice.side_effect = choice_side_effect

        result_type, result_data = gopnik_transform("Привет мир!")
        self.assertEqual(result_type, 'text')
        # Check that "Привет" (capitalized) becomes "Здарова" (capitalized)
        self.assertIn("Здарова", result_data)

    @patch('gopnik_mode.random.random')
    @patch('gopnik_mode.create_visual_post')
    def test_image_generation(self, mock_create_visual_post, mock_random):
        # Trigger image creation condition
        # gopnik_mode checks: random.random() < 0.175 and len(transformed_text) < 200
        # By setting random to 0.01, it triggers.
        # But we must ensure it doesn't trigger subsequent randoms in a way that crashes,
        # so we can mock random.random as a side effect if needed, but it's okay because
        # gopnik_transform returns early if image is returned!
        mock_random.return_value = 0.01
        mock_create_visual_post.return_value = b'fake_image_bytes'

        result_type, result_data = gopnik_transform("Some text to transform")
        self.assertEqual(result_type, 'image')
        self.assertEqual(result_data, b'fake_image_bytes')
        mock_create_visual_post.assert_called_once()

    @patch('gopnik_mode.random.random')
    @patch('gopnik_mode.random.choice')
    @patch('gopnik_mode.random.randint')
    def test_parasite_word_injection(self, mock_randint, mock_choice, mock_random):
        # Let's trigger parasite word injection:
        # random.random() < 0.4 for parasite.
        # Other randoms:
        # < 0.175 image (0.9 here)
        # < 0.8 tsya (0.9)
        # < 0.8 ться (0.9)
        # < 0.8 ешь (0.9)
        # < 0.25 phonetics (0.9)
        # < 0.4 parasite (0.1 here!)
        # < 0.5 suffix (0.9)
        # < 0.25 prefix (0.9)
        # < 0.25 wolf quote (0.9)

        # Generator for random to give specific values:
        def random_side_effect():
            yield 0.9 # image
            yield 0.9 # tsya
            yield 0.9 # ться
            yield 0.9 # ешь
            # _apply_gopnik_phonetics calls random.random() < 0.25
            yield 0.9 # phonetics
            yield 0.1 # parasite word (word_count > 3 and < 0.4)
            yield 0.9 # suffix
            yield 0.9 # prefix
            yield 0.9 # wolf quote
            while True: yield 0.9

        # Need to handle random in _gopnik_replacer (using random.choice) - we don't call random.random() there.
        mock_random.side_effect = random_side_effect()

        mock_choice.return_value = "бля"
        # Mock randint for injection point. words = ['Один', 'два', 'три', 'четыре']
        mock_randint.return_value = 2 # Insert after 'два'

        result_type, result_data = gopnik_transform("Один два три четыре")
        self.assertEqual(result_type, 'text')
        self.assertEqual(result_data, "Один два бля три четыре")

    @patch('gopnik_mode.random.random')
    @patch('gopnik_mode.random.choice')
    def test_prefix_and_suffix(self, mock_choice, mock_random):
        # Trigger suffix and prefix
        # We need random to return < 0.5 for suffix, < 0.25 for prefix
        def random_side_effect():
            yield 0.9 # image
            yield 0.9 # tsya
            yield 0.9 # ться
            yield 0.9 # ешь
            yield 0.9 # phonetics
            yield 0.9 # parasite (word_count > 3, so random will be called if words > 3)
            yield 0.1 # suffix (< 0.5)
            yield 0.1 # prefix (< 0.25)
            yield 0.9 # wolf quote
            while True: yield 0.9

        mock_random.side_effect = random_side_effect()

        def choice_side_effect(seq):
            if ", бля" in seq: return ", бля"
            if "Чисто " in seq: return "Чисто "
            if isinstance(seq, list) or isinstance(seq, tuple):
                return seq[0]
            return seq
        mock_choice.side_effect = choice_side_effect

        result_type, result_data = gopnik_transform("Просто текст чтобы было больше слов.")
        self.assertEqual(result_type, 'text')
        # "текст" is replaced with "малява" by GOPNIK_REPLACEMENTS
        self.assertEqual(result_data, "Чисто Просто малява чтобы было больше слов, бля.")

    @patch('gopnik_mode.random.random')
    @patch('gopnik_mode.random.choice')
    def test_wolf_quote(self, mock_choice, mock_random):
        # Trigger wolf quote (random < 0.25 and len > 5)
        def random_side_effect():
            yield 0.9 # image
            yield 0.9 # tsya
            yield 0.9 # ться
            yield 0.9 # ешь
            yield 0.9 # phonetics
            yield 0.9 # parasite
            yield 0.9 # suffix
            yield 0.9 # prefix
            yield 0.1 # wolf quote (< 0.25)
            while True: yield 0.9

        mock_random.side_effect = random_side_effect()
        mock_choice.return_value = "Братва"

        text = "Это длинное предложение для того чтобы проверить цитату волка."
        result_type, result_data = gopnik_transform(text)
        self.assertEqual(result_type, 'text')

        # Expected quote part
        self.assertIn("Брат, запомни", result_data)
        self.assertIn("АУФ 🐺", result_data)
        self.assertIn("(с) Братва", result_data)


if __name__ == '__main__':
    unittest.main()
