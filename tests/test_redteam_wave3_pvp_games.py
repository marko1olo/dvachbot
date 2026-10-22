# -*- coding: utf-8 -*-
"""
test_redteam_wave3_pvp_games.py — Sector Redteam Inquisition for PvP, Games, and Duels
======================================================================================
Covers:
1. Cross-game concurrency collision: Dice Duel, Russian Roulette, and Tic-Tac-Toe sessions
   strictly mutually exclude each other for both creators and acceptors.
2. Concurrent challenge acceptance race: Acceptor firing simultaneous accept requests on distinct
   games cannot enter multiple sessions or double-spend escrow.
3. Target session integrity: Cancelling or expiring a targeted challenge NEVER wipes out
   the target's existing active session in any game.
4. Target decline vs stranger security: Only challenger and target can decline/cancel; strangers
   are rejected; targets declining notify challenger cleanly.
5. TTT Anti-inflation Whale Burn Rake (pot > 50,000): 10% rake burned out of circulation without
   crediting Abu Fund, matching Dice and Russian Roulette standards.
6. TTT Normal Rake (pot <= 50,000): 5% rake correctly transferred to Abu Fund with donor_id.
7. TTT Draw Ledger Inversion Fix: Draws refund `+refund` (e.g. +490 ₪), never logging negative fee.
8. NaN and Infinity Bet Rejection: All three engines reject non-finite and malformed float bets.
"""

import math
import time
import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import shared_state
from common.database import get_abu_fund_total, get_user_global_balance

from dice_duel_engine import (
    create_dice_challenge,
    accept_dice_challenge,
    cancel_dice_challenge,
    active_dice_games,
    user_active_dice_game,
)
from russian_roulette_pvp import (
    create_rr_challenge,
    accept_rr_challenge,
    decline_or_cancel_rr_challenge,
    active_rr_games,
    user_active_rr_game,
)
from ttt_engine import (
    create_ttt_challenge,
    accept_ttt_challenge,
    cancel_ttt_challenge,
    finish_ttt_game,
    active_ttt_games,
    user_active_ttt_session,
    TicTacToeGame,
)


