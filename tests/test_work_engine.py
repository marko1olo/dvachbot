# -*- coding: utf-8 -*-
import asyncio
import json
import time
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

import aiosqlite
from common.work_engine import WORK_VACANCIES, execute_job_action
import main


def test_work_vacancies_structure():
    assert len(WORK_VACANCIES) == 16, f"Expected 16 vacancies, found {len(WORK_VACANCIES)}"
    
    expected_keys = [
        "bottles", "sweeper", "courier", "captcha", "spy", "factory",
        "it_freelance", "scam", "deputy", "escort_sugar", "crypto_cartel",
        "infogypsy_cult", "propaganda_troll", "abu_consigliere",
        "shadow_oligarch", "matrix_architect"
    ]
    for k in expected_keys:
        assert k in WORK_VACANCIES, f"Missing job key: {k}"
        job = WORK_VACANCIES[k]
        assert "title" in job
        assert "reward_range" in job and len(job["reward_range"]) == 2
        assert job["reward_range"][0] > 0 and job["reward_range"][1] >= job["reward_range"][0]
        assert "required_shifts" in job and job["required_shifts"] >= 0
        assert "cooldown_sec" in job and job["cooldown_sec"] > 0
        assert "risk_pct" in job and 0.0 <= job["risk_pct"] <= 1.0
        assert "phrases" in job and len(job["phrases"]) > 0


@pytest.mark.parametrize("job_id,job", list(WORK_VACANCIES.items()))
def test_all_16_vacancies_boundary_locks(job_id, job):
    req = job.get("required_shifts", 0)
    if req > 0:
        # At req - 1: must be locked
        items_locked = {"work_shifts": req - 1, "work_cooldowns": {}}
        succ, change, msg, drop = execute_job_action(job_id, items_locked)
        assert succ is False
        assert change == 0
        assert "заблокирована" in msg.lower()
        assert str(req) in msg
        assert str(req - 1) in msg
        assert drop is None

    # At req: must be unlocked and executable (never returns locked)
    items_unlocked = {"work_shifts": req, "work_cooldowns": {}}
    succ, change, msg, drop = execute_job_action(job_id, items_unlocked)
    assert isinstance(succ, bool)
    assert change > 0
    assert len(msg) > 0
    assert "заблокирована" not in msg.lower()


def test_unknown_job_id_rejection():
    items = {"work_shifts": 1000, "work_cooldowns": {}}
    succ, change, msg, drop = execute_job_action("non_existent_job", items)
    assert succ is False
    assert change == 0
    assert "Неизвестная вакансия" in msg
    assert drop is None


def test_cooldown_blocking_and_time_formatting():
    now = int(time.time())

    # Case A: Hours + Minutes (> 3600s left) on factory (cd = 7200s)
    items_h = {"work_shifts": 100, "work_cooldowns": {"factory": now - 1800}}  # 5400s left = 1h 30m
    succ, change, msg, drop = execute_job_action("factory", items_h)
    assert succ is False
    assert change == 0
    assert "кулдаун" in msg.lower()
    assert "1 ч 30 мин" in msg

    # Case B: Minutes only (60s <= left < 3600s) on courier (cd = 900s)
    items_m = {"work_shifts": 100, "work_cooldowns": {"courier": now - 300}}  # 600s left = 10m
    succ, change, msg, drop = execute_job_action("courier", items_m)
    assert succ is False
    assert change == 0
    assert "кулдаун" in msg.lower()
    assert "10 мин" in msg

    # Case C: Seconds only (left < 60s) on bottles (cd = 180s)
    items_s = {"work_shifts": 100, "work_cooldowns": {"bottles": now - 135}}  # 45s left
    succ, change, msg, drop = execute_job_action("bottles", items_s)
    assert succ is False
    assert change == 0
    assert "кулдаун" in msg.lower()
    assert "45 сек" in msg


