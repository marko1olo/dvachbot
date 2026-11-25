# -*- coding: utf-8 -*-
import json
import time
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

import aiosqlite
from common.work_engine import WORK_VACANCIES, execute_job_action, is_night_shift_active
import main


@pytest.fixture(autouse=True)
def mock_daytime_work():
    """Default unit tests assume daytime (no night 1.5x bonus) unless explicitly overridden."""
    with patch("common.work_engine.is_night_shift_active", return_value=False):
        yield


def test_work_vacancies_structure():
    assert len(WORK_VACANCIES) == 26, f"Expected 26 vacancies, found {len(WORK_VACANCIES)}"

    expected_keys = [
        "bottles", "sweeper", "shoplifter", "courier", "captcha", "cho_security", "spy",
        "crypto_wiper", "factory", "mod_b", "it_freelance", "scam", "deputy", "cam_model",
        "escort_sugar", "crypto_cartel", "darknet_courier", "infogypsy_cult",
        "propaganda_troll", "abu_consigliere", "shadow_oligarch", "matrix_architect",
        "deep_state_operator", "cheburnet_leviathan", "zog_chairman", "dvach_creator"
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
        assert "Сет Сыча: +35% получки" in msg
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
        # Cap rule: salary_mult (1.0) * jackpot_mult (3) is capped at 2.25x
        # 500 * 2.25 = 1125 (formerly uncapped at 1500)
        assert change == 1125
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
        res = execute_job_action("bottles", items)
        succ, change, msg, drop = res
        assert succ is True
        assert items["work_shifts"] == start_shifts + 1
        assert expected_ach in items.get("unlocked_achievements", [])
        # Shift reward is pure work payout (100), NOT inflated with achievement bonus
        assert change == 100
        # Unlocked achievement is passed separately in result tuple and active_items
        assert res.achievement is not None
        assert res.achievement["id"] == expected_ach
        assert res.ach_bonus == expected_bonus
        assert res[4]["id"] == expected_ach
        assert items.get("last_unlocked_achievement")["id"] == expected_ach
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
            # 13 rows of vacancies (13 rows of 2 = 26) + 4 rows side hustles + 2 rows nav = 19 rows
            assert len(markup.inline_keyboard) == 19

            # 3. Check badge states on vacancy buttons
            all_buttons = [btn for row in markup.inline_keyboard[:13] for btn in row]
            assert len(all_buttons) == 26

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
            assert "work_dumpster" in all_callbacks
            assert "work_flyers" in all_callbacks
            assert "work_microloan" in all_callbacks
            assert "work_overtime" in all_callbacks
            assert "work_quests" in all_callbacks
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


@pytest.mark.asyncio
async def test_work_alert_toggle_callbacks():
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

    user_id = 777001
    await db_conn.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000, '{}')",
        (user_id,)
    )
    await db_conn.commit()

    cb = MagicMock()
    cb.data = "work_toggle_alerts"
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message.photo = None
    cb.message.edit_text = AsyncMock()
    cb.message.edit_caption = AsyncMock()

    with patch("main.get_pool", return_value=db_conn):
        # 1. Toggle ON -> OFF (since default is False, not False -> True)
        await main.cb_work_toggle_alerts(cb, board_id="b")
        cb.answer.assert_called_with("🔕 Уведомления о работе отключены.", show_alert=True)
        async with db_conn.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            data = json.loads(row[0])
            assert data.get("work_alerts_disabled") is True

        # 2. Toggle back: True -> False
        await main.cb_work_toggle_alerts(cb, board_id="b")
        cb.answer.assert_called_with("🔔 Уведомления о работе включены!", show_alert=True)
        async with db_conn.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            data = json.loads(row[0])
            assert data.get("work_alerts_disabled") is False

        # 3. Explicit toggle OFF via cb_work_alert_toggle_off
        await main.cb_work_alert_toggle_off(cb, board_id="b")
        cb.answer.assert_called_with("🔕 Напоминалки о работе отключены! Бот больше не будет писать в ЛС.", show_alert=True)
        async with db_conn.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            data = json.loads(row[0])
            assert data.get("work_alerts_disabled") is True

    await db_conn.close()


