import pytest
from unittest.mock import patch, mock_open
import json

from roulette_logic import load_roulette_data, get_random_event

def test_load_roulette_data_file_not_found():
    with patch("builtins.open", side_effect=FileNotFoundError):
        assert load_roulette_data("non_existent_file.json") == []

def test_load_roulette_data_invalid_json():
    m = mock_open(read_data="{invalid json")
    with patch("builtins.open", m):
        assert load_roulette_data("invalid_file.json") == []

def test_load_roulette_data_success():
    valid_json = {
        "roulettes": [
            {
                "name": "Test Roulette",
                "events": [{"description": "event1"}, {"description": "event2"}]
            }
        ]
    }
    m = mock_open(read_data=json.dumps(valid_json))
    with patch("builtins.open", m):
        result = load_roulette_data("valid_file.json")
        assert len(result) == 2
        assert result[0]["source_roulette"] == "Test Roulette"
        assert result[0]["description"] == "event1"

def test_get_random_event_empty():
    assert get_random_event([]) is None

def test_get_random_event_success():
    events = [{"id": 1}, {"id": 2}]
    # random.choice will be called, we can just assert it returns one of them
    result = get_random_event(events)
    assert result in events

def test_get_random_event_calls_random_choice():
    events = [{"id": 1}, {"id": 2}]
    with patch("roulette_logic.random.choice") as mock_choice:
        mock_choice.return_value = events[1]
        result = get_random_event(events)
        mock_choice.assert_called_once_with(events)
        assert result == events[1]

def test_get_random_event_single_item():
    events = [{"id": 1}]
    result = get_random_event(events)
    assert result == events[0]
