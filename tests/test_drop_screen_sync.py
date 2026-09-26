"""
Unit & Integration Tests for DvachBot Money Drop Synchronization and UI Updates:
- MoneyDropMessages database persistence across bot restarts
- Accurate restoration of donor anon identifier (e.g. "Анон [Сивозе5]")
- Immediate screen update and inline button removal (reply_markup=None) upon late clicks
- Expired and cancelled drop message updates
- Robust edit_caption / edit_text dual fallback on photo & text messages
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import aiosqlite

import drop_engine
from common.anon_identity import get_anon_id
import main


class TestDropScreenSync(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        drop_engine.reset_drop_cooldowns()
        self.db = await aiosqlite.connect(":memory:")
        self.db_lock = asyncio.Lock()

        # Initialize schema including MoneyDrops & MoneyDropMessages
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER NOT NULL,
                board_id TEXT NOT NULL,
                balance REAL DEFAULT 0,
                PRIMARY KEY (user_id, board_id)
            );
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS UserTransactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS MoneyDrops (
                drop_id TEXT PRIMARY KEY,
                donor_id INTEGER NOT NULL,
                board_id TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at REAL NOT NULL,
                claimed_by INTEGER,
                claimed_board_id TEXT,
                claimed_at REAL,
                refunded_at REAL
            );
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS MoneyDropMessages (
                drop_id TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                PRIMARY KEY (drop_id, chat_id, message_id)
            );
        """)
        await self.db.commit()

        # Set up donor and claimer balances
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance) VALUES (1111, 'b', 5000), (2222, 'b', 1000), (3333, 'b', 1000)"
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        drop_engine.reset_drop_cooldowns()

    async def test_record_and_persist_drop_messages_in_db(self):
        """Verifies record_drop_message_db persists messages in memory and SQLite."""
        drop_id = "test_drop_msg_01"
        await drop_engine.record_drop_message_db(self.db, drop_id, 1001, 501)
        await drop_engine.record_drop_message_db(self.db, drop_id, 1002, 502)

        # Check memory
        msgs = drop_engine.get_drop_messages(drop_id)
        self.assertEqual(len(msgs), 2)
        self.assertIn((1001, 501), msgs)
        self.assertIn((1002, 502), msgs)

        # Check DB
        async with self.db.execute("SELECT chat_id, message_id FROM MoneyDropMessages WHERE drop_id = ?", (drop_id,)) as c:
            rows = await c.fetchall()
        self.assertEqual(len(rows), 2)
        self.assertIn((1001, 501), rows)
        self.assertIn((1002, 502), rows)

    async def test_init_drop_engine_restores_donor_anon_name_and_messages(self):
        """Verifies init_drop_engine restores donor anon identifier and message registry."""
        import time
        now = time.time()
        donor_id = 1111
        expected_anon = f"Анон [{get_anon_id(donor_id)}]"

        await self.db.execute(
            "INSERT INTO MoneyDrops (drop_id, donor_id, board_id, amount, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
            ("restore_drop_01", donor_id, "b", 503.0, now)
        )
        await self.db.execute(
            "INSERT INTO MoneyDropMessages (drop_id, chat_id, message_id) VALUES (?, ?, ?), (?, ?, ?)",
            ("restore_drop_01", 1001, 701, "restore_drop_01", 1002, 702)
        )
        await self.db.commit()

        # Simulate restart: clear in-memory registries
        drop_engine.active_drops.clear()
        drop_engine._drop_messages.clear()

        loaded = await drop_engine.init_drop_engine(self.db)
        self.assertEqual(loaded, 1)

        rec = drop_engine.active_drops.get("restore_drop_01")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.donor_name, expected_anon)
        self.assertEqual(rec.amount, 503)

        # Messages restored into memory
        msgs = drop_engine.get_drop_messages("restore_drop_01")
        self.assertEqual(len(msgs), 2)
        self.assertIn((1001, 701), msgs)
        self.assertIn((1002, 702), msgs)

    async def test_update_all_drop_messages_queries_db_if_memory_empty(self):
        """Verifies _update_all_drop_messages falls back to DB table when memory is empty."""
        drop_id = "test_fallback_db_01"
        await self.db.execute(
            "INSERT INTO MoneyDropMessages (drop_id, chat_id, message_id) VALUES (?, ?, ?), (?, ?, ?)",
            (drop_id, 1001, 801, drop_id, 1002, 802)
        )
        await self.db.commit()

        # Memory is empty
        drop_engine._drop_messages.clear()

        mock_bot = AsyncMock()
        mock_bot.edit_message_caption = AsyncMock()

        with patch("main.get_pool", return_value=self.db):
            await main._update_all_drop_messages(mock_bot, drop_id, "FINAL TEXT")

        self.assertEqual(mock_bot.edit_message_caption.call_count, 2)
        mock_bot.edit_message_caption.assert_any_call(
            chat_id=1001, message_id=801, caption="FINAL TEXT", parse_mode="HTML", reply_markup=None
        )
        mock_bot.edit_message_caption.assert_any_call(
            chat_id=1002, message_id=802, caption="FINAL TEXT", parse_mode="HTML", reply_markup=None
        )

    async def test_late_clicker_immediately_updates_message_and_removes_button(self):
        """Verifies that when user B clicks an already claimed drop, their message is immediately edited to remove the button."""
        donor_id = 1111
        user_a = 2222
        user_b = 3333

        ok, _, drop_rec = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name=f"Анон [{get_anon_id(donor_id)}]",
            board_id="b",
            amount=500,
            db_lock=self.db_lock,
            db_conn=self.db,
            check_cooldown=False,
        )
        self.assertTrue(ok)

        # User A claims the drop
        ok_a, _, _ = await drop_engine.claim_money_drop(
            drop_id=drop_rec.drop_id,
            claimer_id=user_a,
            claimer_name=f"Анон [{get_anon_id(user_a)}]",
            claimer_board_id="b",
            db_lock=self.db_lock,
            db_conn=self.db,
            check_reaction_delay=False,
            check_claimer_rate_limit=False,
            check_farm_laundering=False,
            check_anti_snipe=False,
        )
        self.assertTrue(ok_a)
        self.assertEqual(drop_rec.status, "claimed")

        # Now User B clicks the button on their screen
        cb_user_b = MagicMock()
        cb_user_b.from_user.id = user_b
        cb_user_b.data = f"drop:claim:{drop_rec.drop_id}"
        cb_user_b.answer = AsyncMock()

        # User B's message in Telegram
        msg_user_b = AsyncMock()
        msg_user_b.caption = "Some caption"
        msg_user_b.edit_caption = AsyncMock()
        msg_user_b.edit_text = AsyncMock()
        cb_user_b.message = msg_user_b

        with patch("main.get_pool", return_value=self.db), \
             patch("main.db_lock", self.db_lock), \
             patch("common.database.is_shadow_muted", AsyncMock(return_value=False)):
            await main.cb_drop_handler(cb_user_b, board_id="b")

        # Callback answered with alert
        cb_user_b.answer.assert_called_once()
        self.assertTrue(cb_user_b.answer.call_args[1].get("show_alert"))

        # Crucial check: User B's message edit_caption was invoked with reply_markup=None to kill the stale button!
        msg_user_b.edit_caption.assert_called_once()
        edit_kwargs = msg_user_b.edit_caption.call_args[1]
        self.assertIsNone(edit_kwargs.get("reply_markup"))
        self.assertIn("ДРОП ШЕКЕЛЕЙ ПЕРЕХВАЧЕН!", edit_kwargs.get("caption"))
        self.assertIn(f"Анон [{get_anon_id(user_a)}]", edit_kwargs.get("caption"))

    async def test_expired_drop_clicker_immediately_removes_button(self):
        """Verifies that clicking an expired drop immediately edits the message and removes the button."""
        donor_id = 1111
        user_b = 3333

        ok, _, drop_rec = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name=f"Анон [{get_anon_id(donor_id)}]",
            board_id="b",
            amount=500,
            db_lock=self.db_lock,
            db_conn=self.db,
            check_cooldown=False,
        )
        self.assertTrue(ok)
        drop_rec.status = "expired"

        cb = MagicMock()
        cb.from_user.id = user_b
        cb.data = f"drop:claim:{drop_rec.drop_id}"
        cb.answer = AsyncMock()

        msg = AsyncMock()
        msg.caption = "Old caption"
        msg.edit_caption = AsyncMock()
        msg.edit_text = AsyncMock()
        cb.message = msg

        with patch("main.get_pool", return_value=self.db), \
             patch("main.db_lock", self.db_lock), \
             patch("common.database.is_shadow_muted", AsyncMock(return_value=False)):
            await main.cb_drop_handler(cb, board_id="b")

        cb.answer.assert_called_once()
        msg.edit_caption.assert_called_once()
        self.assertIsNone(msg.edit_caption.call_args[1].get("reply_markup"))
        self.assertIn("ДРОП ШЕКЕЛЕЙ ИСТЕК", msg.edit_caption.call_args[1].get("caption"))


if __name__ == "__main__":
    unittest.main()
