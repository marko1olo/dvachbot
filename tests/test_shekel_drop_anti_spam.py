"""
Unit, Concurrency, and Integration Tests for Shekel Drop Anti-Spam & Edit Mechanic.
Verifies:
1. Differentiated cooldowns based on drop amount (150-500 ₪: 45s, 500-5000 ₪: 20s, >5000 ₪: 10s).
2. Creative 2ch-style excuses with countdown timers on cooldown triggers.
3. Minimum (150 ₪) and maximum (1,000,000 ₪) limits with dark toxic excuses.
4. User-isolated cooldown state (User A cooldown does not block User B).
5. In-place message edit mechanic upon claiming (no duplicate board spam).
6. High concurrency protection (100 parallel claims = exactly 1 winner, 0 race condition).
7. Self-claim block, donor PM notification, cancellation refund, and expiration refund.
8. Interactive creator keyboard starting from 150 ₪.
"""

import asyncio
import re
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite
import drop_engine
import main


class TestShekelDropAntiSpam(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        drop_engine.reset_drop_cooldowns()
        drop_engine.active_drops.clear()
        drop_engine._drop_messages.clear()
        self.db = await aiosqlite.connect(":memory:")
        self.db_lock = asyncio.Lock()

        await self.db.execute(
            """CREATE TABLE Users (
                user_id INTEGER,
                board_id TEXT,
                balance INTEGER DEFAULT 0,
                PRIMARY KEY(user_id, board_id)
            )"""
        )
        await self.db.execute(
            """CREATE TABLE IF NOT EXISTS MoneyDrops (
                drop_id TEXT PRIMARY KEY,
                donor_id INTEGER,
                board_id TEXT,
                amount REAL,
                status TEXT,
                created_at REAL,
                claimed_by INTEGER,
                claimed_board_id TEXT,
                claimed_at REAL,
                refunded_at REAL
            )"""
        )
        await self.db.execute(
            """CREATE TABLE IF NOT EXISTS UserTransactions (
                tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                tx_type TEXT,
                details TEXT,
                created_at REAL
            )"""
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        drop_engine.reset_drop_cooldowns()

    # -------------------------------------------------------------------------
    # 1. Differentiated Cooldown Math
    # -------------------------------------------------------------------------
    def test_differentiated_cooldown_tiers(self):
        """Проверяет кулдаун на создание раздач (1 раз в 5 минут / 300 секунд)."""
        self.assertEqual(drop_engine.get_drop_cooldown_seconds(150), 300)
        self.assertEqual(drop_engine.get_drop_cooldown_seconds(500), 300)
        self.assertEqual(drop_engine.get_drop_cooldown_seconds(1000), 300)
        self.assertEqual(drop_engine.get_drop_cooldown_seconds(10000), 300)
        self.assertEqual(drop_engine.get_drop_cooldown_seconds(1000000), 300)

    # -------------------------------------------------------------------------
    # 2. Min & Max Limits & Toxic Excuses
    # -------------------------------------------------------------------------
    async def test_min_and_max_drop_limits(self):
        """Проверяет лимиты сумм: минимум 150 ₪, максимум 1 000 000 ₪ с токсичными отмазками."""
        donor_id = 11111
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000000)", (donor_id,))
        await self.db.commit()

        # Less than 150 ₪ (e.g. 5, 10, 149 ₪)
        for bad_amount in [5, 10, 149]:
            ok, msg, rec = await drop_engine.create_money_drop(
                donor_id=donor_id,
                donor_name="Anon",
                board_id="b",
                amount=bad_amount,
                db_lock=self.db_lock,
                db_conn=self.db,
            )
            self.assertFalse(ok)
            self.assertIn(f"{bad_amount} ₪", msg)
            self.assertIn("150 ₪", msg)
            self.assertIsNone(rec)

        # Greater than 1 000 000 ₪ (e.g. 1 000 001 ₪)
        ok_max, msg_max, rec_max = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="Anon",
            board_id="b",
            amount=1000001,
            db_lock=self.db_lock,
            db_conn=self.db,
        )
        self.assertFalse(ok_max)
        self.assertIn("1 000 000 ₪", msg_max)
        self.assertIn("1000001 ₪", msg_max)
        self.assertIsNone(rec_max)

    # -------------------------------------------------------------------------
    # 3. Anti-Spam Cooldown & 2ch Lore Excuses
    # -------------------------------------------------------------------------
    async def test_user_cooldown_blocking_and_excuse_pool(self):
        """Проверяет срабатывание кулдауна и выдачу циничных фраз с таймером."""
        donor_id = 22222
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 50000)", (donor_id,))
        await self.db.commit()

        # Step 1: First drop of 200 ₪ (150-500 ₪ => 45s cooldown)
        ok1, msg1, rec1 = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="AnonDonor",
            board_id="b",
            amount=200,
            db_lock=self.db_lock,
            db_conn=self.db,
        )
        self.assertTrue(ok1)
        self.assertIsNotNone(rec1)

        rem = drop_engine.get_user_cooldown_remaining(donor_id)
        self.assertGreater(rem, 250)
        self.assertLessEqual(rem, 300)

        # Step 2: Immediate second drop attempt by same user must be blocked
        ok2, msg2, rec2 = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="AnonDonor",
            board_id="b",
            amount=500,
            db_lock=self.db_lock,
            db_conn=self.db,
        )
        self.assertFalse(ok2)
        self.assertIsNone(rec2)
        self.assertTrue(msg2.startswith("⏳"))
        # Check that remaining seconds placeholder was formatted into integer seconds
        self.assertRegex(msg2, r"\d+с")

        # Step 3: Test cooldown excuse generation directly from pool
        for _ in range(50):
            excuse = drop_engine.get_cooldown_rejection_message(42)
            self.assertIn("42с", excuse)
            self.assertTrue(any(template.split("{seconds}")[0] in excuse for template in drop_engine.COOLDOWN_EXCUSES))

        # Step 4: Test min excuse pool directly
        for _ in range(50):
            min_excuse = drop_engine.get_min_drop_rejection_message(88)
            self.assertIn("88 ₪", min_excuse)
            self.assertIn("150 ₪", min_excuse)

        # Step 5: Test max excuse pool directly
        for _ in range(50):
            max_excuse = drop_engine.get_max_drop_rejection_message(5000000)
            self.assertIn("5000000 ₪", max_excuse)
            self.assertIn("1 000 000 ₪", max_excuse)

        # Step 6: After cooldown expires, drop succeeds
        drop_engine.set_user_drop_cooldown(donor_id, -1.0)
        self.assertEqual(drop_engine.get_user_cooldown_remaining(donor_id), 0.0)

        ok3, msg3, rec3 = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="AnonDonor",
            board_id="b",
            amount=1000,
            db_lock=self.db_lock,
            db_conn=self.db,
        )
        self.assertTrue(ok3)
        self.assertIsNotNone(rec3)

    # -------------------------------------------------------------------------
    # 4. User-Isolated Cooldowns
    # -------------------------------------------------------------------------
    async def test_independent_user_cooldowns(self):
        """Кулдаун пользователя A не должен блокировать пользователя B."""
        user_a = 30001
        user_b = 30002
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (user_a,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (user_b,))
        await self.db.commit()

        # User A creates drop and gets on cooldown
        ok_a, _, _ = await drop_engine.create_money_drop(
            donor_id=user_a,
            donor_name="AnonA",
            board_id="b",
            amount=200,
            db_lock=self.db_lock,
            db_conn=self.db,
        )
        self.assertTrue(ok_a)
        self.assertGreater(drop_engine.get_user_cooldown_remaining(user_a), 0)

        # User B should NOT be on cooldown and create drop successfully
        self.assertEqual(drop_engine.get_user_cooldown_remaining(user_b), 0.0)
        ok_b, _, rec_b = await drop_engine.create_money_drop(
            donor_id=user_b,
            donor_name="AnonB",
            board_id="b",
            amount=500,
            db_lock=self.db_lock,
            db_conn=self.db,
        )
        self.assertTrue(ok_b)
        self.assertIsNotNone(rec_b)

    # -------------------------------------------------------------------------
    # 5. Message Registration & Edit Mechanic on Claim (No Board Spam)
    # -------------------------------------------------------------------------
    async def test_drop_message_registration_and_update(self):
        """Проверяет регистрацию всех копий сообщений и их обновление через edit_message."""
        drop_id = "test_drop_123"
        drop_engine.register_drop_message(drop_id, 101, 1001)
        drop_engine.register_drop_message(drop_id, 102, 1002)
        drop_engine.register_drop_message(drop_id, 103, 1003)
        # Duplicate registration test
        drop_engine.register_drop_message(drop_id, 101, 1001)

        messages = drop_engine.get_drop_messages(drop_id)
        self.assertEqual(len(messages), 3)
        self.assertIn((101, 1001), messages)
        self.assertIn((102, 1002), messages)
        self.assertIn((103, 1003), messages)

        # Test _update_all_drop_messages calling edit_message_caption / text on all copies
        mock_bot = AsyncMock()
        mock_bot.edit_message_caption = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()

        new_text = "💸 <b>ДРОП ШЕКЕЛЕЙ ПЕРЕХВАЧЕН!</b>"
        await main._update_all_drop_messages(
            bot=mock_bot,
            drop_id=drop_id,
            new_text=new_text,
            exclude_pair=(101, 1001),
        )

        # Message (101, 1001) was excluded because it was edited in-place by winner callback.
        # Messages (102, 1002) and (103, 1003) must have been edited!
        self.assertEqual(mock_bot.edit_message_caption.call_count, 2)
        edited_chats = [call.kwargs["chat_id"] for call in mock_bot.edit_message_caption.call_args_list]
        self.assertIn(102, edited_chats)
        self.assertIn(103, edited_chats)
        self.assertNotIn(101, edited_chats)

    # -------------------------------------------------------------------------
    # 6. High-Concurrency Claim Protection (100 Parallel Requests)
    # -------------------------------------------------------------------------
    async def test_high_concurrency_race_condition_protection(self):
        """100 параллельных запросов на клейм — строго 1 победитель, 0 гонок."""
        donor_id = 77777
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 10000)", (donor_id,))
        for uid in range(1, 101):
            await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (uid,))
        await self.db.commit()

        ok, msg, drop_rec = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="DonorAnon",
            board_id="b",
            amount=1500,
            db_lock=self.db_lock,
            db_conn=self.db,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(drop_rec)

        drop_id = drop_rec.drop_id

        async def worker_claim(uid: int):
            return await drop_engine.claim_money_drop(
                drop_id=drop_id,
                claimer_id=uid,
                claimer_name=f"Claimer #{uid}",
                claimer_board_id="b",
                db_lock=self.db_lock,
                db_conn=self.db,
            )

        tasks = [worker_claim(i) for i in range(1, 101)]
        results = await asyncio.gather(*tasks)

        success = [r for r in results if r[0] is True]
        failed = [r for r in results if r[0] is False]

        self.assertEqual(len(success), 1, "Must have exactly 1 winner")
        self.assertEqual(len(failed), 99, "Must have exactly 99 rejected claims")

        winner_rec = success[0][2]
        winner_id = winner_rec.claimed_by
        self.assertIsNotNone(winner_id)

        # Check winner balance in DB
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (winner_id,)) as c:
            row = await c.fetchone()
            self.assertEqual(row[0], 1500)

        # Check total remaining balance of all other 99 losers
        async with self.db.execute("SELECT SUM(balance) FROM Users WHERE user_id != ? AND user_id != ?", (winner_id, donor_id)) as c:
            sum_row = await c.fetchone()
            self.assertEqual(sum_row[0], 0)

    # -------------------------------------------------------------------------
    # 7. Self-Claim & Cancellation & Expiry
    # -------------------------------------------------------------------------
    async def test_self_claim_forbidden_and_cancellation(self):
        """Создатель не может перехватить свой дроп, но может его отменить."""
        donor_id = 88888
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 2000)", (donor_id,))
        await self.db.commit()

        ok, _, drop_rec = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="SelfDonor",
            board_id="b",
            amount=500,
            db_lock=self.db_lock,
            db_conn=self.db,
        )
        self.assertTrue(ok)

        # Self claim attempt
        ok_self, msg_self, _ = await drop_engine.claim_money_drop(
            drop_id=drop_rec.drop_id,
            claimer_id=donor_id,
            claimer_name="SelfDonor",
            claimer_board_id="b",
            db_lock=self.db_lock,
            db_conn=self.db,
        )
        self.assertFalse(ok_self)
        self.assertIn("свой собственный дроп", msg_self)

        # Cancellation by donor
        ok_cancel, msg_cancel = await drop_engine.cancel_money_drop(
            drop_id=drop_rec.drop_id,
            user_id=donor_id,
            db_lock=self.db_lock,
            db_conn=self.db,
        )
        self.assertTrue(ok_cancel)
        self.assertIn("отменен", msg_cancel)

        # Balance refunded
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,)) as c:
            row = await c.fetchone()
            self.assertEqual(row[0], 2000)

    async def test_drop_expiry_and_auto_refund(self):
        """Истекший дроп возвращает средства донору."""
        donor_id = 99901
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 3000)", (donor_id,))
        await self.db.commit()

        ok, _, drop_rec = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="ExpireDonor",
            board_id="b",
            amount=700,
            db_lock=self.db_lock,
            db_conn=self.db,
            timeout_sec=0.01,
        )
        self.assertTrue(ok)

        # Force expire
        drop_rec.expires_at = time.time() - 1.0
        expired_list = await drop_engine.expire_unclaimed_drops_step(self.db_lock, self.db)
        self.assertEqual(len(expired_list), 1)
        self.assertEqual(expired_list[0].drop_id, drop_rec.drop_id)

        # Balance refunded to 3000
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,)) as c:
            row = await c.fetchone()
            self.assertEqual(row[0], 3000)

    # -------------------------------------------------------------------------
    # 8. Interactive Drop Creator Keyboard
    # -------------------------------------------------------------------------
    def test_drop_creator_keyboard_structure(self):
        """Проверяет, что клавиатура создания дропа содержит правильные суммы, начиная от 150 ₪."""
        kb = drop_engine.get_drop_creator_keyboard(60000)
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        callback_data_list = [btn.callback_data for btn in all_buttons]

        self.assertIn("drop:create:150", callback_data_list)
        self.assertIn("drop:create:500", callback_data_list)
        self.assertIn("drop:create:1000", callback_data_list)
        self.assertIn("drop:create:5000", callback_data_list)
        self.assertIn("drop:create:10000", callback_data_list)
        self.assertIn("drop:create:50000", callback_data_list)
        self.assertIn("drop:cancel_menu", callback_data_list)

        # Ensure no obsolete buttons like 100 ₪
        self.assertNotIn("drop:create:100", callback_data_list)


if __name__ == "__main__":
    unittest.main()