def test_feet_slippers_cooldown_reduction():
    job_id = "courier"  # base cd 900s, 20% off = 720s
    now = int(time.time())

    # If 750 seconds have elapsed since last shift:
    # 1. Without slippers (cd = 900s): 150s remaining -> BLOCKED
    items_normal = {
        "work_shifts": 50,
        "work_cooldowns": {job_id: now - 750}
    }
    succ, change, msg, drop = execute_job_action(job_id, items_normal)
    assert succ is False
    assert "кулдаун" in msg.lower()

    # 2. With slippers (cd = 720s): 750s > 720s -> UNBLOCKED & SUCCESSFUL
    items_slippers = {
        "work_shifts": 50,
        "equipped_feet": "feet_slippers",
        "work_cooldowns": {job_id: now - 750}
    }
    succ, change, msg, drop = execute_job_action(job_id, items_slippers)
    assert change > 0
    assert "кулдаун" not in msg.lower()


def test_body_wasserman_buff():
    items = {
        "work_shifts": 50,
        "work_cooldowns": {},
        "equipped_torso": "body_wasserman"
    }
    # factory: reward_range (320, 650) * 1.25 -> 400 to 812
    with patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("factory", items)
        assert succ is True
        assert "Жилетка Вассермана: +25% ЗП" in msg
        assert change >= int(320 * 1.25)


def test_hat_crown_buff():
    # 1. Eligible job: deputy
    items_deputy = {
        "work_shifts": 150,
        "work_cooldowns": {},
        "equipped_head": "hat_crown"
    }
    with patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("deputy", items_deputy)
        assert succ is True
        assert "Корона: +20% чаевых" in msg
        assert change >= int(900 * 1.20)

    # 2. Non-eligible job: bottles
    items_bottles = {
        "work_shifts": 150,
        "work_cooldowns": {},
        "equipped_head": "hat_crown"
    }
    with patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("bottles", items_bottles)
        assert succ is True
        assert "Корона: +20% чаевых" not in msg


def test_face_glasses_buff():
    # 1. Eligible job: it_freelance
    items_it = {
        "work_shifts": 80,
        "work_cooldowns": {},
        "equipped_face": "face_wasserman_glasses"
    }
    with patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("it_freelance", items_it)
        assert succ is True
        assert "Очки Интеллекта: +15% ЗП" in msg
        assert change >= int(450 * 1.15)

    # 2. Eligible job with thug glasses: crypto_cartel
    items_crypto = {
        "work_shifts": 250,
        "work_cooldowns": {},
        "equipped_face": "face_thug_glasses"
    }
    with patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("crypto_cartel", items_crypto)
        assert succ is True
        assert "Очки Интеллекта: +15% ЗП" in msg
        assert change >= int(2000 * 1.15)

    # 3. Non-eligible job: sweeper
    items_sweeper = {
        "work_shifts": 80,
        "work_cooldowns": {},
        "equipped_face": "face_wasserman_glasses"
    }
    with patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("sweeper", items_sweeper)
        assert succ is True
        assert "Очки Интеллекта" not in msg


def test_wardrobe_set_bonuses_all():
    # A. Wasserman / Onotole Set (+40%)
    items_wass = {"work_shifts": 50, "work_cooldowns": {}}
    with patch("wardrobe_engine.get_active_set_bonus", return_value={"id": "set_wasserman"}), \
         patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("factory", items_wass)
        assert succ is True
        assert "Сет Онотоле: +40% ЗП" in msg
        assert change >= int(320 * 1.40)

    # B. Skuf Set (+35%)
    items_skuf = {"work_shifts": 50, "work_cooldowns": {}}
    with patch("wardrobe_engine.get_active_set_bonus", return_value={"id": "set_gop_skuf"}), \
         patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("factory", items_skuf)
        assert succ is True
        assert "Сет Скуфа: +35% получки" in msg
        assert change >= int(320 * 1.35)

    # C. Neo Set (+25%)
    items_neo = {"work_shifts": 50, "work_cooldowns": {}}
    with patch("wardrobe_engine.get_active_set_bonus", return_value={"id": "set_neo"}), \
         patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("factory", items_neo)
        assert succ is True
        assert "Сет Нео: +25% ЗП" in msg
        assert change >= int(320 * 1.25)

    # D. Riot Police / OMON Set (0% fine risk immunity)
    items_omon = {"work_shifts": 650, "work_cooldowns": {}}
    with patch("wardrobe_engine.get_active_set_bonus", return_value={"id": "set_riot_police"}), \
         patch("random.random", return_value=0.00001):  # Would fail without immunity
        succ, change, msg, drop = execute_job_action("matrix_architect", items_omon)
        assert succ is True
        assert "Спецназ: 0% штрафов" in msg

    # E. Anime Set (2.0x drop rate multiplier)
    items_anime = {"work_shifts": 50, "work_cooldowns": {}}
    with patch("wardrobe_engine.get_active_set_bonus", return_value={"id": "set_anime_hikka"}), \
         patch("random.random", side_effect=[0.5, 0.15]):
        # bottles drop chance = 0.08 * 2.0 = 0.16. 0.15 < 0.16 -> drop occurs!
        succ, change, msg, drop = execute_job_action("bottles", items_anime)
        assert succ is True
        assert drop == "trash_lootbox"

    # F. Hat Bag (1.5x drop rate multiplier)
    items_bag = {"work_shifts": 50, "work_cooldowns": {}, "equipped_head": "hat_bag"}
    with patch("random.random", side_effect=[0.5, 0.11]):
        # bottles drop chance = 0.08 * 1.5 = 0.12. 0.11 < 0.12 -> drop occurs!
        succ, change, msg, drop = execute_job_action("bottles", items_bag)
        assert succ is True
        assert drop == "trash_lootbox"


