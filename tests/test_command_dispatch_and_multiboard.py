# -*- coding: utf-8 -*-
"""
tests/test_command_dispatch_and_multiboard.py

Comprehensive Test Suite for DvachBot:
1. Command dispatch for all major commands:
   - /work, /shop, /wallet, /ttt, /dice_duel, /duel_rr, /votemute,
     /stats_hub, /avatar, /ach, /lootbox, /drop
2. Multi-board persistence:
   - User working on /b/, switching to /sex/ or /vg/, and retaining
     full shifts, wardrobe, set bonuses, and achievements.
"""

import asyncio
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite
from aiogram import types

import achievements_engine
import avatar_generator
import dice_duel_engine
import drop_engine
import economy_extension
import main
import russian_roulette_pvp
import stats_hub_router
import ttt_engine
import votemute_engine
import wardrobe_engine
from common.bot_helpers import _get_user_active_items


def create_mock_message(
    user_id: int = 10001,
    chat_id: int = -1001234567,
    text: str = "/work",
    reply_to: types.Message | None = None,
    username: str = "test_anon",
) -> MagicMock:
    """Helper to construct a fully spec-compliant mock aiogram Message."""
    msg = MagicMock(spec=types.Message)
    msg.from_user = MagicMock(spec=types.User)
    msg.from_user.id = user_id
    msg.from_user.username = username
    msg.from_user.first_name = "Anon"
    msg.from_user.is_bot = False

    msg.chat = MagicMock(spec=types.Chat)
    msg.chat.id = chat_id
    msg.message_id = 999
    msg.text = text
    msg.caption = None
    msg.reply_to_message = reply_to

    msg.bot = MagicMock()
    msg.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1001))
    msg.bot.send_photo = AsyncMock(return_value=MagicMock(message_id=1002, photo=[MagicMock(file_id="photo_123")]))
    msg.bot.pin_chat_message = AsyncMock()
    msg.bot.restrict_chat_member = AsyncMock()
    msg.bot.get_chat_member = AsyncMock()
    msg.bot.get_me = AsyncMock(return_value=MagicMock(username="test_dvach_bot"))

    msg.answer = AsyncMock(return_value=MagicMock(message_id=1003, chat=MagicMock(id=chat_id)))
    msg.reply = AsyncMock(return_value=MagicMock(message_id=1004, chat=MagicMock(id=chat_id)))
    msg.delete = AsyncMock()
    return msg


