import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import main
from common import db_pool


class TestEconomyDaily(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER NOT NULL,
                board_id TEXT NOT NULL,
                balance REAL DEFAULT 0,
                active_items TEXT,
                PRIMARY KEY(user_id, board_id)
            )
        """)
        await self.db.commit()

        self.orig_pool = db_pool.get_pool
        db_pool.get_pool = AsyncMock(return_value=self.db)
        main.get_pool = AsyncMock(return_value=self.db)

    async def asyncTearDown(self):
        db_pool.get_pool = self.orig_pool
        main.get_pool = self.orig_pool
        await self.db.close()

    async def test_cb_economy_daily_success_and_no_name_error(self):
        user_id = 998877
        board_id = "b"

        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?)",
            (user_id, board_id, 100.0, json.dumps({}))
        )
        await self.db.commit()

        cb = MagicMock()
        cb.from_user = MagicMock(id=user_id)
        cb.answer = AsyncMock()

        await main.cb_economy_daily(cb, board_id)

        cb.answer.assert_called_once()
        answer_text = cb.answer.call_args[0][0]
        self.assertIn("✅ Получено +75 ₪!", answer_text)
        self.assertIn("Баланс: 175 ₪", answer_text)

        async with self.db.execute("SELECT balance, active_items FROM Users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            self.assertEqual(row[0], 175.0)
            items = json.loads(row[1])
            self.assertEqual(items["daily_streak"], 1)
            self.assertGreater(items["daily_last_claim"], 0)

    async def test_cb_economy_daily_cooldown(self):
        user_id = 998878
        board_id = "b"

        now = int(time.time())
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?)",
            (user_id, board_id, 100.0, json.dumps({"daily_last_claim": now - 100, "daily_streak": 1}))
        )
        await self.db.commit()

        cb = MagicMock()
        cb.from_user = MagicMock(id=user_id)
        cb.answer = AsyncMock()

        await main.cb_economy_daily(cb, board_id)

        cb.answer.assert_called_once()
        answer_text = cb.answer.call_args[0][0]
        self.assertIn("⏳ Бонус уже взят!", answer_text)
