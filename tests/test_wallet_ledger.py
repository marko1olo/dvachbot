# -*- coding: utf-8 -*-
"""
test_wallet_ledger.py — Unit and integration tests for Wallet & Ledger HTML Escaping and DB records rendering
"""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import aiosqlite

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import common.database
import common.db_pool
from common.database import record_user_transaction, get_user_recent_transactions
from main import cmd_wallet, _format_ledger_view


class TestWalletLedgerHardening(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:", isolation_level=None)
        self.db.row_factory = aiosqlite.Row
        self._orig_db_conn = getattr(common.db_pool, "_db_connection", None)
        common.db_pool._db_connection = self.db
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER NOT NULL,
                board_id TEXT NOT NULL DEFAULT 'b',
                balance REAL DEFAULT 0,
                is_verified_b INTEGER DEFAULT 0,
                last_failed_amount REAL DEFAULT 0,
                active_items TEXT DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'active',
                PRIMARY KEY(user_id, board_id)
            )
            """
        )
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS UserTransactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                timestamp REAL NOT NULL
            )
            """
        )
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS ReferralAliases (
                code TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL
            )
            """
        )

    async def asyncTearDown(self):
        common.db_pool._db_connection = self._orig_db_conn
        await self.db.close()

    async def test_cmd_wallet_renders_real_db_transactions_and_escapes_html(self):
        user_id = 445566
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, is_verified_b) VALUES (?, 'b', 1500.0, 1)",
            (user_id,)
        )

        # Insert transactions with HTML tags to verify escaping defense
        ts = time.time()
        await record_user_transaction(
            self.db, user_id=user_id, amount=500.0, category="work",
            description="<b>Bold Job</b> & <script>alert(1)</script>", timestamp=ts - 100
        )
        await record_user_transaction(
            self.db, user_id=user_id, amount=-200.0, category="shop",
            description="Item <a href='evil.com'>Potion</a>", timestamp=ts - 50
        )
        await record_user_transaction(
            self.db, user_id=user_id, amount=1200.0, category="casino",
            description="Win & Jackpot <100%>", timestamp=ts
        )

        # Verify DB records
        recent_txs = await get_user_recent_transactions(self.db, user_id=user_id, limit=4)
        self.assertEqual(len(recent_txs), 3)

        # Mock aiogram message
        msg = MagicMock()
        msg.from_user.id = user_id
        msg.chat.id = user_id
        msg.answer = AsyncMock()
        msg.bot = AsyncMock()
        msg.bot.get_me = AsyncMock(return_value=MagicMock(username="tgach_bot"))

        pool_mock = AsyncMock(return_value=self.db)
        with patch("main.get_pool", pool_mock), \
             patch.object(common.db_pool, "get_pool", pool_mock), \
             patch.object(common.database, "get_pool", pool_mock), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner:

            await cmd_wallet(msg, board_id="b", stream="ru")

            # Extract the sent caption/text
            self.assertTrue(mock_send_banner.called)
            sent_caption = mock_send_banner.call_args.kwargs.get("caption", "")

            # Verify balance is rendered
            self.assertIn("1,500 ₪", sent_caption)

            # Verify HTML characters are escaped (defense-in-depth)
            self.assertNotIn("<b>Bold Job</b>", sent_caption)
            self.assertIn("&lt;b&gt;Bold Job&lt;/b&gt;", sent_caption)
            self.assertNotIn("<script>", sent_caption)
            self.assertIn("&lt;script&gt;", sent_caption)
            self.assertNotIn("<a href='evil.com'>", sent_caption)
            self.assertIn("&lt;a href='evil.com'&gt;Po..", sent_caption)
            self.assertNotIn("<100%>", sent_caption)
            self.assertIn("&lt;100%&gt;", sent_caption)

            # Verify amount signs and categories
            self.assertIn("+500", sent_caption)
            self.assertIn("-200", sent_caption)
            self.assertIn("+1,200", sent_caption)

    def test_format_ledger_view_escapes_html(self):
        user_id = 445566
        balance = 1500.0
        transactions = [
            {
                "id": 1,
                "user_id": user_id,
                "amount": 350.0,
                "category": "work",
                "description": "<img src=x onerror=alert(1)>",
                "timestamp": time.time()
            }
        ]
        summary = {"total_earned": 350.0, "total_spent": 0.0, "total_ops": 1}

        text, kb = _format_ledger_view(user_id, balance, transactions, summary)

        self.assertNotIn("<img", text)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", text)


if __name__ == "__main__":
    unittest.main()
