# -*- coding: utf-8 -*-
"""
test_russian_roulette_pvp.py — Unit & Integration Tests for PvP Russian Roulette
"""

import sys
import time
import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite
import russian_roulette_pvp as rr
from russian_roulette_pvp import (
    create_rr_challenge,
    accept_rr_challenge,
    decline_or_cancel_rr_challenge,
    pull_rr_trigger,
    surrender_rr_game,
    format_drum_visual,
    get_shot_probability,
    format_rr_game_message,
    format_rr_challenge_message,
    active_rr_games,
    user_active_rr_game,
    rr_watchdog_step,
    MIN_RR_BET,
    MAX_RR_BET,
    RR_CHAMBERS_COUNT,
    RR_MUTE_DURATION_SEC
)


class TestRussianRoulettePvP(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Reset memory state before each test
        active_rr_games.clear()
        user_active_rr_game.clear()

        # In-memory SQLite DB for testing
        self.db = await aiosqlite.connect(":memory:")
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER,
                board_id TEXT,
                balance REAL DEFAULT 0,
                active_items TEXT DEFAULT '{}',
                custom_prefix TEXT,
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
            CREATE TABLE IF NOT EXISTS AbuFund (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_amount REAL DEFAULT 0
            )
            """
        )
        await self.db.execute("INSERT OR IGNORE INTO AbuFund (id, total_amount) VALUES (1, 0)")
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS Mutes (
                user_id INTEGER,
                board_id TEXT,
                mute_type TEXT,
                expires_at REAL,
                PRIMARY KEY(user_id, board_id, mute_type)
            )
            """
        )
        await self.db.commit()

        self.pool_patch = patch("common.db_pool.get_pool", return_value=self.db)
        self.mock_pool = self.pool_patch.start()
        self.pool_patch2 = patch("russian_roulette_pvp.get_pool", return_value=self.db)
        self.mock_pool2 = self.pool_patch2.start()

    async def asyncTearDown(self):
        self.pool_patch.stop()
        self.pool_patch2.stop()
        await self.db.close()

    async def test_drum_math_and_visuals(self):
        """Tests chamber probabilities and visual drum representation."""
        self.assertEqual(get_shot_probability(0), 16.7)
        self.assertEqual(get_shot_probability(1), 20.0)
        self.assertEqual(get_shot_probability(2), 25.0)
        self.assertEqual(get_shot_probability(3), 33.3)
        self.assertEqual(get_shot_probability(4), 50.0)
        self.assertEqual(get_shot_probability(5), 100.0)

        vis_start = format_drum_visual(0)
        self.assertIn("🎯", vis_start)
        self.assertIn("⚪", vis_start)

        vis_mid = format_drum_visual(2)
        self.assertIn("💨", vis_mid)
        self.assertIn("🎯", vis_mid)

        vis_boom = format_drum_visual(3, is_finished=True, outcome="shot")
        self.assertIn("💥", vis_boom)

    async def test_challenge_creation_and_balance_check(self):
        """Tests challenge creation rules and balance validations."""
        p1 = 1001
        # Set p1 balance to 500
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500)", (p1,))
        await self.db.commit()

        # Below minimum bet
        ok, msg, gid = await create_rr_challenge("b", p1, bet=10)
        self.assertFalse(ok)
        self.assertIn("Минимальная ставка", msg)

        # Above maximum bet
        ok, msg, gid = await create_rr_challenge("b", p1, bet=MAX_RR_BET + 1)
        self.assertFalse(ok)
        self.assertIn("Максимальная ставка", msg)

        # Exceeds user balance
        ok, msg, gid = await create_rr_challenge("b", p1, bet=1000)
        self.assertFalse(ok)
        self.assertIn("Недостаточно шекелей", msg)

        # Valid challenge
        ok, msg, gid = await create_rr_challenge("b", p1, bet=200)
        self.assertTrue(ok)
        self.assertIsNotNone(gid)
        self.assertIn(p1, user_active_rr_game)

        # Cannot create another game while one is active
        ok2, msg2, _ = await create_rr_challenge("b", p1, bet=200)
        self.assertFalse(ok2)
        self.assertIn("У тебя уже есть активная дуэль", msg2)

    async def test_challenge_acceptance_and_escrow(self):
        """Tests accepting challenge, balance escrow deduction, and starting game."""
        p1 = 1001
        p2 = 1002
        bet = 300

        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000)", (p1,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000)", (p2,))
        await self.db.commit()

        ok, _, gid = await create_rr_challenge("b", p1, bet=bet)
        self.assertTrue(ok)

        # Self-play prevention
        ok_self, msg_self, _ = await accept_rr_challenge(gid, p1)
        self.assertFalse(ok_self)
        self.assertIn("с самим собой", msg_self)

        # Successful accept
        ok_acc, msg_acc, game = await accept_rr_challenge(gid, p2)
        self.assertTrue(ok_acc)
        self.assertEqual(game["state"], "playing")
        self.assertEqual(game["acceptor_id"], p2)
        self.assertIn(game["turn"], (p1, p2))
        self.assertEqual(game["current_chamber"], 0)

        # Check balances deducted by bet
        async with self.db.execute("SELECT balance FROM Users WHERE user_id=?", (p1,)) as c:
            bal1 = (await c.fetchone())[0]
        async with self.db.execute("SELECT balance FROM Users WHERE user_id=?", (p2,)) as c:
            bal2 = (await c.fetchone())[0]

        self.assertEqual(bal1, 700)
        self.assertEqual(bal2, 700)

    async def test_trigger_pull_survive_and_shot(self):
        """Tests survivor click and death shot on live round."""
        p1 = 2001
        p2 = 2002
        bet = 100

        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000)", (p1,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000)", (p2,))
        await self.db.commit()

        ok, _, gid = await create_rr_challenge("b", p1, bet=bet)
        ok_acc, _, game = await accept_rr_challenge(gid, p2)
        self.assertTrue(ok_acc)

        # Force bullet chamber to 1 (chamber index 1 is bullet, chamber 0 is empty)
        game["bullet_chamber"] = 1
        turn1 = game["turn"]
        waiting_player = p2 if turn1 == p1 else p1

        # Attempt to shoot out of turn
        ok_wrong, msg_wrong, _ = await pull_rr_trigger(gid, waiting_player)
        self.assertFalse(ok_wrong)
        self.assertIn("не твой ход", msg_wrong)

        # 1st shot: Chamber 0 is EMPTY -> Click!
        ok_shot1, msg_shot1, g_after1 = await pull_rr_trigger(gid, turn1)
        self.assertTrue(ok_shot1)
        self.assertIn("ЩЁЛК", msg_shot1)
        self.assertEqual(g_after1["current_chamber"], 1)
        self.assertEqual(g_after1["turn"], waiting_player)
        self.assertFalse(g_after1["finished"])

        # 2nd shot: Chamber 1 is BULLET -> BOOM!
        ok_shot2, _, g_after2 = await pull_rr_trigger(gid, waiting_player)
        self.assertTrue(ok_shot2)
        self.assertTrue(g_after2["finished"])
        self.assertEqual(g_after2["outcome"], "shot")
        self.assertEqual(g_after2["loser_id"], waiting_player)
        self.assertEqual(g_after2["winner_id"], turn1)

        # Check winner payout (pot = 200, 5% rake = 10, payout = 190, +200 ach_duel_win reward = 1290)
        async with self.db.execute("SELECT balance FROM Users WHERE user_id=?", (turn1,)) as c:
            win_bal = (await c.fetchone())[0]
        self.assertIn(win_bal, (1090.0, 1290.0))

        # Check loser mute in Mutes table (30 minutes = 1800s)
        async with self.db.execute("SELECT expires_at FROM Mutes WHERE user_id=? AND mute_type='mute'", (waiting_player,)) as c:
            mute_row = await c.fetchone()
            self.assertIsNotNone(mute_row)
            self.assertGreater(mute_row[0], time.time() + 1700)

    async def test_voluntary_surrender(self):
        """Tests voluntary surrender."""
        p1 = 3001
        p2 = 3002
        bet = 100

        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500)", (p1,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500)", (p2,))
        await self.db.commit()

        ok, _, gid = await create_rr_challenge("b", p1, bet=bet)
        await accept_rr_challenge(gid, p2)

        # P2 surrenders
        ok_sur, _, game = await surrender_rr_game(gid, p2)
        self.assertTrue(ok_sur)
        self.assertTrue(game["finished"])
        self.assertEqual(game["outcome"], "surrender")
        self.assertEqual(game["loser_id"], p2)
        self.assertEqual(game["winner_id"], p1)

        # P2 is muted in DB
        async with self.db.execute("SELECT expires_at FROM Mutes WHERE user_id=?", (p2,)) as c:
            mute_row = await c.fetchone()
            self.assertIsNotNone(mute_row)
            self.assertGreater(mute_row[0], time.time() + 1700)

    async def test_turn_timeout_watchdog(self):
        """Tests auto-timeout when player does not pull the trigger within 60s."""
        p1 = 4001
        p2 = 4002
        bet = 100

        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500)", (p1,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500)", (p2,))
        await self.db.commit()

        ok, _, gid = await create_rr_challenge("b", p1, bet=bet)
        ok_acc, _, game = await accept_rr_challenge(gid, p2)
        self.assertTrue(ok_acc)

        # Fast forward time past deadline
        game["turn_deadline_ts"] = time.time() - 5.0
        turn_player = game["turn"]
        other_player = p2 if turn_player == p1 else p1

        # Run watchdog step
        await rr_watchdog_step()

        self.assertTrue(game["finished"])
        self.assertEqual(game["outcome"], "timeout")
        self.assertEqual(game["loser_id"], turn_player)
        self.assertEqual(game["winner_id"], other_player)

        # Loser received 30m mute in DB
        async with self.db.execute("SELECT expires_at FROM Mutes WHERE user_id=?", (turn_player,)) as c:
            mute_row = await c.fetchone()
            self.assertIsNotNone(mute_row)
            self.assertGreater(mute_row[0], time.time() + 1700)


if __name__ == "__main__":
    unittest.main()
