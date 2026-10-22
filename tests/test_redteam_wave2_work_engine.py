# -*- coding: utf-8 -*-
"""
tests/test_redteam_wave2_work_engine.py
Dvachbot Redteam Inquisitor Wave 2 (Sector 2: Work Engine, Jobs & Shift Economy).
Verifies:
1. Parallel click race condition dup prevention in execute_job_action
2. Cross-board side hustle cooldown enforcement (dumpster, flyers, bottles, microloan)
3. Mother selling multi-board exploit prevention (work_sell_mother)
4. Flash Ultra (overtime) cross-board daily limit enforcement
5. Durability degradation & tinfoil_until synchronization in apply_tinfoil_damage
6. Negative damage healing prevention & permanent mythic golden foil immunity
7. Corrupted inventory & future timestamp fatigue resilience
"""

import json
import time
import threading
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from common.work_engine import execute_job_action, WORK_VACANCIES
from economy_extension import (
    apply_tinfoil_damage,
    check_flash_ultra_limit,
    record_flash_ultra_use,
    cb_work_action,
)
from shared_state import (
    get_user_work_cooldowns,
    set_user_work_cooldown,
)


def _synthetic_callback(user_id: int, data: str) -> MagicMock:
    cb = MagicMock()
    cb.id = f"cb_{user_id}_{data}"
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.photo = None
    cb.message.edit_caption = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


# =====================================================================
# 1. PARALLEL CLICK RACE CONDITION DUP PREVENTION
# =====================================================================

def test_parallel_job_action_anti_dupe_same_dict():
    """
    Simulates 10 threads concurrently executing the same vacancy on the same inventory dict.
    Strict invariant: EXACTLY 1 thread succeeds; 9 threads receive cooldown rejection.
    Zero reward duplication allowed.
    """
    items = {
        "work_shifts": 0,
        "work_cooldowns": {},
    }
    results = []

    def worker():
        res = execute_job_action("bottles", items)
        results.append(res)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    successes = [r for r in results if r[0] is True]
    failures = [r for r in results if r[0] is False]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}!"
    assert len(failures) == 9, f"Expected 9 cooldown rejections, got {len(failures)}!"
    assert "Кулдаун" in failures[0][2]


def test_parallel_job_action_multi_dict_user_sync():
    """
    Simulates 10 concurrent requests for the same user_id using separate inventory dict snapshots
    (e.g. parallel requests reaching two workers before DB write).
    Global sync must ensure only 1 executes; 9 are blocked.
    """
    user_id = 777001
    results = []

    def worker():
        # Each worker receives a detached copy with zero local cooldowns
        isolated_items = {
            "work_shifts": 0,
            "work_cooldowns": {},
        }
        res = execute_job_action("bottles", isolated_items, user_id=user_id)
        results.append(res)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    successes = [r for r in results if r[0] is True]
    assert len(successes) == 1, f"Multi-dict parallel requests allowed {len(successes)} duplicate rewards!"


# =====================================================================
# 2. CROSS-BOARD SIDE HUSTLE COOLDOWN ENFORCEMENT
# =====================================================================

@pytest.mark.asyncio
async def test_side_hustle_dumpster_cross_board_cooldown(isolated_test_db):
    """
    Verifies dumpster diving on board 'b' activates a global cooldown.
    Attempting to dive on board 'po' immediately afterwards must be REJECTED.
    """
    db = isolated_test_db
    user_id = 888001
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('po', 'Политика')")
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500.0, '{}')",
        (user_id,)
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'po', 500.0, '{}')",
        (user_id,)
    )

    cb_b = _synthetic_callback(user_id, "work_dumpster")
    with patch("main.get_pool", return_value=db):
        await cb_work_action(cb_b, board_id="b")

    assert cb_b.answer.called
    ans_b = cb_b.answer.call_args[0][0].lower()
    assert any(w in ans_b for w in ["контейнер", "жк", "нашел"])

    # Attempt on board 'po' (which previously had empty active_items)
    cb_po = _synthetic_callback(user_id, "work_dumpster")
    with patch("main.get_pool", return_value=db):
        await cb_work_action(cb_po, board_id="po")

    assert cb_po.answer.called
    ans_po = cb_po.answer.call_args[0][0].lower()
    assert "обчистили местные бомжи" in ans_po, f"Bypass succeeded on board 'po'! Answer: {ans_po}"


