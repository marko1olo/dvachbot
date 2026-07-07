from unittest.mock import patch
from mode_visuals import (
    create_visual_post,
    FontFitConfig,
    _wrap_text_by_pixel,
    _find_best_font_size,
)


def test_create_visual_post_template_mode():
    result = create_visual_post("gopnik", "test text")
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_create_visual_post_template_mode_with_header():
    result = create_visual_post("imperial", "test text", header="header")
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_create_visual_post_dynamic_mode():
    result = create_visual_post("polish", "test text")
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_create_visual_post_dynamic_mode_with_header():
    # Will randomly choose split or bottom layout for dynamic mode with header
    result = create_visual_post("polish", "test text", header="header")
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_create_visual_post_invalid_mode():
    result = create_visual_post("invalid_mode", "test text")
    assert result is None


@patch("mode_visuals.Image.open")
def test_create_visual_post_exception(mock_open):
    mock_open.side_effect = Exception("Test Exception")
    result = create_visual_post("gopnik", "test text")
    assert result is None


@patch("mode_visuals.glob.glob")
def test_create_visual_post_dynamic_mode_no_files(mock_glob):
    mock_glob.return_value = []
    result = create_visual_post("polish", "test text")
    assert result is None


@patch("mode_visuals.os.path.exists")
def test_create_visual_post_file_not_exists(mock_exists):
    mock_exists.return_value = False
    result = create_visual_post("gopnik", "test text")
    assert result is None


def test_wrap_text_by_pixel():
    class DummyDraw:
        def textlength(self, text, font=None):
            return len(text) * 10

    draw = DummyDraw()
    text = "hello world\nthis is a test of long text that needs wrapping"
    wrapped = _wrap_text_by_pixel(draw, text, font=None, max_width=50)

    # 5 chars = 50 width
    assert (
        wrapped
        == "hello\nworld\nthis\nis a\ntest\nof\nlong\ntext\nthat\nneeds\nwrapping"
    )


def test_find_best_font_size_default_font_fallback():
    class DummyDraw:
        def textlength(self, text, font=None):
            return len(text) * 5

        def multiline_textbbox(self, xy, text, font=None, align="left"):
            return (0, 0, len(text) * 5, 10)

    draw = DummyDraw()
    fit_config = FontFitConfig(
        font_path="invalid_path.ttf",
        max_width=100,
        max_height=50,
        max_font_size=20,
        text_align="left",
    )

    font, wrapped = _find_best_font_size(draw, "test", fit_config)
    assert font is not None
    assert wrapped == "test"