def test_night_shift_active_and_multiplier():
    """Verifies that night shift (00:00-07:00 MSK) applies 1.5x multiplier."""
    from datetime import datetime, timezone
    # 03:00 MSK = 00:00 UTC
    utc_midnight = int(datetime(2026, 10, 2, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    assert is_night_shift_active(utc_midnight) is True

    # 15:00 MSK = 12:00 UTC
    utc_noon = int(datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc).timestamp())
    assert is_night_shift_active(utc_noon) is False

    # Execute job during night
    items = {"work_shifts": 0, "work_cooldowns": {}}
    with patch("common.work_engine.is_night_shift_active", return_value=True), \
         patch("random.random", return_value=0.5), \
         patch("random.randint", return_value=100):
        res = execute_job_action("bottles", items)
        succ, change, msg, drop = res
        assert succ is True
        # 100 base * 1.5 night = 150 (milestone ach_first_work bonus is separated)
        assert change == 150
        assert res.achievement["id"] == "ach_first_work"
        assert res.ach_bonus == 50
        assert "Ночной тариф x1.5" in msg



# =====================================================================
# GLOBAL DAILY FATIGUE, HARD CAPS & ACHIEVEMENT SEPARATION TESTS
# =====================================================================

def test_global_daily_fatigue_scale_tiers():
    """
    Verifies the 5 distinct global daily fatigue tiers:
    1–3 shifts: 100%
    4–6 shifts: 80% (-20%)
    7–10 shifts: 55% (-45%)
    11–15 shifts: 35% (-65%)
    16+ shifts: 20% (-80% floor)
    """
    now = int(time.time())

    # Tier 1: Shifts 1-3 (100% payout, no fatigue note)
    for prior_count in [0, 1, 2]:
        prior_shifts = [now - 1000 - i * 60 for i in range(prior_count)]
        items = {
            "work_shifts": 50,
            "work_cooldowns": {},
            "recent_shifts": {"bottles": prior_shifts},
            "unlocked_achievements": ["ach_first_work", "ach_work_10", "ach_work_50"]
        }
        with patch("random.random", return_value=0.5), patch("random.randint", return_value=100):
            succ, reward, msg, _ = execute_job_action("bottles", items)
            assert succ is True
            assert reward == 100, f"Expected 100 at prior={prior_count}, got {reward}"
            assert "Усталость" not in msg

    # Tier 2: Shifts 4-6 (80% payout)
    for prior_count in [3, 4, 5]:
        prior_shifts = [now - 1000 - i * 60 for i in range(prior_count)]
        items = {
            "work_shifts": 50,
            "work_cooldowns": {},
            "recent_shifts": {"bottles": prior_shifts},
            "unlocked_achievements": ["ach_first_work", "ach_work_10", "ach_work_50"]
        }
        with patch("random.random", return_value=0.5), patch("random.randint", return_value=100):
            succ, reward, msg, _ = execute_job_action("bottles", items)
            assert succ is True
            assert reward == 80
            assert f"смена #{prior_count + 1}" in msg
            assert "-20%" in msg

    # Tier 3: Shifts 7-10 (55% payout)
    for prior_count in [6, 7, 8, 9]:
        prior_shifts = [now - 1000 - i * 60 for i in range(prior_count)]
        items = {
            "work_shifts": 50,
            "work_cooldowns": {},
            "recent_shifts": {"bottles": prior_shifts},
            "unlocked_achievements": ["ach_first_work", "ach_work_10", "ach_work_50"]
        }
        with patch("random.random", return_value=0.5), patch("random.randint", return_value=100):
            succ, reward, msg, _ = execute_job_action("bottles", items)
            assert succ is True
            assert reward == 55
            assert f"смена #{prior_count + 1}" in msg
            assert "-45%" in msg

    # Tier 4: Shifts 11-15 (35% payout)
    for prior_count in [10, 11, 12, 13, 14]:
        prior_shifts = [now - 1000 - i * 60 for i in range(prior_count)]
        items = {
            "work_shifts": 50,
            "work_cooldowns": {},
            "recent_shifts": {"bottles": prior_shifts},
            "unlocked_achievements": ["ach_first_work", "ach_work_10", "ach_work_50"]
        }
        with patch("random.random", return_value=0.5), patch("random.randint", return_value=100):
            succ, reward, msg, _ = execute_job_action("bottles", items)
            assert succ is True
            assert reward == 35
            assert f"смена #{prior_count + 1}" in msg
            assert "-65%" in msg

    # Tier 5: Shifts 16+ (20% floor payout)
    for prior_count in [15, 20, 25]:
        prior_shifts = [now - 1000 - i * 60 for i in range(prior_count)]
        items = {
            "work_shifts": 50,
            "work_cooldowns": {},
            "recent_shifts": {"bottles": prior_shifts},
            "unlocked_achievements": ["ach_first_work", "ach_work_10", "ach_work_50"]
        }
        with patch("random.random", return_value=0.5), patch("random.randint", return_value=100):
            succ, reward, msg, _ = execute_job_action("bottles", items)
            assert succ is True
            assert reward == 20
            assert f"смена #{prior_count + 1}" in msg
            assert "-80%" in msg


def test_global_fatigue_cross_vacancy():
    """
    Verifies that shifts completed on one vacancy (e.g. bottles, sweeper, shoplifter)
    cause fatigue on a completely different vacancy (e.g. courier).
    Prevents button-mashing across all 26 vacancies.
    """
    now = int(time.time())
    # User completed 3 shifts across 3 different vacancies in the last 24h
    items = {
        "work_shifts": 50,
        "work_cooldowns": {},
        "recent_shifts": {
            "bottles": [now - 3600],
            "sweeper": [now - 2400],
            "shoplifter": [now - 1200],
        },
        "unlocked_achievements": ["ach_first_work", "ach_work_10", "ach_work_50"]
    }

    # Working 'courier' now is the 4th shift overall -> 80% multiplier (-20% fatigue)
    with patch("random.random", return_value=0.5), patch("random.randint", return_value=100):
        succ, reward, msg, _ = execute_job_action("courier", items)
        assert succ is True
        assert reward == 80
        assert "⚡ Усталость: -20% (смена #4)" in msg


def test_multiplier_hard_cap_2_25x():
    """
    Verifies that stacked multipliers (gear + night + jackpot) are strictly capped at 2.25x.
    """
    # Wasserman (+25%) + Crown (+20%) + Set Wasserman (+40%) = 1.85x
    # During night (1.5x) -> 1.85 * 1.5 = 2.78x -> must be capped at 2.25x!
    items = {
        "work_shifts": 150,
        "work_cooldowns": {},
        "equipped_torso": "body_wasserman",
        "equipped_head": "hat_crown",
        "unlocked_achievements": ["ach_first_work", "ach_work_10", "ach_work_50", "ach_work_100", "ach_work_150"]
    }
    with patch("wardrobe_engine.get_active_set_bonus", return_value={"id": "set_wasserman"}),          patch("common.work_engine.is_night_shift_active", return_value=True),          patch("random.randint", return_value=1000),          patch("random.random", return_value=0.5):
        succ, change, msg, drop = execute_job_action("deputy", items)
        assert succ is True
        # 1000 * 2.25 = 2250 (not 1000 * 2.78 = 2780)
        assert change == 2250


def test_reward_absolute_hard_cap_45k():
    """
    Verifies absolute ceiling of 45,000 ₪ per shift.
    Even with dvach_creator (base 88,888 ₪) and max multiplier (2.25x), payout is capped at 45,000 ₪.
    """
    items = {
        "work_shifts": 1337,
        "work_cooldowns": {},
        "equipped_head": "hat_helmet",  # 0% risk
        "unlocked_achievements": [
            "ach_first_work", "ach_work_10", "ach_work_50", "ach_work_100",
            "ach_work_150", "ach_work_250", "ach_work_400", "ach_work_600",
            "ach_work_800", "ach_work_1000", "ach_work_1337"
        ]
    }
    # Mock base reward = 88888, jackpot mult = 3 (combined mult capped at 2.25x)
    # 88,888 * 2.25 = 199,998 -> hard capped at 45,000!
    with patch("random.random", side_effect=[0.5, 0.01, 0.99]),          patch("random.randint", side_effect=[88888, 3]):
        succ, change, msg, _ = execute_job_action("dvach_creator", items)
        assert succ is True
        assert change == 45000, f"Expected 45,000 ₪ cap, got {change} ₪!"


def test_achievement_separation_high_milestone_no_inflation():
    """
    Verifies that high-tier milestone achievements (ach_work_1000 = +50k, ach_work_1337 = +100k)
    do NOT inflate the work shift reward or get recorded into the shift payout.
    """
    # Transitioning from 999 -> 1000 shifts (unlocks ach_work_1000, worth +50,000 ₪)
    items = {
        "work_shifts": 999,
        "work_cooldowns": {},
        "unlocked_achievements": ["ach_first_work", "ach_work_10", "ach_work_50", "ach_work_100", "ach_work_150", "ach_work_250", "ach_work_400", "ach_work_600", "ach_work_800"]
    }
    with patch("random.random", return_value=0.5), patch("random.randint", return_value=100):
        res = execute_job_action("bottles", items)
        succ, change, msg, _ = res
        assert succ is True
        # Shift reward is strictly pure payout (100 ₪), NOT 50,100 ₪!
        assert change == 100
        assert res.achievement["id"] == "ach_work_1000"
        assert res.ach_bonus == 50000
        assert "ach_work_1000" in items["unlocked_achievements"]
        assert "50000" in msg



# =====================================================================
# UI TRANSPARENCY & DAILY FATIGUE HELPER TESTS
# =====================================================================

def test_get_user_daily_fatigue_info_all_tiers():
    """
    Verifies get_user_daily_fatigue_info returns correct structure and values
    for all 5 daily fatigue tiers.
    """
    from common.work_engine import get_user_daily_fatigue_info, format_fatigue_badge
    now = 1700000000

    # 1. Tier 1: 0-3 shifts (100% efficiency, next_tier_at: 4)
    for count in [0, 1, 2, 3]:
        shifts = {"bottles": [now - i * 100 for i in range(count)]}
        info = get_user_daily_fatigue_info(shifts, now=now)
        assert info["shifts_today"] == count
        assert info["efficiency_pct"] == 100
        assert info["tier_desc"] == "1-3 смены (100%)"
        assert info["next_tier_at"] == 4
        badge = format_fatigue_badge(info)
        assert badge == f"⚡ Смена за сутки: {count} | Эффективность: 100%"

    # 2. Tier 2: 4-6 shifts (80% efficiency, next_tier_at: 7)
    # format_fatigue_badge appends " • спад {recovery_text}" when eff < 100 and recovery_text is set.
    # Shifts are spaced 100s apart, so oldest shift decays in ~86400 - (count-1)*100 sec → recovery_text is set.
    for count in [4, 5, 6]:
        shifts = {"bottles": [now - i * 100 for i in range(count)]}
        info = get_user_daily_fatigue_info(shifts, now=now)
        assert info["shifts_today"] == count
        assert info["efficiency_pct"] == 80
        assert info["tier_desc"] == "4-6 смен (80%)"
        assert info["next_tier_at"] == 7
        assert info["recovery_text"], "recovery_text must be non-empty when shifts are within 24h window"
        badge = format_fatigue_badge(info)
        expected_prefix = f"⚡ Смена за сутки: {count} | Эффективность: 80% (усталость -20%"
        assert badge.startswith(expected_prefix), f"badge={badge!r}"
        assert " • спад " in badge, f"expected recovery suffix in badge: {badge!r}"

    # 3. Tier 3: 7-10 shifts (55% efficiency, next_tier_at: 11)
    for count in [7, 8, 9, 10]:
        shifts = {"bottles": [now - i * 100 for i in range(count)]}
        info = get_user_daily_fatigue_info(shifts, now=now)
        assert info["shifts_today"] == count
        assert info["efficiency_pct"] == 55
        assert info["tier_desc"] == "7-10 смен (55%)"
        assert info["next_tier_at"] == 11
        badge = format_fatigue_badge(info)
        expected_prefix = f"⚡ Смена за сутки: {count} | Эффективность: 55% (усталость -45%"
        assert badge.startswith(expected_prefix), f"badge={badge!r}"

    # 4. Tier 4: 11-15 shifts (35% efficiency, next_tier_at: 16)
    for count in [11, 13, 15]:
        shifts = {"bottles": [now - i * 100 for i in range(count)]}
        info = get_user_daily_fatigue_info(shifts, now=now)
        assert info["shifts_today"] == count
        assert info["efficiency_pct"] == 35
        assert info["tier_desc"] == "11-15 смен (35%)"
        assert info["next_tier_at"] == 16
        badge = format_fatigue_badge(info)
        expected_prefix = f"⚡ Смена за сутки: {count} | Эффективность: 35% (усталость -65%"
        assert badge.startswith(expected_prefix), f"badge={badge!r}"

    # 5. Tier 5: 16+ shifts (20% floor efficiency, next_tier_at: None)
    for count in [16, 20, 50]:
        shifts = {"bottles": [now - i * 100 for i in range(count)]}
        info = get_user_daily_fatigue_info(shifts, now=now)
        assert info["shifts_today"] == count
        assert info["efficiency_pct"] == 20
        assert info["tier_desc"] == "16+ смен (20%)"
        assert info["next_tier_at"] is None
        badge = format_fatigue_badge(info)
        expected_prefix = f"⚡ Смена за сутки: {count} | Эффективность: 20% (усталость -80%"
        assert badge.startswith(expected_prefix), f"badge={badge!r}"


def test_get_user_daily_fatigue_info_input_formats_and_expiry():
    """
    Verifies robust handling of None, list, int, future and expired timestamps.
    """
    from common.work_engine import get_user_daily_fatigue_info
    now = 1700000000

    # None and empty
    assert get_user_daily_fatigue_info(None, now=now)["shifts_today"] == 0
    assert get_user_daily_fatigue_info({}, now=now)["shifts_today"] == 0
    assert get_user_daily_fatigue_info([], now=now)["shifts_today"] == 0

    # Direct integer: the function treats int as a *single timestamp* value, not a shift count.
    # int=4 is Unix epoch Jan 1970 — far outside the 24h window → 0 valid shifts.
    assert get_user_daily_fatigue_info(4, now=now)["shifts_today"] == 0
    assert get_user_daily_fatigue_info(4, now=now)["efficiency_pct"] == 100  # 0 shifts → 100%
    # A recent timestamp treated as single-shift input → 1 valid shift
    assert get_user_daily_fatigue_info(now - 100, now=now)["shifts_today"] == 1
    assert get_user_daily_fatigue_info(now - 100, now=now)["efficiency_pct"] == 100

    # List format
    shifts_list = [now - 100, now - 200, now - 300, now - 400]
    assert get_user_daily_fatigue_info(shifts_list, now=now)["shifts_today"] == 4

    # Timestamp expiration (older than 86400s) and future timestamps (> now)
    shifts_mixed = {
        "bottles": [now - 90000, now - 86401, now - 1000],  # only 1 valid
        "sweeper": [now + 500, now - 2000]                   # only 1 valid
    }
    assert get_user_daily_fatigue_info(shifts_mixed, now=now)["shifts_today"] == 2


@pytest.mark.asyncio
async def test_work_ui_transparency_in_menu_and_result():
    """
    Verifies that the fatigue status badge is rendered in:
    1. /work menu (_build_work_card)
    2. shift result message (execute_job_action)
    """
    import main
    from common.work_engine import execute_job_action

    now = int(time.time())
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

    # User with 4 shifts today (80% tier)
    items = {
        "work_shifts": 4,
        "work_cooldowns": {},
        "recent_shifts": {
            "bottles": [now - 3000, now - 2000, now - 1000, now - 500]
        }
    }
    await db_conn.execute(
        "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (888, 'b', 1000, ?)",
        (json.dumps(items),)
    )
    await db_conn.commit()

    with patch("main.get_pool", return_value=db_conn):
        caption, _ = await main._build_work_card(888, "b")
        assert "⚡ Смена за сутки: 4 | Эффективность: 80% (усталость -20%)" in caption

    # Check shift execution result includes fatigue status
    with patch("random.random", return_value=0.5), patch("random.randint", return_value=100):
        # 5th shift -> Tier 2 (80%)
        succ, change, msg, drop = execute_job_action("bottles", items)
        assert succ is True
        assert "⚡ Смена за сутки: 5 | Эффективность: 80% (усталость -20%)" in msg

    await db_conn.close()
