# -*- coding: utf-8 -*-
"""
tests/test_adversarial_dispatcher_multiboard_races.py

Adversarial Stress Test Suite for DvachBot:
1. 114 Commands Live Routing & Handler Signatures under Aiogram Dispatcher.
2. Multi-board Concurrent State Persistence (shifts, cooldowns, drops, wardrobe, transactions).
3. Side Hustles (work_bottles 24h cooldown, work_sell_mother 1-time limit) Race Conditions & Edge Cases.
"""

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import random
import re
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.types import BotCommand, Chat, Message, User, CallbackQuery

import achievements_engine
import common.bot_helpers as bot_helpers
from common.bot_helpers import _get_user_active_items, merge_user_active_items_rows
from common.database import record_user_transaction, add_user_global_balance, get_user_global_balance, deduct_user_global_balance
from common.db_pool import db_lock, get_pool
import dice_duel_engine
import drop_engine
import economy_extension
import main
import russian_roulette_pvp
import stats_hub_router
import ttt_engine
import votemute_engine
import wardrobe_engine


def create_mock_message(
    user_id: int = 10001,
    chat_id: int = -1001234567,
    text: str = "/work",
    reply_to: types.Message | None = None,
    username: str = "test_anon",
) -> MagicMock:
    """Construct a mock aiogram Message."""
    msg = MagicMock(spec=types.Message)
    msg.from_user = MagicMock(spec=types.User)
    msg.from_user.id = user_id
    msg.from_user.username = username
    msg.from_user.first_name = "Anon"
    msg.from_user.is_bot = False

    msg.chat = MagicMock(spec=types.Chat)
    msg.chat.id = chat_id
    msg.chat.type = "supergroup"
    msg.message_id = 999
    msg.text = text
    msg.caption = None
    msg.reply_to_message = reply_to

    msg.bot = MagicMock(spec=Bot)
    msg.bot.id = 123456789
    msg.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1001))
    msg.bot.send_photo = AsyncMock(return_value=MagicMock(message_id=1002, photo=[MagicMock(file_id="photo_123")]))
    msg.bot.pin_chat_message = AsyncMock()
    msg.bot.restrict_chat_member = AsyncMock()
    msg.bot.get_chat_member = AsyncMock()
    msg.bot.get_me = AsyncMock(return_value=MagicMock(id=123456789, username="test_dvach_bot"))

    msg.answer = AsyncMock(return_value=MagicMock(message_id=1003, chat=MagicMock(id=chat_id)))
    msg.reply = AsyncMock(return_value=MagicMock(message_id=1004, chat=MagicMock(id=chat_id)))
    msg.delete = AsyncMock()
    return msg


def create_mock_callback(
    user_id: int = 10001,
    chat_id: int = -1001234567,
    data: str = "work_bottles",
    is_photo: bool = True
) -> MagicMock:
    """Construct a mock aiogram CallbackQuery."""
    cb = MagicMock(spec=CallbackQuery)
    cb.id = f"cb_{random.randint(100000, 999999)}"
    cb.from_user = MagicMock(spec=types.User)
    cb.from_user.id = user_id
    cb.from_user.username = "test_anon"
    cb.from_user.first_name = "Anon"
    cb.from_user.is_bot = False

    msg = MagicMock(spec=types.Message)
    msg.message_id = 888
    msg.chat = MagicMock(spec=types.Chat)
    msg.chat.id = chat_id
    msg.photo = [MagicMock()] if is_photo else None
    msg.edit_caption = AsyncMock()
    msg.edit_text = AsyncMock()
    cb.message = msg

    cb.data = data
    cb.answer = AsyncMock()
    return cb


