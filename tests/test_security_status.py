import json
import pytest
from pathlib import Path
from security_status import load_json, add_blocker

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

def test_add_blocker_positive_count():
    """Test that add_blocker appends a dictionary when count > 0."""
    blockers = []
    add_blocker(blockers, "test_code", 1, "test detail")
    assert len(blockers) == 1
    assert blockers[0] == {"code": "test_code", "count": 1, "detail": "test detail"}

def test_add_blocker_zero_count():
    """Test that add_blocker does not append when count == 0."""
    blockers = []
    add_blocker(blockers, "test_code", 0, "test detail")
    assert len(blockers) == 0

def test_add_blocker_negative_count():
    """Test that add_blocker does not append when count < 0."""
    blockers = []
    add_blocker(blockers, "test_code", -1, "test detail")
    assert len(blockers) == 0
