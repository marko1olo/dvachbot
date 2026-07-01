import json
import pytest
from pathlib import Path
from security_status import load_json, write_status, SECURITY_STATUS_REPORT
from unittest.mock import patch


def test_load_json_non_existent_file(tmp_path: Path):
    """Test that load_json returns an empty dictionary for a non-existent file."""
    file_path = tmp_path / "non_existent.json"
    assert load_json(file_path) == {}

def test_load_json_valid_json(tmp_path: Path):
    """Test that load_json correctly parses and returns valid JSON."""
    file_path = tmp_path / "valid.json"
    file_path.write_text('{"key": "value", "number": 42}', encoding="utf-8")
    result = load_json(file_path)
    assert result == {"key": "value", "number": 42}

def test_load_json_invalid_json(tmp_path: Path):
    """Test that load_json raises a JSONDecodeError for invalid JSON."""
    file_path = tmp_path / "invalid.json"
    file_path.write_text('{"key": "value",', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_json(file_path)

def test_write_status():
    """Test that write_status calls atomic_write_json with the correct arguments."""
    dummy_status = {"test_key": "test_value"}
    with patch("security_status.atomic_write_json") as mock_atomic_write_json:
        write_status(dummy_status)
        mock_atomic_write_json.assert_called_once_with(SECURITY_STATUS_REPORT, dummy_status)
