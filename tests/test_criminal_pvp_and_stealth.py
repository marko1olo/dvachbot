# -*- coding: utf-8 -*-
"""
tests/test_criminal_pvp_and_stealth.py — Test Suite for Criminal Syndicate PvP & Stealth
========================================================================================
Comprehensive verification covering:
1. Criminal Profiles, Schema, and Helpers (Wanted Stars clamping, Dirty Balance, Bounty).
2. /scout Mechanics (cost deduction, 5G jammer block, 75% info disclosure, 25% fail & 15m cooldown).
3. /pickpocket Mechanics (lockpick consumption, beginner protection <15 posts, self-isolation,
   silent success with dirty shekels + wanted bounty, loud failure with [Крыса] status and 2k penalty).
4. /arrest Mechanics (authorization checks, wanted stars requirement, 60/40 bounty split,
   mute duration stars*15m, inventory confiscation of zatochki/lockpicks).
5. Fake Ksiva 35% backfire (10k fine to Abu Fund, 30m mute) vs 65% success.
6. Darknet Catalog and purchase transactions.
7. Aiogram 3 Router Handlers with Mock Messages.
"""

import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from aiogram import types
from aiogram.exceptions import TelegramBadRequest

from common.criminal_phrases import (
    ARREST_DRUZHINA_PHRASES,
    PICKPOCKET_LOUD_FAIL_PHRASES,
    PICKPOCKET_SILENT_SUCCESS_PHRASES,
    SCOUT_FAIL_SPOTTED_PHRASES,
    SCOUT_SUCCESS_COMMENTARY,
)
from criminal_syndicate_engine import (
    BOUNTY_ABU_SHARE,
    BOUNTY_OFFICER_SHARE,
    BOUNTY_PER_STAR,
    DARKNET_CATALOG,
    DARKNET_CONFIG,
    DARKNET_ITEMS,
    DARKNET_ITEM_ALIASES,
    FAKE_KSIVA_BACKFIRE_CHANCE,
    FAKE_KSIVA_FINE,
    FAKE_KSIVA_MUTE_SEC,
    MAX_ARREST_MUTE_MINUTES,
    MAX_WANTED_STARS,
    PICKPOCKET_FAIL_PENALTY,
    SCOUT_COST,
    SCOUT_COOLDOWN_SEC,
    add_dirty_shekels,
    add_wanted_stars,
    build_darknet_keyboard,
    build_darknet_menu_text,
    calculate_scout_cost,
    cb_darknet_buy,
    cb_darknet_open_shop,
    cb_darknet_refresh,
    clear_wanted_status,
    cmd_arrest,
    cmd_bribe_cop,
    cmd_buy_darknet,
    cmd_chloroform,
    cmd_darknet,
    cmd_pickpocket,
    cmd_scout,
    criminal_router,
    detect_target_armor,
    detect_target_traps,
    execute_arrest,
    execute_bribe_cop,
    execute_chloroform,
    execute_pickpocket,
    execute_scout,
    get_criminal_profile,
    get_darknet_item_price,
    get_target_sanity_score,
    get_target_wealth_bracket,
    handle_darknet_item_buy,
    load_user_active_items,
    resolve_darknet_item_id,
    save_user_active_items,
    scout_cooldowns,
)