def test_stacking_gear_and_set_buffs():
    # Stacking: body_wasserman (+25%) + hat_crown (+20%) + set_wasserman (+40%) on deputy
    # Total mult = 1.0 + 0.25 + 0.20 + 0.40 = 1.85 (+85%)
    items = {
        "work_shifts": 150,
        "work_cooldowns": {},
        "equipped_torso": "body_wasserman",
        "equipped_head": "hat_crown",
        "unlocked_achievements": [
            "ach_first_work", "ach_work_10", "ach_work_50", "ach_work_100", "ach_work_150"
        ]
    }
    with patch("wardrobe_engine.get_active_set_bonus", return_value={"id": "set_wasserman"}), \
         patch("random.randint", return_value=1000), \
         patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("deputy", items)
        assert succ is True
        assert change == int(1000 * 1.85)
        assert "Жилетка Вассермана: +25% ЗП" in msg
        assert "Корона: +20% чаевых" in msg
        assert "Сет Онотоле: +40% ЗП" in msg


def test_jackpot_multiplier_calculation():
    items = {
        "work_shifts": 50,
        "work_cooldowns": {},
        "unlocked_achievements": ["ach_first_work", "ach_work_10", "ach_work_50"]
    }

    # Mock:
    # 1. risk check (random.random = 0.5 >= 0.15 -> no fail)
    # 2. base_reward (random.randint = 500)
    # 3. jackpot check (random.random = 0.01 < 0.04 -> is jackpot)
    # 4. jackpot mult (random.randint = 3)
    with patch("random.random", side_effect=[0.5, 0.01, 0.99]), \
         patch("random.randint", side_effect=[500, 3]):
        succ, change, msg, drop = execute_job_action("factory", items)
        assert succ is True
        assert change == 1500  # 500 * 3
        assert items["work_shifts"] == 51
        assert "factory" in items["work_cooldowns"]
        assert "💎" in msg or "ЗОЛОТАЯ" in msg or "УДАРНИК" in msg


def test_job_failure_and_fine_deduction():
    items = {"work_shifts": 50, "work_cooldowns": {}}
    # factory risk is 0.15, penalty is 90
    with patch("random.random", return_value=0.05):  # 0.05 < 0.15 -> FAIL
        succ, penalty, msg, drop = execute_job_action("factory", items)
        assert succ is False
        assert penalty == 90
        assert items["work_shifts"] == 50  # shifts NOT incremented on failure
        assert "factory" in items["work_cooldowns"]  # cooldown IS recorded
        assert drop is None
        assert "90" in msg


