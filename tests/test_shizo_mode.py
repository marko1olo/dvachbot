import unittest
from unittest.mock import patch
import os
import sys

# Ensure import paths work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shizo_mode import shizo_transform

class TestShizoMode(unittest.TestCase):
    def test_shizo_transform_empty_text(self):
        """Test that empty or None text returns appropriately."""
        result = shizo_transform("")
        self.assertEqual(result, ('text', ""))

        result = shizo_transform(None)
        self.assertEqual(result, ('text', ""))

    @patch('shizo_mode.random.random')
    @patch('shizo_mode.random.choice')
    def test_shizo_transform_critical_override(self, mock_choice, mock_random):
        """Test Stage 0: critical override triggered by 5% chance."""
        # Force critical override
        mock_random.return_value = 0.01  # < 0.05
        mock_choice.return_value = "CRITICAL OVERRIDE!"

        result = shizo_transform("Some regular text here")
        self.assertEqual(result, ('text', "CRITICAL OVERRIDE!"))

    @patch('shizo_mode.random.random')
    @patch('shizo_mode._try_create_visual')
    def test_shizo_transform_image_generation(self, mock_try_create_visual, mock_random):
        """Test Stage 0.5: visual generation triggered for short texts."""
        # Bypass critical override (>=0.05), hit image generation (<0.25)
        # Stage 0: 0.1
        # Stage 0.5: 0.1
        mock_random.side_effect = [0.1, 0.1]
        mock_try_create_visual.return_value = b'fake_image_bytes'

        result = shizo_transform("Short text", header="Custom Header")
        self.assertEqual(result, ('image', b'fake_image_bytes'))
        mock_try_create_visual.assert_called_once_with(text="Short text", header="Custom Header")

    @patch('shizo_mode.random.random')
    def test_shizo_transform_bypass_all_randoms(self, mock_random):
        """Test text transformation pipeline with all probabilistic effects bypassed."""
        # Ensure all random.random() checks return 0.99 (failing probability checks)
        mock_random.return_value = 0.99

        input_text = "Обычный текст для проверки"
        result_type, result_text = shizo_transform(input_text)

        self.assertEqual(result_type, 'text')
        self.assertIsInstance(result_text, str)
        # Without random effects, basic replacement might still happen if words match,
        # but here we just check it doesn't fail.

if __name__ == '__main__':
    unittest.main()
