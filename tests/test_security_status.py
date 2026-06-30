import json
import pytest
from pathlib import Path
from security_status import load_json
from unittest.mock import patch
from typing import Any

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


@patch("security_status.validate_reports")
@patch("security_status.load_json")
def test_build_status_default(
    mock_load_json: Any,
    mock_validate_reports: Any,
) -> None:
    """Test build_status with default arguments."""
    from security_status import build_status

    # Setup mocks
    mock_validate_reports.return_value = []

    # We want load_json to return empty dicts for everything, which implies no issues.
    mock_load_json.return_value = {}

    result = build_status()

    assert "generated_utc" in result
    assert result["contains_secret_values"] is False
    assert result["validator_ok"] is True
    assert result["strict_ready"] is False  # Because many reports are empty, it will add blockers

    mock_validate_reports.assert_called_once_with(include_summary=True)


@patch("security_status.validate_reports")
@patch("security_status.load_json")
def test_build_status_without_summary_validation(
    mock_load_json: Any,
    mock_validate_reports: Any,
) -> None:
    """Test build_status with include_summary_validation=False."""
    from security_status import build_status

    # Setup mocks
    mock_validate_reports.return_value = ["mock_issue"]
    mock_load_json.return_value = {}

    result = build_status(include_summary_validation=False)

    assert "generated_utc" in result
    assert result["validator_ok"] is False
    assert result["validator_issues"] == ["mock_issue"]

    mock_validate_reports.assert_called_once_with(include_summary=False)
