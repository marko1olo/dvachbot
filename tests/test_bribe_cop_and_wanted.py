# -*- coding: utf-8 -*-
"""
tests/test_bribe_cop_and_wanted.py — Unit & Integration tests for Wanted, Jail, and Bribe Cop
=============================================================================================
Verifies:
1. Deducting bribe_envelope from darknet.
2. Accepting shop 'bribe' item (индульгенция 450 ₪).
3. Direct shekel payment when items are missing (anti-softlock).
4. Full clearance (/bribe_cop all) with wholesale discount and bank unlock notification.
5. Multi-board database synchronization in Users table.
6. Length limits for /wanted and /jail lists (<1500 characters, no Telegram 4096 breaches).
"""

import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
from aiogram import types

from criminal_syndicate_engine import (
    cmd_bribe_cop,
    cmd_jail,
    cmd_wanted,
    execute_bribe_cop,
)


class TestBribeCopAndWantedSuite(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for /bribe_cop, /wanted, and /jail mechanics.
    """

    async def asyncSetUp(self):
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
                value REAL
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

    async def asyncTearDown(self):
        await self.db.close()

    async def test_bribe_cop_consumes_bribe_envelope(self):
        """1. Verifies that bribe_envelope from darknet is consumed and drops 1 star."""
        user_id = 9101
        initial_items = {"bribe_envelope": 2, "wanted_stars": 2, "bounty_pool": 10000.0}
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 0.0, ?)",
            (user_id, json.dumps(initial_items)),
        )
        await self.db.commit()

        ok, msg, meta = await execute_bribe_cop(self.db, user_id, "b")
        self.assertTrue(ok)
        self.assertEqual(meta["new_stars"], 1)
        self.assertEqual(meta["new_bounty"], 5000.0)
        self.assertEqual(meta["payment_method"], "bribe_envelope")
        self.assertEqual(meta["envelopes_left"], 1)
        self.assertIn("СЛЕДОВАТЕЛЬ ПРИНЯЛ КОНВЕРТ", msg)

        # Check DB persistence
        async with self.db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = 'b'", (user_id,)) as cur:
            row = await cur.fetchone()
        db_items = json.loads(row[0])
        self.assertEqual(db_items["wanted_stars"], 1)
        self.assertEqual(db_items["bribe_envelope"], 1)

    async def test_bribe_cop_accepts_shop_bribe_item(self):
        """2. Verifies that shop 'bribe' item (450 ₪ indulgence) is accepted when envelopes are absent."""
        user_id = 9102
        initial_items = {"bribe": 1, "wanted_stars": 3, "bounty_pool": 15000.0, "bribe_envelope": 0}
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 0.0, ?)",
            (user_id, json.dumps(initial_items)),
        )
        await self.db.commit()

        ok, msg, meta = await execute_bribe_cop(self.db, user_id, "b")
        self.assertTrue(ok)
        self.assertEqual(meta["new_stars"], 2)
        self.assertEqual(meta["new_bounty"], 10000.0)
        self.assertEqual(meta["payment_method"], "shop_bribe")
        self.assertIn("магазинная индульгенция", msg)

        # Check DB
        async with self.db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = 'b'", (user_id,)) as cur:
            row = await cur.fetchone()
        db_items = json.loads(row[0])
        self.assertEqual(db_items["wanted_stars"], 2)
        self.assertEqual(db_items["bribe"], 0)

    async def test_bribe_cop_direct_shekels_anti_softlock_and_bank_unlock(self):
        """3. Verifies direct shekel payment prevents softlock and triggers bank unlock when dropping below 5★."""
        user_id = 9103
        initial_items = {"wanted_stars": 5, "bounty_pool": 25000.0, "bribe_envelope": 0, "bribe": 0}
        initial_balance = 20000.0
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', ?, ?)",
            (user_id, initial_balance, json.dumps(initial_items)),
        )
        await self.db.commit()

        # Step A: Clear 1 star directly with shekels
        ok1, msg1, meta1 = await execute_bribe_cop(self.db, user_id, "b", clear_all=False)
        self.assertTrue(ok1)
        self.assertEqual(meta1["new_stars"], 4)
        self.assertEqual(meta1["new_bounty"], 20000.0)
        self.assertEqual(meta1["payment_method"], "shekels")
        self.assertTrue(meta1["bank_unlocked"])
        self.assertIn("БАНКОВСКИЕ СЧЕТА И ПЕРЕВОДЫ РАЗБЛОКИРОВАНЫ", msg1)

        # Step B: Clear all remaining stars with /bribe_cop all
        ok2, msg2, meta2 = await execute_bribe_cop(self.db, user_id, "b", clear_all=True)
        self.assertTrue(ok2)
        self.assertEqual(meta2["new_stars"], 0)
        self.assertEqual(meta2["new_bounty"], 0.0)
        self.assertEqual(meta2["payment_method"], "shekels")
        self.assertIn("ТЫ ПОЛНОСТЬЮ ЧИСТ ПЕРЕД ЗАКОНОМ", msg2)

    async def test_bribe_cop_insufficient_funds_helpful_error(self):
        """4. Verifies clear informative error when player has no items and insufficient cash balance."""
        user_id = 9104
        initial_items = {"wanted_stars": 5, "bounty_pool": 25000.0, "bribe_envelope": 0, "bribe": 0}
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50.0, ?)",
            (user_id, json.dumps(initial_items)),
        )
        await self.db.commit()

        ok, msg, meta = await execute_bribe_cop(self.db, user_id, "b")
        self.assertFalse(ok)
        self.assertTrue(meta["no_envelope"])
        self.assertTrue(meta["insufficient_funds"])
        self.assertIn("НЕТ КОНВЕРТА С ВЗЯТКОЙ", msg)
        self.assertIn("/work", msg)
        self.assertIn("/darknet", msg)

    async def test_bribe_cop_multi_board_synchronization(self):
        """5. Verifies atomic synchronization of criminal status across all board rows in Users."""
        user_id = 9105
        # User has two rows: board 'b' and board 'ru'
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 10000.0, ?)",
            (user_id, json.dumps({"wanted_stars": 5, "bounty_pool": 25000.0, "bribe_envelope": 0})),
        )
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'ru', 10000.0, ?)",
            (user_id, json.dumps({"wanted_stars": 5, "bounty_pool": 25000.0, "bribe_envelope": 0})),
        )
        await self.db.commit()

        # Bribe executed on board 'b'
        ok, msg, meta = await execute_bribe_cop(self.db, user_id, "b", clear_all=False)
        self.assertTrue(ok)
        self.assertEqual(meta["new_stars"], 4)

        # Verify board 'b' row updated
        async with self.db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = 'b'", (user_id,)) as cur:
            row_b = await cur.fetchone()
        items_b = json.loads(row_b[0])
        self.assertEqual(items_b["wanted_stars"], 4)

        # Verify board 'ru' row ALSO synchronized to 4 stars (preventing LIMIT 1 desync bug)
        async with self.db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = 'ru'", (user_id,)) as cur:
            row_ru = await cur.fetchone()
        items_ru = json.loads(row_ru[0])
        self.assertEqual(items_ru["wanted_stars"], 4)
        self.assertEqual(items_ru["bounty_pool"], 20000.0)

    async def test_wanted_and_jail_length_limits(self):
        """6. Verifies /wanted and /jail lists strictly cap at Top 10 (<1500 chars, no Telegram overflow)."""
        # Populate 25 wanted criminals
        for i in range(1, 26):
            uid = 9200 + i
            stars = (i % 5) + 1
            bounty = stars * 5000.0
            await self.db.execute(
                "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
                (uid, json.dumps({"wanted_stars": stars, "bounty_pool": bounty})),
            )

        # Populate 20 active mutes/inmates
        now = time.time()
        for i in range(1, 21):
            uid = 9300 + i
            await self.db.execute(
                "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at, reason) VALUES (?, 'b', 'mute', ?, ?)",
                (uid, now + (i * 600), f"Арест дружинниками по статье {i}"),
            )
        await self.db.commit()

        mock_msg = MagicMock(spec=types.Message)
        mock_msg.board_id = "b"
        mock_msg.from_user = MagicMock(id=9305)  # Inmate 9305
        mock_msg.text = "/wanted"
        mock_msg.answer = AsyncMock()

        # Test /wanted
        with patch("common.db_pool.get_pool", AsyncMock(return_value=self.db)):
            await cmd_wanted(mock_msg, board_id="b")

        mock_msg.answer.assert_called_once()
        wanted_text = mock_msg.answer.call_args[0][0]
        self.assertLess(len(wanted_text), 1500, f"/wanted output too long: {len(wanted_text)} chars")
        self.assertIn("ДОСКА ОРИЕНТИРОВОК", wanted_text)
        self.assertIn("10.", wanted_text)
        self.assertNotIn("11.", wanted_text)  # strictly Top-10

        # Test /jail
        mock_msg.answer.reset_mock()
        mock_msg.text = "/jail"
        with patch("common.db_pool.get_pool", AsyncMock(return_value=self.db)):
            await cmd_jail(mock_msg, board_id="b")

        mock_msg.answer.assert_called_once()
        jail_text = mock_msg.answer.call_args[0][0]
        self.assertLess(len(jail_text), 1500, f"/jail output too long: {len(jail_text)} chars")
        self.assertIn("ОБЕЗЬЯННИК И КПЗ", jail_text)
        self.assertIn("ТЫ НАХОДИШЬСЯ ПОД АРЕСТОМ", jail_text)
        self.assertIn("10.", jail_text)
        self.assertNotIn("11.", jail_text)  # strictly Top-10


if __name__ == "__main__":
    unittest.main()
