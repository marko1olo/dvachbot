# -*- coding: utf-8 -*-
"""
tests/test_work_fatigue.py — Unit tests for work fatigue and rolling 24h shifts decay per vacancy.
"""
import time
import pytest
from common.work_engine import execute_job_action, WORK_VACANCIES

def test_work_fatigue_progression():
    """Verify each consecutive shift on the SAME vacancy in 24h reduces payout progressively down to 20% floor."""
    items = {"work_shifts": 0, "work_cooldowns": {}, "recent_shifts": {}}
    now = 1000000

    # First shift (shifts_today = 0): multiplier 1.0 (100%)
    success, r0, msg0, _ = execute_job_action("bottles", items)
    assert success is True
    assert r0 >= 15
    assert len(items["recent_shifts"]["bottles"]) == 1
    assert "Усталость" not in msg0

    # Advance time past bottles cooldown (180s)
    items["work_cooldowns"]["bottles"] = now - 500

    # Second shift (shifts_today = 1): multiplier 0.85 (85%)
    success, r1, msg1, _ = execute_job_action("bottles", items)
    assert success is True
    assert len(items["recent_shifts"]["bottles"]) == 2
    assert "Усталость" in msg1
    assert "-15%" in msg1

    # Advance time past bottles cooldown again
    items["work_cooldowns"]["bottles"] = now - 500

    # Third shift (shifts_today = 2): multiplier 0.85^2 = 0.7225 (~72%)
    success, r2, msg2, _ = execute_job_action("bottles", items)
    assert success is True
    assert len(items["recent_shifts"]["bottles"]) == 3
    assert "Усталость" in msg2
    assert "-28%" in msg2


def test_work_fatigue_separate_per_vacancy():
    """Verify fatigue on one vacancy (e.g. bottles) does NOT affect other vacancies (e.g. courier)."""
    now = int(time.time())
    # User has 3 previous shifts on 'bottles' (fatigued)
    items = {
        "work_shifts": 10,  # Unlocks courier (req: 5)
        "work_cooldowns": {"bottles": now - 500, "courier": now - 5000},
        "recent_shifts": {
            "bottles": [now - 600, now - 300]
        }
    }

    # Working 'courier' for the first time today: NO fatigue from bottles!
    success_c1, r_c1, msg_c1, _ = execute_job_action("courier", items)
    assert success_c1 is True
    assert "Усталость" not in msg_c1
    assert len(items["recent_shifts"]["courier"]) == 1
    # Bottles shifts still preserved
    assert len(items["recent_shifts"]["bottles"]) == 2

    # Advance courier cooldown
    items["work_cooldowns"]["courier"] = now - 5000

    # Second shift on 'courier': now courier has its own fatigue (-15%)
    success_c2, r_c2, msg_c2, _ = execute_job_action("courier", items)
    assert success_c2 is True
    assert "Усталость" in msg_c2
    assert "-15%" in msg_c2
    assert len(items["recent_shifts"]["courier"]) == 2

    # Advance bottles cooldown and work 'bottles' (this will be 3rd shift for bottles -> -28%)
    items["work_cooldowns"]["bottles"] = now - 500
    success_b3, r_b3, msg_b3, _ = execute_job_action("bottles", items)
    assert success_b3 is True
    assert "Усталость" in msg_b3
    assert "-28%" in msg_b3
    assert len(items["recent_shifts"]["bottles"]) == 3


def test_work_fatigue_floor_and_rolling_24h_reset():
    """Verify fatigue never drops below 20% and resets after 24 hours."""
    now = int(time.time())
    # Simulate 15 shifts on 'bottles' in the last few hours
    recent = [now - (i * 300) for i in range(15)]
    items = {
        "work_shifts": 15,
        "work_cooldowns": {"bottles": now - 3600},
        "recent_shifts": {"bottles": recent}
    }

    success, reward, msg, _ = execute_job_action("bottles", items)
    assert success is True
    # At 15 shifts today, 0.85^15 = ~0.087, capped at 0.20 floor (-80%)
    assert "-80%" in msg
    assert reward >= 1

    # Now simulate all previous shifts happened > 24 hours ago
    expired_shifts = [now - 90000 - (i * 300) for i in range(15)]
    items_fresh = {
        "work_shifts": 15,
        "work_cooldowns": {"bottles": now - 3600},
        "recent_shifts": {"bottles": expired_shifts}
    }

    success_fresh, reward_fresh, msg_fresh, _ = execute_job_action("bottles", items_fresh)
    assert success_fresh is True
    # Fatigue should be completely cleared
    assert "Усталость" not in msg_fresh
    assert len(items_fresh["recent_shifts"]["bottles"]) == 1


def test_work_fatigue_legacy_list_migration():
    """Verify legacy list format in recent_shifts is gracefully handled and migrated to dict."""
    now = int(time.time())
    items_legacy = {
        "work_shifts": 5,
        "work_cooldowns": {"bottles": now - 3600},
        "recent_shifts": [now - 300]  # 1 legacy shift
    }
    success, reward, msg, _ = execute_job_action("bottles", items_legacy)
    assert success is True
    assert isinstance(items_legacy["recent_shifts"], dict)
    assert "-15%" in msg
    assert len(items_legacy["recent_shifts"]["bottles"]) == 2

