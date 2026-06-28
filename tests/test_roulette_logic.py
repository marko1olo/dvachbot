import pytest
import json
from unittest.mock import patch, mock_open
from roulette_logic import load_roulette_data

def test_load_roulette_data_success():
    mock_data = {
        "roulettes": [
            {
                "name": "Roulette 1",
                "events": [{"id": 1, "text": "Event 1"}, {"id": 2, "text": "Event 2"}]
            },
            {
                "name": "Roulette 2",
                "events": [{"id": 3, "text": "Event 3"}]
            }
        ]
    }
    mock_json = json.dumps(mock_data)
    with patch('builtins.open', mock_open(read_data=mock_json)):
        result = load_roulette_data('dummy.json')

    assert len(result) == 3
    assert result[0]['id'] == 1
    assert result[0]['source_roulette'] == 'Roulette 1'
    assert result[2]['id'] == 3
    assert result[2]['source_roulette'] == 'Roulette 2'

def test_load_roulette_data_empty_events():
    mock_data = {
        "roulettes": [
            {
                "name": "Roulette 1",
                "events": []
            }
        ]
    }
    mock_json = json.dumps(mock_data)
    with patch('builtins.open', mock_open(read_data=mock_json)):
        result = load_roulette_data('dummy.json')

    assert result == []

def test_load_roulette_data_file_not_found():
    with patch('builtins.open', side_effect=FileNotFoundError):
        result = load_roulette_data('missing.json')

    assert result == []

def test_load_roulette_data_invalid_json():
    with patch('builtins.open', mock_open(read_data="invalid json {[")):
        result = load_roulette_data('invalid.json')

    assert result == []
