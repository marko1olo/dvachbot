import json
import pytest
from pathlib import Path
from unittest.mock import patch
from security_status import load_json, write_status
import security_status

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

@patch("security_status.atomic_write_json")
def test_write_status(mock_atomic_write_json):
    """Test that write_status calls atomic_write_json with correct arguments."""
    status_data = {"status": "ok", "issue_count": 0}
    write_status(status_data)
    mock_atomic_write_json.assert_called_once_with(security_status.SECURITY_STATUS_REPORT, status_data)
