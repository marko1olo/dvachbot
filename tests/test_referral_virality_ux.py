# -*- coding: utf-8 -*-
"""
tests/test_referral_virality_ux.py — Comprehensive Unit & Integration Tests for
Referral Engine, Anti-Abuse, Mobile Virality UX, and Privacy Protection.
"""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import aiosqlite
import urllib.parse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import common.database
import common.db_pool
from common.referral_engine import (
    REFERRAL_REWARD_REFERRER,
    REFERRAL_REWARD_REFEREE,
    get_or_create_referral_code,
    build_referral_link,
    build_share_url,
    resolve_referral_code,
    get_referral_stats,
    format_referral_dashboard_message,
    process_referral_activation,
    process_start_referral,
    handle_referral_command,
)
from common.anon_identity import get_referral_code, generate_anon_name


class TestReferralViralityUX(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:", isolation_level=None)
        self.db.row_factory = aiosqlite.Row
        self._orig_db_conn = getattr(common.db_pool, "_db_connection", None)
        common.db_pool._db_connection = self.db

        # Initialize test tables
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER NOT NULL,
                board_id TEXT NOT NULL DEFAULT 'b',
                balance REAL DEFAULT 0,
                referrals_count INTEGER DEFAULT 0,
                posts_count INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                PRIMARY KEY(user_id, board_id)
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS ReferralAliases (
                code TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS Referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                board_id TEXT NOT NULL DEFAULT 'b',
                reward_amount REAL DEFAULT 22320.0,
                created_at REAL NOT NULL,
                status TEXT DEFAULT 'active'
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS UserTransactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            )
        """)

    async def asyncTearDown(self):
        common.db_pool._db_connection = self._orig_db_conn
        await self.db.close()

    # =========================================================================
    # 1. Phonetic Code Generation & Resolution
    # =========================================================================

    async def test_get_or_create_referral_code(self):
        user_id = 987654321
        code = await get_or_create_referral_code(self.db, user_id)
        self.assertTrue(len(code) >= 6)
        self.assertFalse(code.isdigit())

        # Verify entry created in ReferralAliases
        async with self.db.execute("SELECT user_id FROM ReferralAliases WHERE code = ?", (code,)) as cur:
            row = await cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], user_id)

    async def test_resolve_referral_code_various_formats(self):
        user_id = 555111222
        code = await get_or_create_referral_code(self.db, user_id)

        # Exact code
        resolved = await resolve_referral_code(self.db, code)
        self.assertEqual(resolved, user_id)

        # Lowercase
        resolved_lower = await resolve_referral_code(self.db, code.lower())
        self.assertEqual(resolved_lower, user_id)

        # With ref_ prefix
        resolved_pref = await resolve_referral_code(self.db, f"ref_{code}")
        self.assertEqual(resolved_pref, user_id)

        # With ref- prefix
        resolved_dash = await resolve_referral_code(self.db, f"ref-{code}")
        self.assertEqual(resolved_dash, user_id)

        # Non-existent code
        self.assertIsNone(await resolve_referral_code(self.db, "NonExistentCode999"))

    # =========================================================================
    # 2. Anti-Abuse Checks
    # =========================================================================

    async def test_anti_abuse_self_referral_rejected(self):
        user_id = 123456789
        bot = AsyncMock()
        success, reason, _ = await process_referral_activation(
            db=self.db,
            bot=bot,
            referred_id=user_id,
            referrer_id=user_id,
            board_id="b"
        )
        self.assertFalse(success)
        self.assertEqual(reason, "self_referral")
        bot.send_message.assert_not_called()

    async def test_anti_abuse_duplicate_referral_rejected(self):
        referrer_id = 100000001
        referee_id = 200000002
        bot = AsyncMock()

        # First activation: should succeed
        success, reason, details = await process_referral_activation(
            db=self.db,
            bot=bot,
            referred_id=referee_id,
            referrer_id=referrer_id,
            board_id="b"
        )
        self.assertTrue(success)
        self.assertEqual(reason, "success")

        # Second activation with same referee: MUST be rejected
        success2, reason2, _ = await process_referral_activation(
            db=self.db,
            bot=bot,
            referred_id=referee_id,
            referrer_id=referrer_id,
            board_id="b"
        )
        self.assertFalse(success2)
        self.assertEqual(reason2, "already_referred")

    async def test_anti_abuse_existing_active_user_rejected(self):
        referrer_id = 100000001
        existing_user_id = 300000003
        bot = AsyncMock()

        # Seed existing user with prior posts and balance
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, posts_count) VALUES (?, 'b', 250.0, 5)",
            (existing_user_id,)
        )

        success, reason, _ = await process_referral_activation(
            db=self.db,
            bot=bot,
            referred_id=existing_user_id,
            referrer_id=referrer_id,
            board_id="b"
        )
        self.assertFalse(success)
        self.assertEqual(reason, "not_new_user")

    async def test_anti_abuse_service_bot_rejected(self):
        bot = AsyncMock()
        success, reason, _ = await process_referral_activation(
            db=self.db,
            bot=bot,
            referred_id=777000,  # Telegram service notification bot
            referrer_id=100000001,
            board_id="b"
        )
        self.assertFalse(success)
        self.assertEqual(reason, "invalid_referee")

    # =========================================================================
    # 3. Reward Distribution & Financial Ledger
    # =========================================================================

    async def test_successful_reward_distribution_and_ledger(self):
        referrer_id = 111222333
        referee_id = 444555666
        bot = AsyncMock()

        success, reason, details = await process_referral_activation(
            db=self.db,
            bot=bot,
            referred_id=referee_id,
            referrer_id=referrer_id,
            board_id="b",
            stream="ru"
        )
        self.assertTrue(success)
        self.assertEqual(details["referrer_reward"], REFERRAL_REWARD_REFERRER)
        self.assertEqual(details["referee_reward"], REFERRAL_REWARD_REFEREE)

        # Check Referrer balance & referrals_count
        async with self.db.execute("SELECT balance, referrals_count FROM Users WHERE user_id = ?", (referrer_id,)) as cur:
            row = await cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], REFERRAL_REWARD_REFERRER)
            self.assertEqual(row[1], 1)

        # Check Referee balance
        async with self.db.execute("SELECT balance FROM Users WHERE user_id = ?", (referee_id,)) as cur:
            row = await cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], REFERRAL_REWARD_REFEREE)

        # Check UserTransactions for both parties
        async with self.db.execute("SELECT user_id, amount, category FROM UserTransactions ORDER BY id ASC") as cur:
            txs = await cur.fetchall()
            self.assertEqual(len(txs), 2)
            self.assertEqual(txs[0][0], referrer_id)
            self.assertEqual(txs[0][1], REFERRAL_REWARD_REFERRER)
            self.assertEqual(txs[0][2], "referral")

            self.assertEqual(txs[1][0], referee_id)
            self.assertEqual(txs[1][1], REFERRAL_REWARD_REFEREE)
            self.assertEqual(txs[1][2], "referral_welcome")

        # Check Referrals table persistence
        async with self.db.execute("SELECT referrer_id, referred_id, reward_amount, status FROM Referrals") as cur:
            ref_row = await cur.fetchone()
            self.assertIsNotNone(ref_row)
            self.assertEqual(ref_row[0], referrer_id)
            self.assertEqual(ref_row[1], referee_id)
            self.assertEqual(ref_row[2], REFERRAL_REWARD_REFERRER)
            self.assertEqual(ref_row[3], "active")

        # Check PM notification sent to referrer
        bot.send_message.assert_called_once()
        sent_to, sent_text = bot.send_message.call_args[0][:2]
        self.assertEqual(sent_to, referrer_id)
        self.assertIn("НОВЫЙ РЕФЕРАЛ В ТГАЧ", sent_text)
        self.assertIn(f"+{REFERRAL_REWARD_REFERRER:,.2f} ₪", sent_text)

        # ZERO RAW USER ID LEAKAGE in PM notification
        self.assertNotIn(str(referee_id), sent_text)
        self.assertIn("Анон [", sent_text)

    # =========================================================================
    # 4. Mobile UX - One-Tap Copy Monospace Formatting
    # =========================================================================

    def test_format_referral_dashboard_mobile_ux_isolated_code_blocks(self):
        user_id = 777888999
        ref_code = "Sholter5"
        stats = {"referrals_count": 3, "total_earned": 66960.0}
        bot_username = "dvach_chatbot"

        text, kb = format_referral_dashboard_message(
            user_id=user_id,
            bot_username=bot_username,
            ref_code=ref_code,
            stats=stats,
            board_id="b",
            stream="ru"
        )

        expected_link = f"https://t.me/{bot_username}?start=ref_{ref_code}"
        expected_isolated_code = f"<code>{expected_link}</code>"

        # 1. Referral link MUST be enclosed in its own standalone <code>...</code> tag
        self.assertIn(expected_isolated_code, text)

        # 2. Ref code MUST be enclosed in its own standalone <code>...</code> tag
        self.assertIn(f"<code>ref_{ref_code}</code>", text)

        # 3. Statistics correctly formatted
        self.assertIn("3", text)
        self.assertIn("66,960 ₪", text)

        # 4. Keyboard contains native 1-tap share button
        found_share = False
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.url and "t.me/share/url" in btn.url:
                    found_share = True
                    self.assertIn(expected_link, urllib.parse.unquote(btn.url))
        self.assertTrue(found_share, "Keyboard missing 1-tap share button with t.me/share/url")

        # 5. ZERO raw user_id leakage in dashboard message
        self.assertNotIn(str(user_id), text)

    def test_format_referral_dashboard_multilingual(self):
        user_id = 777888999
        ref_code = "Sholter5"
        stats = {"referrals_count": 1, "total_earned": 22320.0}
        bot_username = "dvach_chatbot"

        # EN
        text_en, kb_en = format_referral_dashboard_message(
            user_id=user_id, bot_username=bot_username, ref_code=ref_code,
            stats=stats, board_id="int", stream="en"
        )
        self.assertIn("TGACH REFERRAL SYSTEM", text_en)
        self.assertIn("Your Invite Link (tap to copy):", text_en)
        self.assertIn(f"<code>https://t.me/{bot_username}?start=ref_{ref_code}</code>", text_en)

        # JP
        text_jp, kb_jp = format_referral_dashboard_message(
            user_id=user_id, bot_username=bot_username, ref_code=ref_code,
            stats=stats, board_id="b", stream="jp"
        )
        self.assertIn("紹介（リファラル）システム", text_jp)
        self.assertIn(f"<code>https://t.me/{bot_username}?start=ref_{ref_code}</code>", text_jp)

    # =========================================================================
    # 5. Full Start & Command Flow Integration
    # =========================================================================

    async def test_process_start_referral_flow(self):
        referrer_id = 333444555
        referee_id = 666777888
        bot = AsyncMock()

        # Register referrer alias
        ref_code = await get_or_create_referral_code(self.db, referrer_id)

        # Simulate /start ref_Sholter5
        handled = await process_start_referral(
            db=self.db,
            bot=bot,
            user_id=referee_id,
            text_payload=f"/start ref_{ref_code}",
            board_id="b",
            stream="ru"
        )
        self.assertTrue(handled)

        # Ensure referrer got credited
        stats = await get_referral_stats(self.db, referrer_id)
        self.assertEqual(stats["referrals_count"], 1)
        self.assertEqual(stats["total_earned"], REFERRAL_REWARD_REFERRER)

    async def test_handle_referral_command_execution(self):
        user_id = 888999111
        message = AsyncMock()
        message.from_user.id = user_id
        message.bot.get_me.return_value = MagicMock(username="dvach_chatbot")

        await handle_referral_command(message, board_id="b", stream="ru")

        message.answer.assert_called_once()
        answered_text = message.answer.call_args[0][0]
        self.assertIn("РЕФЕРАЛЬНАЯ СИСТЕМА ТГАЧА", answered_text)
        self.assertIn("https://t.me/dvach_chatbot?start=ref_", answered_text)
        self.assertNotIn(str(user_id), answered_text)
        message.delete.assert_called_once()


if __name__ == "__main__":
    unittest.main()