@pytest.mark.parametrize("start_shifts,expected_ach,expected_bonus", [
    (0, "ach_first_work", 50),
    (9, "ach_work_10", 100),
    (49, "ach_work_50", 500),
    (99, "ach_work_100", 1500),
    (149, "ach_work_150", 2500),
    (249, "ach_work_250", 4000),
    (399, "ach_work_400", 7500),
    (599, "ach_work_600", 15000),
])
def test_all_milestone_achievements_unlock(start_shifts, expected_ach, expected_bonus):
    milestone_order = [
        (1, "ach_first_work"),
        (10, "ach_work_10"),
        (50, "ach_work_50"),
        (100, "ach_work_100"),
        (150, "ach_work_150"),
        (250, "ach_work_250"),
        (400, "ach_work_400"),
        (600, "ach_work_600"),
    ]
    prior = [k for req, k in milestone_order if req <= start_shifts]
    items = {
        "work_shifts": start_shifts,
        "work_cooldowns": {},
        "unlocked_achievements": prior
    }
    with patch("random.random", return_value=0.5), \
         patch("random.randint", return_value=100):
        succ, change, msg, drop = execute_job_action("bottles", items)
        assert succ is True
        assert items["work_shifts"] == start_shifts + 1
        assert expected_ach in items.get("unlocked_achievements", [])
        assert change == 100 + expected_bonus
        assert "🏆 Ачивка" in msg
        assert str(expected_bonus) in msg


def test_milestone_achievements_no_duplicate_payout():
    items = {
        "work_shifts": 9,
        "work_cooldowns": {},
        "unlocked_achievements": ["ach_first_work", "ach_work_10"]
    }
    with patch("random.random", return_value=0.5), \
         patch("random.randint", return_value=100):
        succ, change, msg, drop = execute_job_action("bottles", items)
        assert succ is True
        assert change == 100  # no bonus added
        assert "🏆 Ачивка" not in msg


