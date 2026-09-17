from achievements_engine import (
    check_and_unlock_achievement,
    ACHIEVEMENTS_CATALOG
)


def test_check_and_unlock_achievement_invalid_id():
    active_items = {}
    was_unlocked, info = check_and_unlock_achievement(
        active_items, "invalid_ach_id"
    )
    assert not was_unlocked
    assert info is None
    assert "unlocked_achievements" not in active_items


def test_check_and_unlock_achievement_new():
    active_items = {}
    ach_id = "ach_work_10"
    was_unlocked, info = check_and_unlock_achievement(active_items, ach_id)

    assert was_unlocked
    assert info == ACHIEVEMENTS_CATALOG[ach_id]
    assert "unlocked_achievements" in active_items
    assert ach_id in active_items["unlocked_achievements"]


def test_check_and_unlock_achievement_already_unlocked():
    ach_id = "ach_work_10"
    active_items = {"unlocked_achievements": [ach_id]}
    was_unlocked, info = check_and_unlock_achievement(active_items, ach_id)

    assert not was_unlocked
    assert info is None
    assert active_items["unlocked_achievements"] == [ach_id]


def test_check_and_unlock_achievement_append_to_existing():
    existing_ach = "ach_work_10"
    new_ach = "ach_work_50"
    active_items = {"unlocked_achievements": [existing_ach]}
    was_unlocked, info = check_and_unlock_achievement(active_items, new_ach)

    assert was_unlocked
    assert info == ACHIEVEMENTS_CATALOG[new_ach]
    assert active_items["unlocked_achievements"] == [existing_ach, new_ach]
