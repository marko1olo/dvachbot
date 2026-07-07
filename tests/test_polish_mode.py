import unittest
from unittest.mock import patch
import os
import sys

# Ensure import paths work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We need to mock mode_visuals early to avoid heavy imports/errors if it has external dependencies not present in tests
sys.modules['mode_visuals'] = unittest.mock.MagicMock()

from polish_mode import polish_transform

class TestPolishMode(unittest.TestCase):
    def test_polish_transform_empty_text(self):
        """Test that empty or None text returns appropriately."""
        result = polish_transform("")
        self.assertEqual(result, ('text', ""))

        result = polish_transform(None)
        self.assertEqual(result, ('text', ""))

    @patch('polish_mode.random.random')
    @patch('polish_mode.create_visual_post')
    def test_polish_transform_short_text_kurwa(self, mock_create_visual, mock_random):
        """Test short messages (<= 2 words) get kurwa appended and no image if random fails."""
        # For word_count <= 2:
        # First random.random() check for kurwa: < 0.4. Let's make it 0.1 to trigger.
        # Second random.random() check for visual chance: < 0.25. Let's make it 0.99 to fail.
        mock_random.side_effect = [0.1, 0.99]

        result = polish_transform("Hello")
        self.assertEqual(result, ('text', "Hello, kurwa"))
        mock_create_visual.assert_not_called()

    @patch('polish_mode.random.random')
    @patch('polish_mode.create_visual_post')
    def test_polish_transform_short_text_visual(self, mock_create_visual, mock_random):
        """Test short messages can trigger visual generation."""
        # For word_count <= 2:
        # First random.random() check for kurwa: < 0.4. Let's make it 0.99 to fail.
        # Second random.random() check for visual chance: < 0.25. Let's make it 0.1 to trigger.
        mock_random.side_effect = [0.99, 0.1]
        mock_create_visual.return_value = b'fake_image_bytes'

        result = polish_transform("Short text", header="Test")
        self.assertEqual(result, ('image', b'fake_image_bytes'))
        mock_create_visual.assert_called_once_with('polish', "Short text", "Test")

    @patch('polish_mode.random.random')
    @patch('polish_mode.create_visual_post')
    def test_polish_transform_long_text_visual(self, mock_create_visual, mock_random):
        """Test longer messages (< 180 chars) can trigger visual generation."""
        # word_count > 2.
        # Pipeline Stage 2: Kurwa-comma injection (for each comma, chance < 0.4). No commas.
        # Pipeline Stage 3: Ending dot transformation (chance < 0.30). No ending dot.
        # Pipeline Stage 4: Prefix (chance < 0.35). Return 0.99 to fail.
        # Pipeline Stage 5: Suffix (chance < 0.55). Return 0.99 to fail.
        # Pipeline Stage 6: Mid-sentence injection (chance < 0.25, if word_count > 5). word_count=3.
        # Pipeline Stage 7: Pseudo-Polish Orthography (chance <= 0.4 to apply, >0.4 to skip). Return 0.99 to skip.
        # Visual generation chance (chance < 0.25, len < 180). Return 0.1 to trigger.

        mock_random.side_effect = [0.99, 0.99, 0.99, 0.1]
        mock_create_visual.return_value = b'fake_image_bytes'

        result = polish_transform("Three words text")
        self.assertEqual(result, ('image', b'fake_image_bytes'))
        mock_create_visual.assert_called_once_with('polish', "Three words text", None)

    @patch('polish_mode.random.random')
    def test_polish_transform_bypass_all_randoms(self, mock_random):
        """Test text transformation pipeline with all probabilistic effects bypassed."""
        # Ensure all random.random() checks return 0.99 (failing probability checks)
        mock_random.return_value = 0.99

        # Use words that will trigger basic dictionary replacement to verify it works
        # 'лицо' -> 'morda' or similar (let's assume it picks one if it's a list, but wait,
        # _stage_word_replacement uses random.choice if it's a list. We should mock choice too if needed.
        # But 'телефон' -> ['telefon', 'komórka'], 'огонь' -> 'ogień'.
        input_text = "Большой огонь горит."
        # 'огонь' -> 'ogień', 'горит' -> 'pali się' or 'fajczy się'

        result_type, result_text = polish_transform(input_text)

        self.assertEqual(result_type, 'text')
        self.assertIsInstance(result_text, str)
        self.assertIn("ogień", result_text.lower())

        # Make sure no kurwa commas or prefixes/suffixes were added since random is bypassed
        self.assertNotIn("kurwa", result_text.lower())

if __name__ == '__main__':
    unittest.main()
