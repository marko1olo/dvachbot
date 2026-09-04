# -*- coding: utf-8 -*-
import unittest
import asyncio
import json
import time
from datetime import datetime, UTC, timedelta
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

class TestLiveCombatHandlers(unittest.IsolatedAsyncioTestCase):
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
                cursed_until INTEGER
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

    def get_mock_message(self, user_id=1000, reply_target_id=2000):
        msg = MagicMock()
        msg.from_user = MagicMock()
        msg.from_user.id = user_id
        msg.chat = MagicMock()
        msg.chat.id = 77777
        msg.reply_to_message = MagicMock()
        msg.reply_to_message.message_id = 9999
        msg.reply_to_message.chat.id = 77777
        msg.answer = AsyncMock()
        msg.reply = AsyncMock()
        msg.bot = MagicMock()
        msg.bot.send_message = AsyncMock(return_value=MagicMock(message_id=8888))
        msg.delete = AsyncMock()
        return msg

    @patch('main.get_author_id_by_reply')
    async def test_cmd_shoot_newbie_immunity(self, mock_get_author):
        attacker = 1001
        target = 2001
        mock_get_author.return_value = target

        # Attacker has mute_gun, target has only 10 posts (< 25)
        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 5000.0, 500, ?, 0)",
                              (attacker, json.dumps({"mute_gun": True})))
        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 500.0, 10, ?, 0)",
                              (target, json.dumps({})))
        await self.db.commit()

        msg = self.get_mock_message(user_id=attacker, reply_target_id=target)
        await main.cmd_shoot(msg, board_id="b")

        # Must reply with newbie immunity
        msg.reply.assert_called_once()
        self.assertIn("ИММУНИТЕТ НОВИЧКА", msg.reply.call_args[0][0])
        # Target not muted
        self.assertNotIn(target, main.board_data["b"]["mutes"])

    @patch('main.get_author_id_by_reply')
    async def test_cmd_shoot_success_progressive_duration(self, mock_get_author):
        attacker = 1002
        target = 2002
        mock_get_author.return_value = target

        # Attacker has mute_gun, target has 100 posts
        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 5000.0, 500, ?, 0)",
                              (attacker, json.dumps({"mute_gun": True})))
        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 500.0, 100, ?, 0)",
                              (target, json.dumps({})))
        await self.db.commit()

        msg = self.get_mock_message(user_id=attacker, reply_target_id=target)
        with patch('combat_moderation_engine.calculate_combat_duration_and_backfire', return_value=(1020, False, 0.0)):
            await main.cmd_shoot(msg, board_id="b")

        # Target muted for 1020s
        self.assertIn(target, main.board_data["b"]["mutes"])
        # Announcement sent with appeal keyboard
        msg.bot.send_message.assert_called()
        announcement_call = [call for call in msg.bot.send_message.call_args_list if call[0][0] == msg.chat.id][0]
        self.assertIn("Длительность мута:", announcement_call[0][1])
        self.assertIsNotNone(announcement_call[1].get("reply_markup"))

    @patch('main.get_author_id_by_reply')
    async def test_cmd_partyvan_newbie_immunity(self, mock_get_author):
        attacker = 1003
        target = 2003
        mock_get_author.return_value = target

        # Attacker has radio, target has 5 posts (< 25)
        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 5000.0, 500, ?, 0)",
                              (attacker, json.dumps({"partyvan_gun": True})))
        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 500.0, 5, ?, 0)",
                              (target, json.dumps({})))
        await self.db.commit()

        msg = self.get_mock_message(user_id=attacker, reply_target_id=target)
        await main.cmd_partyvan(msg, board_id="b")

        msg.reply.assert_called_once()
        self.assertIn("ИММУНИТЕТ НОВИЧКА", msg.reply.call_args[0][0])
        self.assertNotIn(target, main.board_data["b"]["mutes"])

    @patch('main.get_author_id_by_reply')
    async def test_cmd_partyvan_success_progressive_duration(self, mock_get_author):
        attacker = 1004
        target = 2004
        mock_get_author.return_value = target

        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 5000.0, 500, ?, 0)",
                              (attacker, json.dumps({"partyvan_gun": True})))
        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 500.0, 1500, ?, 0)",
                              (target, json.dumps({})))
        await self.db.commit()

        msg = self.get_mock_message(user_id=attacker, reply_target_id=target)
        with patch('combat_moderation_engine.calculate_combat_duration_and_backfire', return_value=(3600, False, 0.0)):
            await main.cmd_partyvan(msg, board_id="b")

        # Target muted
        self.assertIn(target, main.board_data["b"]["mutes"])
        # Announcement sent with appeal keyboard
        msg.bot.send_message.assert_called()
        announcement_call = [call for call in msg.bot.send_message.call_args_list if call[0][0] == msg.chat.id][0]
        self.assertIn("Срок ареста в КПЗ:", announcement_call[0][1])
        self.assertIsNotNone(announcement_call[1].get("reply_markup"))


    @patch('main.get_author_id_by_reply')
    async def test_cmd_partyvan_backfire_false_report(self, mock_get_author):
        attacker = 1005
        target = 2005
        mock_get_author.return_value = target

        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 5000.0, 500, ?, 0)",
                              (attacker, json.dumps({"partyvan_gun": True})))
        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 500.0, 100, ?, 0)",
                              (target, json.dumps({})))
        await self.db.commit()

        msg = self.get_mock_message(user_id=attacker, reply_target_id=target)
        with patch('combat_moderation_engine.calculate_combat_duration_and_backfire', return_value=(0, True, 0.50)):
            await main.cmd_partyvan(msg, board_id="b")

        # Attacker must be muted for 2 hours! Target must NOT be muted!
        self.assertIn(attacker, main.board_data["b"]["mutes"])
        self.assertNotIn(target, main.board_data["b"]["mutes"])
        # Announcement sent
        msg.bot.send_message.assert_called()
        self.assertIn("ОБЛАВА ПО ЛОЖНОМУ ДОНОСУ", msg.bot.send_message.call_args[0][1])

    @patch('main.get_author_id_by_reply')
    async def test_cmd_shoot_and_partyvan_victim_immunity(self, mock_get_author):
        attacker = 1006
        target = 2006
        mock_get_author.return_value = target

        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 5000.0, 500, ?, 0)",
                              (attacker, json.dumps({"mute_gun": True, "partyvan_gun": True})))
        await self.db.execute("INSERT INTO Users VALUES (?, 'b', 500.0, 100, ?, 0)",
                              (target, json.dumps({})))
        await self.db.commit()

        # Set 1h victim immunity
        shared_state.set_partyvan_victim_immunity(target, int(time.time()) + 3600)

        # 1. /shoot must be blocked by victim immunity
        msg_shoot = self.get_mock_message(user_id=attacker, reply_target_id=target)
        await main.cmd_shoot(msg_shoot, board_id="b")
        msg_shoot.reply.assert_called_once()
        self.assertIn("ЖЕРТВА ПОД ЗАЩИТОЙ", msg_shoot.reply.call_args[0][0])
        self.assertNotIn(target, main.board_data["b"]["mutes"])

        # 2. /partyvan must also be blocked by victim immunity
        msg_pv = self.get_mock_message(user_id=attacker, reply_target_id=target)
        await main.cmd_partyvan(msg_pv, board_id="b")
        msg_pv.answer.assert_called_once()
        self.assertIn("Жертва под защитой", msg_pv.answer.call_args[0][0])
        self.assertNotIn(target, main.board_data["b"]["mutes"])


if __name__ == '__main__':
    unittest.main()
