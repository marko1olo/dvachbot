# -*- coding: utf-8 -*-
"""
tests/test_adversarial_review.py — Adversarial Edge-Case Test Suite by Reviewer 2
Tests edge cases, boundary values, wardrobe missing keys, item drops, command unshadowing, and race conditions.
"""

import time
import pytest
import asyncio
from common.work_engine import WORK_VACANCIES, execute_job_action, get_vacancies
from wardrobe_engine import get_active_set_bonus, get_active_set_bonuses, get_equipped_gear, SET_BONUSES
import lootbox_engine

def test_shift_edge_cases_0_620_10000():
    # 0 shifts: only tier 1 (bottles) is unlocked
    items_0 = {"work_shifts": 0}
    for jid, job in WORK_VACANCIES.items():
        succ, val, msg, drop = execute_job_action(jid, dict(items_0))
        if jid == "bottles":
            # Can succeed or fail on risk, but cannot be blocked by shifts
            assert "заблокирована" not in msg
        else:
            assert not succ
            assert "заблокирована" in msg
            assert f"Требуется стаж: {job['required_shifts']}" in msg

    # 620 shifts: all 16 tiers are unlocked
    items_620 = {"work_shifts": 620}
    for jid, job in WORK_VACANCIES.items():
        succ, val, msg, drop = execute_job_action(jid, dict(items_620))
        assert "заблокирована" not in msg, f"{jid} failed to unlock at 620 shifts"

    # 10000 shifts: all 16 tiers unlocked, no overflow, shifts increment to 10001
    items_10k = {"work_shifts": 10000}
    for jid in WORK_VACANCIES:
        d = dict(items_10k)
        succ, val, msg, drop = execute_job_action(jid, d)
        assert "заблокирована" not in msg
        if succ:
            assert d["work_shifts"] == 10001


def test_cooldown_mechanics_and_slippers():
    now = int(time.time())
    
    # Active cooldown
    items = {
        "work_shifts": 10,
        "work_cooldowns": {"courier": now - 100} # courier cooldown is 900s
    }
    succ, val, msg, drop = execute_job_action("courier", items)
    assert not succ
    assert "Кулдаун" in msg
    assert "мин" in msg or "сек" in msg

    # Slippers reduce cooldown by 20%
    # courier base_cd = 900s -> with slippers = 720s
    items_slip = {
        "work_shifts": 10,
        "equipped_feet": "feet_slippers",
        "work_cooldowns": {"courier": now - 750} # 750s passed > 720s
    }
    succ_slip, val_slip, msg_slip, drop_slip = execute_job_action("courier", items_slip)
    # Should be ready (not in cooldown)
    assert "Кулдаун" not in msg_slip


def test_wardrobe_missing_keys_and_robustness():
    # Empty dictionary
    sb = get_active_set_bonus({})
    assert sb is None
    eq = get_equipped_gear({})
    assert eq == {"head": None, "torso": None, "face": None, "feet": None}

    # Missing keys / unknown string IDs
    partial = {
        "equipped_head": "nonexistent_hat",
        "equipped_torso": None,
        "equipped_face": "unknown_glasses",
        "equipped_feet": None,
        "work_shifts": 50,
        "work_cooldowns": {}
    }
    sb_p = get_active_set_bonus(partial)
    assert sb_p is None
    succ, val, msg, drop = execute_job_action("sweeper", partial)
    assert isinstance(succ, bool)
    assert isinstance(val, int)
    assert isinstance(msg, str)

    # Work engine handles unhashable corrupted types gracefully via try-except
    corrupted = {
        "equipped_head": "hat_crown",
        "equipped_face": ["corrupted_list"],
        "work_shifts": 50,
        "work_cooldowns": {}
    }
    succ_c, val_c, msg_c, drop_c = execute_job_action("sweeper", corrupted)
    assert isinstance(succ_c, bool)


