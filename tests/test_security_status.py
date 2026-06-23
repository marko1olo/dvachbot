import pytest
from typing import Any

from security_status import add_blocker

def test_add_blocker_count_greater_than_zero():
    blockers: list[dict[str, Any]] = []
    add_blocker(blockers, "test_code", 1, "test detail")
    assert len(blockers) == 1
    assert blockers[0] == {"code": "test_code", "count": 1, "detail": "test detail"}

def test_add_blocker_count_zero():
    blockers: list[dict[str, Any]] = []
    add_blocker(blockers, "test_code", 0, "test detail")
    assert len(blockers) == 0

def test_add_blocker_count_negative():
    blockers: list[dict[str, Any]] = []
    add_blocker(blockers, "test_code", -1, "test detail")
    assert len(blockers) == 0

def test_add_blocker_multiple_appends():
    blockers: list[dict[str, Any]] = []
    add_blocker(blockers, "code_1", 1, "detail 1")
    add_blocker(blockers, "code_2", 0, "detail 2")
    add_blocker(blockers, "code_3", 5, "detail 3")

    assert len(blockers) == 2
    assert blockers[0] == {"code": "code_1", "count": 1, "detail": "detail 1"}
    assert blockers[1] == {"code": "code_3", "count": 5, "detail": "detail 3"}