@pytest.mark.asyncio
async def test_side_hustle_flyers_cross_board_cooldown(isolated_test_db):
    """
    Verifies flyers pasting cooldown is enforced cross-board.
    """
    db = isolated_test_db
    user_id = 888002
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('po', 'Политика')")
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500.0, '{}')",
        (user_id,)
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'po', 500.0, '{}')",
        (user_id,)
    )

    cb_b = _synthetic_callback(user_id, "work_flyers")
    with patch("main.get_pool", return_value=db):
        await cb_work_action(cb_b, board_id="b")

    cb_po = _synthetic_callback(user_id, "work_flyers")
    with patch("main.get_pool", return_value=db):
        await cb_work_action(cb_po, board_id="po")

    ans_po = cb_po.answer.call_args[0][0].lower()
    assert "заклеены" in ans_po, f"Flyers cooldown bypass on board 'po': {ans_po}"


@pytest.mark.asyncio
async def test_side_hustle_microloan_cross_board_cooldown(isolated_test_db):
    """
    Verifies microloan cooldown is enforced cross-board.
    """
    db = isolated_test_db
    user_id = 888003
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('po', 'Политика')")
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500.0, '{}')",
        (user_id,)
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'po', 500.0, '{}')",
        (user_id,)
    )

    cb_b = _synthetic_callback(user_id, "work_microloan")
    with patch("main.get_pool", return_value=db):
        await cb_work_action(cb_b, board_id="b")

    cb_po = _synthetic_callback(user_id, "work_microloan")
    with patch("main.get_pool", return_value=db):
        await cb_work_action(cb_po, board_id="po")

    ans_po = cb_po.answer.call_args[0][0].lower()
    assert "пересменка" in ans_po, f"Microloan cooldown bypass on board 'po': {ans_po}"


# =====================================================================
# 3. MOTHER SELLING MULTI-BOARD EXPLOIT PREVENTION
# =====================================================================

@pytest.mark.asyncio
async def test_sell_mother_cross_board_exploit_prevention(isolated_test_db):
    """
    Selling mother awards 8000 shekels and is permanently once-in-a-lifetime.
    Switching boards must NOT allow selling mother a second time.
    """
    db = isolated_test_db
    user_id = 888004
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('po', 'Политика'), ('vg', 'Видеоигры')")
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 0.0, '{}')",
        (user_id,)
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'po', 0.0, '{}')",
        (user_id,)
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'vg', 0.0, '{}')",
        (user_id,)
    )

    # 1. First sale on board 'b'
    cb_b = _synthetic_callback(user_id, "work_sell_mother")
    with patch("main.get_pool", return_value=db):
        await cb_work_action(cb_b, board_id="b")

    assert "8000" in cb_b.answer.call_args[0][0]

    # 2. Attempt on board 'po'
    cb_po = _synthetic_callback(user_id, "work_sell_mother")
    with patch("main.get_pool", return_value=db):
        await cb_work_action(cb_po, board_id="po")

    assert "уже продал мать" in cb_po.answer.call_args[0][0].lower()

    # 3. Attempt on board 'vg'
    cb_vg = _synthetic_callback(user_id, "work_sell_mother")
    with patch("main.get_pool", return_value=db):
        await cb_work_action(cb_vg, board_id="vg")

    assert "уже продал мать" in cb_vg.answer.call_args[0][0].lower()


# =====================================================================
# 4. FLASH ULTRA (OVERTIME) CROSS-BOARD DAILY LIMIT
# =====================================================================

@pytest.mark.asyncio
async def test_flash_ultra_cross_board_daily_limit():
    """
    Flash Ultra limit is strictly 2 cans per day.
    Switching board_id or using clean active_items must NOT bypass the daily limit.
    """
    user_id = 888005
    now = time.time()

    items_b = {}
    can_use, _ = check_flash_ultra_limit(items_b, now=now, user_id=user_id)
    assert can_use is True
    rem1 = record_flash_ultra_use(items_b, now=now, user_id=user_id)
    assert rem1 == 1

    # Second can (after 30 min cooldown)
    now2 = now + 1850
    can_use2, _ = check_flash_ultra_limit(items_b, now=now2, user_id=user_id)
    assert can_use2 is True
    rem2 = record_flash_ultra_use(items_b, now=now2, user_id=user_id)
    assert rem2 == 0

    # Third can attempted on board 'po' with fresh active_items dict
    now3 = now2 + 1850
    items_po = {}
    can_use3, err3 = check_flash_ultra_limit(items_po, now=now3, user_id=user_id)
    assert can_use3 is False, "Daily limit bypassed on new board!"
    assert "Лимит Flash Ultra исчерпан" in err3


