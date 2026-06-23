import random
import unicodedata
from witching_hour import apply_zalgo

def test_apply_zalgo_empty_string():
    assert apply_zalgo("") == ""

def test_apply_zalgo_none():
    assert apply_zalgo(None) is None

def test_apply_zalgo_whitespace():
    assert apply_zalgo("\n \t") == "\n \t"

def test_apply_zalgo_text():
    random.seed(42)
    original_text = "hello"
    zalgo_text = apply_zalgo(original_text)

    # Check that output is longer than input (due to added characters)
    assert len(zalgo_text) > len(original_text)

    # Check that original characters are preserved
    # In python, combining characters have category 'Mn' (Mark, Nonspacing)
    cleaned_text = ''.join(c for c in zalgo_text if unicodedata.category(c) != 'Mn')

    assert cleaned_text == original_text

def test_apply_zalgo_mixed():
    random.seed(42)
    original_text = "hello world"
    zalgo_text = apply_zalgo(original_text)

    # Space should be preserved exactly without combining chars
    # We can check this by removing all combining chars and asserting it equals original
    cleaned_text = ''.join(c for c in zalgo_text if unicodedata.category(c) != 'Mn')
    assert cleaned_text == original_text
