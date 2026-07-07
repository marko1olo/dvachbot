import pytest
from unittest.mock import patch
from mode_visuals import create_visual_post, _wrap_text_by_pixel

def test_create_visual_post_template_mode():
    result = create_visual_post('gopnik', 'Test gopnik text')
    assert isinstance(result, bytes)
    assert len(result) > 0

def test_create_visual_post_template_mode_with_header():
    result = create_visual_post('imperial', 'Test imperial text', header='### Test <i>Header</i>')
    assert isinstance(result, bytes)
    assert len(result) > 0

def test_create_visual_post_dynamic_mode():
    result = create_visual_post('polish', 'Test polish text')
    assert isinstance(result, bytes)
    assert len(result) > 0

def test_create_visual_post_dynamic_mode_with_header():
    result = create_visual_post('shizo', 'Test shizo text', header='Header')
    assert isinstance(result, bytes)
    assert len(result) > 0

def test_create_visual_post_invalid_mode():
    result = create_visual_post('invalid_mode_name', 'Some text')
    assert result is None

def test_create_visual_post_long_text():
    long_text = "This is a very long text that will definitely need to be wrapped across multiple lines. " * 10
    result = create_visual_post('warhammer', long_text)
    assert isinstance(result, bytes)
    assert len(result) > 0

@patch('mode_visuals.Image.open')
def test_create_visual_post_exception_handling(mock_image_open):
    mock_image_open.side_effect = Exception("Simulated PIL error")
    result = create_visual_post('gopnik', 'Some text')
    assert result is None

def test_wrap_text_by_pixel():
    class DummyDraw:
        def textlength(self, text, font=None):
            # Assume each character is 10 pixels wide
            return len(text) * 10

    draw = DummyDraw()
    text = "word1 word2 word3 word4"
    # max_width = 100 means max 10 chars per line
    # "word1 word2" = 11 chars = 110 px -> wrapped
    wrapped = _wrap_text_by_pixel(draw, text, font=None, max_width=100)
    assert wrapped == "word1\nword2\nword3\nword4"
