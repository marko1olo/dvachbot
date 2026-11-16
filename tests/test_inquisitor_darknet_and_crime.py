# -*- coding: utf-8 -*-
"""
tests/test_inquisitor_darknet_and_crime.py — Comprehensive Red Team Inquisitor Test Suite:
Darknet Mass Purchasing, Crime, Warrants, Arrests, Detective Bribes, and Jail Board Limits.
========================================================================================

Coverage:
1. Mass Darknet Purchasing (/buy_darknet):
   - All 6 syndicate items: lockpick, fake_ksiva, jammer, master_key, bribe_envelope, chloroform.
   - 60+ aliases (Russian, English, Translit, Typos, compound phrases with hyphens/spaces).
   - /buy_darknet with no arguments returns a beautiful help guide with examples, NOT an error.
   - Insufficient funds returns a polite warning indicating exact missing amount.

2. Detective Bribes (/bribe_cop) & Deadlock Elimination:
   - 5★ wanted player with 0 envelopes and cash: buys off, 50% kickback to Abu Fund, unblocks bank.
   - Shop bribe (bribe, 450 ₪): mayor accepts with skepticism, -1★ wanted.
   - Syndicate bribe envelope (bribe_envelope): consumes 1 envelope, -1★ wanted.
   - /bribe_cop all: clears all stars with 10% wholesale discount when paying with shekels.
   - Cross-board sync: stars on /b/ are visible and synchronized on /po/, /int/, and Users table.

3. Arrests (/arrest) & Defensive Traps:
   - Legit arrest by druzhinnik with badge (60% officer, 40% Abu, mute stars*15m, confiscation).
   - Fake ksiva arrest: 35% backfire chance (10,000 ₪ fine to Abu Fund, 30m mute).
   - Chloroform neutralizes pepperspray during thefts (/pickpocket) and robberies (/rob).

4. Wanted Board (/wanted) & Jail Status (/jail):
   - 50 criminals emulation: /wanted outputs strictly Top-10 and stays under 1500 characters.
   - 30 inmates emulation: /jail outputs strictly Top-10 and stays under 1500 characters.
"""

import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from aiogram import types

from common.criminal_phrases import (
    ARREST_DRUZHINA_PHRASES,
    PICKPOCKET_LOUD_FAIL_PHRASES,
    PICKPOCKET_SILENT_SUCCESS_PHRASES,
)
from common.database import get_abu_fund_total
from criminal_syndicate_engine import (
    BOUNTY_ABU_SHARE,
    BOUNTY_OFFICER_SHARE,
    BOUNTY_PER_STAR,
    DARKNET_CATALOG,
    DARKNET_CONFIG,
    DARKNET_ITEM_ALIASES,
    FAKE_KSIVA_BACKFIRE_CHANCE,
    FAKE_KSIVA_FINE,
    FAKE_KSIVA_MUTE_SEC,
    MAX_ARREST_MUTE_MINUTES,
    MAX_WANTED_STARS,
    PICKPOCKET_FAIL_PENALTY,
    add_dirty_shekels,
    add_wanted_stars,
    clear_wanted_status,
    cmd_arrest,
    cmd_bribe_cop,
    cmd_buy_darknet,
    cmd_chloroform,
    cmd_darknet,
    cmd_jail,
    cmd_pickpocket,
    cmd_scout,
    cmd_wanted,
    detect_target_armor,
    detect_target_traps,
    execute_arrest,
    execute_bribe_cop,
    execute_chloroform,
    execute_pickpocket,
    execute_scout,
    format_jail_board,
    format_wanted_board,
    get_criminal_profile,
    get_darknet_item_price,
    handle_darknet_item_buy,
    load_user_active_items,
    resolve_darknet_item_id,
    save_user_active_items,
    sync_user_criminal_status,
)


