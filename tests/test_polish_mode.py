import pytest
from unittest.mock import patch, MagicMock
import polish_mode

def test_polish_transform_empty_text():
    assert polish_mode.polish_transform("") == ('text', "")

@patch("polish_mode.random.random")
def test_polish_transform_short_text_no_kurwa_no_image(mock_random):
    mock_random.return_value = 0.5  # Greater than 0.4, so no kurwa

    with patch("polish_mode._stage_word_replacement") as mock_word_replacement:
        mock_word_replacement.return_value = "hello"
        assert polish_mode.polish_transform("hello") == ('text', "hello")

@patch("polish_mode.random.random")
def test_polish_transform_short_text_with_kurwa(mock_random):
    mock_random.return_value = 0.3  # Less than 0.4, so adds kurwa

    with patch("polish_mode._stage_word_replacement") as mock_word_replacement:
        mock_word_replacement.return_value = "hello"
        assert polish_mode.polish_transform("hello") == ('text', "hello, kurwa")

@patch("polish_mode.random.random")
@patch("polish_mode.create_visual_post")
def test_polish_transform_short_text_with_image(mock_create_visual_post, mock_random):
    # Ensure word count is <= 2.
    mock_random.side_effect = [0.5, 0.1] # No kurwa, but generate image
    mock_create_visual_post.return_value = b"image_data"

    with patch("polish_mode._stage_word_replacement") as mock_word_replacement:
        mock_word_replacement.return_value = "hello"
        assert polish_mode.polish_transform("hello") == ('image', b"image_data")

@patch("polish_mode.random.random")
@patch("polish_mode.create_visual_post")
def test_polish_transform_long_text_full_pipeline(mock_create_visual_post, mock_random):
    mock_random.return_value = 0.5 # No image
    mock_create_visual_post.return_value = None

    with patch("polish_mode._stage_word_replacement", return_value="hello world this is long") as mock_p1, \
         patch("polish_mode._stage_kurwa_comma", return_value="stage2") as mock_p2, \
         patch("polish_mode._stage_ending_transform", return_value="stage3") as mock_p3, \
         patch("polish_mode._stage_prefix", return_value="stage4") as mock_p4, \
         patch("polish_mode._stage_suffix", return_value="stage5") as mock_p5, \
         patch("polish_mode._stage_injection", return_value="stage6") as mock_p6, \
         patch("polish_mode._stage_pseudo_polish", return_value="stage7") as mock_p7:

        result = polish_mode.polish_transform("hello world this is long")
        assert result == ('text', "stage7")

        mock_p1.assert_called_once_with("hello world this is long")
        mock_p2.assert_called_once_with("hello world this is long")
        mock_p3.assert_called_once_with("stage2")
        mock_p4.assert_called_once_with("stage3")
        mock_p5.assert_called_once_with("stage4")
        mock_p6.assert_called_once_with("stage5", 5)
        mock_p7.assert_called_once_with("stage6")

@patch("polish_mode.random.random")
@patch("polish_mode.create_visual_post")
def test_polish_transform_long_text_with_image(mock_create_visual_post, mock_random):
    mock_random.return_value = 0.1 # Generate image
    mock_create_visual_post.return_value = b"image_data"

    with patch("polish_mode._stage_word_replacement", return_value="hello world this is long") as mock_p1, \
         patch("polish_mode._stage_kurwa_comma", return_value="stage2") as mock_p2, \
         patch("polish_mode._stage_ending_transform", return_value="stage3") as mock_p3, \
         patch("polish_mode._stage_prefix", return_value="stage4") as mock_p4, \
         patch("polish_mode._stage_suffix", return_value="stage5") as mock_p5, \
         patch("polish_mode._stage_injection", return_value="stage6") as mock_p6, \
         patch("polish_mode._stage_pseudo_polish", return_value="stage7") as mock_p7:

        result = polish_mode.polish_transform("hello world this is long")
        assert result == ('image', b"image_data")