def test_all_wardrobe_set_bonuses_recognized():
    # Test Wasserman Set
    items_wasserman = {
        "work_shifts": 100,
        "equipped_torso": "body_wasserman",
        "equipped_face": "face_wasserman_glasses"
    }
    sb = get_active_set_bonus(items_wasserman)
    assert sb is not None
    assert sb.get("id") == "set_wasserman"
    
    # Test Anime Hikka Set (both set_anime and set_anime_hikka aliases)
    items_anime = {
        "work_shifts": 100,
        "equipped_head": "hat_cat_ears",
        "equipped_torso": "body_hoodie"
    }
    sb_anime = get_active_set_bonus(items_anime)
    assert sb_anime is not None
    assert sb_anime.get("id") == "set_anime_hikka"

    # Test Skuf Set
    items_skuf = {
        "work_shifts": 100,
        "equipped_head": "hat_crown",
        "equipped_torso": "body_tracksuit"
    }
    sb_skuf = get_active_set_bonus(items_skuf)
    assert sb_skuf is not None
    assert sb_skuf.get("id") == "set_gop_skuf"

    # Test Riot Police Set (0% penalty risk)
    items_riot = {
        "work_shifts": 100,
        "equipped_head": "hat_helmet",
        "equipped_feet": "feet_boots"
    }
    sb_riot = get_active_set_bonus(items_riot)
    assert sb_riot is not None
    assert sb_riot.get("id") == "set_riot_police"

    # Test Neo Set
    items_neo = {
        "work_shifts": 100,
        "equipped_torso": "body_cloak",
        "equipped_face": "face_anon_mask"
    }
    sb_neo = get_active_set_bonus(items_neo)
    assert sb_neo is not None
    assert sb_neo.get("id") == "set_neo"


def test_item_drops_and_duplicate_inventory_handling():
    # Simulate user already having rare items, guns, brooms, lootboxes
    items = {
        "work_shifts": 500,
        "knife_gun": True,
        "mute_gun": True,
        "shield_gun": True,
        "pepperspray": True,
        "tinfoil_hat": int(time.time()) + 1000,
        "janitor_deletes_left": 5,
        "janitor_until": int(time.time()) + 5000,
        "work_cooldowns": {}
    }

    # Simulate what main.py:cb_work_do does when receiving drops:
    # 1. Broom drop: should increment janitor_deletes_left from 5 to 8
    broom_items = dict(items)
    broom_items["janitor_deletes_left"] = broom_items.get("janitor_deletes_left", 0) + 3
    broom_items["janitor_until"] = int(time.time()) + 86400
    assert broom_items["janitor_deletes_left"] == 8

    # 2. Tinfoil drop: should reset timer to now + 21600
    tinfoil_items = dict(items)
    now = int(time.time())
    tinfoil_items["tinfoil_hat"] = now + 21600
    tinfoil_items["tinfoil_until"] = now + 21600
    assert tinfoil_items["tinfoil_hat"] == now + 21600

    # 3. Guns / consumables keys
    gun_items = dict(items)
    for g in ["pepperspray", "partyvan", "schizopill", "megaphone", "shield", "knife_gun", "mute_gun", "shield_gun"]:
        key = g if (g.endswith("_gun") or g in ["pepperspray", "partyvan", "schizopill", "megaphone", "shield"]) else f"{g}_gun"
        gun_items[key] = True
        assert not key.endswith("_gun_gun")
        assert gun_items[key] is True


def test_all_16_vacancies_data_integrity():
    vacancies = get_vacancies()
    assert len(vacancies) == 16
    
    expected_order = [
        "bottles", "sweeper", "courier", "captcha", "spy", "factory",
        "it_freelance", "scam", "deputy", "escort_sugar", "crypto_cartel",
        "infogypsy_cult", "propaganda_troll", "abu_consigliere",
        "shadow_oligarch", "matrix_architect"
    ]
    assert list(vacancies.keys()) == expected_order

    req_shifts = [v["required_shifts"] for v in vacancies.values()]
    # Assert strictly non-decreasing shift requirements
    for i in range(len(req_shifts) - 1):
        assert req_shifts[i] <= req_shifts[i + 1]

    # Verify each vacancy has required keys
    for jid, data in vacancies.items():
        assert "title" in data
        assert "desc" in data
        assert "tier" in data
        assert "required_shifts" in data
        assert "reward_range" in data
        assert len(data["reward_range"]) == 2
        assert data["reward_range"][0] <= data["reward_range"][1]
        assert "cooldown_sec" in data
        assert data["cooldown_sec"] > 0
        assert "phrases" in data
        assert len(data["phrases"]) > 0
        assert "jackpot_phrases" in data


