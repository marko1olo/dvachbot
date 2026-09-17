import pytest
from achievements_engine import check_and_unlock_achievement, ACHIEVEMENTS_CATALOG

def test_check_and_unlock_achievement():
    # Setup
    active_items = {}
    ach_id = list(ACHIEVEMENTS_CATALOG.keys())[0]  # Get a valid ID

    # Test valid, not unlocked
    unlocked, info = check_and_unlock_achievement(active_items, ach_id)
    assert unlocked is True
    assert info is not None
    assert info['id'] == ach_id
    assert ach_id in active_items['unlocked_achievements']

    # Test valid, already unlocked
    unlocked, info = check_and_unlock_achievement(active_items, ach_id)
    assert unlocked is False
    assert info is None

    # Test invalid achievement
    unlocked, info = check_and_unlock_achievement(active_items, "invalid_id_123")
    assert unlocked is False
    assert info is None


def test_check_and_unlock_achievement_preserves_existing():
    # Setup
    active_items = {"unlocked_achievements": ["ach_some_other_1", "ach_some_other_2"]}
    ach_id = list(ACHIEVEMENTS_CATALOG.keys())[0]  # Get a valid ID

    # Test valid, not unlocked
    unlocked, info = check_and_unlock_achievement(active_items, ach_id)
    assert unlocked is True
    assert "ach_some_other_1" in active_items['unlocked_achievements']
    assert "ach_some_other_2" in active_items['unlocked_achievements']
    assert ach_id in active_items['unlocked_achievements']

def test_get_user_achievements():
    from achievements_engine import get_user_achievements
    active_items = {"unlocked_achievements": ["ach_first_work"]}

    achievements = get_user_achievements(active_items)

    # Check it returns a list of dictionaries
    assert isinstance(achievements, list)
    assert len(achievements) == len(ACHIEVEMENTS_CATALOG)

    # Verify is_unlocked is set correctly
    unlocked_achs = [a for a in achievements if a["is_unlocked"]]
    assert len(unlocked_achs) == 1
    assert unlocked_achs[0]["id"] == "ach_first_work"

    locked_achs = [a for a in achievements if not a["is_unlocked"]]
    assert len(locked_achs) == len(ACHIEVEMENTS_CATALOG) - 1
