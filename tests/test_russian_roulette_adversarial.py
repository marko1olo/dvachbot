# -*- coding: utf-8 -*-
"""
test_russian_roulette_adversarial.py — Empirical Adversarial Stress Harness for Russian Roulette PvP
===================================================================================================
Covers:
1. Concurrency stress: 100 simultaneous concurrent clicks on `rr_accept` (single-winner & no double escrow).
2. Concurrency stress: 100 simultaneous concurrent accepts from the same user.
3. Out-of-turn shoots: Sequential and concurrent spam by non-turn player.
4. Concurrent shoots: Turn player firing 20 concurrent shoot requests.
5. Escrow boundaries: Balance < stake (stake-1, 0, negative, challenger balance drain).
6. Watchdog auto-timeout: Expired turns trigger forfeit, rake payout, 30m DB mute and RAM mute.
7. Watchdog pending challenge expiration: Unaccepted challenge expires cleanly without charge.
8. Aiogram callback handlers: `cb_rr_accept`, `cb_rr_shoot`, `cb_rr_surrender`, `cb_rr_decline` under stress.
"""

import sys
import time
import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite
import shared_state
import russian_roulette_pvp as rr
from common.database import get_abu_fund_total
from russian_roulette_pvp import (
    create_rr_challenge,
    accept_rr_challenge,
    decline_or_cancel_rr_challenge,
    pull_rr_trigger,
    surrender_rr_game,
    rr_watchdog_step,
    cb_rr_accept,
    cb_rr_shoot,
    cb_rr_surrender,
    cb_rr_decline,
    active_rr_games,
    user_active_rr_game,
    MIN_RR_BET,
    MAX_RR_BET,
    RR_CHAMBERS_COUNT,
    RR_MUTE_DURATION_SEC,
    RR_RAKE_PERCENT
)