# =====================================================================
# 5. DURABILITY DEGRADATION & TINFOIL SYNCHRONIZATION
# =====================================================================

def test_tinfoil_damage_synchronizes_tinfoil_until():
    """
    apply_tinfoil_damage must synchronously decrease BOTH tinfoil_hat and tinfoil_until.
    Leaving tinfoil_until desynced is a critical security vulnerability.
    """
    now = int(time.time())
    items = {
        "tinfoil_hat": now + 36000,
        "tinfoil_until": now + 36000,
        "equipped_head": "hat_tinfoil",
    }

    destroyed, left_h, left_m, remaining = apply_tinfoil_damage(
        items, now=now, hours_damage=4.0, burn_chance=0.0
    )

    assert destroyed is False
    assert left_h == 6
    assert items["tinfoil_hat"] == now + 21600
    assert items["tinfoil_until"] == now + 21600, "tinfoil_until was not updated with damage!"
    assert items.get("hat_tinfoil_expires") == now + 21600


def test_tinfoil_damage_preserves_tinfoil_until_when_hat_key_missing():
    """
    If active_items only holds tinfoil_until (legacy format or external grant),
    it must NOT be treated as expired and deleted.
    """
    now = int(time.time())
    items = {
        "tinfoil_until": now + 28800,  # 8 hours
    }

    destroyed, left_h, left_m, remaining = apply_tinfoil_damage(
        items, now=now, hours_damage=2.0, burn_chance=0.0
    )

    assert destroyed is False
    assert left_h == 6
    assert items["tinfoil_hat"] == now + 21600
    assert items["tinfoil_until"] == now + 21600


def test_tinfoil_negative_damage_does_not_heal():
    """
    Passing negative hours_damage must not heal the hat or increase remaining time.
    """
    now = int(time.time())
    items = {
        "tinfoil_hat": now + 7200,
        "tinfoil_until": now + 7200,
    }

    destroyed, left_h, left_m, remaining = apply_tinfoil_damage(
        items, now=now, hours_damage=-10.0, burn_chance=0.0
    )

    assert destroyed is False
    assert items["tinfoil_hat"] == now + 7200
    assert items["tinfoil_until"] == now + 7200


def test_permanent_golden_foil_immunity():
    """
    Permanent mythic golden foil hat (hat_golden_foil) must be completely immune
    to durability loss and destruction.
    """
    now = int(time.time())
    items = {
        "equipped_head": "hat_golden_foil",
        "owned_hat_golden_foil": True,
    }

    destroyed, left_h, left_m, remaining = apply_tinfoil_damage(
        items, now=now, hours_damage=24.0, burn_chance=1.0
    )

    assert destroyed is False
    assert items.get("equipped_head") == "hat_golden_foil"


# =====================================================================
# 6. CORRUPTED DATA & FUTURE TIMESTAMP RESILIENCE
# =====================================================================

def test_corrupted_inventory_resilience():
    """
    Verifies execute_job_action handles corrupted inventory fields (string work_shifts,
    None work_cooldowns) without raising unhandled exceptions.
    """
    corrupted_items = {
        "work_shifts": "corrupted_string",
        "work_cooldowns": None,
        "recent_shifts": "invalid_type",
    }

    success, amount, msg, drop = execute_job_action("bottles", corrupted_items)
    assert success is True
    assert amount >= 15
    assert isinstance(corrupted_items["work_shifts"], int)
    assert isinstance(corrupted_items["work_cooldowns"], dict)


def test_future_timestamp_fatigue_resilience():
    """
    Verifies that timestamps from the future (clock skew/corrupted entries)
    do not glitch the daily fatigue multiplier.
    """
    now = int(time.time())
    items = {
        "work_shifts": 0,
        "work_cooldowns": {},
        "recent_shifts": {
            "bottles": [now + 999999, now - 1000]  # One future timestamp, one valid
        }
    }

    # Should only count 1 valid recent shift (shifts_today = 1), ignoring future timestamp
    success, amount, msg, _ = execute_job_action("bottles", items)
    assert success is True
    # Future timestamp was ignored, only 1 previous shift counted (15% fatigue)
    assert "смена #2" in msg
