# -*- coding: utf-8 -*-
import unittest
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite

import main
import shared_state
import combat_moderation_engine as cme

class DummyLock:
    async def __aenter__(self):
        pass
    async def __aexit__(self, exc_type, exc, tb):
        pass

class TestExtinguisherAndCombatRebalance(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        cme.reset_combat_moderation_state()
        shared_state.reset_combat_state()

        self.db = await aiosqlite.connect(":memory:")
        await self.db.execute("""
            CREATE TABLE Users (
                user_id INTEGER,
                board_id TEXT,
                balance REAL,
                posts_count INTEGER,
                active_items TEXT,
                cursed_until INTEGER,
                PRIMARY KEY (user_id, board_id)
            )
        """)
        await self.db.execute("""
            CREATE TABLE Mutes (
                user_id INTEGER,
                board_id TEXT,
                mute_type TEXT,
                thread_id TEXT,
                expires_at REAL,
                reason TEXT
            )
        """)
        await self.db.execute("""
            CREATE TABLE Transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                category TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.commit()

        self.patch_pool = patch('main.get_pool', return_value=self.db)
        self.patch_pool.start()

        self.patch_db_lock = patch('main.db_lock', new_callable=lambda: DummyLock())
        self.patch_db_lock.start()

        self.patch_storage_lock = patch('main.storage_lock', new_callable=lambda: DummyLock())
        self.patch_storage_lock.start()

        main.board_data["b"] = {
            'mutes': {},
            'shadow_mutes': {}
        }

    async def asyncTearDown(self):
        self.patch_pool.stop()
        self.patch_db_lock.stop()
        self.patch_storage_lock.stop()
        await self.db.close()

    def get_mock_message(self, user_id=1000, reply_target_id=None):
        msg = MagicMock()
        msg.from_user = MagicMock()
        msg.from_user.id = user_id
        msg.chat = MagicMock()
        msg.chat.id = 77777
        if reply_target_id is not None:
            msg.reply_to_message = MagicMock()
            msg.reply_to_message.message_id = 9999
            msg.reply_to_message.chat.id = 77777
        else:
            msg.reply_to_message = None
        msg.answer = AsyncMock()
        msg.reply = AsyncMock()
        msg.bot = MagicMock()
        msg.bot.send_message = AsyncMock(return_value=MagicMock(message_id=8888))
        msg.delete = AsyncMock()
        return msg

    def get_mock_callback(self, user_id=1000, data="shop_buy_extinguisher_obep"):
        cb = MagicMock()
        cb.from_user = MagicMock()
        cb.from_user.id = user_id
        cb.data = data
        cb.message = MagicMock()
        cb.message.chat = MagicMock()
        cb.message.chat.id = 77777
        cb.message.message_id = 5555
        cb.answer = AsyncMock()
        cb.bot = MagicMock()
        cb.bot.edit_message_text = AsyncMock()
        return cb

    # -------------------------------------------------------------
    # 1. /extinguish SELF-USE
    # -------------------------------------------------------------
    async def test_extinguish_self_no_debuffs_saves_charge(self):
        user_id = 1010
        await self.db.execute(
            "INSERT INTO Users VALUES (?, 'b', 5000.0, 50, ?, 0)",
            (user_id, json.dumps({"extinguisher_obep": True, "extinguisher_obep_charges": 2}))
        )
        await self.db.commit()

        msg = self.get_mock_message(user_id=user_id, reply_target_id=None)
        await main.cmd_extinguish(msg, board_id="b")

        msg.reply.assert_called_once()
        self.assertIn("нет активных дебаффов", msg.reply.call_args[0][0])

        # Charges unchanged
        items = await main._get_user_active_items(self.db, user_id, "b")
        self.assertEqual(items.get("extinguisher_obep_charges"), 2)

    async def test_extinguish_self_with_debuffs_cleans_and_consumes_charge(self):
        user_id = 1011
        now = int(time.time())
        ai = {
            "extinguisher_obep": True,
            "extinguisher_obep_charges": 2,
            "shit_until": now + 3600,
            "foamed_until": now + 300,
            "peppersprayed_until": now + 600,
        }
        await self.db.execute(
            "INSERT INTO Users VALUES (?, 'b', 5000.0, 50, ?, ?)",
            (user_id, json.dumps(ai), now + 3600)
        )
        await self.db.commit()

        shared_state.set_combat_cooldown(user_id, 300)

        msg = self.get_mock_message(user_id=user_id, reply_target_id=None)
        await main.cmd_extinguish(msg, board_id="b")

        msg.reply.assert_called_once()
        self.assertIn("САМООЧИЩЕНИЕ", msg.reply.call_args[0][0])

        # Charges decremented to 1
        items = await main._get_user_active_items(self.db, user_id, "b")
        self.assertEqual(items.get("extinguisher_obep_charges"), 1)
        self.assertNotIn("shit_until", items)
        self.assertNotIn("foamed_until", items)
        self.assertNotIn("peppersprayed_until", items)

        # Combat cooldown cleared
        self.assertEqual(shared_state.get_combat_cooldown_remaining(user_id), 0)

    # -------------------------------------------------------------
    # 2. /extinguish MEDIC / RESCUE ON TARGET
    # -------------------------------------------------------------
    @patch('main.get_author_id_by_reply')
    async def test_extinguish_rescue_target(self, mock_author):
        user_id = 1012
        target_id = 2012
        mock_author.return_value = target_id
        now = int(time.time())

        user_ai = {"extinguisher_obep": True, "extinguisher_obep_charges": 3}
        target_ai = {
            "shit_until": now + 3600,
            "vomit_until": now + 1800,
            "cursed_until": now + 2000,
        }
        await self.db.execute(
            "INSERT INTO Users VALUES (?, 'b', 5000.0, 100, ?, 0)",
            (user_id, json.dumps(user_ai))
        )
        await self.db.execute(
            "INSERT INTO Users VALUES (?, 'b', 1000.0, 50, ?, ?)",
            (target_id, json.dumps(target_ai), now + 2000)
        )
        await self.db.commit()

        msg = self.get_mock_message(user_id=user_id, reply_target_id=target_id)
        await main.cmd_extinguish(msg, board_id="b")

        msg.reply.assert_called_once()
        self.assertIn("СПАСАТЕЛЬНАЯ ОПЕРАЦИЯ ОБЭП", msg.reply.call_args[0][0])

        # Rescuer charges decremented
        u_items = await main._get_user_active_items(self.db, user_id, "b")
        self.assertEqual(u_items.get("extinguisher_obep_charges"), 2)

        # Target debuffs stripped
        t_items = await main._get_user_active_items(self.db, target_id, "b")
        self.assertNotIn("shit_until", t_items)
        self.assertNotIn("vomit_until", t_items)
        self.assertNotIn("cursed_until", t_items)

        # Target cursed_until column cleared in DB
        async with self.db.execute("SELECT cursed_until FROM Users WHERE user_id = ?", (target_id,)) as c:
            row = await c.fetchone()
            self.assertEqual(row[0], 0)

    # -------------------------------------------------------------
    # 3. /extinguish ACTIVE FOAMY DISARM
    # -------------------------------------------------------------
    @patch('main.get_author_id_by_reply')
    async def test_extinguish_offensive_disarm_success(self, mock_author):
        user_id = 1013
        target_id = 2013
        mock_author.return_value = target_id

        user_ai = {"extinguisher_obep": True, "extinguisher_obep_charges": 1}
        target_ai = {
            "mute_gun": True,
            "knife_gun": True,
            "shit_gun": True,
        }
        await self.db.execute(
            "INSERT INTO Users VALUES (?, 'b', 5000.0, 100, ?, 0)",
            (user_id, json.dumps(user_ai))
        )
        await self.db.execute(
            "INSERT INTO Users VALUES (?, 'b', 1000.0, 50, ?, 0)",
            (target_id, json.dumps(target_ai))
        )
        await self.db.commit()

        msg = self.get_mock_message(user_id=user_id, reply_target_id=target_id)
        await main.cmd_extinguish(msg, board_id="b")

        msg.reply.assert_called_once()
        self.assertIn("ОБЭП НАКРЫЛ С ПЕНОЙ", msg.reply.call_args[0][0])
        self.assertIn("выбито оружие: 3 шт.", msg.reply.call_args[0][0])

        # User's last charge consumed -> keys removed
        u_items = await main._get_user_active_items(self.db, user_id, "b")
        self.assertNotIn("extinguisher_obep", u_items)
        self.assertNotIn("extinguisher_obep_charges", u_items)

        # Target disarmed
        t_items = await main._get_user_active_items(self.db, target_id, "b")
        self.assertNotIn("mute_gun", t_items)
        self.assertNotIn("knife_gun", t_items)
        self.assertNotIn("shit_gun", t_items)
        self.assertIn("foamed_until", t_items)
        self.assertIn("disarmed_until", t_items)

        # Target combat cooldown is 300s
        self.assertTrue(shared_state.get_combat_cooldown_remaining(target_id) > 250)

    @patch('main.get_author_id_by_reply')
    async def test_extinguish_offensive_reflect_shield_bounce(self, mock_author):
        user_id = 1014
        target_id = 2014
        mock_author.return_value = target_id
        now = int(time.time())

        user_ai = {
            "extinguisher_obep": True,
            "extinguisher_obep_charges": 2,
            "knife_gun": True,
        }
        target_ai = {
            "reflect_shield_until": now + 3600,
            "shield_until": now + 3600,
            "shield": True,
        }
        await self.db.execute(
            "INSERT INTO Users VALUES (?, 'b', 5000.0, 100, ?, 0)",
            (user_id, json.dumps(user_ai))
        )
        await self.db.execute(
            "INSERT INTO Users VALUES (?, 'b', 1000.0, 50, ?, 0)",
            (target_id, json.dumps(target_ai))
        )
        await self.db.commit()

        msg = self.get_mock_message(user_id=user_id, reply_target_id=target_id)
        await main.cmd_extinguish(msg, board_id="b")

        msg.answer.assert_called_once()
        self.assertIn("ОТРАЖЕНИЕ ЗЕРКАЛА ЗАДНЕГО ВИДА", msg.answer.call_args[0][0])

        # Target shield consumed
        t_items = await main._get_user_active_items(self.db, target_id, "b")
        self.assertEqual(t_items.get("reflect_shield_until"), 0)
        self.assertEqual(t_items.get("shield_until"), 0)
        self.assertFalse(t_items.get("shield"))

        # Attacker foamed and guns disarmed
        u_items = await main._get_user_active_items(self.db, user_id, "b")
        self.assertEqual(u_items.get("extinguisher_obep_charges"), 1)
        self.assertNotIn("knife_gun", u_items)
        self.assertIn("foamed_until", u_items)
        self.assertTrue(shared_state.get_combat_cooldown_remaining(user_id) > 250)

    # -------------------------------------------------------------
    # 4. SHOP PURCHASES
    # -------------------------------------------------------------
    @patch('main._check_menu_owner', return_value=True)
    async def test_shop_buy_extinguisher_and_charges_cap(self, mock_owner):
        user_id = 1015
        await self.db.execute(
            "INSERT INTO Users VALUES (?, 'b', 10000.0, 100, '{}', 0)",
            (user_id,)
        )
        await self.db.commit()

        cb = self.get_mock_callback(user_id=user_id, data="shop_buy_extinguisher_obep")

        # 1st purchase
        await main.cb_shop_buy(cb, board_id="b")
        items = await main._get_user_active_items(self.db, user_id, "b")
        self.assertTrue(items.get("extinguisher_obep"))
        self.assertEqual(items.get("extinguisher_obep_charges"), 1)

        # 2nd purchase
        await main.cb_shop_buy(cb, board_id="b")
        items = await main._get_user_active_items(self.db, user_id, "b")
        self.assertEqual(items.get("extinguisher_obep_charges"), 2)

        # 3rd purchase
        await main.cb_shop_buy(cb, board_id="b")
        items = await main._get_user_active_items(self.db, user_id, "b")
        self.assertEqual(items.get("extinguisher_obep_charges"), 3)

        # 4th purchase -> blocked
        await main.cb_shop_buy(cb, board_id="b")
        cb.answer.assert_called_with("🧯 У тебя уже полный баллон Огнетушителя ОБЭП (максимум 3 заряда)!", show_alert=True)
        items = await main._get_user_active_items(self.db, user_id, "b")
        self.assertEqual(items.get("extinguisher_obep_charges"), 3)

    @patch('main._check_menu_owner', return_value=True)
    async def test_shop_buy_shield_duration_and_cap(self, mock_owner):
        user_id = 1016
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO Users VALUES (?, 'b', 10000.0, 100, '{}', 0)",
            (user_id,)
        )
        await self.db.commit()

        cb = self.get_mock_callback(user_id=user_id, data="shop_buy_shield")

        # 1st purchase: +1 hour (3600s)
        await main.cb_shop_buy(cb, board_id="b")
        items = await main._get_user_active_items(self.db, user_id, "b")
        self.assertTrue(items.get("shield"))
        self.assertTrue(now + 3500 <= items.get("shield_until") <= now + 3600)
        self.assertEqual(items.get("reflect_shield_until"), items.get("shield_until"))

        # Cap verification: 5 purchases must cap at now + 4 * 3600
        for _ in range(5):
            await main.cb_shop_buy(cb, board_id="b")
        items = await main._get_user_active_items(self.db, user_id, "b")
        max_cap = now + 4 * 3600
        self.assertTrue(items.get("shield_until") <= max_cap)
