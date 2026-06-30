import json
import pytest
from pathlib import Path
from security_status import load_json

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

def test_load_json_empty_file(tmp_path: Path):
    """Test that load_json raises a JSONDecodeError for an empty file."""
    file_path = tmp_path / "empty.json"
    file_path.write_text("", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_json(file_path)

def test_load_json_is_directory(tmp_path: Path):
    """Test that load_json raises IsADirectoryError when path is a directory."""
    dir_path = tmp_path / "somedir"
    dir_path.mkdir()
    with pytest.raises((IsADirectoryError, PermissionError)):
        load_json(dir_path)
