import json
import pytest
from pathlib import Path
from security_status import load_json, add_blocker, build_status
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

def test_build_status_default():
    """Test build_status with default arguments (include_summary_validation=True)."""
    with patch('security_status._load_reports') as mock_load, \
         patch('security_status.validate_reports') as mock_validate, \
         patch('security_status._evaluate_blockers') as mock_evaluate, \
         patch('security_status._build_status_dict') as mock_build:

        mock_load.return_value = {"mock": "reports"}
        mock_validate.return_value = ["mock_issue"]
        mock_evaluate.return_value = [{"mock": "blocker"}]
        mock_build.return_value = {"mock": "status"}

        result = build_status()

        assert result == {"mock": "status"}
        mock_load.assert_called_once_with()
        mock_validate.assert_called_once_with(include_summary=True)
        mock_evaluate.assert_called_once_with({"mock": "reports"}, ["mock_issue"])
        mock_build.assert_called_once_with({"mock": "reports"}, ["mock_issue"], [{"mock": "blocker"}])

def test_build_status_no_summary_validation():
    """Test build_status with include_summary_validation=False."""
    with patch('security_status._load_reports') as mock_load, \
         patch('security_status.validate_reports') as mock_validate, \
         patch('security_status._evaluate_blockers') as mock_evaluate, \
         patch('security_status._build_status_dict') as mock_build:

        mock_load.return_value = {"mock": "reports_diff"}
        mock_validate.return_value = []
        mock_evaluate.return_value = []
        mock_build.return_value = {"mock": "status_diff"}

        result = build_status(include_summary_validation=False)

        assert result == {"mock": "status_diff"}
        mock_load.assert_called_once_with()
        mock_validate.assert_called_once_with(include_summary=False)
        mock_evaluate.assert_called_once_with({"mock": "reports_diff"}, [])
        mock_build.assert_called_once_with({"mock": "reports_diff"}, [], [])
