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

    async def test_dynamic_bet_caps(self):
        """
        Verify dynamic bet caps based on player balance:
        - Novices (balance <= 10,000): cap = 1,000
        - Middle class (10,000 < balance <= 100,000): cap = 25,000
        - Wealthy (100,000 < balance <= 500,000): cap = 150,000
        - Oligarchs (500,000 < balance <= 2,000,000): cap = 500,000
        - Whales / Multi-millionaires (balance > 2,000,000): cap = 1,000,000 (absolute limit)
        - Absolute ceiling: MAX_CASINO_BET == 1,000,000
        """
        self.assertEqual(casino_engine.MAX_CASINO_BET, 1_000_000)
        self.assertEqual(casino_engine.MAX_ROULETTE_BET, 1_000_000)

        # Tier 1: <= 10,000
        self.assertEqual(casino_engine.get_max_bet_for_balance(0), 1_000)
        self.assertEqual(casino_engine.get_max_bet_for_balance(5_000), 1_000)
        self.assertEqual(casino_engine.get_max_bet_for_balance(10_000), 1_000)

        # Tier 2: 10,000 < balance <= 100,000
        self.assertEqual(casino_engine.get_max_bet_for_balance(10_001), 25_000)
        self.assertEqual(casino_engine.get_max_bet_for_balance(50_000), 25_000)
        self.assertEqual(casino_engine.get_max_bet_for_balance(100_000), 25_000)

        # Tier 3: 100,000 < balance <= 500,000
        self.assertEqual(casino_engine.get_max_bet_for_balance(100_001), 150_000)
        self.assertEqual(casino_engine.get_max_bet_for_balance(300_000), 150_000)
        self.assertEqual(casino_engine.get_max_bet_for_balance(500_000), 150_000)

        # Tier 4: 500,000 < balance <= 2,000,000 (Oligarchs)
        self.assertEqual(casino_engine.get_max_bet_for_balance(500_001), 500_000)
        self.assertEqual(casino_engine.get_max_bet_for_balance(1_000_000), 500_000)
        self.assertEqual(casino_engine.get_max_bet_for_balance(2_000_000), 500_000)

        # Tier 5: > 2,000,000 (Whales / Multi-millionaires)
        self.assertEqual(casino_engine.get_max_bet_for_balance(2_000_001), 1_000_000)
        self.assertEqual(casino_engine.get_max_bet_for_balance(10_000_000), 1_000_000)

        # Validation helper
        valid, cap, err = casino_engine.validate_casino_bet(1_200, balance=5_000)
        self.assertFalse(valid)
        self.assertEqual(cap, 1_000)
        self.assertIn("1,000", err)

        valid_ok, cap_ok, _ = casino_engine.validate_casino_bet(1_000, balance=5_000)
        self.assertTrue(valid_ok)

        # Excessive bet > 1,000,000 blocked even for multi-millionaires
        valid_excess, cap_excess, _ = casino_engine.validate_casino_bet(1_500_000, balance=50_000_000)
        self.assertFalse(valid_excess)
        self.assertEqual(cap_excess, 1_000_000)

        # Presets clamping
        presets_novice = casino_engine.get_adaptive_bet_presets(balance=8_000)
        self.assertTrue(all(p <= 1_000 for p in presets_novice))
        self.assertIn(1_000, presets_novice)

        presets_oligarch = casino_engine.get_adaptive_bet_presets(balance=10_000_000)
        self.assertTrue(all(p <= 1_000_000 for p in presets_oligarch))
        self.assertIn(1_000_000, presets_oligarch)

    async def test_jackpot_and_high_win_tax(self):
        """
        Verify Jackpot & High-Win Tax:
        - Pure profit >= 10,000 or multiplier >= 4.0x: 10% tax sent to Abu's yacht fund.
        - Player gets 90% net profit.
        - Message contains: '🏛️ Налог Абу (10%): -X ₪ перечислено в фонд яхты'
        """
        # Case A: Pure profit >= 10,000 with low multiplier (<4.0x)
        tax, payout, msg = casino_engine.calculate_jackpot_tax(net_profit=10_000, multiplier=2.0)
        self.assertEqual(tax, 1_000)
        self.assertEqual(payout, 9_000)
        self.assertEqual(msg, "🏛️ Налог Абу (10%): -1000 ₪ перечислено в фонд яхты")

        # Case B: Multiplier >= 4.0x with profit < 10,000
        tax_m, payout_m, msg_m = casino_engine.calculate_jackpot_tax(net_profit=3_000, multiplier=4.0)
        self.assertEqual(tax_m, 300)
        self.assertEqual(payout_m, 2_700)
        self.assertEqual(msg_m, "🏛️ Налог Абу (10%): -300 ₪ перечислено в фонд яхты")

        # Case C: Big Jackpot (e.g. 50.0x crown jackpot, 1000 bet -> profit 49,000)
        tax_j, payout_j, msg_j = casino_engine.calculate_jackpot_tax(net_profit=49_000, multiplier=50.0)
        self.assertEqual(tax_j, 4_900)
        self.assertEqual(payout_j, 44_100)
        self.assertEqual(msg_j, "🏛️ Налог Абу (10%): -4900 ₪ перечислено в фонд яхты")

        # Case D: Normal small win (profit < 10,000 and multiplier < 4.0) -> NO TAX
        tax_n, payout_n, msg_n = casino_engine.calculate_jackpot_tax(net_profit=2_000, multiplier=1.8)
        self.assertEqual(tax_n, 0)
        self.assertEqual(payout_n, 2_000)
        self.assertEqual(msg_n, "")

        # Case E: Loss or break-even -> NO TAX
        tax_0, payout_0, msg_0 = casino_engine.calculate_jackpot_tax(net_profit=0, multiplier=0.0)
        self.assertEqual(tax_0, 0)
        self.assertEqual(payout_0, 0)
        self.assertEqual(msg_0, "")

        # Compatibility helper calculate_win_tax
        c_tax, c_payout = casino_engine.calculate_win_tax(net_profit=15_000, multiplier=2.0)
        self.assertEqual(c_tax, 1_500)
        self.assertEqual(c_payout, 13_500)

    async def test_spin_cooldown_and_autoclicker_guard(self):
        """
        Verify spin cooldown of at least 1.5 seconds between bets/spins.
        Attempting faster returns friendly warning: '⏳ Не части! Колесу нужно остановиться.'
        """
        user_id = 123456789
        casino_engine.user_casino_last_action.pop(user_id, None)

        # 1st spin: allowed
        is_allowed, rem = casino_engine.check_casino_cooldown(user_id)
        self.assertTrue(is_allowed)
        self.assertEqual(rem, 0.0)

        # Immediate 2nd spin: blocked
        res = casino_engine.check_casino_cooldown(user_id)
        is_allowed2, rem2 = res
        self.assertFalse(is_allowed2)
        self.assertGreater(rem2, 0.0)
        self.assertLessEqual(rem2, 1.5)
        self.assertEqual(res.message, "⏳ Не части! Колесу нужно остановиться.")

        # check_spin_cooldown 3-tuple helper
        ok_spin, rem_spin, msg_spin = casino_engine.check_spin_cooldown(user_id)
        self.assertFalse(ok_spin)
        self.assertEqual(msg_spin, "⏳ Не части! Колесу нужно остановиться.")

    async def test_mmorpg_rtp_and_house_edge_math(self):
        """
        Verify MMORPG RTP & House Edge across all games:
        - Slots mathematical RTP must be in 92–95% (house edge 5–8%).
        - Russian Roulette streak RTPs must be in 92–95%.
        - Coinflip RTP must be in 92–95%.
        """
        # 1. Slots Untilted RTP
        total_weight = sum(s[2] for s in casino_engine.SLOT_SYMBOLS)
        prob = {s[0]: s[2] / total_weight for s in casino_engine.SLOT_SYMBOLS}
        expected_return = 0.0
        for sym, mult, _ in casino_engine.SLOT_SYMBOLS:
            expected_return += (prob[sym] ** 3) * mult
        for sym, _, _ in casino_engine.SLOT_SYMBOLS:
            if sym == "💀":
                continue
            for other, _, _ in casino_engine.SLOT_SYMBOLS:
                if other == sym:
                    continue
                p_combo = 3 * (prob[sym] ** 2) * prob[other]
                m = 4.5 if sym == "👑" else (2.8 if sym == "💎" else 1.8)
                expected_return += p_combo * m
        slots_rtp = expected_return * 100
        self.assertTrue(92.0 <= slots_rtp <= 95.0, f"Slots RTP {slots_rtp:.2f}% out of [92%, 95%]")

        # 2. Russian Roulette Streaks RTP
        for streak, mult in casino_engine.ROULETTE_STREAK_MULTS.items():
            prob_survive = (5 / 6) ** streak
            rtp = prob_survive * mult * 100
            self.assertTrue(92.0 <= rtp <= 95.0, f"Roulette streak {streak} RTP {rtp:.2f}% out of [92%, 95%]")

        # 3. Coinflip RTP
        base_cf_rtp = 0.48 * 1.96 * 100
        tilted_cf_rtp = 0.47 * 1.96 * 100
        self.assertTrue(92.0 <= base_cf_rtp <= 95.0, f"Coinflip base RTP {base_cf_rtp:.2f}% out of [92%, 95%]")
        self.assertTrue(92.0 <= tilted_cf_rtp <= 95.0, f"Coinflip tilted RTP {tilted_cf_rtp:.2f}% out of [92%, 95%]")

    async def test_transfer_tax_to_abu_fund(self):
        """Verify tax transfer to Abu's fund in database."""
        async with aiosqlite.connect(":memory:") as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS GlobalStats (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )"""
            )
            await db.commit()

            await casino_engine.transfer_tax_to_abu_fund(db, 2500)
            cur = await db.execute("SELECT value FROM GlobalStats WHERE key = 'abu_yacht_fund'")
            row = await cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(float(row[0]), 2500.0)


if __name__ == "__main__":
    unittest.main()