class TestRedteamWave3PvPGames(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        active_dice_games.clear()
        user_active_dice_game.clear()
        active_rr_games.clear()
        user_active_rr_game.clear()
        active_ttt_games.clear()
        user_active_ttt_session.clear()

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

        # Patch get_pool across modules
        self.patchers = [
            patch("common.db_pool.get_pool", return_value=self.db),
            patch("dice_duel_engine.get_pool", return_value=self.db),
            patch("russian_roulette_pvp.get_pool", return_value=self.db),
            patch("ttt_engine.get_pool", return_value=self.db),
        ]
        for p in self.patchers:
            p.start()

        # Seed test players
        for uid in (1001, 1002, 1003, 1004, 1005):
            await self.db.execute(
                "INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 500000)",
                (uid,)
            )
        await self.db.commit()

    async def asyncTearDown(self):
        for p in self.patchers:
            p.stop()
        await self.db.close()
        active_dice_games.clear()
        user_active_dice_game.clear()
        active_rr_games.clear()
        user_active_rr_game.clear()
        active_ttt_games.clear()
        user_active_ttt_session.clear()

    # -------------------------------------------------------------------------
    # 1. CROSS-GAME CONCURRENCY COLLISION
    # -------------------------------------------------------------------------

    async def test_cross_game_collision_dice_blocks_rr_and_ttt(self):
        """User busy in Dice Duel cannot create or accept RR or TTT games."""
        u1, u2 = 1001, 1002
        ok, _, d_gid = await create_dice_challenge("b", u1, bet=500)
        self.assertTrue(ok)

        # u1 tries to create RR challenge -> BLOCKED
        ok_rr, msg_rr, _ = await create_rr_challenge("b", u1, bet=500)
        self.assertFalse(ok_rr)
        self.assertIn("активная партия или вызов", msg_rr)
        self.assertIn("дайс-дуэли", msg_rr)

        # u1 tries to create TTT challenge -> BLOCKED
        ok_ttt, msg_ttt, _ = await create_ttt_challenge(None, 1234, "b", u1, bet=500)
        self.assertFalse(ok_ttt)
        self.assertIn("активная партия или вызов", msg_ttt)
        self.assertIn("дайс-дуэли", msg_ttt)

        # u2 creates an open RR challenge
        ok_rr2, _, rr_gid = await create_rr_challenge("b", u2, bet=500)
        self.assertTrue(ok_rr2)

        # u1 tries to accept RR challenge -> BLOCKED
        ok_acc_rr, msg_acc_rr, _ = await accept_rr_challenge(rr_gid, u1)
        self.assertFalse(ok_acc_rr)
        self.assertIn("активная партия или вызов", msg_acc_rr)

    async def test_cross_game_collision_rr_blocks_dice_and_ttt(self):
        """User busy in Russian Roulette cannot create or accept Dice or TTT games."""
        u1 = 1001
        ok, _, rr_gid = await create_rr_challenge("b", u1, bet=500)
        self.assertTrue(ok)

        # u1 tries to create Dice challenge -> BLOCKED
        ok_dice, msg_dice, _ = await create_dice_challenge("b", u1, bet=500)
        self.assertFalse(ok_dice)
        self.assertIn("активная партия или вызов", msg_dice)
        self.assertIn("русской рулетке", msg_dice)

        # u1 tries to create TTT challenge -> BLOCKED
        ok_ttt, msg_ttt, _ = await create_ttt_challenge(None, 1234, "b", u1, bet=500)
        self.assertFalse(ok_ttt)
        self.assertIn("активная партия или вызов", msg_ttt)
        self.assertIn("русской рулетке", msg_ttt)

    async def test_cross_game_collision_ttt_blocks_dice_and_rr(self):
        """User busy in Tic-Tac-Toe cannot create or accept Dice or RR games."""
        u1 = 1001
        ok, _, ttt_game = await create_ttt_challenge(None, 1234, "b", u1, bet=500)
        self.assertTrue(ok)

        # u1 tries to create Dice challenge -> BLOCKED
        ok_dice, msg_dice, _ = await create_dice_challenge("b", u1, bet=500)
        self.assertFalse(ok_dice)
        self.assertIn("активная партия или вызов", msg_dice)
        self.assertIn("крестиках-ноликах", msg_dice)

        # u1 tries to create RR challenge -> BLOCKED
        ok_rr, msg_rr, _ = await create_rr_challenge("b", u1, bet=500)
        self.assertFalse(ok_rr)
        self.assertIn("активная партия или вызов", msg_rr)
        self.assertIn("крестиках-ноликах", msg_rr)

    async def test_free_after_finish_allows_other_games(self):
        """When a game finishes/cancels, user is completely freed for all engines."""
        u1 = 1001
        ok, _, ttt_game = await create_ttt_challenge(None, 1234, "b", u1, bet=500)
        self.assertTrue(ok)
        self.assertIn(u1, user_active_ttt_session)

        # Cancel TTT
        ok_c, _ = await cancel_ttt_challenge(ttt_game.game_id, u1)
        self.assertTrue(ok_c)
        self.assertNotIn(u1, user_active_ttt_session)

        # u1 can now immediately create Dice challenge
        ok_dice, _, d_gid = await create_dice_challenge("b", u1, bet=500)
        self.assertTrue(ok_dice)

        # Cancel Dice
        ok_dc, _ = await cancel_dice_challenge(d_gid, u1)
        self.assertTrue(ok_dc)

        # u1 can now immediately create RR challenge
        ok_rr, _, rr_gid = await create_rr_challenge("b", u1, bet=500)
        self.assertTrue(ok_rr)

    # -------------------------------------------------------------------------
    # 2. CONCURRENT ACCEPTANCE RACE ON DISTINCT CHALLENGES
    # -------------------------------------------------------------------------

    async def test_concurrent_accept_distinct_challenges_same_user(self):
        """
        User attempts to accept two distinct challenges at the exact same moment.
        Strict invariant: exactly ONE accept succeeds; second is rejected.
        """
        p_c1, p_c2, p_acceptor = 1001, 1002, 1003
        bet = 1000

        # Create two distinct TTT challenges
        ok1, _, g1 = await create_ttt_challenge(None, 1001, "b", p_c1, bet=bet)
        ok2, _, g2 = await create_ttt_challenge(None, 1002, "b", p_c2, bet=bet)
        self.assertTrue(ok1 and ok2)

        # Acceptor concurrently accepts both
        results = await asyncio.gather(
            accept_ttt_challenge(None, g1.game_id, p_acceptor),
            accept_ttt_challenge(None, g2.game_id, p_acceptor),
            return_exceptions=False,
        )

        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]

        self.assertEqual(len(successes), 1, "Exactly one challenge accept must succeed")
        self.assertEqual(len(failures), 1, "The second challenge accept must fail")
        self.assertIn("активная партия или вызов", failures[0][1])

        # Verify acceptor balance deducted exactly once
        bal = await get_user_global_balance(self.db, p_acceptor)
        self.assertEqual(bal, 500000 - bet)

    # -------------------------------------------------------------------------
    # 3. TARGET SESSION INTEGRITY ON CANCEL / EXPIRE
    # -------------------------------------------------------------------------

    async def test_target_session_preserved_when_targeted_challenge_cancelled(self):
        """
        Target user B has an active game in RR.
        Challenger A issues a targeted challenge for B in TTT, then cancels it.
        Target user B's active RR game MUST NOT be purged!
        """
        p_a, p_b = 1001, 1002
        ok_rr, _, rr_gid = await create_rr_challenge("b", p_b, bet=500)
        self.assertTrue(ok_rr)
        self.assertEqual(user_active_rr_game.get(p_b), rr_gid)

        # p_a creates targeted TTT challenge for p_b
        # Note: create_ttt_challenge doesn't register target in active session,
        # but cancel must not blindly pop target from user_active_ttt_session either
        ok_ttt, _, ttt_g = await create_ttt_challenge(None, 1234, "b", p_a, bet=500, target_user_id=p_b)
        self.assertTrue(ok_ttt)

        # p_a cancels the TTT challenge
        ok_canc, _ = await cancel_ttt_challenge(ttt_g.game_id, p_a)
        self.assertTrue(ok_canc)

        # p_b's RR game MUST still be fully intact
        self.assertEqual(user_active_rr_game.get(p_b), rr_gid)
        self.assertIn(rr_gid, active_rr_games)

    async def test_target_session_preserved_in_dice_cancel(self):
        """
        Target user B has an active game in TTT.
        Challenger A issues a targeted challenge for B in Dice, then cancels it.
        Target user B's active TTT game MUST NOT be purged!
        """
        p_a, p_b = 1001, 1002
        ok_ttt, _, ttt_g = await create_ttt_challenge(None, 1234, "b", p_b, bet=500)
        self.assertTrue(ok_ttt)
        self.assertEqual(user_active_ttt_session.get(p_b), ttt_g.game_id)

        # p_a creates targeted Dice challenge for p_b
        ok_d, _, d_gid = await create_dice_challenge("b", p_a, bet=500, target_id=p_b)
        self.assertTrue(ok_d)

        # p_a cancels the Dice challenge
        ok_canc, _ = await cancel_dice_challenge(d_gid, p_a)
        self.assertTrue(ok_canc)

        # p_b's TTT session MUST remain active
        self.assertEqual(user_active_ttt_session.get(p_b), ttt_g.game_id)
        self.assertIn(ttt_g.game_id, active_ttt_games)

    # -------------------------------------------------------------------------
    # 4. TARGET DECLINE VS STRANGER SECURITY
    # -------------------------------------------------------------------------

    async def test_rr_decline_permissions_stranger_vs_target(self):
        """In Russian Roulette, strangers cannot cancel; target can decline."""
        p_a, p_b, p_stranger = 1001, 1002, 1003
        ok, _, gid = await create_rr_challenge("b", p_a, bet=500, target_id=p_b)
        self.assertTrue(ok)

        # Stranger attempts to decline -> REJECTED
        ok_s, msg_s = await decline_or_cancel_rr_challenge(gid, p_stranger)
        self.assertFalse(ok_s)
        self.assertIn("Только участники", msg_s)

        # Target declines -> ACCEPTED
        mock_bot = AsyncMock()
        ok_t, msg_t = await decline_or_cancel_rr_challenge(gid, p_b, bot=mock_bot)
        self.assertTrue(ok_t)
        self.assertIn("отклонен", msg_t)
        self.assertNotIn(gid, active_rr_games)

    async def test_ttt_decline_permissions_stranger_vs_target(self):
        """In Tic-Tac-Toe, strangers cannot cancel; target can decline."""
        p_a, p_b, p_stranger = 1001, 1002, 1003
        ok, _, game = await create_ttt_challenge(None, 1234, "b", p_a, bet=500, target_user_id=p_b)
        self.assertTrue(ok)
        gid = game.game_id

        # Stranger attempts to decline -> REJECTED
        ok_s, msg_s = await cancel_ttt_challenge(gid, p_stranger)
        self.assertFalse(ok_s)
        self.assertIn("Только участники", msg_s)

        # Target declines -> ACCEPTED
        mock_bot = AsyncMock()
        ok_t, msg_t = await cancel_ttt_challenge(gid, p_b, bot=mock_bot)
        self.assertTrue(ok_t)
        self.assertIn("отклонен", msg_t)
        self.assertNotIn(gid, active_ttt_games)

    # -------------------------------------------------------------------------
    # 5. TTT WHALE BURN RAKE (POT > 50,000)
    # -------------------------------------------------------------------------

    async def test_ttt_whale_burn_rake_over_50k(self):
        """
        When TTT pot > 50,000 (e.g. bet = 30,000, pot = 60,000):
        10% rake (6,000 ₪) is burned out of circulation without crediting Abu Fund.
        Winner receives 54,000 ₪.
        """
        p1, p2 = 1001, 1002
        bet = 30000
        initial_abu = await get_abu_fund_total(self.db)

        ok1, _, game = await create_ttt_challenge(None, 1001, "b", p1, bet=bet)
        self.assertTrue(ok1)
        gid = game.game_id

        ok2, _, game = await accept_ttt_challenge(None, gid, p2)
        self.assertTrue(ok2)

        # p1 wins
        game.status = "finished"
        game.winner_id = p1
        game.finish_reason = "win"

        with patch("ttt_engine.publish_ttt_board_announcement", new_callable=AsyncMock):
            ok_f, _, _ = await finish_ttt_game(game, is_win=True, bot=None)
            self.assertTrue(ok_f)

        # Rake is 10% of 60,000 = 6,000. Net win = 54,000.
        # p1 paid 30,000 escrow, now receives 54,000 -> net +24,000 (500000 + 24000 = 524000)
        bal_w = await get_user_global_balance(self.db, p1)
        self.assertEqual(bal_w, 524000)

        # Abu Fund must NOT receive the burned rake!
        final_abu = await get_abu_fund_total(self.db)
        self.assertEqual(final_abu, initial_abu, "Burned whale rake must NOT enter Abu Fund")

        # Transaction log audit
        cursor = await self.db.execute(
            "SELECT description FROM UserTransactions WHERE user_id = ? AND category = 'ttt' ORDER BY id DESC LIMIT 1",
            (p1,)
        )
        row = await cursor.fetchone()
        self.assertIn("сожжён рейк 10%", row[0])

    async def test_ttt_normal_rake_under_50k(self):
        """
        When TTT pot <= 50,000 (e.g. bet = 1,000, pot = 2,000):
        Standard 5% rake (100 ₪) goes to Abu Fund.
        Winner receives 1,900 ₪.
        """
        p1, p2 = 1001, 1002
        bet = 1000
        initial_abu = await get_abu_fund_total(self.db)

        ok1, _, game = await create_ttt_challenge(None, 1001, "b", p1, bet=bet)
        self.assertTrue(ok1)
        gid = game.game_id

        ok2, _, game = await accept_ttt_challenge(None, gid, p2)
        self.assertTrue(ok2)

        game.status = "finished"
        game.winner_id = p1
        game.finish_reason = "win"

        with patch("ttt_engine.publish_ttt_board_announcement", new_callable=AsyncMock):
            ok_f, _, _ = await finish_ttt_game(game, is_win=True, bot=None)
            self.assertTrue(ok_f)

        # Net win = 1,900. P1 escrow -1,000 + 1,900 = +900.
        bal_w = await get_user_global_balance(self.db, p1)
        self.assertEqual(bal_w, 500900)

        # Abu Fund must increase by 100
        final_abu = await get_abu_fund_total(self.db)
        self.assertEqual(final_abu, initial_abu + 100)

    # -------------------------------------------------------------------------
    # 6. TTT DRAW REFUND LEDGER EXACT CREDIT
    # -------------------------------------------------------------------------

    async def test_ttt_draw_refund_ledger_accuracy(self):
        """
        In a TTT draw with bet = 500:
        2% fee = 10 ₪, refund = 490 ₪.
        The transaction ledger MUST record +490 (positive credit), not negative fee.
        """
        p1, p2 = 1001, 1002
        bet = 500

        ok1, _, game = await create_ttt_challenge(None, 1001, "b", p1, bet=bet)
        self.assertTrue(ok1)
        gid = game.game_id

        ok2, _, game = await accept_ttt_challenge(None, gid, p2)
        self.assertTrue(ok2)

        game.status = "finished"
        game.finish_reason = "draw"

        with patch("ttt_engine.publish_ttt_board_announcement", new_callable=AsyncMock):
            ok_f, _, _ = await finish_ttt_game(game, is_draw=True, bot=None)
            self.assertTrue(ok_f)

        # Both players should have 500000 - 500 + 490 = 499990
        bal_p1 = await get_user_global_balance(self.db, p1)
        bal_p2 = await get_user_global_balance(self.db, p2)
        self.assertEqual(bal_p1, 499990)
        self.assertEqual(bal_p2, 499990)

        # Check transaction ledger entries: the refund transaction amount must be +490
        cursor = await self.db.execute(
            "SELECT amount, description FROM UserTransactions WHERE user_id = ? AND category = 'ttt' ORDER BY id DESC LIMIT 1",
            (p1,)
        )
        row = await cursor.fetchone()
        self.assertEqual(row[0], 490.0, "Refund transaction amount must be +490, NOT negative fee!")
        self.assertIn("Возврат ставки", row[1])

    # -------------------------------------------------------------------------
    # 7. NAN / INFINITY BET REJECTION IN ALL ENGINES
    # -------------------------------------------------------------------------

    async def test_nan_and_infinity_bet_rejection_all_engines(self):
        """Dice, RR, and TTT MUST reject NaN and Inf bets gracefully."""
        uid = 1001
        nan_val = float("nan")
        inf_val = float("inf")

        # 1. Dice Duel
        ok_d_nan, msg_d_nan, _ = await create_dice_challenge("b", uid, bet=nan_val)
        self.assertFalse(ok_d_nan)
        self.assertIn("Некорректная сумма ставки", msg_d_nan)

        ok_d_inf, msg_d_inf, _ = await create_dice_challenge("b", uid, bet=inf_val)
        self.assertFalse(ok_d_inf)
        self.assertIn("Некорректная сумма ставки", msg_d_inf)

        # 2. Russian Roulette
        ok_rr_nan, msg_rr_nan, _ = await create_rr_challenge("b", uid, bet=nan_val)
        self.assertFalse(ok_rr_nan)
        self.assertIn("Некорректная сумма ставки", msg_rr_nan)

        ok_rr_inf, msg_rr_inf, _ = await create_rr_challenge("b", uid, bet=inf_val)
        self.assertFalse(ok_rr_inf)
        self.assertIn("Некорректная сумма ставки", msg_rr_inf)

        # 3. Tic-Tac-Toe
        ok_ttt_nan, msg_ttt_nan, _ = await create_ttt_challenge(None, 1234, "b", uid, bet=nan_val)
        self.assertFalse(ok_ttt_nan)
        self.assertIn("Некорректная сумма ставки", msg_ttt_nan)

        ok_ttt_inf, msg_ttt_inf, _ = await create_ttt_challenge(None, 1234, "b", uid, bet=inf_val)
        self.assertFalse(ok_ttt_inf)
        self.assertIn("Некорректная сумма ставки", msg_ttt_inf)
