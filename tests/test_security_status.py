import json
import pytest
import sys
from pathlib import Path
import tempfile
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
verification_path = os.path.join(PROJECT_ROOT, "verification_scripts")
if verification_path not in sys.path:
    sys.path.insert(0, verification_path)

from security_status import load_json

def test_load_json_non_existent_file():
    """Test that load_json returns an empty dictionary for a non-existent file."""
    # Create a path that is guaranteed not to exist
    with tempfile.TemporaryDirectory() as temp_dir:
        non_existent_path = Path(temp_dir) / "does_not_exist.json"

        result = load_json(non_existent_path)
        assert result == {}

def test_load_json_valid_file():
    """Test that load_json correctly parses and returns the contents of a valid JSON file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        valid_json_path = Path(temp_dir) / "valid.json"
        data = {"key": "value", "list": [1, 2, 3]}
        valid_json_path.write_text(json.dumps(data), encoding="utf-8")

        result = load_json(valid_json_path)
        assert result == data

def test_load_json_invalid_file():
    """Test that load_json raises json.JSONDecodeError for an invalid JSON file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        invalid_json_path = Path(temp_dir) / "invalid.json"
        invalid_json_path.write_text("{invalid_json_here: true", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            load_json(invalid_json_path)