@pytest.mark.asyncio
async def test_build_work_card_length_under_1024_all_tiers():
    db_conn = await aiosqlite.connect(":memory:")
    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS Users (
            user_id INTEGER,
            board_id TEXT,
            balance REAL DEFAULT 0,
            posts_count INTEGER DEFAULT 0,
            active_items TEXT DEFAULT '{}',
            is_verified_b INTEGER DEFAULT 0,
            last_failed_amount REAL DEFAULT 0,
            custom_prefix TEXT DEFAULT NULL,
            prefix_expires_at REAL DEFAULT 0,
            cursed_until REAL DEFAULT 0,
            PRIMARY KEY (user_id, board_id)
        )
        """
    )
    await db_conn.commit()

    shift_levels = [0, 1, 3, 8, 15, 25, 40, 60, 85, 120, 160, 210, 270, 340, 420, 510, 620, 800, 1000]
    now = int(time.time())

    for shifts in shift_levels:
        items = {
            "work_shifts": shifts,
            "equipped_torso": "body_wasserman",
            "equipped_head": "hat_crown",
            "equipped_face": "face_wasserman_glasses",
            "equipped_feet": "feet_slippers",
            "work_cooldowns": {
                "bottles": now - 50,   # on cooldown (130s left)
                "sweeper": now - 1000, # ready
            }
        }
        await db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (999, 'b', 500000, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items",
            (json.dumps(items),)
        )
        await db_conn.commit()

        with patch("main.get_pool", return_value=db_conn), \
             patch("wardrobe_engine.get_active_set_bonus", return_value={"id": "set_wasserman"}):
            caption, markup = await main._build_work_card(999, "b")

            # 1. Caption length assertion
            assert len(caption) <= 1024, f"Caption length {len(caption)} exceeds 1024 for shifts={shifts}"
            assert "БИРЖА ТРУДА" in caption
            assert f"{shifts} смен" in caption

            # 2. Keyboard structure assertion
            # 8 rows of 2 vacancies + 1 row side hustles + 2 rows nav = 11 rows
            assert len(markup.inline_keyboard) == 11

            # 3. Check badge states on vacancy buttons
            all_buttons = [btn for row in markup.inline_keyboard[:8] for btn in row]
            assert len(all_buttons) == 16

            for btn in all_buttons:
                job_key = btn.callback_data.replace("work_do_", "")
                job_cfg = WORK_VACANCIES[job_key]
                req = job_cfg.get("required_shifts", 0)

                if shifts < req:
                    assert btn.text.startswith("🔒"), f"Job {job_key} should have 🔒 badge at shifts={shifts}"
                elif job_key == "bottles":
                    assert btn.text.startswith("⏳"), f"Job {job_key} should have ⏳ badge"
                else:
                    assert btn.text.startswith("✅"), f"Job {job_key} should have ✅ badge"

            # 4. Check side hustles and navigation
            all_callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
            assert "work_bottles" in all_callbacks
            assert "work_sell_mother" in all_callbacks
            assert "work_refresh" in all_callbacks
            assert "shop_main_hub" in all_callbacks
            assert "prof_wallet" in all_callbacks
            assert "avatar_view" in all_callbacks

    await db_conn.close()


@pytest.mark.asyncio
async def test_cb_work_do_drop_keys_handling():
    db_conn = await aiosqlite.connect(":memory:")
    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS Users (
            user_id INTEGER,
            board_id TEXT,
            balance REAL DEFAULT 0,
            posts_count INTEGER DEFAULT 0,
            active_items TEXT DEFAULT '{}',
            is_verified_b INTEGER DEFAULT 0,
            last_failed_amount REAL DEFAULT 0,
            custom_prefix TEXT DEFAULT NULL,
            prefix_expires_at REAL DEFAULT 0,
            cursed_until REAL DEFAULT 0,
            PRIMARY KEY (user_id, board_id)
        )
        """
    )
    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS UserTransactions (
            tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            tx_type TEXT,
            description TEXT,
            created_at REAL
        )
        """
    )
    await db_conn.commit()

    user_id = 555001
    await db_conn.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000, '{}')",
        (user_id,)
    )
    await db_conn.commit()

    # Helper to test cb_work_do with mocked drop
    async def _test_drop(dropped_item_name):
        await db_conn.execute("UPDATE Users SET active_items = '{}' WHERE user_id = ? AND board_id = 'b'", (user_id,))
        await db_conn.commit()

        cb = MagicMock()
        cb.data = "work_do_bottles"
        cb.from_user.id = user_id
        cb.answer = AsyncMock()
        cb.message.photo = None
        cb.message.edit_text = AsyncMock()
        cb.message.edit_caption = AsyncMock()

        with patch("main.get_pool", return_value=db_conn), \
             patch("main.execute_job_action", return_value=(True, 50, "Отработал смену!", dropped_item_name)):
            await main.cb_work_do(cb, board_id="b")

        async with db_conn.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = 'b'", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0])

    # 1. trash_lootbox
    items1 = await _test_drop("trash_lootbox")
    assert "trash_lootbox_gun" not in items1

    # 2. gold_safe
    items2 = await _test_drop("gold_safe")
    assert "gold_safe_gun" not in items2

    # 3. tinfoil_hat
    items3 = await _test_drop("tinfoil_hat")
    assert items3.get("tinfoil_hat", 0) > int(time.time())
    assert items3.get("tinfoil_until", 0) > int(time.time())
    assert "tinfoil_hat_gun" not in items3

    # 4. janitor_broom
    items4 = await _test_drop("janitor_broom")
    assert items4.get("janitor_deletes_left") == 3
    assert items4.get("janitor_until", 0) > int(time.time())
    assert "janitor_broom_gun" not in items4

    # 5. knife_gun (should not become knife_gun_gun)
    items5 = await _test_drop("knife_gun")
    assert items5.get("knife_gun") is True
    assert "knife_gun_gun" not in items5

    # 6. pepperspray
    items6 = await _test_drop("pepperspray")
    assert items6.get("pepperspray") is True
    assert "pepperspray_gun" not in items6

    # 7. partyvan
    items7 = await _test_drop("partyvan")
    assert items7.get("partyvan") is True

    # 8. mute_gun
    items8 = await _test_drop("mute_gun")
    assert items8.get("mute_gun") is True
    assert "mute_gun_gun" not in items8

    # 9. shield_gun
    items9 = await _test_drop("shield_gun")
    assert items9.get("shield_gun") is True
    assert "shield_gun_gun" not in items9

    # 10. schizopill
    items10 = await _test_drop("schizopill")
    assert items10.get("schizopill") is True

    # 11. megaphone
    items11 = await _test_drop("megaphone")
    assert items11.get("megaphone") is True

    # 12. shield
    items12 = await _test_drop("shield")
    assert items12.get("shield") is True

    await db_conn.close()
