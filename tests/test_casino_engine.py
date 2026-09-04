import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite
import casino_engine
import drop_engine


class TestCasinoAndDrop(unittest.IsolatedAsyncioTestCase):

    async def test_slots_engine(self):
        wins = 0
        spins = 500
        for _ in range(spins):
            reels, mult, title = casino_engine.roll_slots()
            self.assertEqual(len(reels), 3)
            if mult > 0:
                wins += 1
        self.assertGreater(wins, 0)

    async def test_coinflip_engine(self):
        cf_wins = 0
        for _ in range(500):
            side, is_win, mult, text = casino_engine.play_coinflip("heads")
            self.assertIn(mult, [0.0, 1.96])
            if is_win:
                cf_wins += 1
        self.assertTrue(150 <= cf_wins <= 350)

    async def test_blackjack_math(self):
        hand1 = [("A", "♠️"), ("K", "♥️")]
        self.assertEqual(casino_engine.calculate_hand(hand1), 21)

        hand2 = [("A", "♠️"), ("A", "♥️"), ("9", "♦️")]
        self.assertEqual(casino_engine.calculate_hand(hand2), 21)

        hand3 = [("10", "♠️"), ("8", "♥️"), ("5", "♦️")]
        self.assertEqual(casino_engine.calculate_hand(hand3), 23)

    async def test_high_concurrency_money_drop(self):
        db_lock = asyncio.Lock()
        async with aiosqlite.connect(":memory:") as db:
            await db.execute(
                """CREATE TABLE Users (
                    user_id INTEGER,
                    board_id TEXT,
                    balance INTEGER DEFAULT 0,
                    PRIMARY KEY(user_id, board_id)
                )"""
            )
            await db.execute(
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
            donor_id = 999999
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (donor_id,))
            for i in range(1, 101):
                await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (i,))
            await db.commit()

            # Step 1: Create drop
            drop_engine._user_drop_cooldowns.pop(donor_id, None)
            ok, msg, drop_rec = await drop_engine.create_money_drop(
                donor_id=donor_id,
                donor_name="DonorAnon",
                board_id="b",
                amount=1000,
                db_lock=db_lock,
                db_conn=db,
                check_cooldown=False,
            )
            self.assertTrue(ok)
            self.assertIsNotNone(drop_rec)

            # Step 2: 100 concurrent claims
            drop_id = drop_rec.drop_id

            async def try_claim(user_id: int):
                return await drop_engine.claim_money_drop(
                    drop_id=drop_id,
                    claimer_id=user_id,
                    claimer_name=f"Claimer #{user_id}",
                    claimer_board_id="b",
                    db_lock=db_lock,
                    db_conn=db,
                )

            tasks = [try_claim(uid) for uid in range(1, 101)]
            results = await asyncio.gather(*tasks)

            success_claims = [r for r in results if r[0] is True]
            rejected_claims = [r for r in results if r[0] is False]

            self.assertEqual(len(success_claims), 1)
            self.assertEqual(len(rejected_claims), 99)

            # Step 3: Overdraft protection
            poor_id = 888888
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 50)", (poor_id,))
            await db.commit()
            ok_od, _, _ = await drop_engine.create_money_drop(
                donor_id=poor_id,
                donor_name="PoorAnon",
                board_id="b",
                amount=500,
                db_lock=db_lock,
                db_conn=db,
            )
            self.assertFalse(ok_od)


if __name__ == "__main__":
    unittest.main()