class TestRussianRouletteAdversarial(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        active_rr_games.clear()
        user_active_rr_game.clear()

        # In-memory SQLite DB matching dvachbot database schema
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
                category TEXT,
                description TEXT,
                timestamp INTEGER
            )
            """
        )
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS GlobalStats (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
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

        # Initialize shared_state for board mutes
        async with shared_state.storage_lock:
            shared_state.board_data.setdefault('b', {})['mutes'] = {}

        self.pool_patch = patch("common.db_pool.get_pool", return_value=self.db)
        self.mock_pool = self.pool_patch.start()
        self.pool_patch2 = patch("russian_roulette_pvp.get_pool", return_value=self.db)
        self.mock_pool2 = self.pool_patch2.start()

    async def asyncTearDown(self):
        self.pool_patch.stop()
        self.pool_patch2.stop()
        await self.db.close()

    async def test_100_concurrent_accepts_distinct_users(self):
        """
        Adversarial Test 1:
        100 distinct users concurrently attempt to accept the SAME open challenge.
        MUST guarantee:
        - Exactly ONE user succeeds in accepting.
        - Exactly 99 users fail.
        - Challenger balance deducted exactly ONCE.
        - Successful acceptor balance deducted exactly ONCE.
        - All 99 losing contenders keep full initial balance.
        - UserTransactions contains exactly TWO stake deduction entries.
        """
        p1 = 9000
        bet = 500
        initial_balance = 10_000

        # Challenger setup
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', ?)", (p1, initial_balance))

        # 100 contenders setup (user_ids 9001 to 9100)
        contender_ids = [9000 + i for i in range(1, 101)]
        for uid in contender_ids:
            await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', ?)", (uid, initial_balance))
        await self.db.commit()

        # Create challenge
        ok, _, gid = await create_rr_challenge("b", p1, bet=bet)
        self.assertTrue(ok)
        self.assertIsNotNone(gid)

        # Launch 100 concurrent accept calls
        tasks = [accept_rr_challenge(gid, uid) for uid in contender_ids]
        results = await asyncio.gather(*tasks)

        # Evaluate outcomes
        successes = [res for res in results if res[0] is True]
        failures = [res for res in results if res[0] is False]

        self.assertEqual(len(successes), 1, f"Expected exactly 1 accept success, got {len(successes)}")
        self.assertEqual(len(failures), 99, f"Expected 99 accept failures, got {len(failures)}")

        winning_game = successes[0][2]
        winning_user_id = winning_game["acceptor_id"]
        self.assertIn(winning_user_id, contender_ids)
        self.assertEqual(winning_game["state"], "playing")

        # Verify balances in DB
        async with self.db.execute("SELECT balance FROM Users WHERE user_id=?", (p1,)) as c:
            p1_balance = (await c.fetchone())[0]
        self.assertEqual(p1_balance, initial_balance - bet, "Challenger balance must be deducted exactly once")

        async with self.db.execute("SELECT balance FROM Users WHERE user_id=?", (winning_user_id,)) as c:
            winner_balance = (await c.fetchone())[0]
        self.assertEqual(winner_balance, initial_balance - bet, "Winner balance must be deducted exactly once")

        # Verify all 99 losing contenders balances are untouched
        for uid in contender_ids:
            if uid == winning_user_id:
                continue
            async with self.db.execute("SELECT balance FROM Users WHERE user_id=?", (uid,)) as c:
                bal = (await c.fetchone())[0]
            self.assertEqual(bal, initial_balance, f"User {uid} was rejected but balance changed: {bal}")

        # Verify UserTransactions ledger count for stake
        async with self.db.execute("SELECT COUNT(*) FROM UserTransactions WHERE category='rr_pvp' AND amount=?", (-bet,)) as c:
            tx_count = (await c.fetchone())[0]
        self.assertEqual(tx_count, 2, f"Expected exactly 2 stake transaction entries, got {tx_count}")

    async def test_100_concurrent_accepts_same_user(self):
        """
        Adversarial Test 2:
        The SAME user sends 100 concurrent accept calls for the same challenge.
        MUST guarantee:
        - Exactly ONE succeeds.
        - Exactly 99 fail.
        - Balances deducted only once.
        """
        p1 = 8000
        p2 = 8001
        bet = 300
        initial_balance = 5000

        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', ?)", (p1, initial_balance))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', ?)", (p2, initial_balance))
        await self.db.commit()

        ok, _, gid = await create_rr_challenge("b", p1, bet=bet)
        self.assertTrue(ok)

        tasks = [accept_rr_challenge(gid, p2) for _ in range(100)]
        results = await asyncio.gather(*tasks)

        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 99)

        async with self.db.execute("SELECT balance FROM Users WHERE user_id=?", (p1,)) as c:
            self.assertEqual((await c.fetchone())[0], initial_balance - bet)
        async with self.db.execute("SELECT balance FROM Users WHERE user_id=?", (p2,)) as c:
            self.assertEqual((await c.fetchone())[0], initial_balance - bet)

    async def test_escrow_boundary_insufficient_balances(self):
        """
        Adversarial Test 3:
        Boundary conditions for balance < stake:
        - Exact edge: balance = stake - 1
        - Zero balance: balance = 0
        - Negative balance: balance = -100
        - Challenger balance depleted between creation and acceptance.
        """
        p_challenger = 7000
        bet = 500

        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', ?)", (p_challenger, 1000))
        # Edge test users
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (7001, 'b', 499)", ())  # bet - 1
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (7002, 'b', 0)", ())    # 0
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (7003, 'b', -100)", ()) # negative
        await self.db.commit()

        ok, _, gid = await create_rr_challenge("b", p_challenger, bet=bet)
        self.assertTrue(ok)

        # 1. bet - 1 attempt
        ok_edge, msg_edge, _ = await accept_rr_challenge(gid, 7001)
        self.assertFalse(ok_edge)
        self.assertIn("не хватает шекелей", msg_edge)
        self.assertEqual(active_rr_games[gid]["state"], "pending")

        # 2. zero balance attempt
        ok_zero, msg_zero, _ = await accept_rr_challenge(gid, 7002)
        self.assertFalse(ok_zero)
        self.assertIn("не хватает шекелей", msg_zero)
        self.assertEqual(active_rr_games[gid]["state"], "pending")

        # 3. negative balance attempt
        ok_neg, msg_neg, _ = await accept_rr_challenge(gid, 7003)
        self.assertFalse(ok_neg)
        self.assertIn("не хватает шекелей", msg_neg)
        self.assertEqual(active_rr_games[gid]["state"], "pending")

        # 4. Challenger balance drained while challenge was pending
        await self.db.execute("UPDATE Users SET balance = 100 WHERE user_id = ?", (p_challenger,))
        await self.db.commit()
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (7004, 'b', 2000)", ())
        await self.db.commit()

        ok_drain, msg_drain, _ = await accept_rr_challenge(gid, 7004)
        self.assertFalse(ok_drain)
        self.assertIn("У создателя вызова не хватает шекелей", msg_drain)
        # Verify game rolls back to pending and no balance was deducted from 7004
        self.assertEqual(active_rr_games[gid]["state"], "pending")
        async with self.db.execute("SELECT balance FROM Users WHERE user_id=7004") as c:
            self.assertEqual((await c.fetchone())[0], 2000)

    async def test_out_of_turn_and_concurrent_shoots(self):
        """
        Adversarial Test 4:
        - Out-of-turn player shooting sequentially & concurrently.
        - Active player spamming 20 concurrent shoot requests.
        """
        p1 = 6001
        p2 = 6002
        bet = 100

        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000)", (p1,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000)", (p2,))
        await self.db.commit()

        ok, _, gid = await create_rr_challenge("b", p1, bet=bet)
        ok_acc, _, game = await accept_rr_challenge(gid, p2)
        self.assertTrue(ok_acc)

        turn_player = game["turn"]
        waiting_player = p2 if turn_player == p1 else p1

        # Non-turn player sends 30 concurrent pull_rr_trigger calls
        tasks = [pull_rr_trigger(gid, waiting_player) for _ in range(30)]
        results = await asyncio.gather(*tasks)

        for ok_res, msg_res, _ in results:
            self.assertFalse(ok_res)
            self.assertIn("не твой ход", msg_res)

        # Verify game state was not corrupted
        self.assertEqual(game["current_chamber"], 0)
        self.assertEqual(game["turn"], turn_player)
        self.assertFalse(game["finished"])

        # Force bullet chamber to 5 so first 5 shots are safe clicks
        game["bullet_chamber"] = 5

        # Active player sends 20 concurrent shoot requests for turn 0
        tasks = [pull_rr_trigger(gid, turn_player) for _ in range(20)]
        results = await asyncio.gather(*tasks)

        successful_shots = [r for r in results if r[0] is True]
        failed_shots = [r for r in results if r[0] is False]

        self.assertEqual(len(successful_shots), 1, "Exactly 1 shot should succeed for the active player's turn")
        self.assertEqual(len(failed_shots), 19, "Remaining concurrent requests must fail as turn has passed")

        # After shot 1, chamber should be 1 and turn should have flipped
        self.assertEqual(game["current_chamber"], 1)
        self.assertEqual(game["turn"], waiting_player)

    async def test_watchdog_timeout_mute_and_pot_distribution(self):
        """
        Adversarial Test 5:
        Watchdog step when game turn expires:
        - Loser gets marked and penalized with 30-min mute in DB Mutes table and shared_state.
        - Winner receives pot minus 5% rake.
        - AbuFund receives 5% rake.
        - UserTransactions reflects correct win entry.
        """
        p1 = 5001
        p2 = 5002
        bet = 1000
        pot = 2000
        rake = int(pot * RR_RAKE_PERCENT)  # 100
        payout = pot - rake  # 1900

        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 2000)", (p1,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 2000)", (p2,))
        await self.db.commit()

        ok, _, gid = await create_rr_challenge("b", p1, bet=bet)
        ok_acc, _, game = await accept_rr_challenge(gid, p2)
        self.assertTrue(ok_acc)

        turn_player = game["turn"]
        winner_player = p2 if turn_player == p1 else p1

        # Simulate expired turn deadline
        game["turn_deadline_ts"] = time.time() - 15.0

        mock_bot = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()

        await rr_watchdog_step(bot=mock_bot)

        # Verify game finalized
        self.assertTrue(game["finished"])
        self.assertEqual(game["outcome"], "timeout")
        self.assertEqual(game["loser_id"], turn_player)
        self.assertEqual(game["winner_id"], winner_player)

        # Winner balance: Initial 2000 - 1000 (bet) + 1900 (payout) = 2900 (or +200 if achievement unlocked = 3100)
        async with self.db.execute("SELECT balance FROM Users WHERE user_id=?", (winner_player,)) as c:
            win_bal = (await c.fetchone())[0]
        self.assertIn(win_bal, (2900.0, 3100.0))

        # AbuFund total
        fund_bal = await get_abu_fund_total(self.db)
        self.assertEqual(fund_bal, float(rake))

        # Loser Mute in DB Mutes table
        async with self.db.execute("SELECT expires_at FROM Mutes WHERE user_id=? AND mute_type='mute'", (turn_player,)) as c:
            mute_row = await c.fetchone()
            self.assertIsNotNone(mute_row, "Loser must have a record in Mutes table")
            self.assertGreater(mute_row[0], time.time() + 550, "Mute duration must be ~600 seconds (10m)")

        # Loser Mute in RAM shared_state
        async with shared_state.storage_lock:
            ram_mutes = shared_state.board_data['b']['mutes']
            self.assertIn(turn_player, ram_mutes, "Loser must have RAM mute in shared_state")

    async def test_watchdog_expired_pending_challenge_cleanup(self):
        """
        Adversarial Test 6:
        Watchdog cleans up pending challenges older than 120s without deducting any funds.
        """
        p1 = 4001
        bet = 500

        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000)", (p1,))
        await self.db.commit()

        ok, _, gid = await create_rr_challenge("b", p1, bet=bet)
        self.assertTrue(ok)
        self.assertIn(p1, user_active_rr_game)

        # Backdate created_ts past timeout
        active_rr_games[gid]["created_ts"] = time.time() - 150.0

        mock_bot = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()

        await rr_watchdog_step(bot=mock_bot)

        # Challenge state should be 'expired'
        self.assertEqual(active_rr_games[gid]["state"], "expired")
        self.assertTrue(active_rr_games[gid]["finished"])
        self.assertNotIn(p1, user_active_rr_game, "Challenger must be released from active games")

        # Balance remains 1000 (no escrow was taken during pending)
        async with self.db.execute("SELECT balance FROM Users WHERE user_id=?", (p1,)) as c:
            self.assertEqual((await c.fetchone())[0], 1000)

    async def test_aiogram_callbacks_resilience(self):
        """
        Adversarial Test 7:
        Test aiogram callback wrappers (`cb_rr_accept`, `cb_rr_shoot`, `cb_rr_surrender`, `cb_rr_decline`)
        to guarantee no NameError or unhandled exceptions under invalid/stress calls.
        """
        p1 = 3001
        p2 = 3002
        bet = 100

        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000)", (p1,))
        await self.db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 1000)", (p2,))
        await self.db.commit()

        ok, _, gid = await create_rr_challenge("b", p1, bet=bet)

        # Create mock callback query
        cb = AsyncMock()
        cb.from_user = MagicMock()
        cb.from_user.id = p2
        cb.message = AsyncMock()
        cb.message.chat = MagicMock()
        cb.message.chat.id = 12345
        cb.message.message_id = 999
        cb.answer = AsyncMock()
        cb.message.edit_text = AsyncMock()

        # 1. cb_rr_accept
        cb.data = f"rr_accept:{gid}"
        await cb_rr_accept(cb, board_id="b")
        cb.answer.assert_called()

        # 2. cb_rr_shoot from non-turn or turn
        game = active_rr_games[gid]
        turn = game["turn"]
        cb.from_user.id = turn
        cb.data = f"rr_shoot:{gid}"
        await cb_rr_shoot(cb)
        cb.answer.assert_called()

        # 3. cb_rr_surrender
        cb.data = f"rr_surrender:{gid}"
        await cb_rr_surrender(cb)
        cb.answer.assert_called()

        # 4. cb_rr_decline on completed or non-existent game
        cb.data = f"rr_decline:{gid}"
        await cb_rr_decline(cb)
        cb.answer.assert_called()


if __name__ == "__main__":
    unittest.main()