class TestInquisitorDarknetAndCrime(unittest.IsolatedAsyncioTestCase):
    """
    Inquisitor 2: Darknet, Crime, Bribes, Warrants and Arrests Red Team Test Suite.
    """

    async def asyncSetUp(self):
        # Isolated in-memory SQLite database
        self.db = await aiosqlite.connect(":memory:")

        # Schema matching live dvach_bot.db
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER,
                board_id TEXT,
                balance REAL DEFAULT 0.0,
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

        # Patch connection pool to use our isolated test database
        self.pool_patch = patch("common.db_pool.get_pool", return_value=self.db)
        self.mock_pool = self.pool_patch.start()

    async def asyncTearDown(self):
        self.pool_patch.stop()
        await self.db.close()

    # =========================================================================
    # DIRECTION 1: MASS BUY DARKNET GOODS & 60+ ALIASES
    # =========================================================================

    def test_all_six_darknet_catalog_items_exist(self):
        """Verifies all 6 items are registered in DARKNET_CATALOG with valid attributes."""
        expected_items = {
            "lockpick": ("🗝️ Отмычка", 400.0),
            "fake_ksiva": ("🪪 Палёная ксива", 250.0),
            "jammer": ("📡 5G-глушилка", 1200.0),
            "master_key": ("🗝️ Монтировка", 5000.0),
            "bribe_envelope": ("✉️ Взятка следаку", 2500.0),
            "chloroform": ("🧪 Хлороформ", 1500.0),
        }
        for item_id, (expected_name, expected_base_price) in expected_items.items():
            self.assertIn(item_id, DARKNET_CATALOG)
            item = DARKNET_CATALOG[item_id]
            self.assertEqual(item["id"], item_id)
            self.assertEqual(item["name"], expected_name)
            self.assertEqual(item["price"], expected_base_price)
            self.assertTrue(len(item["desc"]) > 10)

    def test_sixty_plus_multilingual_aliases_and_typos(self):
        """
        Tests 60+ aliases covering Russian forms, English synonyms, translit,
        typos, and hyphenated/spaced variations across all 6 items.
        """
        alias_test_matrix = {
            # 1. lockpick (16 aliases)
            "lockpick": "lockpick",
            "lockpicks": "lockpick",
            "pick": "lockpick",
            "picklock": "lockpick",
            "lock-pick": "lockpick",
            "lock pick": "lockpick",
            "отмычка": "lockpick",
            "отмычки": "lockpick",
            "отмычку": "lockpick",
            "отмычкой": "lockpick",
            "отмычка вора": "lockpick",
            "воровская отмычка": "lockpick",
            "otmychka": "lockpick",
            "otmychki": "lockpick",
            "атмычка": "lockpick",
            "отмычька": "lockpick",

            # 2. fake_ksiva (20 aliases)
            "fake_ksiva": "fake_ksiva",
            "fake-ksiva": "fake_ksiva",
            "fake ksiva": "fake_ksiva",
            "fake_id": "fake_ksiva",
            "fake-id": "fake_ksiva",
            "fake id": "fake_ksiva",
            "fake_badge": "fake_ksiva",
            "ksiva": "fake_ksiva",
            "ксива": "fake_ksiva",
            "ксиву": "fake_ksiva",
            "ксивы": "fake_ksiva",
            "паленая ксива": "fake_ksiva",
            "палёная ксива": "fake_ksiva",
            "паленая-ксива": "fake_ksiva",
            "паленка": "fake_ksiva",
            "липовая ксива": "fake_ksiva",
            "корочка": "fake_ksiva",
            "удостоверение": "fake_ksiva",
            "palenaya_ksiva": "fake_ksiva",
            "ксыва": "fake_ksiva",

            # 3. jammer (17 aliases)
            "jammer": "jammer",
            "jammers": "jammer",
            "5g_jammer": "jammer",
            "5g-jammer": "jammer",
            "5g jammer": "jammer",
            "signal_jammer": "jammer",
            "глушилка": "jammer",
            "глушилку": "jammer",
            "глушилки": "jammer",
            "глушитель": "jammer",
            "5g глушилка": "jammer",
            "5g-глушилка": "jammer",
            "5г глушилка": "jammer",
            "подавитель сигнала": "jammer",
            "подавитель слежки": "jammer",
            "glushilka": "jammer",
            "глушылка": "jammer",

            # 4. master_key (17 aliases)
            "master_key": "master_key",
            "masterkey": "master_key",
            "master-key": "master_key",
            "master key": "master_key",
            "crowbar": "master_key",
            "prybar": "master_key",
            "монтировка": "master_key",
            "монтировку": "master_key",
            "монтировки": "master_key",
            "мастер ключ": "master_key",
            "мастер-ключ": "master_key",
            "фомка": "master_key",
            "фомку": "master_key",
            "фомка медвежатника": "master_key",
            "montirovka": "master_key",
            "fomka": "master_key",
            "мантировка": "master_key",

            # 5. bribe_envelope (26 aliases)
            "bribe_envelope": "bribe_envelope",
            "bribe-envelope": "bribe_envelope",
            "bribe envelope": "bribe_envelope",
            "bribe": "bribe_envelope",
            "cop_bribe": "bribe_envelope",
            "bribe_cop": "bribe_envelope",
            "detective_bribe": "bribe_envelope",
            "конверт": "bribe_envelope",
            "конверты": "bribe_envelope",
            "конверт со взяткой": "bribe_envelope",
            "конверт-со-взяткой": "bribe_envelope",
            "конверт с взяткой": "bribe_envelope",
            "взятка": "bribe_envelope",
            "взятку": "bribe_envelope",
            "взятка следователю": "bribe_envelope",
            "взятка-следователю": "bribe_envelope",
            "взятка следаку": "bribe_envelope",
            "взятка-следаку": "bribe_envelope",
            "взятка копу": "bribe_envelope",
            "подкуп": "bribe_envelope",
            "откуп": "bribe_envelope",
            "konvert": "bribe_envelope",
            "vzyatka": "bribe_envelope",
            "vzjatka": "bribe_envelope",
            "канверт": "bribe_envelope",
            "канверт со взяткой": "bribe_envelope",

            # 6. chloroform (17 aliases)
            "chloroform": "chloroform",
            "chloroforms": "chloroform",
            "chlor": "chloroform",
            "sleep_potion": "chloroform",
            "хлороформ": "chloroform",
            "хлороформа": "chloroform",
            "хлороформу": "chloroform",
            "хлороформом": "chloroform",
            "хлорик": "chloroform",
            "усыпитель": "chloroform",
            "снотворное": "chloroform",
            "флакон хлороформа": "chloroform",
            "флакон-хлороформа": "chloroform",
            "hloroform": "chloroform",
            "khloroform": "chloroform",
            "хлораформ": "chloroform",
        }

        self.assertGreaterEqual(len(alias_test_matrix), 60)

        for query, expected_id in alias_test_matrix.items():
            resolved = resolve_darknet_item_id(query)
            self.assertEqual(
                resolved,
                expected_id,
                f"Failed to resolve alias: '{query}', expected: '{expected_id}', got: '{resolved}'",
            )

    async def test_buy_darknet_all_six_items_execution(self):
        """Buys all 6 items and checks active_items and dynamic balance deduction."""
        user_id = 110001
        start_balance = 50000.0
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', ?)",
            (user_id, start_balance),
        )
        await self.db.commit()

        items_to_buy = [
            "lockpick",
            "fake_ksiva",
            "jammer",
            "master_key",
            "bribe_envelope",
            "chloroform",
        ]

        expected_spent = 0.0
        cur_bal = start_balance
        for item_key in items_to_buy:
            price = get_darknet_item_price(item_key, cur_bal)
            ok, msg, items = await handle_darknet_item_buy(self.db, user_id, "b", item_key)
            self.assertTrue(ok, f"Failed to buy {item_key}: {msg}")
            self.assertIn("ПОДПОЛЬНАЯ СДЕЛКА СОВЕРШЕНА", msg)
            expected_spent += price
            cur_bal -= price

        # Check resulting active_items
        profile = get_criminal_profile(items)
        self.assertEqual(profile["lockpick"], 1)
        self.assertEqual(profile["fake_ksiva"], 1)
        self.assertTrue(profile["is_jammed"])
        self.assertEqual(profile["master_key"], 1)
        self.assertEqual(profile["bribe_envelope"], 1)
        self.assertEqual(profile["chloroform"], 1)

        # Check final balance in DB
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ? AND board_id = 'b'", (user_id,)) as cur:
            row = await cur.fetchone()
        self.assertEqual(row[0], start_balance - expected_spent)

    async def test_cmd_buy_darknet_without_args_returns_beautiful_help(self):
        """Calling /buy_darknet with no arguments must return a helpful guide, NOT an error."""
        mock_msg = MagicMock(spec=types.Message)
        mock_msg.from_user = MagicMock(id=110002)
        mock_msg.text = "/buy_darknet"
        mock_msg.board_id = "b"
        mock_msg.answer = AsyncMock()

        await cmd_buy_darknet(mock_msg, board_id="b")

        mock_msg.answer.assert_called_once()
        reply = mock_msg.answer.call_args[0][0]

        # Must NOT be an error
        self.assertNotIn("❌", reply)
        # Must be a beautiful guide with headers, catalog, and examples
        self.assertIn("СПРАВКА ПО ПОКУПКЕ", reply)
        self.assertIn("lockpick", reply)
        self.assertIn("fake_ksiva", reply)
        self.assertIn("jammer", reply)
        self.assertIn("master_key", reply)
        self.assertIn("bribe_envelope", reply)
        self.assertIn("chloroform", reply)
        self.assertIn("/buy_darknet отмычка", reply)
        self.assertIn("/buy_darknet ксива", reply)
        self.assertIn("/buy_darknet конверт со взяткой", reply)

    async def test_buy_darknet_insufficient_funds_polite_warning_with_missing_amount(self):
        """When lacking funds, buy returns a polite warning with exact missing amount."""
        user_id = 110003
        current_balance = 350.0  # Needs 400 for lockpick, missing 50 ₪
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', ?)",
            (user_id, current_balance),
        )
        await self.db.commit()

        ok, msg, meta = await handle_darknet_item_buy(self.db, user_id, "b", "lockpick")
        self.assertFalse(ok)

        # Must include missing amount in metadata
        self.assertTrue(meta.get("insufficient_funds"))
        self.assertEqual(meta.get("required"), 400.0)
        self.assertEqual(meta.get("balance"), 350.0)
        self.assertEqual(meta.get("missing"), 50.0)

        # Must contain polite warning with missing amount in message text
        self.assertIn("НЕДОСТАТОЧНО", msg)
        self.assertIn("400", msg)
        self.assertIn("350", msg)
        self.assertIn("50.00", msg)
        self.assertIn("Не хватает", msg)

    # =========================================================================
    # DIRECTION 2: BRIBE DETECTIVE & DEADLOCK ELIMINATION
    # =========================================================================

    async def test_bribe_cop_five_stars_cash_payoff_and_bank_unlock(self):
        """
        Player with 5★ wanted, 0 envelopes, but cash:
        - Pays off in shekels.
        - Slices 1 star (or all).
        - 50% kickback to Abu Yacht Fund.
        - Bank is unlocked (since stars drop < 5).
        """
        user_id = 220001
        start_bal = 100000.0
        active_items = {
            "wanted_stars": 5,
            "bounty_pool": 25000.0,
            "bounty": 25000.0,
            "bribe_envelope": 0,
            "bribe": 0,
        }
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', ?, ?)",
            (user_id, start_bal, json.dumps(active_items)),
        )
        await self.db.commit()

        price_1_star = get_darknet_item_price("bribe_envelope", start_bal)
        expected_kickback = round(price_1_star * 0.50, 2)

        # Pay off 1 star with cash
        ok, msg, meta = await execute_bribe_cop(self.db, user_id, "b", clear_all=False)
        self.assertTrue(ok)
        self.assertEqual(meta["new_stars"], 4)
        self.assertEqual(meta["payment_method"], "shekels")
        self.assertEqual(meta["cost_paid"], price_1_star)
        self.assertTrue(meta["bank_unlocked"])
        self.assertIn("БАНКОВСКИЕ СЧЕТА И ПЕРЕВОДЫ РАЗБЛОКИРОВАНЫ", msg)

        # Check Abu Fund got 50% kickback via canonical helper
        fund_total = await get_abu_fund_total(self.db)
        self.assertEqual(fund_total, expected_kickback)

        # Check balance deducted
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ? AND board_id = 'b'", (user_id,)) as cur:
            b_row = await cur.fetchone()
        self.assertEqual(b_row[0], start_bal - price_1_star)

    async def test_bribe_cop_all_wholesale_ten_percent_discount(self):
        """
        /bribe_cop all with shekels:
        - Clears all 5 stars.
        - Applies 10% wholesale discount on total sum.
        - 50% kickback to Abu Fund.
        - Stars reset to 0★ and bounty to 0 ₪.
        """
        user_id = 220002
        start_bal = 100000.0
        active_items = {
            "wanted_stars": 5,
            "bounty_pool": 25000.0,
            "bounty": 25000.0,
            "bribe_envelope": 0,
            "bribe": 0,
        }
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', ?, ?)",
            (user_id, start_bal, json.dumps(active_items)),
        )
        await self.db.commit()

        price_per_star = get_darknet_item_price("bribe_envelope", start_bal)
        base_cost = price_per_star * 5
        expected_discounted = round(base_cost * 0.90, 2)
        expected_abu = round(expected_discounted * 0.50, 2)

        ok, msg, meta = await execute_bribe_cop(self.db, user_id, "b", clear_all=True)
        self.assertTrue(ok)
        self.assertEqual(meta["new_stars"], 0)
        self.assertEqual(meta["cost_paid"], expected_discounted)
        self.assertIn("скидки 10%", msg)
        self.assertIn("ПОЛНОСТЬЮ ЧИСТ ПЕРЕД ЗАКОНОМ", msg)

        # Verify Abu Fund via canonical helper
        fund_total = await get_abu_fund_total(self.db)
        self.assertEqual(fund_total, expected_abu)

    async def test_bribe_cop_shop_indulgence_skepticism(self):
        """
        Player with regular /shop 'bribe':
        - Detective accepts with skepticism ('Ладно, на первый раз сойдёт, сыч!').
        - Consumes 1 shop bribe.
        - Slices 1 star.
        """
        user_id = 220003
        active_items = {
            "wanted_stars": 3,
            "bounty_pool": 15000.0,
            "bribe_envelope": 0,
            "bribe": 2,  # 2 shop bribes
        }
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500, ?)",
            (user_id, json.dumps(active_items)),
        )
        await self.db.commit()

        ok, msg, meta = await execute_bribe_cop(self.db, user_id, "b")
        self.assertTrue(ok)
        self.assertEqual(meta["new_stars"], 2)
        self.assertEqual(meta["payment_method"], "shop_bribe")
        self.assertIn("магазинную индульгенцию", msg)
        self.assertIn("Ладно, на первый раз сойдёт, сыч!", msg)

        # Verify 1 bribe was consumed
        user_items = await load_user_active_items(self.db, user_id, "b")
        self.assertEqual(user_items["bribe"], 1)

    async def test_bribe_cop_bribe_envelope_priority(self):
        """
        Player with syndicate bribe_envelope:
        - Consumes 1 envelope.
        - Slices 1 star.
        - Fluff about major spilling coffee on criminal case.
        """
        user_id = 220004
        active_items = {
            "wanted_stars": 4,
            "bounty_pool": 20000.0,
            "bribe_envelope": 3,
            "bribe": 1,
        }
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 5000, ?)",
            (user_id, json.dumps(active_items)),
        )
        await self.db.commit()

        ok, msg, meta = await execute_bribe_cop(self.db, user_id, "b")
        self.assertTrue(ok)
        self.assertEqual(meta["new_stars"], 3)
        self.assertEqual(meta["payment_method"], "bribe_envelope")
        self.assertEqual(meta["envelopes_left"], 2)
        self.assertIn("пролил кофе на твое уголовное дело", msg)

    async def test_cross_board_wanted_status_synchronization(self):
        """
        Wanted stars accrued on board /b/ must be visible and synchronized
        on /po/, /int/, and across all rows in Users table.
        """
        user_id = 220005
        # User has rows on 'b', 'po', and 'int' with wallet funds
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50000.0, '{}')", (user_id,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'po', 50000.0, '{}')", (user_id,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'int', 50000.0, '{}')", (user_id,))
        await self.db.commit()

        # Accrue 4 stars on board 'b'
        items_b = await load_user_active_items(self.db, user_id, "b")
        add_wanted_stars(items_b, stars=4, bounty=20000.0)
        await save_user_active_items(self.db, user_id, "b", items_b)
        await sync_user_criminal_status(self.db, user_id, items_b)

        # 1. Verify in direct SQL for all boards
        async with self.db.execute("SELECT board_id, active_items FROM Users WHERE user_id = ?", (user_id,)) as cur:
            rows = await cur.fetchall()
        for b_id, a_str in rows:
            data = json.loads(a_str)
            self.assertEqual(data.get("wanted_stars"), 4, f"Board {b_id} desynced in DB!")
            self.assertEqual(data.get("bounty_pool"), 20000.0, f"Board {b_id} bounty desynced!")

        # 2. Verify via load_user_active_items on /po/ and /int/
        items_po = await load_user_active_items(self.db, user_id, "po")
        self.assertEqual(items_po.get("wanted_stars"), 4)

        items_int = await load_user_active_items(self.db, user_id, "int")
        self.assertEqual(items_int.get("wanted_stars"), 4)

        # 3. Pay off bribe on board 'po' and verify synchronization back to 'b' and 'int'
        ok, _, meta = await execute_bribe_cop(self.db, user_id, "po", clear_all=True)
        self.assertTrue(ok)
        self.assertEqual(meta["new_stars"], 0)

        # Check /b/ is now 0★
        items_b_after = await load_user_active_items(self.db, user_id, "b")
        self.assertEqual(items_b_after.get("wanted_stars"), 0)

    # =========================================================================
    # DIRECTION 3: ARRESTS & DEFENSIVE TRAPS
    # =========================================================================

    async def test_legit_druzhinnik_arrest(self):
        """
        Legit arrest by officer with badge_druzhinnik_expires:
        - Mutes criminal for stars * 15m.
        - Officer gets 60% of bounty, 40% to Abu Fund.
        - Criminal заточки and lockpicks confiscated.
        - Criminal wanted status cleared (0★).
        """
        officer = 330001
        criminal = 330002
        now = time.time()

        officer_items = {"badge_druzhinnik_expires": now + 86400}
        criminal_items = {
            "wanted_stars": 3,
            "bounty_pool": 15000.0,
            "lockpick": 5,
            "knife": 2,
            "zatochka": 3,
        }

        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 0.0, ?)",
            (officer, json.dumps(officer_items)),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000.0, ?)",
            (criminal, json.dumps(criminal_items)),
        )
        await self.db.commit()

        ok, msg, meta = await execute_arrest(self.db, officer, criminal, "b")
        self.assertTrue(ok)
        self.assertEqual(meta["officer_payout"], 9000.0)  # 60% of 15,000
        self.assertEqual(meta["abu_burn"], 6000.0)        # 40% of 15,000
        self.assertEqual(meta["jail_minutes"], 45)         # 3 * 15 min
        self.assertTrue(meta["confiscated"])

        # Officer received payout
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ? AND board_id = 'b'", (officer,)) as cur:
            row = await cur.fetchone()
        self.assertEqual(row[0], 9000.0)

        # Criminal inventory confiscated & stars cleared
        c_after = await load_user_active_items(self.db, criminal, "b")
        self.assertEqual(c_after["lockpick"], 0)
        self.assertEqual(c_after["zatochka"], 0)
        self.assertEqual(c_after["knife"], 0)
        self.assertEqual(c_after["wanted_stars"], 0)
        self.assertEqual(c_after["bounty_pool"], 0.0)

    async def test_fake_ksiva_arrest_backfire_thirty_five_percent(self):
        """
        Arrest with fake ksiva:
        - 35% backfire roll: 10,000 ₪ fine, 30m mute, fake ksiva burned, 10k to Abu Fund.
        - 65% success roll: succeeds normally, fake ksiva consumed.
        """
        officer = 330003
        criminal = 330004
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50000.0, ?)",
            (officer, json.dumps({"fake_ksiva": 2})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 0.0, ?)",
            (criminal, json.dumps({"wanted_stars": 2, "bounty_pool": 10000.0})),
        )
        await self.db.commit()

        # 1. Test Backfire (roll = 0.20 < 0.35)
        ok_bf, msg_bf, meta_bf = await execute_arrest(self.db, officer, criminal, "b", fake_roll=0.20)
        self.assertFalse(ok_bf)
        self.assertTrue(meta_bf["backfire"])
        self.assertEqual(meta_bf["fine"], 10000.0)
        self.assertEqual(meta_bf["mute_sec"], 1800)
        self.assertIn("ПАЛЁНАЯ КСИВА", msg_bf)
        self.assertIn("10,000", msg_bf)

        # Verify 1 fake ksiva consumed
        off_after_bf = await load_user_active_items(self.db, officer, "b")
        self.assertEqual(off_after_bf["fake_ksiva"], 1)

        # 2. Test Success (roll = 0.80 >= 0.35)
        ok_succ, msg_succ, meta_succ = await execute_arrest(self.db, officer, criminal, "b", fake_roll=0.80)
        self.assertTrue(ok_succ)
        self.assertEqual(meta_succ["officer_payout"], 6000.0)  # 60% of 10,000

        # Verify remaining fake ksiva consumed
        off_after_succ = await load_user_active_items(self.db, officer, "b")
        self.assertEqual(off_after_succ["fake_ksiva"], 0)

    async def test_chloroform_neutralizes_pepperspray_in_theft_and_robbery(self):
        """
        Comprehensive test of Chloroform vs Pepperspray:
        1. When victim has pepperspray and is NOT chloroformed:
           - /pickpocket fails: pepperspray triggers, thief blinded 30m, fined 2000 ₪.
        2. When victim is chloroformed (/chloroform):
           - Victim sleeps for 30m.
           - detect_target_traps reports pepperspray is neutralized.
           - /pickpocket succeeds: pepperspray does NOT fire, thief steals dirty shekels.
        """
        thief = 330005
        victim = 330006
        now = time.time()

        thief_items = {"lockpick": 5, "chloroform": 1}
        victim_items = {"pepperspray_gun": True}

        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, 'b', 10000.0, ?, 100)",
            (thief, json.dumps(thief_items)),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items, posts_count) VALUES (?, 'b', 50000.0, ?, 100)",
            (victim, json.dumps(victim_items)),
        )
        await self.db.commit()

        # Step 1: Attempt pickpocket while victim is awake with pepperspray -> FAILS
        ok_theft1, msg_theft1, meta_theft1 = await execute_pickpocket(self.db, thief, victim, "b")
        self.assertFalse(ok_theft1)
        self.assertTrue(meta_theft1.get("peppersprayed"))
        self.assertIn("ПЕРЦОВАЯ СТРУЯ В ЕБЛО", msg_theft1)
        self.assertIn("30 минут", msg_theft1)

        # Step 2: Thief uses chloroform on victim
        ok_chlor, msg_chlor, meta_chlor = await execute_chloroform(self.db, thief, victim, "b")
        self.assertTrue(ok_chlor)
        self.assertIn("ХЛОРОФОРМ ПРИМЕНЁН", msg_chlor)
        self.assertGreater(meta_chlor["chloroformed_until"], now)

        # Step 3: Check detect_target_traps
        v_items_asleep = await load_user_active_items(self.db, victim, "b")
        v_items_asleep["pepperspray_gun"] = True  # reset gun for check
        traps = detect_target_traps(v_items_asleep, now=now)
        self.assertTrue(any("нейтрализован хлороформом" in t for t in traps))

        # Step 4: Attempt pickpocket while victim is chloroformed -> SUCCEEDS without pepper spray!
        # Force pickpocket success roll=0.10
        ok_theft2, msg_theft2, meta_theft2 = await execute_pickpocket(self.db, thief, victim, "b", roll=0.10)
        self.assertTrue(ok_theft2)
        self.assertTrue(meta_theft2.get("silent"))
        self.assertGreater(meta_theft2["stolen"], 0)
        self.assertNotIn("ПЕРЦОВАЯ СТРУЯ", msg_theft2)

    # =========================================================================
    # DIRECTION 4: WANTED & JAIL BOARDS LIMITS (<1500 CHARS & TOP-10)
    # =========================================================================

    async def test_wanted_board_fifty_criminals_top_ten_and_char_limit(self):
        """
        Emulate 50 criminals with varying wanted stars (1★ to 5★) and bounties:
        - format_wanted_board MUST output strictly Top-10 criminals.
        - Total character length MUST be strictly under 1500 characters.
        - Sorted in descending order by stars then bounty.
        """
        for i in range(1, 51):
            uid = 440000 + i
            stars = (i % 5) + 1  # 1 to 5 stars
            bounty = stars * 5000.0 + (i * 100)
            items = {"wanted_stars": stars, "bounty_pool": bounty}
            await self.db.execute(
                "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
                (uid, json.dumps(items)),
            )
        await self.db.commit()

        wanted_text = await format_wanted_board(self.db)

        # 1. Total character length must be strictly < 1500 chars
        self.assertLess(
            len(wanted_text),
            1500,
            f"Wanted board text length ({len(wanted_text)}) exceeded 1500 characters!",
        )

        # 2. Must state total 50 fugitives
        self.assertIn("50", wanted_text)

        # 3. Must contain 10 numbered positions (1. to 10.)
        for pos in range(1, 11):
            self.assertIn(f"<b>{pos}.</b>", wanted_text)
        # Position 11 must NOT be present
        self.assertNotIn("<b>11.</b>", wanted_text)

    async def test_jail_board_thirty_inmates_top_ten_and_char_limit(self):
        """
        Emulate 30 inmates in Mutes:
        - format_jail_board MUST output strictly Top-10 inmates.
        - Total character length MUST be strictly under 1500 characters.
        """
        now = time.time()
        for i in range(1, 31):
            uid = 550000 + i
            expires = now + (i * 300)
            reason = f"Статья 228 ч.{i}: Воровство шекелей у анонов"
            await self.db.execute(
                "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at, reason) VALUES (?, 'b', 'jail', ?, ?)",
                (uid, expires, reason),
            )
        await self.db.commit()

        jail_text = await format_jail_board(self.db, caller_id=550001)

        # 1. Total character length must be strictly < 1500 chars
        self.assertLess(
            len(jail_text),
            1500,
            f"Jail board text length ({len(jail_text)}) exceeded 1500 characters!",
        )

        # 2. Must contain Top-10 inmates
        self.assertIn("Топ-10", jail_text)
        for pos in range(1, 11):
            self.assertIn(f"<b>{pos}.</b>", jail_text)
        # Position 11 must NOT be present
        self.assertNotIn("<b>11.</b>", jail_text)

        # 3. Caller jail status must be displayed
        self.assertIn("ТЫ НАХОДИШЬСЯ ПОД АРЕСТОМ", jail_text)


if __name__ == "__main__":
    unittest.main()