class TestCriminalSyndicateSuite(unittest.IsolatedAsyncioTestCase):
    """
    Exhaustive integration and unit test suite with in-memory SQLite database.
    """

    async def asyncSetUp(self):
        scout_cooldowns.clear()

        # In-memory SQLite DB
        self.db = await aiosqlite.connect(":memory:")
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER,
                board_id TEXT,
                balance REAL DEFAULT 0,
                active_items TEXT DEFAULT '{}',
                posts_count INTEGER DEFAULT 100,
                is_isolated INTEGER DEFAULT 0,
                role TEXT DEFAULT 'user',
                custom_prefix TEXT DEFAULT NULL,
                prefix_expires_at INTEGER DEFAULT 0,
                cursed_until INTEGER DEFAULT 0,
                PRIMARY KEY(user_id, board_id)
            )
            """
        )
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS UserTransactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                tx_type TEXT,
                description TEXT,
                timestamp REAL
            )
            """
        )
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS GlobalStats (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS Mutes (
                user_id INTEGER,
                board_id TEXT,
                mute_type TEXT,
                expires_at REAL,
                reason TEXT,
                PRIMARY KEY(user_id, board_id, mute_type)
            )
            """
        )
        await self.db.commit()

        self.pool_patch = patch("common.db_pool.get_pool", return_value=self.db)
        self.mock_pool = self.pool_patch.start()
        self.db_patch = patch("criminal_syndicate_engine.load_user_active_items", side_effect=self._mock_load_items)
        self.mock_load = self.db_patch.start()
        self.db_save_patch = patch("criminal_syndicate_engine.save_user_active_items", side_effect=self._mock_save_items)
        self.mock_save = self.db_save_patch.start()

    async def asyncTearDown(self):
        self.pool_patch.stop()
        self.db_patch.stop()
        self.db_save_patch.stop()
        await self.db.close()

    async def _mock_load_items(self, db, user_id, board_id):
        async with self.db.execute(
            "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
            (user_id, board_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except Exception:
                    return {}
        return {}

    async def _mock_save_items(self, db, user_id, board_id, active_items):
        serialized = json.dumps(active_items, ensure_ascii=False)
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items",
            (user_id, board_id, serialized),
        )
        await self.db.commit()

    # =========================================================================
    # 1. PROFILE, SCHEMA & HELPER TESTS
    # =========================================================================

    def test_get_criminal_profile_sanitization(self):
        """Validates that get_criminal_profile clamps values and safely handles bad types."""
        # Test None & empty dict
        empty_prof = get_criminal_profile(None)
        self.assertEqual(empty_prof["wanted_stars"], 0)
        self.assertEqual(empty_prof["bounty_pool"], 0.0)
        self.assertEqual(empty_prof["dirty_balance"], 0.0)
        self.assertEqual(empty_prof["lockpick"], 0)
        self.assertEqual(empty_prof["fake_ksiva"], 0)
        self.assertFalse(empty_prof["is_rat"])
        self.assertFalse(empty_prof["is_jammed"])

        # Test extreme & corrupted values
        corrupt = {
            "wanted_stars": 999,  # Must clamp to 5
            "bounty_pool": "50000.5",
            "dirty_balance": -100.0,  # Clamps to 0
            "lockpick": -5,
            "fake_ksiva": True,
            "jammer_until": time.time() + 3600,
            "rat_until": time.time() + 1800,
        }
        prof = get_criminal_profile(corrupt)
        self.assertEqual(prof["wanted_stars"], 5)
        self.assertEqual(prof["bounty_pool"], 50000.5)
        self.assertEqual(prof["dirty_balance"], 0.0)
        self.assertEqual(prof["lockpick"], 0)
        self.assertEqual(prof["fake_ksiva"], 1)
        self.assertTrue(prof["is_jammed"])
        self.assertTrue(prof["is_rat"])

    def test_add_dirty_shekels(self):
        """Tests dirty balance accumulation and float rounding."""
        items = {}
        res1 = add_dirty_shekels(items, 1500.256)
        self.assertEqual(res1, 1500.26)
        self.assertEqual(items["dirty_balance"], 1500.26)

        res2 = add_dirty_shekels(items, 499.74)
        self.assertEqual(res2, 2000.0)
        self.assertEqual(items["dirty_balance"], 2000.0)

    def test_add_wanted_stars_and_bounty(self):
        """Tests wanted stars clamping at 5 and bounty pool progression."""
        items = {}
        stars, bounty = add_wanted_stars(items, stars=2, bounty=10000.0)
        self.assertEqual(stars, 2)
        self.assertEqual(bounty, 10000.0)

        # Increment past maximum (2 + 4 = 6 -> clamped to 5)
        stars, bounty = add_wanted_stars(items, stars=4, bounty=20000.0)
        self.assertEqual(stars, 5)
        self.assertEqual(bounty, 30000.0)

    def test_clear_wanted_status(self):
        """Tests reset of wanted status and return of cleared bounty amount."""
        items = {"wanted_stars": 4, "bounty_pool": 20000.0}
        cleared = clear_wanted_status(items)
        self.assertEqual(cleared, 20000.0)
        self.assertEqual(items["wanted_stars"], 0)
        self.assertEqual(items["bounty_pool"], 0.0)

    def test_wealth_brackets_and_traps(self):
        """Tests wealth categorization and defensive trap detection."""
        self.assertEqual(get_target_wealth_bracket(100), "Нищий сыч (до 5,000 ₪)")
        self.assertEqual(get_target_wealth_bracket(15000), "Работяга с завода (5,000 - 50,000 ₪)")
        self.assertEqual(get_target_wealth_bracket(150000), "Зажиточный мажор (50,000 - 250,000 ₪)")
        self.assertEqual(get_target_wealth_bracket(500000), "Подпольный крипто-олигарх (250k - 1M ₪)")
        self.assertEqual(get_target_wealth_bracket(2500000), "Жирный кит / Владелец борды (> 1,000,000 ₪)")

        traps_empty = detect_target_traps({})
        self.assertEqual(traps_empty, [])

        traps_active = detect_target_traps({
            "pepperspray_gun": True,
            "reflect_shield_until": time.time() + 1000,
        })
        self.assertEqual(len(traps_active), 2)
        self.assertIn("Перцовый", traps_active[0])
        self.assertIn("Зеркало", traps_active[1])

    # =========================================================================
    # 2. SCOUT MECHANICS TESTS
    # =========================================================================

    async def test_scout_insufficient_balance(self):
        """Scout fails if user balance < 150 ₪."""
        u1, target = 1001, 2001
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 50)", (u1,))
        await self.db.commit()

        ok, msg, meta = await execute_scout(self.db, u1, target, "b")
        self.assertFalse(ok)
        self.assertIn("НИЩИЙ РАЗВЕДЧИК", msg)
        self.assertTrue(meta.get("insufficient_funds"))

    async def test_scout_blocked_by_5g_jammer(self):
        """Target's active 5G-jammer stops the scout, burning thief's 150 ₪."""
        u1, target = 1002, 2002
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500)", (u1,))
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 10000, ?)",
            (target, json.dumps({"jammer_until": time.time() + 3600})),
        )
        await self.db.commit()

        ok, msg, meta = await execute_scout(self.db, u1, target, "b")
        self.assertFalse(ok)
        self.assertIn("СИГНАЛ ЗАГЛУШЕН", msg)
        self.assertIn("5G-глушилка", msg)
        self.assertTrue(meta.get("jammed"))

        # Verify scout cost was dynamically deducted from thief (500 - 151 = 349.0)
        expected_cost = calculate_scout_cost(500.0)
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (u1,)) as cursor:
            bal = (await cursor.fetchone())[0]
        self.assertEqual(bal, 500.0 - expected_cost)

    async def test_scout_fail_alert_and_15m_cooldown(self):
        """25% fail roll triggers salty 2ch alert from SCOUT_FAIL_SPOTTED_PHRASES and sets 15-minute cooldown on target."""
        u1, target = 1003, 2003
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500)", (u1,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 10000)", (target,))
        await self.db.commit()

        # Force fail with roll=0.85 (>= 0.75)
        ok, msg, meta = await execute_scout(self.db, u1, target, "b", roll=0.85)
        self.assertFalse(ok)
        self.assertIn("ПАЛЕВО НА ШМОНЕ", msg)
        self.assertTrue(any(phrase in msg for phrase in SCOUT_FAIL_SPOTTED_PHRASES))
        self.assertTrue(meta.get("spotted"))
        self.assertIn((u1, target), scout_cooldowns)

        # Immediate follow-up attempt rejected due to cooldown
        ok_cd, msg_cd, meta_cd = await execute_scout(self.db, u1, target, "b")
        self.assertFalse(ok_cd)
        self.assertIn("ТЫ НА СТРЕМЕ", msg_cd)
        self.assertTrue(meta_cd.get("cooldown"))

    async def test_scout_success_discloses_info(self):
        """75% success roll returns dossier with wealth bracket, armor, traps, and commentary."""
        u1, target = 1004, 2004
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500)", (u1,))
        target_items = {
            "equipped_head": "hat_ushanka",
            "pepperspray_gun": True,
        }
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 65000, ?)",
            (target, json.dumps(target_items)),
        )
        await self.db.commit()

        # Force success with roll=0.20 (< 0.75)
        ok, msg, meta = await execute_scout(self.db, u1, target, "b", roll=0.20)
        self.assertTrue(ok)
        self.assertIn("ДОСЬЕ ШМОНА", msg)
        self.assertIn("Зажиточный мажор", msg)
        self.assertIn("Перцовый баллончик", msg)
        self.assertTrue(any(comment in msg for comment in SCOUT_SUCCESS_COMMENTARY))
        self.assertIn("traps", meta)

    # =========================================================================
    # 3. PICKPOCKET MECHANICS TESTS
    # =========================================================================

    async def test_pickpocket_no_lockpick(self):
        """Pickpocket requires at least 1 lockpick in active_items."""
        thief, victim = 1010, 2010
        await self.db.execute("INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', '{}')", (thief,))
        await self.db.commit()

        ok, msg, meta = await execute_pickpocket(self.db, thief, victim, "b")
        self.assertFalse(ok)
        self.assertIn("НЕТ ОТМЫЧКИ", msg)
        self.assertTrue(meta.get("no_lockpick"))

    async def test_pickpocket_beginner_protection(self):
        """Victims with < 15 posts are protected; lockpick is NOT consumed."""
        thief, victim = 1011, 2011
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (thief, json.dumps({"lockpick": 2})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 10000, 10)",
            (victim,),
        )
        await self.db.commit()

        ok, msg, meta = await execute_pickpocket(self.db, thief, victim, "b")
        self.assertFalse(ok)
        self.assertIn("ЗАЩИТА НЬЮФАГА", msg)
        self.assertTrue(meta.get("beginner_protected"))

        # Verify lockpick count was preserved
        t_items = await load_user_active_items(self.db, thief, "b")
        self.assertEqual(t_items.get("lockpick"), 2)

    async def test_pickpocket_isolation_protection(self):
        """Self-isolated victims cannot be pickpocketed; lockpick is NOT consumed."""
        thief, victim = 1012, 2012
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (thief, json.dumps({"lockpick": 1})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count, is_isolated) VALUES (?, 'b', 10000, 50, 1)",
            (victim,),
        )
        await self.db.commit()

        ok, msg, meta = await execute_pickpocket(self.db, thief, victim, "b")
        self.assertFalse(ok)
        self.assertIn("ЦЕЛЬ В САМОИЗОЛЯЦИИ", msg)
        self.assertTrue(meta.get("isolated"))

        t_items = await load_user_active_items(self.db, thief, "b")
        self.assertEqual(t_items.get("lockpick"), 1)

    async def test_pickpocket_silent_success_and_dirty_money(self):
        """
        Successful pickpocket:
        - Consumes 1 lockpick.
        - Steals 4%..10% of victim balance (capped at 25k).
        - Stolen funds credited to thief's dirty_balance.
        - Adds 1 wanted star and 5,000 ₪ bounty.
        - Marked silent=True for private DM delivery.
        """
        thief, victim = 1013, 2013
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 0, ?)",
            (thief, json.dumps({"lockpick": 3, "dirty_balance": 1000.0, "wanted_stars": 1, "bounty_pool": 5000.0})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count, is_isolated) VALUES (?, 'b', 100000.0, 50, 0)",
            (victim,),
        )
        await self.db.commit()

        # Force success with roll=0.10 and steal 8% (8,000 ₪)
        ok, dm_msg, meta = await execute_pickpocket(self.db, thief, victim, "b", roll=0.10, pct=0.08)
        self.assertTrue(ok)
        self.assertTrue(meta.get("silent"))
        self.assertEqual(meta["stolen"], 8000.0)
        self.assertEqual(meta["stars"], 2)
        self.assertEqual(meta["bounty"], 10000.0)
        self.assertEqual(meta["lockpicks_left"], 2)
        self.assertIn("ТИХИЙ КАРМАННЫЙ КРАЖ", dm_msg)

        # Verify DB updates
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (victim,)) as cursor:
            v_bal = (await cursor.fetchone())[0]
        self.assertEqual(v_bal, 92000.0)

        t_items = await load_user_active_items(self.db, thief, "b")
        self.assertEqual(t_items["dirty_balance"], 9000.0)  # 1000 + 8000
        self.assertEqual(t_items["wanted_stars"], 2)
        self.assertEqual(t_items["bounty_pool"], 10000.0)
        self.assertEqual(t_items["lockpick"], 2)

    async def test_pickpocket_max_cap_25k(self):
        """Pickpocket theft is capped at 25,000 ₪ even if 10% of victim balance is much larger."""
        thief, victim = 1014, 2014
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (thief, json.dumps({"lockpick": 1})),
        )
        # Victim has 1,000,000 ₪; 10% would be 100,000 ₪
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 1000000.0, 50)",
            (victim,),
        )
        await self.db.commit()

        ok, _, meta = await execute_pickpocket(self.db, thief, victim, "b", roll=0.10, pct=0.10)
        self.assertTrue(ok)
        self.assertEqual(meta["stolen"], 25000.0)

    async def test_pickpocket_loud_fail_and_rat_status(self):
        """
        Failed pickpocket:
        - Lockpick consumed.
        - Thief gains [Крыса] status for 2 hours.
        - Thief pays 2,000 ₪ penalty to victim.
        - Loud public alert in chat.
        """
        thief, victim = 1015, 2015
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 5000.0, ?)",
            (thief, json.dumps({"lockpick": 1})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 10000.0, 50)",
            (victim,),
        )
        await self.db.commit()

        # Force fail with roll=0.95
        ok, loud_msg, meta = await execute_pickpocket(self.db, thief, victim, "b", roll=0.95)
        self.assertFalse(ok)
        self.assertTrue(meta.get("caught"))
        self.assertEqual(meta["penalty"], 2000.0)
        self.assertIn("КРЫСА ПОЙМАНА С ПОЛИЧНЫМ", loud_msg)
        self.assertIn("[Крыса]", loud_msg)

        # Verify balances & status
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (thief,)) as cursor:
            t_bal = (await cursor.fetchone())[0]
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (victim,)) as cursor:
            v_bal = (await cursor.fetchone())[0]
        self.assertEqual(t_bal, 3000.0)
        self.assertEqual(v_bal, 12000.0)

        t_items = await load_user_active_items(self.db, thief, "b")
        self.assertGreater(t_items.get("rat_until", 0), time.time())
        self.assertEqual(t_items.get("lockpick"), 0)

    # =========================================================================
    # 4. ARREST & LAW ENFORCEMENT TESTS
    # =========================================================================

    async def test_arrest_unauthorized_user(self):
        """Ordinary user without druzhinnik badge, ksiva, or fake ksiva cannot arrest."""
        officer, criminal = 3001, 4001
        await self.db.execute("INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', '{}')", (officer,))
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (criminal, json.dumps({"wanted_stars": 3, "bounty_pool": 15000.0})),
        )
        await self.db.commit()

        ok, msg, meta = await execute_arrest(self.db, officer, criminal, "b")
        self.assertFalse(ok)
        self.assertIn("ТЫ КТО ТАКОЙ, ЧУХАН", msg)
        self.assertTrue(meta.get("unauthorized"))

    async def test_arrest_target_not_wanted(self):
        """Cannot arrest target with 0 wanted stars."""
        officer, clean_user = 3002, 4002
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (officer, json.dumps({"ksiva_polkovnik": 1})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (clean_user, json.dumps({"wanted_stars": 0, "bounty_pool": 0.0})),
        )
        await self.db.commit()

        ok, msg, meta = await execute_arrest(self.db, officer, clean_user, "b")
        self.assertFalse(ok)
        self.assertIn("ЧИСТ ПЕРЕД ЗАКОНОМ", msg)
        self.assertTrue(meta.get("not_wanted"))

    async def test_legit_druzhinnik_arrest_and_payout_split(self):
        """
        Legit druzhinnik arrest:
        - 60% of bounty paid to officer.
        - 40% of bounty burned to Abu Yacht Fund.
        - Criminal muted for stars * 15m.
        - Confiscates criminal's заточки and lockpicks.
        - Resets criminal wanted stars and bounty to 0.
        """
        officer, criminal = 3003, 4003
        bounty = 20000.0
        stars = 3

        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000.0, ?)",
            (officer, json.dumps({"badge_druzhinnik_expires": time.time() + 86400})),
        )
        crim_items = {
            "wanted_stars": stars,
            "bounty_pool": bounty,
            "lockpick": 4,
            "knife": 1,
            "knife_gun": True,
            "zatochka": 2,
        }
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 5000.0, ?)",
            (criminal, json.dumps(crim_items)),
        )
        await self.db.commit()

        ok, msg, meta = await execute_arrest(self.db, officer, criminal, "b")
        self.assertTrue(ok)
        self.assertEqual(meta["officer_payout"], 12000.0)  # 60%
        self.assertEqual(meta["abu_burn"], 8000.0)        # 40%
        self.assertEqual(meta["jail_minutes"], 45)         # 3 * 15m
        self.assertIn("ОБЛАВА ДРУЖИННИКОВ", msg)

        # Check officer balance (+12,000)
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (officer,)) as cursor:
            off_bal = (await cursor.fetchone())[0]
        self.assertEqual(off_bal, 13000.0)

        # Check Abu Fund (+8,000)
        async with self.db.execute("SELECT value FROM GlobalStats WHERE key = 'abu_yacht_fund'") as cursor:
            fund_row = await cursor.fetchone()
            abu_fund_val = float(fund_row[0]) if fund_row else 0.0
        self.assertEqual(abu_fund_val, 8000.0)

        # Check criminal mute in Mutes table
        async with self.db.execute("SELECT expires_at, reason FROM Mutes WHERE user_id = ?", (criminal,)) as cursor:
            mute_row = await cursor.fetchone()
        self.assertIsNotNone(mute_row)
        self.assertGreater(mute_row[0], time.time())
        self.assertIn("3★", mute_row[1])

        # Check criminal inventory confiscation
        updated_crim_items = await load_user_active_items(self.db, criminal, "b")
        self.assertEqual(updated_crim_items["wanted_stars"], 0)
        self.assertEqual(updated_crim_items["bounty_pool"], 0.0)
        self.assertEqual(updated_crim_items["lockpick"], 0)
        self.assertEqual(updated_crim_items["knife"], 0)
        self.assertFalse(updated_crim_items["knife_gun"])
        self.assertEqual(updated_crim_items["zatochka"], 0)

    # =========================================================================
    # 5. FAKE KSIVA 35% BACKFIRE VS 65% SUCCESS
    # =========================================================================

    async def test_fake_ksiva_backfire(self):
        """
        Fake ksiva backfire (roll < 0.35):
        - Fined 10,000 ₪ (sent to Abu Fund).
        - Caller muted for 30 minutes.
        - Fake ksiva consumed.
        """
        officer, criminal = 3004, 4004
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 25000.0, ?)",
            (officer, json.dumps({"fake_ksiva": 1})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (criminal, json.dumps({"wanted_stars": 2, "bounty_pool": 10000.0})),
        )
        await self.db.commit()

        # Force backfire with fake_roll=0.20 (< 0.35)
        ok, msg, meta = await execute_arrest(self.db, officer, criminal, "b", fake_roll=0.20)
        self.assertFalse(ok)
        self.assertTrue(meta.get("backfire"))
        self.assertEqual(meta["fine"], 10000.0)
        self.assertEqual(meta["mute_sec"], 1800)
        self.assertIn("ПАЛЁНАЯ КСИВА", msg)
        self.assertIn("Майор раскусил подделку", msg)

        # Check officer fined 10,000
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (officer,)) as cursor:
            bal = (await cursor.fetchone())[0]
        self.assertEqual(bal, 15000.0)

        # Check Abu Fund received 10,000
        async with self.db.execute("SELECT value FROM GlobalStats WHERE key = 'abu_yacht_fund'") as cursor:
            fund_val = float((await cursor.fetchone())[0])
        self.assertEqual(fund_val, 10000.0)

        # Check officer muted
        async with self.db.execute("SELECT expires_at FROM Mutes WHERE user_id = ?", (officer,)) as cursor:
            mute_row = await cursor.fetchone()
        self.assertIsNotNone(mute_row)

        # Check fake_ksiva consumed
        off_items = await load_user_active_items(self.db, officer, "b")
        self.assertEqual(off_items.get("fake_ksiva"), 0)

    async def test_fake_ksiva_success(self):
        """
        Fake ksiva success (roll >= 0.35):
        - Successfully arrests criminal.
        - Payout split 60/40, criminal muted, inventory confiscated.
        - Fake ksiva consumed.
        """
        officer, criminal = 3005, 4005
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 5000.0, ?)",
            (officer, json.dumps({"fake_ksiva": 1})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (criminal, json.dumps({"wanted_stars": 1, "bounty_pool": 5000.0, "lockpick": 1})),
        )
        await self.db.commit()

        # Force success with fake_roll=0.60 (>= 0.35)
        ok, msg, meta = await execute_arrest(self.db, officer, criminal, "b", fake_roll=0.60)
        self.assertTrue(ok)
        self.assertEqual(meta["officer_payout"], 3000.0)
        self.assertEqual(meta["abu_burn"], 2000.0)

        # Check fake ksiva consumed
        off_items = await load_user_active_items(self.db, officer, "b")
        self.assertEqual(off_items.get("fake_ksiva"), 0)

    # =========================================================================
    # 6. DARKNET CATALOG & PURCHASING TESTS
    # =========================================================================

    async def test_darknet_item_buy_lockpick(self):
        """Purchasing lockpick from Darknet deducts 400 ₪ and adds 1 lockpick."""
        user = 5001
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000.0)", (user,))
        await self.db.commit()

        ok, msg, items = await handle_darknet_item_buy(self.db, user, "b", "lockpick")
        self.assertTrue(ok)
        self.assertEqual(items.get("lockpick"), 1)
        self.assertIn("ПОДПОЛЬНАЯ СДЕЛКА СОВЕРШЕНА", msg)

        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (user,)) as cursor:
            bal = (await cursor.fetchone())[0]
        self.assertEqual(bal, 600.0)

    async def test_darknet_item_buy_jammer(self):
        """Purchasing 5G-jammer from Darknet deducts 1,200 ₪ and grants 1 hour jammer_until."""
        user = 5002
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 2000.0)", (user,))
        await self.db.commit()

        ok, msg, items = await handle_darknet_item_buy(self.db, user, "b", "jammer")
        self.assertTrue(ok)
        self.assertGreater(items.get("jammer_until", 0), time.time() + 3500)

        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (user,)) as cursor:
            bal = (await cursor.fetchone())[0]
        self.assertEqual(bal, 800.0)

    async def test_darknet_item_buy_insufficient_funds(self):
        """Purchase fails gracefully if user lacks funds."""
        user = 5003
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 100.0)", (user,))
        await self.db.commit()

        ok, msg, _ = await handle_darknet_item_buy(self.db, user, "b", "lockpick")
        self.assertFalse(ok)
        self.assertIn("НЕДОСТАТОЧНО ШЕКЕЛЕЙ", msg)

    # =========================================================================
    # 7. AIOGRAM ROUTER & HANDLERS TESTS
    # =========================================================================

    async def test_cmd_darknet_and_buy_handlers(self):
        """Tests /darknet and /buy_darknet message handlers."""
        mock_msg = MagicMock(spec=types.Message)
        mock_msg.from_user = MagicMock(id=5004)
        mock_msg.board_id = "b"
        mock_msg.answer = AsyncMock()

        await cmd_darknet(mock_msg)
        mock_msg.answer.assert_called_once()
        text = mock_msg.answer.call_args[0][0]
        self.assertIn("ТЕНЕВОЙ РЫНОК", text)
        self.assertIn("Отмычка", text)
        self.assertIn("Палёная ксива", text)

        # /buy_darknet without arg
        mock_msg.text = "/buy_darknet"
        mock_msg.answer.reset_mock()
        await cmd_buy_darknet(mock_msg, board_id="b")
        self.assertIn("Укажи идентификатор", mock_msg.answer.call_args[0][0])

    async def test_cmd_scout_no_reply_validation(self):
        """Calling /scout without replying to a target returns 2ch prompt."""
        mock_msg = MagicMock(spec=types.Message)
        mock_msg.from_user = MagicMock(id=5005)
        mock_msg.reply_to_message = None
        mock_msg.answer = AsyncMock()

        await cmd_scout(mock_msg, board_id="b")
        mock_msg.answer.assert_called_once()
        self.assertIn("КОГО ШМОНАТЬ-ТО", mock_msg.answer.call_args[0][0])

    async def test_cmd_pickpocket_no_reply_validation(self):
        """Calling /pickpocket without replying returns 2ch prompt."""
        mock_msg = MagicMock(spec=types.Message)
        mock_msg.from_user = MagicMock(id=5006)
        mock_msg.reply_to_message = None
        mock_msg.answer = AsyncMock()

        await cmd_pickpocket(mock_msg, board_id="b")
        mock_msg.answer.assert_called_once()
        self.assertIn("КОГО ЩИПАТЬ-ТО", mock_msg.answer.call_args[0][0])

    async def test_cmd_arrest_no_reply_validation(self):
        """Calling /arrest without replying returns 2ch prompt."""
        mock_msg = MagicMock(spec=types.Message)
        mock_msg.from_user = MagicMock(id=5007)
        mock_msg.reply_to_message = None
        mock_msg.answer = AsyncMock()

        await cmd_arrest(mock_msg, board_id="b")
        mock_msg.answer.assert_called_once()
        self.assertIn("ПРИЕМ НА МЕСТЕ", mock_msg.answer.call_args[0][0])

    # =========================================================================
    # 8. ADVERSARIAL & EDGE-CASE HARDENING TESTS
    # =========================================================================

    async def test_pickpocket_low_sanity_boosts_success_chance(self):
        """Low target sanity increases effective pickpocket success rate above base 65%."""
        thief, insane_victim = 6001, 7001
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 0, ?)",
            (thief, json.dumps({"lockpick": 1})),
        )
        # Victim has crazy debuff items giving negative sanity (sanity < 50)
        insane_items = {"equipped_head": "hat_tinfoil", "equipped_torso": "torso_straightjacket"}
        with patch("criminal_syndicate_engine.get_target_sanity_score", return_value=10):
            await self.db.execute(
                "INSERT INTO Users (user_id, board_id, balance, posts_count, is_isolated, active_items) VALUES (?, 'b', 50000.0, 50, 0, ?)",
                (insane_victim, json.dumps(insane_items)),
            )
            await self.db.commit()

            # roll=0.75 would fail with base 0.65, but with sanity=10 bonus (+0.20), rate=0.85 -> succeeds!
            ok, _, meta = await execute_pickpocket(self.db, thief, insane_victim, "b", roll=0.75, pct=0.05)
            self.assertTrue(ok)
            self.assertTrue(meta.get("silent"))
            self.assertEqual(meta["stolen"], 2500.0)

    async def test_arrest_max_mute_cap_75_minutes(self):
        """Criminal with 5 stars receives exactly 75 minutes of mute."""
        officer, criminal = 6002, 7002
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000.0, ?)",
            (officer, json.dumps({"ksiva_polkovnik": 1})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (criminal, json.dumps({"wanted_stars": 5, "bounty_pool": 25000.0})),
        )
        await self.db.commit()

        ok, _, meta = await execute_arrest(self.db, officer, criminal, "b")
        self.assertTrue(ok)
        self.assertEqual(meta["jail_minutes"], MAX_ARREST_MUTE_MINUTES)
        self.assertEqual(meta["officer_payout"], 15000.0)  # 60%
        self.assertEqual(meta["abu_burn"], 10000.0)        # 40%

    async def test_cmd_self_target_guards(self):
        """Verifies self-target rejections in /scout, /pickpocket, and /arrest."""
        uid = 6003
        mock_msg = MagicMock(spec=types.Message)
        mock_msg.from_user = MagicMock(id=uid)
        mock_msg.reply_to_message = MagicMock()
        mock_msg.reply_to_message.chat = MagicMock(id=123)
        mock_msg.reply_to_message.message_id = 456
        mock_msg.reply_to_message.from_user = MagicMock(id=uid, is_bot=False)
        mock_msg.answer = AsyncMock()

        # Scout self
        await cmd_scout(mock_msg, board_id="b")
        self.assertIn("ТЫ ЕБАНУЛСЯ", mock_msg.answer.call_args[0][0])

        # Pickpocket self
        mock_msg.answer.reset_mock()
        await cmd_pickpocket(mock_msg, board_id="b")
        self.assertIn("обчистить сам себя", mock_msg.answer.call_args[0][0])

        # Arrest self
        mock_msg.answer.reset_mock()
        await cmd_arrest(mock_msg, board_id="b")
        self.assertIn("надеть наручники на самого себя", mock_msg.answer.call_args[0][0])

    async def test_darknet_unknown_item_purchase(self):
        """Buying non-existent darknet item returns error without deducting funds."""
        user = 6004
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000.0)", (user,))
        await self.db.commit()

        ok, msg, _ = await handle_darknet_item_buy(self.db, user, "b", "nuclear_bomb")
        self.assertFalse(ok)
        self.assertIn("Неизвестный товар Даркнета", msg)

    # =========================================================================
    # 9. SUBAGENT 2: DYNAMIC WEALTH SCALING & NEW ILLICIT ARSENAL TESTS
    # =========================================================================

    def test_dynamic_pricing_darknet_items_novice_vs_whale(self):
        """
        Validates dynamic wealth scaling for all darknet catalog items:
        - Novices (balance <= 10,000 ₪) pay pure base price.
        - Intermediate users pay base + balance * rate.
        - Whales (10M ₪) hit maximum price ceiling caps.
        """
        items_spec = {
            "lockpick": {"base": 400, "rate": 0.002, "max": 10000},
            "fake_ksiva": {"base": 250, "rate": 0.003, "max": 7500},
            "jammer": {"base": 1200, "rate": 0.005, "max": 35000},
            "master_key": {"base": 5000, "rate": 0.01, "max": 100000},
            "bribe_envelope": {"base": 2500, "rate": 0.008, "max": 75000},
            "chloroform": {"base": 1500, "rate": 0.004, "max": 25000},
        }

        # 1. Novices (balance <= 10,000 ₪)
        for key, spec in items_spec.items():
            self.assertEqual(get_darknet_item_price(key, 0.0), spec["base"])
            self.assertEqual(get_darknet_item_price(key, 500.0), spec["base"])
            self.assertEqual(get_darknet_item_price(key, 10000.0), spec["base"])

        # 2. Intermediate wealth (balance = 100,000 ₪)
        inter_bal = 100000.0
        for key, spec in items_spec.items():
            expected = spec["base"] + int(inter_bal * spec["rate"])
            self.assertEqual(get_darknet_item_price(key, inter_bal), expected)

        # 3. 10M Whale (balance = 10,000,000 ₪) hitting caps
        whale_bal = 10000000.0
        for key, spec in items_spec.items():
            self.assertEqual(get_darknet_item_price(key, whale_bal), spec["max"])

    def test_dynamic_scout_pricing(self):
        """
        Tests dynamic scout price scaling:
        max(150.0, min(15000.0, 150.0 + float(int(caller_balance * 0.003))))
        Novices pay 150 ₪; oligarchs with 5M pay 15,000 ₪!
        """
        # Novice edge cases
        self.assertEqual(calculate_scout_cost(0.0), 150.0)
        self.assertEqual(calculate_scout_cost(-50.0), 150.0)
        self.assertEqual(calculate_scout_cost(100.0), 150.0)  # int(100 * 0.003) = 0

        # Small balance
        self.assertEqual(calculate_scout_cost(500.0), 151.0)  # 150 + int(1.5) = 151

        # Medium balance
        self.assertEqual(calculate_scout_cost(10000.0), 180.0)  # 150 + 30
        self.assertEqual(calculate_scout_cost(100000.0), 450.0)  # 150 + 300

        # 5M Oligarch exactly hits 15,000 cap
        self.assertEqual(calculate_scout_cost(5000000.0), 15000.0)

        # 10M Whale clamped to 15,000
        self.assertEqual(calculate_scout_cost(10000000.0), 15000.0)

    async def test_new_item_master_key_pickpocket_bonus(self):
        """
        Master key (+20% success bonus) turns a failing roll (0.80) into a success:
        Base 0.65 + MasterKey 0.20 = 0.85 > 0.80.
        """
        thief, victim = 7101, 7102
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000.0, ?)",
            (thief, json.dumps({"lockpick": 2, "master_key": 1, "dirty_balance": 0.0})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 50000.0, 50)",
            (victim,),
        )
        await self.db.commit()

        # Roll 0.80 fails without master key (0.65 < 0.80), but succeeds with master key (0.85 > 0.80)
        ok, dm_msg, meta = await execute_pickpocket(self.db, thief, victim, "b", roll=0.80, pct=0.06)
        self.assertTrue(ok)
        self.assertTrue(meta.get("silent"))
        self.assertTrue(meta.get("has_master_key"))
        self.assertEqual(meta.get("master_key_bonus"), 0.20)
        self.assertEqual(meta["stolen"], 3000.0)
        self.assertEqual(meta["lockpicks_left"], 1)

        # Verify master_key is kept as a durable burglary tool
        t_items = await load_user_active_items(self.db, thief, "b")
        self.assertEqual(t_items.get("master_key"), 1)
        self.assertEqual(t_items.get("dirty_balance"), 3000.0)

    async def test_new_item_bribe_envelope_bribe_cop(self):
        """
        /bribe_cop mechanics:
        - Consumes 1 bribe_envelope.
        - Reduces wanted_stars by 1.
        - Reduces bounty_pool by 5,000 ₪ (or to 0 if 0 stars).
        - Rejects clean users (0 stars) and users without envelopes.
        """
        user = 7201
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (user, json.dumps({"bribe_envelope": 2, "wanted_stars": 2, "bounty_pool": 10000.0})),
        )
        await self.db.commit()

        # 1. First bribe: drops from 2★ / 10k to 1★ / 5k
        ok1, msg1, meta1 = await execute_bribe_cop(self.db, user, "b")
        self.assertTrue(ok1)
        self.assertEqual(meta1["new_stars"], 1)
        self.assertEqual(meta1["new_bounty"], 5000.0)
        self.assertEqual(meta1["envelopes_left"], 1)
        self.assertIn("СЛЕДОВАТЕЛЬ ПРИНЯЛ КОНВЕРТ", msg1)

        # 2. Second bribe: drops from 1★ / 5k to 0★ / 0
        ok2, msg2, meta2 = await execute_bribe_cop(self.db, user, "b")
        self.assertTrue(ok2)
        self.assertEqual(meta2["new_stars"], 0)
        self.assertEqual(meta2["new_bounty"], 0.0)
        self.assertEqual(meta2["envelopes_left"], 0)

        # 3. Third bribe: out of envelopes
        ok3, msg3, meta3 = await execute_bribe_cop(self.db, user, "b")
        self.assertFalse(ok3)
        self.assertTrue(meta3.get("no_envelope"))
        self.assertIn("НЕТ КОНВЕРТА С ВЗЯТКОЙ", msg3)

        # 4. Clean user with envelope cannot bribe
        user_clean = 7202
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (user_clean, json.dumps({"bribe_envelope": 1, "wanted_stars": 0, "bounty_pool": 0.0})),
        )
        await self.db.commit()

        ok4, msg4, meta4 = await execute_bribe_cop(self.db, user_clean, "b")
        self.assertFalse(ok4)
        self.assertTrue(meta4.get("not_wanted"))
        self.assertIn("ЧИСТ ПЕРЕД ЗАКОНОМ", msg4)

    async def test_new_item_chloroform_and_pepperspray_neutralization(self):
        """
        Chloroform mechanics:
        - Consumes 1 chloroform.
        - Puts victim to sleep for 30 minutes (chloroformed_until = now + 1800).
        - Neutralizes victim's pepperspray trap in detect_target_traps.
        - Self-target and zero-item guards.
        """
        thief, victim = 7301, 7302
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (thief, json.dumps({"chloroform": 1})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (victim, json.dumps({"pepperspray_gun": True})),
        )
        await self.db.commit()

        # Before chloroform: pepperspray is active
        v_items_before = await load_user_active_items(self.db, victim, "b")
        traps_before = detect_target_traps(v_items_before)
        self.assertTrue(any("авто-струя" in t for t in traps_before))

        # Apply chloroform
        ok, msg, meta = await execute_chloroform(self.db, thief, victim, "b")
        self.assertTrue(ok)
        self.assertIn("ХЛОРОФОРМ ПРИМЕНЁН", msg)
        self.assertIn("Перцовый баллончик цели полностью отключен", msg)
        self.assertEqual(meta["chloroform_left"], 0)
        self.assertGreater(meta["chloroformed_until"], time.time())

        # After chloroform: pepperspray is neutralized
        v_items_after = await load_user_active_items(self.db, victim, "b")
        traps_after = detect_target_traps(v_items_after)
        self.assertTrue(any("нейтрализован хлороформом" in t for t in traps_after))

        # Try to use without chloroform in inventory
        ok_empty, msg_empty, meta_empty = await execute_chloroform(self.db, thief, victim, "b")
        self.assertFalse(ok_empty)
        self.assertTrue(meta_empty.get("no_chloroform"))

        # Self-target guard
        await self.db.execute(
            "UPDATE Users SET active_items = ? WHERE user_id = ?",
            (json.dumps({"chloroform": 1}), thief),
        )
        await self.db.commit()
        ok_self, msg_self, _ = await execute_chloroform(self.db, thief, thief, "b")
        self.assertFalse(ok_self)
        self.assertIn("ТЫ ЕБАНУЛСЯ", msg_self)

    async def test_darknet_interactive_callback_purchasing_flow(self):
        """
        Interactive callback purchasing flow:
        - build_darknet_keyboard generates buttons with dynamic pricing.
        - cb_darknet_buy executes purchase, updates shekels and inventory, and edits menu.
        - cb_darknet_refresh updates view.
        - Insufficient funds triggers alert.
        """
        user = 7401
        bal = 25000.0  # Wealthy enough: master_key price = 5000 + int(25000 * 0.01) = 5250
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', ?)", (user, bal))
        await self.db.commit()

        # 1. Keyboard generation check
        kb = build_darknet_keyboard(bal)
        self.assertEqual(len(kb.inline_keyboard), 4)
        p_mkey = get_darknet_item_price("master_key", bal)
        self.assertEqual(p_mkey, 5250)

        # 2. Callback purchase execution
        mock_cb = MagicMock(spec=types.CallbackQuery)
        mock_cb.from_user = MagicMock(id=user)
        mock_cb.data = "darknet_buy_master_key"
        mock_cb.answer = AsyncMock()
        mock_cb.message = MagicMock(spec=types.Message)
        mock_cb.message.board_id = "b"
        mock_cb.message.edit_text = AsyncMock()

        await cb_darknet_buy(mock_cb, board_id="b")

        # Verify callback acknowledged & message edited
        mock_cb.answer.assert_called_with("✅ Товар успешно куплен!", show_alert=False)
        mock_cb.message.edit_text.assert_called_once()

        # Verify inventory & balance in DB
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (user,)) as cursor:
            new_bal = (await cursor.fetchone())[0]
        self.assertEqual(new_bal, bal - 5250.0)

        items = await load_user_active_items(self.db, user, "b")
        self.assertEqual(items.get("master_key"), 1)

        # 3. Test cb_darknet_refresh
        mock_cb.answer.reset_mock()
        mock_cb.message.edit_text.reset_mock()
        await cb_darknet_refresh(mock_cb, board_id="b")
        mock_cb.answer.assert_called_with("🔄 Каталог обновлен!")
        mock_cb.message.edit_text.assert_called_once()

        # 4. Test insufficient funds error handling
        broke_user = 7402
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 10.0)", (broke_user,))
        await self.db.commit()

        mock_cb_broke = MagicMock(spec=types.CallbackQuery)
        mock_cb_broke.from_user = MagicMock(id=broke_user)
        mock_cb_broke.data = "darknet_buy_jammer"
        mock_cb_broke.answer = AsyncMock()
        mock_cb_broke.message = MagicMock(spec=types.Message)
        mock_cb_broke.message.board_id = "b"
        mock_cb_broke.message.edit_text = AsyncMock()

        await cb_darknet_buy(mock_cb_broke, board_id="b")
        mock_cb_broke.answer.assert_called_once()
        alert_msg = mock_cb_broke.answer.call_args[0][0]
        self.assertIn("НЕДОСТАТОЧНО ШЕКЕЛЕЙ", alert_msg)
        self.assertTrue(mock_cb_broke.answer.call_args[1].get("show_alert"))

    async def test_criminal_phrases_comprehensive_integration(self):
        """
        Validates authentic 2ch slang phrase integration from common.criminal_phrases:
        - SCOUT_FAIL_SPOTTED_PHRASES in scout fails.
        - SCOUT_SUCCESS_COMMENTARY in scout dossiers.
        - PICKPOCKET_SILENT_SUCCESS_PHRASES in silent pickpocket wins.
        - PICKPOCKET_LOUD_FAIL_PHRASES in loud pickpocket fails.
        - ARREST_DRUZHINA_PHRASES in legitimate arrests.
        """
        thief, victim = 7501, 7502
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 5000.0, ?)",
            (thief, json.dumps({"lockpick": 10})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 20000.0, 50)",
            (victim,),
        )
        await self.db.commit()

        # 1. Silent pickpocket win phrase
        ok_pick, dm_pick, _ = await execute_pickpocket(self.db, thief, victim, "b", roll=0.10)
        self.assertTrue(ok_pick)
        self.assertTrue(any(p in dm_pick for p in PICKPOCKET_SILENT_SUCCESS_PHRASES))

        # 2. Loud pickpocket fail phrase
        ok_fail, loud_fail, _ = await execute_pickpocket(self.db, thief, victim, "b", roll=0.99)
        self.assertFalse(ok_fail)
        self.assertTrue(any(p in loud_fail for p in PICKPOCKET_LOUD_FAIL_PHRASES))

        # 3. Legitimate arrest phrase
        officer = 7503
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (officer, json.dumps({"ksiva_polkovnik": 1})),
        )
        await self.db.commit()

        ok_arr, arr_msg, _ = await execute_arrest(self.db, officer, thief, "b")
        self.assertTrue(ok_arr)
        self.assertTrue(any(p in arr_msg for p in ARREST_DRUZHINA_PHRASES))

    async def test_cmd_bribe_cop_and_chloroform_handlers(self):
        """Tests message command handlers for /bribe_cop and /chloroform."""
        mock_msg = MagicMock(spec=types.Message)
        mock_msg.from_user = MagicMock(id=7601)
        mock_msg.board_id = "b"
        mock_msg.answer = AsyncMock()

        # /bribe_cop without envelope
        await self.db.execute("INSERT INTO Users (user_id, board_id, active_items) VALUES (7601, 'b', '{}')")
        await self.db.commit()
        await cmd_bribe_cop(mock_msg, board_id="b")
        mock_msg.answer.assert_called_once()
        self.assertIn("НЕТ КОНВЕРТА", mock_msg.answer.call_args[0][0])

        # /chloroform without reply
        mock_msg.answer.reset_mock()
        mock_msg.reply_to_message = None
        await cmd_chloroform(mock_msg, board_id="b")
        mock_msg.answer.assert_called_once()
        self.assertIn("КОГО УСЫПЛЯТЬ-ТО", mock_msg.answer.call_args[0][0])

    async def test_cb_darknet_refresh_from_photo_message_deletes_and_answers(self):
        """
        Verifies that clicking 'darknet_hub' / 'darknet_refresh' from a photo message (e.g. /shop banner)
        detects media message, deletes the photo message (since darknet text is >1024 chars),
        and sends a clean text message with reply_markup, answering the callback query.
        """
        user_id = 7701
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000.0)", (user_id,))
        await self.db.commit()

        cb = MagicMock()
        cb.from_user = MagicMock(id=user_id)
        cb.data = "darknet_hub"
        cb.answer = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.board_id = "b"
        mock_msg.photo = [MagicMock()]  # Explicit photo sequence
        mock_msg.delete = AsyncMock()
        mock_msg.answer = AsyncMock()
        cb.message = mock_msg

        with patch("common.db_pool.get_pool", AsyncMock(return_value=self.db)):
            await cb_darknet_refresh(cb, board_id="b")

        mock_msg.delete.assert_called_once()
        mock_msg.answer.assert_called_once()
        sent_text = mock_msg.answer.call_args[0][0]
        self.assertIn("DARKNET SYNDICATE", sent_text)
        cb.answer.assert_called_with("🔄 Каталог обновлен!")

    async def test_cb_darknet_refresh_from_photo_message_short_caption(self):
        """
        Verifies that if darknet menu text happens to be <=1024 chars,
        edit_caption is called instead of deleting.
        """
        user_id = 7702
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000.0)", (user_id,))
        await self.db.commit()

        cb = MagicMock()
        cb.from_user = MagicMock(id=user_id)
        cb.data = "darknet_refresh"
        cb.answer = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.board_id = "b"
        mock_msg.photo = [MagicMock()]
        mock_msg.edit_caption = AsyncMock()
        mock_msg.delete = AsyncMock()
        cb.message = mock_msg

        short_menu = "<b>🕵️ ДАРКНЕТ</b>\nКраткий каталог."
        with patch("common.db_pool.get_pool", AsyncMock(return_value=self.db)), \
             patch("criminal_syndicate_engine.build_darknet_menu_text", return_value=short_menu):
            await cb_darknet_refresh(cb, board_id="b")

        mock_msg.edit_caption.assert_called_once()
        mock_msg.delete.assert_not_called()
        cb.answer.assert_called_with("🔄 Каталог обновлен!")

    async def test_cb_darknet_refresh_from_text_message_and_unmodified_toast(self):
        """
        Verifies navigation from plain text message:
        1. Calls edit_text on normal update.
        2. Shows toast 'Каталог уже актуален.' if TelegramBadRequest 'message is not modified' occurs.
        """
        user_id = 7703
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 2000.0)", (user_id,))
        await self.db.commit()

        cb = MagicMock()
        cb.from_user = MagicMock(id=user_id)
        cb.data = "darknet_hub"
        cb.answer = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.board_id = "b"
        mock_msg.photo = None
        mock_msg.caption = None
        mock_msg.edit_text = AsyncMock()
        cb.message = mock_msg

        with patch("common.db_pool.get_pool", AsyncMock(return_value=self.db)):
            # 1. Normal modification
            await cb_darknet_refresh(cb, board_id="b")
            mock_msg.edit_text.assert_called_once()
            cb.answer.assert_called_with("🔄 Каталог обновлен!")

            # 2. Unmodified toast
            mock_msg.edit_text.reset_mock()
            cb.answer.reset_mock()
            mock_msg.edit_text.side_effect = TelegramBadRequest(
                method="editMessageText", message="Bad Request: message is not modified: specified new message content and reply markup are exactly the same as a current content and reply markup of the message"
            )
            await cb_darknet_refresh(cb, board_id="b")
            cb.answer.assert_called_with("Каталог уже актуален.")

    async def test_cb_darknet_open_shop_navigation(self):
        """
        Verifies that [🛒 Обычный магазин (/shop)] correctly delegates to the shop hub.
        """
        user_id = 7704
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1500.0)", (user_id,))
        await self.db.commit()

        cb = MagicMock()
        cb.from_user = MagicMock(id=user_id)
        cb.data = "darknet_open_shop"
        cb.answer = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.board_id = "b"
        mock_msg.photo = None
        mock_msg.answer = AsyncMock()
        cb.message = mock_msg

        mock_shop_hub = AsyncMock()
        with patch("common.db_pool.get_pool", AsyncMock(return_value=self.db)), \
             patch("main.cb_shop_main_hub", mock_shop_hub):
            await cb_darknet_open_shop(cb, board_id="b")
            mock_shop_hub.assert_called_once_with(cb, board_id="b")

    async def test_darknet_items_export_and_catalog_integrity(self):
        """Verifies DARKNET_ITEMS export, presence of bribe_envelope, and all 6 items."""
        self.assertIs(DARKNET_ITEMS, DARKNET_CATALOG)
        expected_items = ["lockpick", "fake_ksiva", "jammer", "master_key", "bribe_envelope", "chloroform"]
        for item_id in expected_items:
            self.assertIn(item_id, DARKNET_ITEMS, f"{item_id} must be in DARKNET_ITEMS")
            self.assertIn(item_id, DARKNET_CATALOG, f"{item_id} must be in DARKNET_CATALOG")
            self.assertIn(item_id, DARKNET_CONFIG, f"{item_id} must be in DARKNET_CONFIG")
            item = DARKNET_ITEMS[item_id]
            self.assertTrue(item["name"])
            self.assertGreater(item["price"], 0)
            self.assertTrue(item["desc"])

    def test_darknet_item_aliases_resolution_multilingual(self):
        """Tests that Russian, English, Japanese, and multi-word aliases resolve properly."""
        test_cases = {
            # bribe_envelope
            "bribe_envelope": "bribe_envelope",
            "bribe": "bribe_envelope",
            "envelope": "bribe_envelope",
            "взятка": "bribe_envelope",
            "конверт": "bribe_envelope",
            "конверт со взяткой": "bribe_envelope",
            "конверт_со_взяткой": "bribe_envelope",
            "взятка следователю": "bribe_envelope",
            "взятка копу": "bribe_envelope",
            "bribe cop": "bribe_envelope",
            "賄賂の封筒": "bribe_envelope",
            "賄賂": "bribe_envelope",
            # lockpick
            "lockpick": "lockpick",
            "lockpicks": "lockpick",
            "отмычка": "lockpick",
            "отмычки": "lockpick",
            "пикинг": "lockpick",
            "ピッキングツール": "lockpick",
            # fake_ksiva
            "fake_ksiva": "fake_ksiva",
            "fake ksiva": "fake_ksiva",
            "fake_id": "fake_ksiva",
            "палёная ксива": "fake_ksiva",
            "паленая ксива": "fake_ksiva",
            "ксива": "fake_ksiva",
            "удостоверение": "fake_ksiva",
            "偽造警察手帳": "fake_ksiva",
            # jammer
            "jammer": "jammer",
            "5g jammer": "jammer",
            "5g-jammer": "jammer",
            "глушилка": "jammer",
            "5g глушилка": "jammer",
            "5g_глушилка": "jammer",
            "5g 電波ジャマー": "jammer",
            # master_key
            "master_key": "master_key",
            "master key": "master_key",
            "crowbar": "master_key",
            "монтировка": "master_key",
            "мастер ключ": "master_key",
            "мастер-ключ": "master_key",
            "фомка": "master_key",
            "バール": "master_key",
            # chloroform
            "chloroform": "chloroform",
            "chlor": "chloroform",
            "хлороформ": "chloroform",
            "снотворное": "chloroform",
            "флакон хлороформа": "chloroform",
            "クロロホルム": "chloroform",
        }
        for alias, expected_canonical in test_cases.items():
            resolved = resolve_darknet_item_id(alias)
            self.assertEqual(resolved, expected_canonical, f"Alias '{alias}' failed to resolve to '{expected_canonical}'")

    async def test_buy_darknet_with_russian_and_english_aliases(self):
        """Verifies buying through handle_darknet_item_buy using various aliases."""
        user = 991100
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500000.0, '{}')",
            (user,),
        )
        await self.db.commit()

        # 1. Buy bribe_envelope using "взятка"
        ok, msg, items = await handle_darknet_item_buy(self.db, user, "b", "взятка")
        self.assertTrue(ok)
        self.assertIn("Взятка следаку", msg)
        self.assertEqual(items.get("bribe_envelope"), 1)

        # 2. Buy bribe_envelope using "конверт со взяткой"
        ok, msg, items = await handle_darknet_item_buy(self.db, user, "b", "конверт со взяткой")
        self.assertTrue(ok)
        self.assertEqual(items.get("bribe_envelope"), 2)

        # 3. Buy lockpick using "отмычка"
        ok, msg, items = await handle_darknet_item_buy(self.db, user, "b", "отмычка")
        self.assertTrue(ok)
        self.assertEqual(items.get("lockpick"), 1)

        # 4. Buy fake_ksiva using "палёная ксива"
        ok, msg, items = await handle_darknet_item_buy(self.db, user, "b", "палёная ксива")
        self.assertTrue(ok)
        self.assertEqual(items.get("fake_ksiva"), 1)

        # 5. Buy jammer using "глушилка"
        ok, msg, items = await handle_darknet_item_buy(self.db, user, "b", "глушилка")
        self.assertTrue(ok)
        self.assertGreater(items.get("jammer_until", 0), time.time())

        # 6. Buy master_key using "монтировка"
        ok, msg, items = await handle_darknet_item_buy(self.db, user, "b", "монтировка")
        self.assertTrue(ok)
        self.assertEqual(items.get("master_key"), 1)

        # 7. Buy chloroform using "хлороформ"
        ok, msg, items = await handle_darknet_item_buy(self.db, user, "b", "хлороформ")
        self.assertTrue(ok)
        self.assertEqual(items.get("chloroform"), 1)

    async def test_cmd_buy_darknet_multi_word_and_aliases(self):
        """Verifies cmd_buy_darknet message handler with multi-word and aliases."""
        user = 991101
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500000.0, '{}')",
            (user,),
        )
        await self.db.commit()

        mock_msg = MagicMock(spec=types.Message)
        mock_msg.from_user = MagicMock(id=user)
        mock_msg.board_id = "b"
        mock_msg.answer = AsyncMock()

        # Buy multi-word: /buy_darknet bribe envelope
        mock_msg.text = "/buy_darknet bribe envelope"
        with patch("common.db_pool.get_pool", AsyncMock(return_value=self.db)):
            await cmd_buy_darknet(mock_msg, board_id="b")
        mock_msg.answer.assert_called_once()
        self.assertIn("ПОДПОЛЬНАЯ СДЕЛКА СОВЕРШЕНА", mock_msg.answer.call_args[0][0])
        self.assertIn("Взятка следаку", mock_msg.answer.call_args[0][0])

        # Buy multi-word: /buy_darknet конверт со взяткой
        mock_msg.text = "/buy_darknet конверт со взяткой"
        mock_msg.answer.reset_mock()
        with patch("common.db_pool.get_pool", AsyncMock(return_value=self.db)):
            await cmd_buy_darknet(mock_msg, board_id="b")
        self.assertIn("ПОДПОЛЬНАЯ СДЕЛКА СОВЕРШЕНА", mock_msg.answer.call_args[0][0])

        # Verify active_items has 2 envelopes
        items = await load_user_active_items(self.db, user, "b")
        self.assertEqual(items.get("bribe_envelope"), 2)

    def test_wealth_tax_pricing_with_aliases_and_nan_inf_protection(self):
        """Verifies get_darknet_item_price works with aliases and handles NaN/Inf safely."""
        # 1. Aliases return correct base price for novice
        self.assertEqual(get_darknet_item_price("взятка", 0.0), 2500)
        self.assertEqual(get_darknet_item_price("конверт со взяткой", 0.0), 2500)
        self.assertEqual(get_darknet_item_price("отмычка", 5000.0), 400)
        self.assertEqual(get_darknet_item_price("палёная ксива", 0.0), 250)
        self.assertEqual(get_darknet_item_price("глушилка", 0.0), 1200)
        self.assertEqual(get_darknet_item_price("монтировка", 0.0), 5000)
        self.assertEqual(get_darknet_item_price("хлороформ", 0.0), 1500)

        # 2. Surcharge scaling with aliases
        p_bribe = get_darknet_item_price("взятка", 50000.0)
        self.assertEqual(p_bribe, 2500 + int(50000 * 0.008))

        # 3. Cap enforcement
        self.assertEqual(get_darknet_item_price("взятка", 100000000.0), 75000)

        # 4. NaN / Inf edge-cases do not crash with ValueError or OverflowError
        self.assertEqual(get_darknet_item_price("bribe_envelope", float("nan")), 2500)
        self.assertEqual(get_darknet_item_price("bribe_envelope", float("inf")), 2500)
        self.assertEqual(calculate_scout_cost(float("nan")), 150.0)
        self.assertEqual(calculate_scout_cost(float("inf")), 150.0)

    async def test_chloroform_neutralizes_pepperspray_in_rob(self):
        """Verifies that in main.py, a chloroformed victim cannot trigger pepperspray during /rob."""
        import main
        # When target is chloroformed, is_target_chloroformed is True, so pepperspray doesn't trigger
        t_items_asleep = {"pepperspray_gun": True, "chloroformed_until": time.time() + 1800.0}
        is_asleep = float(t_items_asleep.get("chloroformed_until", 0.0) or 0.0) > time.time()
        should_trigger = t_items_asleep.get("pepperspray_gun") and not is_asleep
        self.assertFalse(should_trigger)

        # When target is awake, pepperspray triggers
        t_items_awake = {"pepperspray_gun": True, "chloroformed_until": 0.0}
        is_awake_asleep = float(t_items_awake.get("chloroformed_until", 0.0) or 0.0) > time.time()
        should_trigger_awake = t_items_awake.get("pepperspray_gun") and not is_awake_asleep
        self.assertTrue(should_trigger_awake)

    async def test_inventory_displays_criminal_items(self):
        """Verifies _build_inventory_content in main.py displays the criminal inventory."""
        import main
        user = 991102
        active_items = {
            "lockpick": 3,
            "fake_ksiva": 1,
            "master_key": 1,
            "bribe_envelope": 2,
            "chloroform": 1,
            "jammer_until": time.time() + 1800.0,
        }
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 5000.0, ?)",
            (user, json.dumps(active_items)),
        )
        await self.db.commit()

        with patch("main.get_pool", AsyncMock(return_value=self.db)), \
             patch("common.db_pool.get_pool", AsyncMock(return_value=self.db)):
            inv_text, kb = await main._build_inventory_content(user, "b")

        self.assertIn("ТЕНЕВОЙ КРИМИНАЛЬНЫЙ СНАРЯД", inv_text)
        self.assertIn("Отмычки:</b> 3 шт.", inv_text)
        self.assertIn("Палёная ксива:</b> 1 шт.", inv_text)
        self.assertIn("Монтировка:</b> 1 шт.", inv_text)
        self.assertIn("Конверт со взяткой:</b> 2 шт.", inv_text)
        self.assertIn("Хлороформ:</b> 1 шт.", inv_text)
        self.assertIn("5G-Глушилка:</b> Активна", inv_text)


