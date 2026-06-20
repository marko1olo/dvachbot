import pytest
from roulette_logic import get_random_event

def test_get_random_event_empty_list():
    assert get_random_event([]) is None

def test_get_random_event_single_element():
    event = {"id": 1, "name": "Event 1"}
    assert get_random_event([event]) == event

def test_get_random_event_multiple_elements():
    events = [
        {"id": 1, "name": "Event 1"},
        {"id": 2, "name": "Event 2"},
        {"id": 3, "name": "Event 3"}
    ]
    # Call the function a few times to ensure it returns elements from the list
    for _ in range(10):
        result = get_random_event(events)
        assert result in events
