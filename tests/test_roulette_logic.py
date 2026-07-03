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

import tempfile
import os

def test_load_roulette_data_empty_array():
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write("[]")
        name = f.name

    try:
        assert load_roulette_data(name) == []
    finally:
        os.remove(name)

def test_load_roulette_data_empty_object():
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write("{}")
        name = f.name

    try:
        assert load_roulette_data(name) == []
    finally:
        os.remove(name)

def test_load_roulette_data_malformed():
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write("{invalid json")
        name = f.name

    try:
        assert load_roulette_data(name) == []
    finally:
        os.remove(name)

def test_load_roulette_data_unexpected_types():
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write('{"roulettes": ["invalid", {"name": "Valid", "events": "not a list"}, {"name": "Also Valid", "events": ["not a dict", {"id": 1}]}]}')
        name = f.name

    try:
        result = load_roulette_data(name)
        assert len(result) == 1
        assert result[0]["source_roulette"] == "Also Valid"
        assert result[0]["id"] == 1
    finally:
        os.remove(name)