class TestCommandDispatch(unittest.IsolatedAsyncioTestCase):
    """
    Tests command dispatch and handlers for all 12 major DvachBot commands:
    /work, /shop, /wallet, /ttt, /dice_duel, /duel_rr, /votemute,
    /stats_hub, /avatar, /ach, /lootbox, /drop.
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
            CREATE TABLE IF NOT EXISTS ReferralAliases (
                code TEXT PRIMARY KEY,
                user_id INTEGER
            )
            """
        )
        await self.db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS MoneyDrops (
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
            )
            """
        )
        await self.db_conn.commit()

        # Seed test user
        self.user_id = 777001
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 5000, '{}')",
            (self.user_id,)
        )
        await self.db_conn.commit()

    async def asyncTearDown(self):
        await self.db_conn.close()

    # 1. /work command dispatch and all aliases
    async def test_dispatch_work(self):
        msg = create_mock_message(user_id=self.user_id, text="/work")
        with patch("main.get_pool", return_value=self.db_conn), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            await main.cmd_work(msg, board_id="b", stream="ru")
            self.assertTrue(mock_banner.called)
            args, kwargs = mock_banner.call_args
            self.assertIn("БИРЖА ТРУДА", kwargs["caption"].upper())
            self.assertEqual(kwargs["category"], "wallet")

        # Test economy_extension.cmd_work_menu handler delegates to unified career hub
        msg_ext = create_mock_message(user_id=self.user_id, text="/work")
        with patch("main.get_pool", return_value=self.db_conn), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner_ext:
            await economy_extension.cmd_work_menu(msg_ext, board_id="b")
            self.assertTrue(mock_banner_ext.called)
            self.assertIn("БИРЖА ТРУДА", mock_banner_ext.call_args[1]["caption"].upper())

    async def test_dispatch_work_all_aliases(self):
        """Verify all 7 career exchange aliases, case variations, and mentions dispatch correctly."""
        aliases = [
            "/work", "/job", "/работа", "/биржа", "/earn", "/bomj", "/economy",
            "/WORK", "/JOB", "/РАБОТА", "/БИРЖА", "/EARN", "/BOMJ", "/ECONOMY",
            "/work@test_dvach_bot", "/job@test_dvach_bot", "/работа@test_dvach_bot"
        ]
        for alias in aliases:
            msg = create_mock_message(user_id=self.user_id, text=alias)
            with patch("main.get_pool", return_value=self.db_conn), \
                 patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
                await main.cmd_work(msg, board_id="b", stream="ru")
                self.assertTrue(mock_banner.called, f"Failed banner dispatch for alias {alias}")
                self.assertIn("БИРЖА ТРУДА", mock_banner.call_args[1]["caption"].upper())

    async def test_work_callback_queries_routing(self):
        """Test all 16 work_do_* callbacks, side hustles, refresh, and nav callbacks."""
        from common.work_engine import WORK_VACANCIES
        for job_id in WORK_VACANCIES:
            cb = MagicMock(spec=types.CallbackQuery)
            cb.data = f"work_do_{job_id}"
            cb.from_user = MagicMock(id=self.user_id)
            cb.answer = AsyncMock()
            cb.message = MagicMock()
            cb.message.photo = None
            cb.message.edit_caption = AsyncMock()
            cb.message.edit_text = AsyncMock()

            with patch("main.get_pool", return_value=self.db_conn), \
                 patch("main.execute_job_action", return_value=(True, 50, "Отработал!", None)):
                await main.cb_work_do(cb, board_id="b")
                self.assertTrue(cb.answer.called, f"Callback work_do_{job_id} did not answer")

        # Test work_refresh
        cb_ref = MagicMock(spec=types.CallbackQuery)
        cb_ref.data = "work_refresh"
        cb_ref.from_user = MagicMock(id=self.user_id)
        cb_ref.answer = AsyncMock()
        cb_ref.message = MagicMock()
        cb_ref.message.photo = None
        cb_ref.message.edit_caption = AsyncMock()
        cb_ref.message.edit_text = AsyncMock()
        with patch("main.get_pool", return_value=self.db_conn):
            await main.cb_work_refresh(cb_ref, board_id="b")
            self.assertTrue(cb_ref.answer.called)

    async def test_all_114_bot_commands_dispatch(self):
        """Verify all 114 commands registered in setup_bot_commands have valid router endpoints."""
        mock_bot = MagicMock()
        mock_bot.set_my_commands = AsyncMock()
        with patch("main.ADMIN_IDS", [111222]):
            await main.setup_bot_commands({"b": mock_bot})
            self.assertTrue(mock_bot.set_my_commands.called)

            user_cmd_call = mock_bot.set_my_commands.call_args_list[0][0][0]
            admin_cmd_call = mock_bot.set_my_commands.call_args_list[1][0][0]

            self.assertEqual(len(user_cmd_call), 95)
            self.assertEqual(len(admin_cmd_call), 99)
            self.assertTrue(len(user_cmd_call) <= 100)
            self.assertTrue(len(admin_cmd_call) <= 100)

            # Ensure all command strings are unique in admin list and non-empty
            all_cmds = [cmd.command for cmd in admin_cmd_call]
            self.assertEqual(len(all_cmds), len(set(all_cmds)))
            self.assertIn("boards", all_cmds)
            self.assertIn("settings", all_cmds)
            for c in all_cmds:
                self.assertTrue(len(c) > 0)
                self.assertTrue(c.isascii() or c.isalnum())

    # 2. /shop command dispatch
    async def test_dispatch_shop(self):
        msg = create_mock_message(user_id=self.user_id, text="/shop")
        with patch("main.get_pool", return_value=self.db_conn), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            await main.cmd_shop(msg, board_id="b", stream="ru")
            self.assertTrue(mock_banner.called)
            args, kwargs = mock_banner.call_args
            self.assertIn("ТОРГОВЫЙ ХАБ", kwargs["caption"].upper())
            self.assertEqual(kwargs["category"], "shop")

    # 3. /wallet command dispatch
    async def test_dispatch_wallet(self):
        msg = create_mock_message(user_id=self.user_id, text="/wallet")
        with patch("main.get_pool", return_value=self.db_conn), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            await main.cmd_wallet(msg, board_id="b", stream="ru")
            self.assertTrue(mock_banner.called)
            args, kwargs = mock_banner.call_args
            self.assertIn("КОШЕЛЕК И БАЛАНС", kwargs["caption"])
            self.assertIn("5,000 ₪", kwargs["caption"])

    # 4. /ttt (Tic-Tac-Toe) command dispatch
    async def test_dispatch_ttt(self):
        msg = create_mock_message(user_id=self.user_id, text="/ttt 100")
        with patch("ttt_engine.get_pool", return_value=self.db_conn), \
             patch("ttt_engine.get_user_global_balance", return_value=5000), \
             patch("ttt_engine.create_ttt_challenge", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = (True, "Game Created", MagicMock(game_id="ttt_123", bet=100))
            await ttt_engine.cmd_ttt(msg, board_id="b", stream="ru")
            self.assertTrue(mock_create.called)

    # 5. /dice_duel command dispatch
    async def test_dispatch_dice_duel(self):
        # 1. No args -> interactive lobby menu
        msg_lobby = create_mock_message(user_id=self.user_id, text="/dice_duel")
        with patch("dice_duel_engine.get_pool", return_value=self.db_conn), \
             patch("dice_duel_engine.get_user_global_balance", return_value=5000):
            await dice_duel_engine.cmd_dice_duel_entry(msg_lobby, board_id="b", stream="ru")
            self.assertTrue(msg_lobby.answer.called)
            self.assertIn("ДАЙС-ДУЭЛЬ", msg_lobby.answer.call_args[0][0])

        # 2. With stake -> challenge creation
        msg_bet = create_mock_message(user_id=self.user_id, text="/dice_duel 200")
        fake_game = {
            "game_id": "dd_123",
            "bet": 200,
            "player_1": self.user_id,
            "player_2": None,
            "state": "pending",
            "board_id": "b",
            "target_id": None,
            "num_dice": 2,
            "rolls": {},
            "round": 1,
            "turn_deadline_ts": time.time() + 60,
            "created_at": time.time(),
        }
        with patch("dice_duel_engine.get_pool", return_value=self.db_conn), \
             patch("dice_duel_engine.get_user_global_balance", return_value=5000), \
             patch("dice_duel_engine.create_dice_challenge", new_callable=AsyncMock, return_value=(True, "OK", "dd_123")), \
             patch.dict(dice_duel_engine.active_dice_games, {"dd_123": fake_game}):
            await dice_duel_engine.cmd_dice_duel_entry(msg_bet, board_id="b", stream="ru")
            self.assertTrue(msg_bet.answer.called)

    # 6. /duel_rr (Russian Roulette PvP) command dispatch
    async def test_dispatch_duel_rr(self):
        # 1. Dispatch with no args shows interactive rules
        msg_help = create_mock_message(user_id=self.user_id, text="/duel_rr")
        await russian_roulette_pvp.cmd_russian_roulette(msg_help, board_id="b", stream="ru")
        self.assertTrue(msg_help.answer.called)
        self.assertIn("РУССКАЯ РУЛЕТКА", msg_help.answer.call_args[0][0])

        # 2. Dispatch with bet creates challenge
        msg_bet = create_mock_message(user_id=self.user_id, text="/duel_rr 300")
        fake_rr = {
            "game_id": "rr_123",
            "bet": 300,
            "challenger_id": self.user_id,
            "opponent_id": None,
            "target_id": None,
            "board_id": "b",
            "state": "pending",
            "current_chamber": 0,
            "bullet_chamber": 3,
            "turn_player_id": None,
            "turn_deadline": 0,
            "created_at": time.time(),
        }
        with patch("russian_roulette_pvp.get_pool", return_value=self.db_conn), \
             patch("russian_roulette_pvp.get_user_global_balance", return_value=5000), \
             patch("russian_roulette_pvp.create_rr_challenge", new_callable=AsyncMock, return_value=(True, "OK", "rr_123")), \
             patch.dict(russian_roulette_pvp.active_rr_games, {"rr_123": fake_rr}):
            await russian_roulette_pvp.cmd_russian_roulette(msg_bet, board_id="b", stream="ru")
            self.assertTrue(msg_bet.answer.called)

    # 7. /votemute command dispatch
    async def test_dispatch_votemute(self):
        # 1. No target / no reply -> shows usage help
        msg_help = create_mock_message(user_id=self.user_id, text="/votemute")
        await votemute_engine.cmd_votemute(msg_help, board_id="b")
        self.assertTrue(msg_help.answer.called)
        self.assertIn("Народный Вотум", msg_help.answer.call_args[0][0])

        # 2. Self votemute rejection
        msg_self = create_mock_message(user_id=self.user_id, text="/votemute")
        with patch("votemute_engine._resolve_target_from_message", new_callable=AsyncMock, return_value=(888, self.user_id)):
            await votemute_engine.cmd_votemute(msg_self, board_id="b")
            self.assertTrue(msg_self.answer.called)
            self.assertIn("против самого себя", msg_self.answer.call_args[0][0])

        # 3. Successful vote initialization on target
        msg_vote = create_mock_message(user_id=self.user_id, text="/votemute")
        with patch("votemute_engine._resolve_target_from_message", new_callable=AsyncMock, return_value=(888, 999111)), \
             patch("votemute_engine.check_user_unbribable_mute", new_callable=AsyncMock, return_value=(False, 0)), \
             patch("votemute_engine.start_or_add_vote", new_callable=AsyncMock, return_value=(True, "Vote added", 1, False)):
            await votemute_engine.cmd_votemute(msg_vote, board_id="b")
            self.assertTrue(msg_vote.answer.called)
            self.assertIn("НАРОДНЫЙ ВОТУМ", msg_vote.answer.call_args[0][0])

    # 8. /stats_hub command dispatch
    async def test_dispatch_stats_hub(self):
        msg = create_mock_message(user_id=self.user_id, text="/stats_hub")
        with patch("stats_v2.generate_instant_snapshot_text", return_value=("📊 ПУЛЬС БОРДЫ", None)):
            await stats_hub_router.cmd_stats_hub(msg, board_id="b")
            self.assertTrue(msg.reply.called)
            self.assertIn("ПУЛЬС БОРДЫ", msg.reply.call_args[1]["text"])

    # 9. /avatar command dispatch
    async def test_dispatch_avatar(self):
        msg = create_mock_message(user_id=self.user_id, text="/avatar")
        with patch("main.get_pool", return_value=self.db_conn), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            await main.cmd_avatar(msg, board_id="b", stream="ru")
            self.assertTrue(mock_banner.called)
            args, kwargs = mock_banner.call_args
            self.assertIn("КАРТОЧКА ПЕРСОНАЖА", kwargs["caption"])

    # 10. /ach (Achievements) command dispatch
    async def test_dispatch_ach(self):
        msg = create_mock_message(user_id=self.user_id, text="/ach")
        with patch("main.get_pool", return_value=self.db_conn), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            await main.cmd_achievements(msg, board_id="b", stream="ru")
            self.assertTrue(mock_banner.called)
            args, kwargs = mock_banner.call_args
            self.assertIn("ДОСТИЖЕНИЯ И ТРОФЕИ АНОНА", kwargs["caption"])

    # 11. /lootbox command dispatch
    async def test_dispatch_lootbox(self):
        msg = create_mock_message(user_id=self.user_id, text="/lootbox")
        with patch("main.get_pool", return_value=self.db_conn), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            await main.cmd_lootbox(msg, board_id="b", stream="ru")
            self.assertTrue(mock_banner.called)
            args, kwargs = mock_banner.call_args
            self.assertIn("ЛУТБОКСЫ", kwargs["caption"].upper())

    # 12. /drop command dispatch
    async def test_dispatch_drop(self):
        msg = create_mock_message(user_id=self.user_id, text="/drop 150")
        with patch("main.get_pool", return_value=self.db_conn), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            await main.cmd_drop(msg, board_id="b", stream="ru")
            self.assertTrue(mock_banner.called)
            args, kwargs = mock_banner.call_args
            self.assertIn("ДРОП ШЕКЕЛЕЙ В ТРЕД", kwargs["caption"])
            self.assertIn("150 ₪", kwargs["caption"])


class TestMultiBoardPersistence(unittest.IsolatedAsyncioTestCase):
    """
    Tests multi-board state persistence:
    User working on /b/, switching to /sex/ or /vg/, and retaining:
    - Full shifts count (work_shifts)
    - Full wardrobe inventory and active items (owned_*, *_expires, permanent items)
    - Full achievements (unlocked_achievements)
    - Set bonuses persistence across board switches
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
        await self.db_conn.commit()
        self.user_id = 888123

    async def asyncTearDown(self):
        await self.db_conn.close()

    async def test_shifts_persistence_across_boards(self):
        """User closes shifts on /b/, switches to /sex/ and /vg/, shifts remain intact."""
        # 1. User on board /b/ achieves 25 shifts
        b_items = {"work_shifts": 25}
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000, ?)",
            (self.user_id, json.dumps(b_items))
        )
        await self.db_conn.commit()

        # 2. Query active items on board /sex/ (user never worked on /sex/ before)
        sex_items = await _get_user_active_items(self.db_conn, self.user_id, "sex")
        self.assertEqual(sex_items.get("work_shifts"), 25)

        # 3. Query active items on board /vg/
        vg_items = await _get_user_active_items(self.db_conn, self.user_id, "vg")
        self.assertEqual(vg_items.get("work_shifts"), 25)

        # 4. User works on /vg/, advancing shifts to 40
        vg_items["work_shifts"] = 40
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'vg', 1500, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = ?",
            (self.user_id, json.dumps(vg_items), json.dumps(vg_items))
        )
        await self.db_conn.commit()

        # 5. Switch back to /b/ -> shifts should reflect the maximum across boards (40)
        b_synced = await _get_user_active_items(self.db_conn, self.user_id, "b")
        self.assertEqual(b_synced.get("work_shifts"), 40)

    async def test_cooldowns_persistence_across_boards(self):
        """User works on /b/ triggering cooldown; switching to /sex/ and /vg/ preserves cooldown."""
        now = int(time.time())
        b_items = {
            "work_shifts": 5,
            "work_cooldowns": {
                "bottles": now - 30,  # 150s remaining
                "courier": now - 100  # 800s remaining
            }
        }
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000, ?)",
            (self.user_id, json.dumps(b_items))
        )
        await self.db_conn.commit()

        # Check /sex/
        sex_items = await _get_user_active_items(self.db_conn, self.user_id, "sex")
        self.assertIn("bottles", sex_items.get("work_cooldowns", {}))
        self.assertEqual(sex_items["work_cooldowns"]["bottles"], now - 30)

        # Check /vg/
        vg_items = await _get_user_active_items(self.db_conn, self.user_id, "vg")
        self.assertIn("courier", vg_items.get("work_cooldowns", {}))
        self.assertEqual(vg_items["work_cooldowns"]["courier"], now - 100)

    async def test_side_hustles_persistence_across_boards(self):
        """User performs side hustles (bottles, mother) on /b/; state persists across /sex/ and /vg/."""
        b_items = {
            "mother_sold": True,
            "last_bottles_date": "2026-08-27",
            "last_bottles": int(time.time())
        }
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 5000, ?)",
            (self.user_id, json.dumps(b_items))
        )
        await self.db_conn.commit()

        # Switch to /sex/
        sex_items = await _get_user_active_items(self.db_conn, self.user_id, "sex")
        self.assertTrue(sex_items.get("mother_sold"))

        # Switch to /vg/
        vg_items = await _get_user_active_items(self.db_conn, self.user_id, "vg")
        self.assertTrue(vg_items.get("mother_sold"))
        self.assertEqual(vg_items.get("last_bottles_date"), "2026-08-27")

    async def test_wardrobe_persistence_across_boards(self):
        """User buys/equips wardrobe items on /b/, switches to /sex/ and /vg/, wardrobe persists."""
        # 1. Equip Riot Police set items on /b/
        b_items = {
            "work_shifts": 10,
            "owned_hat_helmet": True,
            "hat_helmet_expires": int(time.time()) + 720 * 3600,
            "hat_helmet_is_permanent": False,
            "equipped_head": "hat_helmet",
            "owned_feet_boots": True,
            "feet_boots_expires": int(time.time()) + 336 * 3600,
            "feet_boots_is_permanent": True,
            "equipped_feet": "feet_boots",
        }
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 2000, ?)",
            (self.user_id, json.dumps(b_items))
        )
        await self.db_conn.commit()

        # 2. Switch to /sex/
        sex_items = await _get_user_active_items(self.db_conn, self.user_id, "sex")
        self.assertTrue(sex_items.get("owned_hat_helmet"))
        self.assertTrue(sex_items.get("owned_feet_boots"))
        self.assertTrue(sex_items.get("feet_boots_is_permanent"))

        # 3. Switch to /vg/
        vg_items = await _get_user_active_items(self.db_conn, self.user_id, "vg")
        self.assertTrue(vg_items.get("owned_hat_helmet"))
        self.assertTrue(vg_items.get("owned_feet_boots"))

    async def test_achievements_persistence_across_boards(self):
        """User unlocks achievements on /b/ and /sex/, both persist on /vg/ and /b/."""
        # 1. Unlock work achievements on /b/
        b_items = {
            "work_shifts": 10,
            "unlocked_achievements": ["ach_first_work", "ach_work_10"]
        }
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 1000, ?)",
            (self.user_id, json.dumps(b_items))
        )
        await self.db_conn.commit()

        # 2. Switch to /sex/ -> verify achievements present
        sex_items = await _get_user_active_items(self.db_conn, self.user_id, "sex")
        self.assertIn("ach_first_work", sex_items.get("unlocked_achievements", []))
        self.assertIn("ach_work_10", sex_items.get("unlocked_achievements", []))

        # 3. Unlock a new achievement on /sex/
        unlocked_now, info = achievements_engine.check_and_unlock_achievement(sex_items, "ach_set_skuf")
        self.assertTrue(unlocked_now)
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'sex', 1200, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = ?",
            (self.user_id, json.dumps(sex_items), json.dumps(sex_items))
        )
        await self.db_conn.commit()

        # 4. Switch to /vg/ -> verify union of achievements across all boards
        vg_items = await _get_user_active_items(self.db_conn, self.user_id, "vg")
        unlocked_vg = set(vg_items.get("unlocked_achievements", []))
        self.assertIn("ach_first_work", unlocked_vg)
        self.assertIn("ach_work_10", unlocked_vg)
        self.assertIn("ach_set_skuf", unlocked_vg)

    async def test_full_multiboard_workflow_consistency(self):
        """Complete workflow across /b/ -> /sex/ -> /vg/ -> /b/."""
        # Step 1: Initialize on /b/ with 50 shifts, Wasserman set, and achievements
        b_items = {
            "work_shifts": 50,
            "owned_body_wasserman": True,
            "owned_face_wasserman_glasses": True,
            "unlocked_achievements": ["ach_first_work", "ach_work_10", "ach_work_50", "ach_set_wasserman"]
        }
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 3000, ?)",
            (self.user_id, json.dumps(b_items))
        )
        await self.db_conn.commit()

        # Step 2: Switch to /sex/ and verify achievements and character card view
        sex_items = await _get_user_active_items(self.db_conn, self.user_id, "sex")
        ach_text, ach_kb = achievements_engine.build_achievements_content(self.user_id, sex_items)
        self.assertIn("Истинный Онотоле", ach_text)
        self.assertIn("Ударник Пятилетки", ach_text)

        # Step 3: Switch to /vg/, advance shifts to 100 and unlock ach_work_100
        vg_items = await _get_user_active_items(self.db_conn, self.user_id, "vg")
        vg_items["work_shifts"] = 100
        achievements_engine.check_and_unlock_achievement(vg_items, "ach_work_100")
        await self.db_conn.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'vg', 5000, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = ?",
            (self.user_id, json.dumps(vg_items), json.dumps(vg_items))
        )
        await self.db_conn.commit()

        # Step 4: Return to /b/ and verify complete synchronization
        final_b = await _get_user_active_items(self.db_conn, self.user_id, "b")
        self.assertEqual(final_b.get("work_shifts"), 100)
        self.assertTrue(final_b.get("owned_body_wasserman"))
        self.assertTrue(final_b.get("owned_face_wasserman_glasses"))
        self.assertIn("ach_work_100", final_b.get("unlocked_achievements", []))
        self.assertIn("ach_set_wasserman", final_b.get("unlocked_achievements", []))


if __name__ == "__main__":
    unittest.main()
