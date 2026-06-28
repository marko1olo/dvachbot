import json
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "verification_scripts"))

from security_status import load_json


def test_load_json_exists(tmp_path: Path):
    test_file = tmp_path / "test.json"
    test_data = {"key": "value", "number": 42}
    test_file.write_text(json.dumps(test_data), encoding="utf-8")

    result = load_json(test_file)
    assert result == test_data


def test_load_json_not_exists(tmp_path: Path):
    test_file = tmp_path / "nonexistent.json"

    result = load_json(test_file)
    assert result == {}


def test_load_json_invalid_json(tmp_path: Path):
    test_file = tmp_path / "invalid.json"
    test_file.write_text("{invalid json}", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_json(test_file)
