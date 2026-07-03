import pytest
from unittest.mock import patch

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ukrainian_mode import ukrainian_transform

class TestUkrainianMode:
    def test_empty_string(self):
        """Test with an empty string, should return text and empty string without processing."""
        result = ukrainian_transform("")
        assert result == ('text', "")

    @patch('ukrainian_mode.random.random')
    def test_text_only(self, mock_random):
        """Test basic transformation without random additions (slogan, zrada detector) or visual posts."""
        # mock_random.return_value = 1.0 will prevent zrada detector (<0.30), slogan (<0.30), and visual post (<0.20)
        mock_random.return_value = 1.0

        # Test basic translation
        result_type, result_content = ukrainian_transform("привет")
        assert result_type == 'text'
        # Can't reliably check translation output because of random.choice in _get_replacement,
        # but we know it should process and return a non-empty string.
        assert isinstance(result_content, str)
        assert len(result_content) > 0

    @patch('ukrainian_mode.random.random')
    @patch('ukrainian_mode.create_visual_post')
    def test_visual_post_success(self, mock_create_visual, mock_random):
        """Test that visual post is generated when conditions are met."""
        # mock_random.return_value = 0.1 to trigger visual post (<0.20)
        # Note: this will also trigger slogan (<0.30) and zrada detector (<0.30) if length > 2 etc,
        # but we mock visual post to just check it gets called.
        mock_random.return_value = 0.1
        mock_create_visual.return_value = b'fake_image_data'

        result_type, result_content = ukrainian_transform("привет", header="Test Header")

        assert result_type == 'image'
        assert result_content == b'fake_image_data'

        mock_create_visual.assert_called_once()
        # Ensure header is passed properly to the image creation function
        assert mock_create_visual.call_args[1].get('header') == "Test Header"

    @patch('ukrainian_mode.random.random')
    @patch('ukrainian_mode.create_visual_post')
    def test_visual_post_exception_fallback(self, mock_create_visual, mock_random):
        """Test that if image generation fails, it falls back to text."""
        # mock_random.return_value = 0.1 to trigger visual post (<0.20)
        mock_random.return_value = 0.1
        mock_create_visual.side_effect = Exception("Visual generation failed")

        result_type, result_content = ukrainian_transform("привет")

        # Should fall back to text output since image generation threw an exception
        assert result_type == 'text'
        assert isinstance(result_content, str)
        assert len(result_content) > 0