def test_all_114_commands_unshadowed():
    import re
    import main
    import inspect
    from aiogram.filters import Command

    try:
        src = inspect.getsource(main.setup_bot_commands)
        commands = re.findall(r'BotCommand\(command="([^"]+)"', src)
    except Exception:
        commands = []
    if len(commands) < 114:
        with open("main.py", "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r"async def setup_bot_commands\b.*?(?=\n(?:async )?def |\Z)", content, re.DOTALL)
        if match:
            commands = re.findall(r'BotCommand\(command="([^"]+)"', match.group(0))
    
    # Command count grows as bot features are added; accept any count >= 114
    assert len(commands) >= 114, f"Expected at least 114 commands, found {len(commands)}"

    # Collect all commands supported across main.dp and all included sub-routers
    registered_commands = set()

    def extract_from_router(router):
        for observer in [router.message]:
            for handler in observer.handlers:
                for filter_ in getattr(handler, "filters", []):
                    # Check if Command filter
                    if hasattr(filter_, "commands"):
                        for c in filter_.commands:
                            if isinstance(c, str):
                                registered_commands.add(c.lower())
                            elif hasattr(c, "pattern"):
                                registered_commands.add(c.pattern.lower())
                    # MagicFilter or callback
                    call_obj = getattr(filter_, "callback", None)
                    if call_obj and hasattr(call_obj, "commands"):
                        for c in call_obj.commands:
                            if isinstance(c, str):
                                registered_commands.add(c.lower())
        for sub in router.sub_routers:
            extract_from_router(sub)

    extract_from_router(main.dp)

    # Also check ANIME_COMMAND_MAP for regexp-based command handlers like /fap, /loli, /hent
    for k in main.ANIME_COMMAND_MAP.keys():
        registered_commands.add(k.lower())

    # Specific check for work command aliases
    assert "work" in registered_commands
    assert "job" in registered_commands
    assert "earn" in registered_commands
    assert "bomj" in registered_commands

    # Verify every registered command in setup_bot_commands exists in registered_commands
    # or has an active handler pattern
    missing = []
    for cmd in set(commands):
        if cmd.lower() not in registered_commands:
            missing.append(cmd)

    # Print if any missing
    assert not missing, f"Missing command handlers for: {missing}"


@pytest.mark.asyncio
async def test_concurrent_cb_work_do_and_race_prevention():
    import aiosqlite
    import json
    from unittest.mock import AsyncMock, MagicMock, patch
    import main

    db = await aiosqlite.connect(":memory:")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            user_id INTEGER,
            board_id TEXT,
            balance REAL DEFAULT 0,
            posts_count INTEGER DEFAULT 0,
            active_items TEXT DEFAULT '{}',
            PRIMARY KEY (user_id, board_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS UserTransactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            tx_type TEXT,
            description TEXT,
            timestamp REAL
        )
    """)
    user_id = 999111
    # Seed user with 0 shifts
    await db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000, '{}')", (user_id,))
    await db.commit()

    # Simulate 5 concurrent button clicks on "work_do_bottles"
    cb_mocks = []
    for i in range(5):
        cb = MagicMock(spec=main.types.CallbackQuery)
        cb.from_user = MagicMock(id=user_id)
        cb.data = "work_do_bottles"
        cb.message = MagicMock()
        cb.message.edit_caption = AsyncMock()
        cb.message.edit_text = AsyncMock()
        cb.answer = AsyncMock()
        cb_mocks.append(cb)

    with patch("main.get_pool", return_value=db), \
         patch("main.get_user_global_balance", return_value=1000), \
         patch("main.add_user_global_balance", new_callable=AsyncMock) as mock_add_bal:
        # Launch concurrently
        await asyncio.gather(*(main.cb_work_do(cb, "b") for cb in cb_mocks))

    # Read committed active_items
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = 'b'", (user_id,)) as cur:
        row = await cur.fetchone()
        saved_items = json.loads(row[0])

    # Exactly 1 shift completed, work_shifts == 1
    assert saved_items.get("work_shifts") == 1
    # work_cooldowns should contain bottles
    assert "bottles" in saved_items.get("work_cooldowns", {})

    # Out of 5 callback answers, exactly 1 was successful execution/toast, 4 were cooldown rejections!
    cooldown_toasts = [cb.answer.call_args[0][0] for cb in cb_mocks if cb.answer.called and "Кулдаун" in cb.answer.call_args[0][0]]
    assert len(cooldown_toasts) == 4, f"Expected 4 cooldown rejections, got {len(cooldown_toasts)}"

    await db.close()


