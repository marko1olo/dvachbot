from utils import split_text


def test_split_text_short():
    text = "Hello world"
    parts = split_text(text, 50)
    assert len(parts) == 1
    assert parts[0] == "Hello world"


def test_split_text_lorem_ipsum():
    # Generate long lorem ipsum text
    lorem = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 50
    limit = 100
    parts = split_text(lorem, limit)

    assert len(parts) > 1

    for i, part in enumerate(parts):
        # The limit should be respected
        assert len(part) <= limit
        assert f"({i+1}/{len(parts)})" in part


def test_split_text_no_spaces():
    text = "a" * 150
    limit = 50
    parts = split_text(text, limit)
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= limit


def test_split_text_newlines():
    text = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
    limit = 15
    parts = split_text(text, limit)
    for part in parts:
        assert len(part) <= limit