class TestAll114CommandsLiveRouting(unittest.IsolatedAsyncioTestCase):
    """
    Verifies that all 114 commands registered in setup_bot_commands match active handlers
    in the Aiogram Dispatcher tree and DO NOT hit the fallback router.
    """

    async def test_all_114_commands_live_resolution(self):
        # 1. Extract commands from setup_bot_commands
        with open(ROOT / "main.py", "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r"async def setup_bot_commands\b.*?(?=\n(?:async )?def |\Z)", content, re.DOTALL)
        self.assertIsNotNone(match, "setup_bot_commands function must exist in main.py")
        commands = re.findall(r'BotCommand\s*\(\s*command\s*=\s*["\']([^"\']+)["\']\s*,\s*description\s*=\s*["\']([^"\']+)["\']', match.group(0))

        self.assertEqual(len(commands), 114, f"Expected 114 commands in setup_bot_commands, found {len(commands)}")

        dp = main.dp
        self.assertIsNotNone(dp, "Dispatcher dp must be initialized")

        # 2. Collect all handlers across router hierarchy
        def get_all_handlers(router):
            all_h = []
            for h in router.message.handlers:
                all_h.append((router, h))
            for sub in router.sub_routers:
                all_h.extend(get_all_handlers(sub))
            return all_h

        handlers = get_all_handlers(dp)
        self.assertGreaterEqual(len(handlers), 114, "Dispatcher should have at least 114 registered message handlers")

        mock_bot = MagicMock(spec=Bot)
        mock_bot.id = 123456789
        mock_bot.get_me = AsyncMock(return_value=User(id=123456789, is_bot=True, first_name="DvachBot", username="dvach_test_bot"))

        user = User(id=123456, is_bot=False, first_name="Anon", username="test_anon")
        chat = Chat(id=-1001234567, type="supergroup", title="Test Board")

        resolved = {}
        unresolved = []

        for cmd, desc in commands:
            msg = Message.model_construct(
                message_id=100,
                date=datetime.now(),
                chat=chat,
                from_user=user,
                text=f"/{cmd}",
            )

            matched_handler = None
            matched_router = None

            for router, handler in handlers:
                # Disallow matching fallback router
                if router == main._fallback_router:
                    continue

                try:
                    res, _ = await handler.check(
                        msg,
                        bot=mock_bot,
                        event_from_user=user,
                        event_chat=chat,
                    )
                    if res:
                        matched_handler = handler
                        matched_router = router
                        break
                except Exception:
                    pass

            if matched_handler:
                func_name = getattr(matched_handler.callback, "__name__", str(matched_handler.callback))
                mod_name = getattr(matched_handler.callback, "__module__", "")
                rname = getattr(matched_router, "name", "root")
                resolved[cmd] = (func_name, mod_name, rname)
            else:
                unresolved.append(cmd)

        self.assertEqual(
            len(unresolved), 0,
            f"The following {len(unresolved)} commands in setup_bot_commands failed to resolve to an active handler: {unresolved}"
        )
        self.assertEqual(len(resolved), 114, "All 114 commands must be successfully resolved.")


class TestMultiboardConcurrentPersistence(unittest.IsolatedAsyncioTestCase):
    """
    Adversarial stress testing of multi-board persistence across /b/, /sex/, /vg/.
    Tests concurrent updates, shifts, cooldowns, drops, wardrobe items, and transactions.
    """

    async def asyncSetUp(self):
        self.db_conn = await aiosqlite.connect(":memory:")
        await self.db_conn.execute(
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
        await self.db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS UserTransactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                category TEXT,
                description TEXT,
                timestamp INTEGER
            )
            """
        )
        await self.db_conn.commit()
        self.user_id = 998877

    async def asyncTearDown(self):
        await self.db_conn.close()

    async def test_concurrent_multiboard_shifts_and_monotonicity(self):
        """Simulate concurrent shift completion on 3 different boards and verify no shift regression."""
        async def work_on_board(board: str, target_shifts: int):
            async with db_lock:
                items = await _get_user_active_items(self.db_conn, self.user_id, board)
                current = items.get("work_shifts", 0)
                items["work_shifts"] = max(current, target_shifts)
                await self.db_conn.execute(
                    "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items",
                    (self.user_id, board, json.dumps(items))
                )
                await self.db_conn.commit()

        # Run concurrent workers advancing shifts:
        # Worker 1: advances b to 20
        # Worker 2: advances sex to 55
        # Worker 3: advances vg to 90
        await asyncio.gather(
            work_on_board("b", 20),
            work_on_board("sex", 55),
            work_on_board("vg", 90),
        )

        # Verify all boards see the maximum shift count (90)
        for b in ["b", "sex", "vg", "po", "a"]:
            state = await _get_user_active_items(self.db_conn, self.user_id, b)
            self.assertEqual(state.get("work_shifts"), 90, f"Board {b} must report 90 shifts")

    async def test_concurrent_multiboard_cooldowns_and_drops(self):
        """Simulate concurrent jobs with distinct cooldowns, item drops, and permanent wardrobe gear."""
        t_now = int(time.time())

        # Board /b/: job courier (cooldown t_now + 300), dropped trash_lootbox
        b_items = {
            "work_shifts": 5,
            "work_cooldowns": {"courier": t_now + 300},
            "owned_trash_lootbox": 2,
            "owned_body_wasserman": True,
            "body_wasserman_is_permanent": True,
        }
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'b', ?)",
            (self.user_id, json.dumps(b_items))
        )

        # Board /sex/: job escort (cooldown t_now + 600), dropped gold_safe
        sex_items = {
            "work_shifts": 8,
            "work_cooldowns": {"escort": t_now + 600},
            "owned_gold_safe": 1,
            "owned_hat_tinfoil": True,
            "hat_tinfoil_is_permanent": True,
        }
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'sex', ?)",
            (self.user_id, json.dumps(sex_items))
        )

        # Board /vg/: job cybersport (cooldown t_now + 900), dropped knife_gun
        vg_items = {
            "work_shifts": 12,
            "work_cooldowns": {"cybersport": t_now + 900},
            "knife_gun": True,
            "unlocked_achievements": ["ach_first_work", "ach_cyber_hero"],
        }
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, 'vg', ?)",
            (self.user_id, json.dumps(vg_items))
        )
        await self.db_conn.commit()

        # Query merged state from /b/
        merged = await _get_user_active_items(self.db_conn, self.user_id, "b")

        # 1. Shifts: max(5, 8, 12) = 12
        self.assertEqual(merged.get("work_shifts"), 12)

        # 2. Cooldowns: all 3 vacancies preserved
        cds = merged.get("work_cooldowns", {})
        self.assertEqual(cds.get("courier"), t_now + 300)
        self.assertEqual(cds.get("escort"), t_now + 600)
        self.assertEqual(cds.get("cybersport"), t_now + 900)

        # 3. Drops & Wardrobe
        self.assertTrue(merged.get("owned_body_wasserman"))
        self.assertTrue(merged.get("owned_hat_tinfoil"))
        self.assertTrue(merged.get("knife_gun"))

        # 4. Achievements
        achs = merged.get("unlocked_achievements", [])
        self.assertIn("ach_first_work", achs)
        self.assertIn("ach_cyber_hero", achs)

    async def test_merge_user_active_items_rows_adversarial_inputs(self):
        """Stress-test merge_user_active_items_rows with corrupt, invalid, and boundary data."""
        # 1. Empty rows
        self.assertEqual(merge_user_active_items_rows([]), {})

        # 2. Corrupt JSON strings and None values
        corrupt_rows = [
            ("b", "INVALID_JSON{"),
            ("sex", None),
            ("vg", ""),
            ("po", "{'invalid_single_quotes': 1}"),
            ("a", json.dumps({"work_shifts": 45, "unlocked_achievements": ["ach_a"]})),
        ]
        res = merge_user_active_items_rows(corrupt_rows, "a")
        self.assertEqual(res.get("work_shifts"), 45)
        self.assertEqual(res.get("unlocked_achievements"), ["ach_a"])

        # 3. Non-numeric or negative values
        fuzzed_rows = [
            ("b", json.dumps({"work_shifts": "invalid", "daily_streak": None, "last_bottles": -500})),
            ("sex", json.dumps({"work_shifts": 77, "mother_sold": True, "work_cooldowns": {"job1": "corrupt"}})),
        ]
        fuzzed_res = merge_user_active_items_rows(fuzzed_rows, "b")
        self.assertEqual(fuzzed_res.get("work_shifts"), 77)
        self.assertTrue(fuzzed_res.get("mother_sold"))


class TestSideHustlesRaceConditions(unittest.IsolatedAsyncioTestCase):
    """
    Adversarial verification of side hustles:
    - work_bottles: strict 24h cooldown under high-concurrency spam.
    - work_sell_mother: strictly 1-time execution limit under high-concurrency spam.
    """

    async def asyncSetUp(self):
        self.db_conn = await aiosqlite.connect(":memory:")
        await self.db_conn.execute(
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
        await self.db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS UserTransactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                category TEXT,
                description TEXT,
                timestamp INTEGER
            )
            """
        )
        await self.db_conn.commit()
        self.user_id = 554433

    async def asyncTearDown(self):
        await self.db_conn.close()

    async def test_work_bottles_concurrency_race_condition(self):
        """Simulate 30 concurrent clicks on work_bottles and verify exactly 1 succeeds."""
        with patch("economy_extension.get_pool", return_value=self.db_conn), \
             patch("main._build_work_card", return_value=("CAPTION", MagicMock())):

            callbacks = [create_mock_callback(user_id=self.user_id, data="work_bottles") for _ in range(30)]

            # Dispatch concurrently
            await asyncio.gather(*[
                economy_extension.cb_work_action(cb, board_id="b") for cb in callbacks
            ])

            # Inspect callback answers
            success_count = 0
            cooldown_count = 0
            for cb in callbacks:
                self.assertTrue(cb.answer.called)
                ans_text = cb.answer.call_args[0][0]
                if "Ты успешно сдал бутылки" in ans_text:
                    success_count += 1
                elif "Пункты приема закрыты" in ans_text:
                    cooldown_count += 1

            self.assertEqual(success_count, 1, f"Expected exactly 1 successful bottle collection, got {success_count}")
            self.assertEqual(cooldown_count, 29, f"Expected 29 rejected cooldown requests, got {cooldown_count}")

            # Verify balance in database
            bal = await get_user_global_balance(self.db_conn, self.user_id)
            self.assertGreaterEqual(bal, 10)
            self.assertLessEqual(bal, 50)

            # Verify transactions
            async with self.db_conn.execute("SELECT COUNT(*) FROM UserTransactions WHERE user_id = ?", (self.user_id,)) as c:
                tx_count = (await c.fetchone())[0]
            self.assertEqual(tx_count, 1, "Exactly 1 transaction should be recorded")

    async def test_work_bottles_24h_boundary_conditions(self):
        """Verify cooldown expiration precision at 24h boundary."""
        now = int(time.time())
        # Set last_bottles to 23 hours 59 minutes ago (86340s)
        items = {"last_bottles": now - 86340}
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 0, ?)",
            (self.user_id, json.dumps(items))
        )
        await self.db_conn.commit()

        with patch("economy_extension.get_pool", return_value=self.db_conn), \
             patch("main._build_work_card", return_value=("CAPTION", MagicMock())):

            # 1. At 23h 59m -> Rejected
            cb1 = create_mock_callback(user_id=self.user_id, data="work_bottles")
            await economy_extension.cb_work_action(cb1, board_id="b")
            self.assertIn("Пункты приема закрыты", cb1.answer.call_args[0][0])

            # 2. Advance time to 24h + 1s (86401s ago)
            items["last_bottles"] = now - 86401
            await self.db_conn.execute(
                "UPDATE Users SET active_items = ? WHERE user_id = ?",
                (json.dumps(items), self.user_id)
            )
            await self.db_conn.commit()

            cb2 = create_mock_callback(user_id=self.user_id, data="work_bottles")
            await economy_extension.cb_work_action(cb2, board_id="b")
            self.assertIn("Ты успешно сдал бутылки", cb2.answer.call_args[0][0])

    async def test_work_sell_mother_concurrency_race_condition(self):
        """Simulate 30 concurrent clicks on work_sell_mother and verify exactly 1 succeeds (8000 shekels)."""
        with patch("economy_extension.get_pool", return_value=self.db_conn), \
             patch("main._build_work_card", return_value=("CAPTION", MagicMock())):

            callbacks = [create_mock_callback(user_id=self.user_id, data="work_sell_mother") for _ in range(30)]

            # Dispatch concurrently
            await asyncio.gather(*[
                economy_extension.cb_work_action(cb, board_id="b") for cb in callbacks
            ])

            success_count = 0
            rejected_count = 0
            for cb in callbacks:
                self.assertTrue(cb.answer.called)
                ans_text = cb.answer.call_args[0][0]
                if "Сделка века! Ты продал мать" in ans_text:
                    success_count += 1
                elif "Ты уже продал мать" in ans_text:
                    rejected_count += 1

            self.assertEqual(success_count, 1, f"Expected exactly 1 mother sale, got {success_count}")
            self.assertEqual(rejected_count, 29, f"Expected 29 rejections, got {rejected_count}")

            # Verify balance is strictly 8000
            bal = await get_user_global_balance(self.db_conn, self.user_id)
            self.assertEqual(bal, 8000, "User balance must increase by exactly 8000 shekels once")

            # Verify cross-board persistence: user switches to /sex/ and attempts selling mother again
            cb_sex = create_mock_callback(user_id=self.user_id, data="work_sell_mother")
            await economy_extension.cb_work_action(cb_sex, board_id="sex")
            self.assertIn("Ты уже продал мать", cb_sex.answer.call_args[0][0])

            # Verify final balance is still strictly 8000
            bal_final = await get_user_global_balance(self.db_conn, self.user_id)
            self.assertEqual(bal_final, 8000)


if __name__ == "__main__":
    unittest.main()
