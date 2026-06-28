import pytest
from roulette_logic import get_random_event


def test_get_random_event_empty_list():
    """Test that get_random_event returns None when given an empty list."""
    assert get_random_event([]) is None


def test_get_random_event_single_item():
    """Test that get_random_event returns the item when given a list with one item."""
    event = {"text": "You won!"}
    result = get_random_event([event])
    assert result == event


def test_get_random_event_multiple_items():
    """Test that get_random_event returns an item from the list when given multiple items."""
    events = [{"text": "A"}, {"text": "B"}, {"text": "C"}]
    result = get_random_event(events)
    assert result in events
