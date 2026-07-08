import pytest
from unittest.mock import patch

from zaputin_mode import zaputin_transform

def test_zaputin_transform_empty():
    """Verify that passing an empty string or None returns the input directly, without modifications."""
    assert zaputin_transform("") == ""
    assert zaputin_transform(None) == None

@patch('zaputin_mode.random.random', return_value=1.0)
def test_zaputin_transform_zv_replacements(mock_random):
    """Verify that the characters З/з and В/в are replaced with Z and V."""
    text = "Зебра зебра Ветер ветер"
    expected = "Zебра Zебра Vетер Vетер"
    assert zaputin_transform(text) == expected

@patch('zaputin_mode.random.random', return_value=1.0)
@patch('zaputin_mode.random.choice', return_value="т.н.")
def test_zaputin_transform_english_quoting(mock_choice, mock_random):
    """Verify English words are matched and quoted with a prefix."""
    text = "hello world"
    expected = "т.н. «hello» т.н. «world»"
    assert zaputin_transform(text) == expected

@patch('zaputin_mode.random.random', return_value=1.0)
@patch('zaputin_mode._zaputin_ideological_replacer')
def test_zaputin_transform_kancelarit(mock_ideological_replacer, mock_random):
    """Verify Kancelarit replacements from _KANCELARIT_MAP_COMPILED."""
    # We mock _zaputin_ideological_replacer to return the original word so it doesn't affect our test
    mock_ideological_replacer.side_effect = lambda match: match.group(0)
    text = "я сделал"
    expected = "мною был реализован комплекс мер"
    assert zaputin_transform(text) == expected

@patch('zaputin_mode.random.random', return_value=0.1) # < 0.15 for caps
@patch('zaputin_mode.random.choice', return_value="СЛАВА РОССИИ!")
def test_zaputin_transform_caps(mock_choice, mock_random):
    """Verify the 15% random capitalization logic in _caps_important."""
    text = "параллелепипед"
    expected = "ПАРАЛЛЕЛЕПИПЕД"
    assert zaputin_transform(text) == expected

@patch('zaputin_mode.random.random', return_value=0.2) # 0.2 >= 0.15 (no caps), < 0.25 (yes slogan)
@patch('zaputin_mode.random.choice', return_value="СЛАВА РОССИИ!")
def test_zaputin_transform_slogan(mock_choice, mock_random):
    """Verify the 25% chance of appending a slogan for texts longer than 3 words."""
    text = "один два три четыре"
    # replacements applied to letters, wait V/Z replacements
    # "два" -> "дVа"
    expected = "один дVа три четыре\n\n<b>СЛАВА РОССИИ!</b>"

    assert zaputin_transform(text) == expected
