import pytest
import json
import os
from roulette_logic import load_roulette_data

def test_load_roulette_data_success(tmp_path):
    """Test successful loading of valid JSON and correct mapping of source_roulette."""
    # Setup mock data
    test_data = {
        "roulettes": [
            {
                "name": "Russian Roulette",
                "events": [
                    {"result": "bang"},
                    {"result": "click"}
                ]
            },
            {
                "name": "Another Roulette",
                "events": [
                    {"outcome": "win"}
                ]
            }
        ]
    }

    file_path = tmp_path / "test_roulette.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(test_data, f)

    result = load_roulette_data(str(file_path))

    assert isinstance(result, list)
    assert len(result) == 3

    # Check if events got the source_roulette key
    assert result[0]["result"] == "bang"
    assert result[0]["source_roulette"] == "Russian Roulette"

    assert result[1]["result"] == "click"
    assert result[1]["source_roulette"] == "Russian Roulette"

    assert result[2]["outcome"] == "win"
    assert result[2]["source_roulette"] == "Another Roulette"

def test_load_roulette_data_file_not_found(tmp_path):
    """Test handling of FileNotFoundError."""
    file_path = tmp_path / "nonexistent.json"
    result = load_roulette_data(str(file_path))
    assert result == []

def test_load_roulette_data_invalid_json(tmp_path):
    """Test handling of json.JSONDecodeError."""
    file_path = tmp_path / "invalid.json"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("this is not valid json")

    result = load_roulette_data(str(file_path))
    assert result == []

def test_load_roulette_data_missing_keys(tmp_path):
    """Test handling of JSON with missing 'roulettes' or 'events' keys."""
    # JSON with no 'roulettes' key
    test_data_no_roulettes = {"other_key": "value"}
    file_path1 = tmp_path / "no_roulettes.json"
    with open(file_path1, "w", encoding="utf-8") as f:
        json.dump(test_data_no_roulettes, f)

    result1 = load_roulette_data(str(file_path1))
    assert result1 == []

    # JSON with missing 'events' key
    test_data_no_events = {
        "roulettes": [
            {
                "name": "Empty Roulette"
            }
        ]
    }
    file_path2 = tmp_path / "no_events.json"
    with open(file_path2, "w", encoding="utf-8") as f:
        json.dump(test_data_no_events, f)

    result2 = load_roulette_data(str(file_path2))
    assert result2 == []

    # JSON with missing 'name' key
    test_data_no_name = {
        "roulettes": [
            {
                "events": [
                    {"result": "unknown"}
                ]
            }
        ]
    }
    file_path3 = tmp_path / "no_name.json"
    with open(file_path3, "w", encoding="utf-8") as f:
        json.dump(test_data_no_name, f)

    result3 = load_roulette_data(str(file_path3))
    assert len(result3) == 1
    assert result3[0]["source_roulette"] == "Неизвестная рулетка"
