import pytest
from unittest.mock import patch, MagicMock
from mode_visuals import create_visual_post

def test_create_visual_post_error_path():
    with patch("mode_visuals.Image.new", side_effect=Exception("Mocked error!")):
        result = create_visual_post("polish", "test text")
        assert result is None
