import pytest
from unittest.mock import patch
from mode_punchup import punch_up_mode_text

def test_punch_up_mode_text_missing_mode():
    assert punch_up_mode_text("hello world", None) == "hello world"
    assert punch_up_mode_text("hello world", "") == "hello world"

def test_punch_up_mode_text_invalid_mode():
    assert punch_up_mode_text("hello world", "non_existent_mode_123") == "hello world"

def test_punch_up_mode_text_valid_mode_calls_decorate():
    # We mock _decorate to prevent actual randomness from interfering with our test,
    # and to verify it gets called with the right arguments.
    with patch("mode_punchup._decorate") as mock_decorate:
        mock_decorate.return_value = "decorated text"

        # 'anime_mode' is a known mode in MODE_PUNCHUP_PROFILES
        result = punch_up_mode_text("hello world", "anime_mode")

        assert result == "decorated text"
        mock_decorate.assert_called_once()
        args, kwargs = mock_decorate.call_args
        assert args[0] == "hello world"
        assert isinstance(args[1], dict) # It should pass the profile dictionary
        assert "prefixes" in args[1]
