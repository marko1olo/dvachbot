import json
import pytest
from pathlib import Path
from security_status import load_json


def test_load_json_non_existent_file(tmp_path: Path):
    non_existent = tmp_path / "does_not_exist.json"
    result = load_json(non_existent)
    assert result == {}


def test_load_json_valid_file(tmp_path: Path):
    valid_file = tmp_path / "valid.json"
    valid_data = {"key": "value", "number": 42}
    valid_file.write_text(json.dumps(valid_data), encoding="utf-8")

    result = load_json(valid_file)
    assert result == valid_data


def test_load_json_invalid_file(tmp_path: Path):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{invalid json:", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_json(invalid_file)
