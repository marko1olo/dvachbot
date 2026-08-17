import asyncio
import aiosqlite
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import casino_engine
import drop_engine

async def run_tests():
    print("=== STARTING CASINO & MONEY DROP TEST SUITE ===")
    
    # 1. Test Slots Engine
    print("\n--- Testing Slots Engine ---")
    wins = 0
    jackpots = 0
    spins = 1000
    for _ in range(spins):
        reels, mult, title = casino_engine.roll_slots()
        assert len(reels) == 3, "Slots must return 3 reels"
        if mult > 0:
            wins += 1
        if mult >= 50.0:
            jackpots += 1
    print(f"✅ Slots passed: {wins}/{spins} wins, {jackpots} jackpots.")

    # 2. Test Coinflip Engine
    print("\n--- Testing Coinflip Engine ---")
    cf_wins = 0
    for _ in range(1000):
        side, is_win, mult, text = casino_engine.play_coinflip("heads")
        assert mult in [0.0, 1.95]
        if is_win:
            cf_wins += 1
    print(f"✅ Coinflip passed: {cf_wins}/1000 wins on Heads (approx 50%).")

    # 3. Test Blackjack Deck & Hand Math
    print("\n--- Testing Blackjack Math ---")
    hand1 = [("A", "♠️"), ("K", "♥️")]
    assert casino_engine.calculate_hand(hand1) == 21, "Natural 21 must equal 21"
    
    hand2 = [("A", "♠️"), ("A", "♥️"), ("9", "♦️")]
    assert casino_engine.calculate_hand(hand2) == 21, "A + A + 9 must equal 21"

    hand3 = [("10", "♠️"), ("8", "♥️"), ("5", "♦️")]
    assert casino_engine.calculate_hand(hand3) == 23, "Bust hand must be 23"
    print("✅ Blackjack hand calculations passed.")

    # 4. Test In-Memory SQLite Concurrency for Drop System
    print("\n--- Testing High-Concurrency Money Drop Claims ---")
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
        # Create donor and 100 prospective claimers
        donor_id = 999999
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (donor_id,))
        for i in range(1, 101):
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (i,))
        await db.commit()

        # Step A: Donor drops 1000 shekels
        ok, msg, drop_rec = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="DonorAnon",
            board_id="b",
            amount=1000,
            db_lock=db_lock,
            db_conn=db,
        )
        assert ok, f"Drop creation failed: {msg}"
        assert drop_rec is not None
        
        # Verify donor balance deducted
        cur = await db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,))
        row = await cur.fetchone()
        assert row[0] == 4000, f"Expected donor balance 4000, got {row[0]}"
        print(f"✅ Drop created: 1000 ₪ deducted from donor (new balance: {row[0]} ₪).")

        # Step B: 100 parallel workers try to claim the drop at the exact same microsecond!
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

        print(f"✅ Concurrency result: {len(success_claims)} SUCCESS, {len(rejected_claims)} REJECTED.")
        assert len(success_claims) == 1, f"Expected exactly 1 winner, got {len(success_claims)}"
        assert len(rejected_claims) == 99, f"Expected 99 rejections, got {len(rejected_claims)}"

        winner_id = drop_rec.claimed_by
        cur = await db.execute("SELECT balance FROM Users WHERE user_id = ?", (winner_id,))
        row = await cur.fetchone()
        assert row[0] == 1000, f"Winner balance should be 1000, got {row[0]}"
        print(f"✅ Winner verified: User #{winner_id} received {row[0]} ₪ with ZERO race condition!")

        # Step C: Overdraft protection test
        poor_id = 888888
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 50)", (poor_id,))
        await db.commit()
        ok_od, msg_od, _ = await drop_engine.create_money_drop(
            donor_id=poor_id,
            donor_name="PoorAnon",
            board_id="b",
            amount=500,
            db_lock=db_lock,
            db_conn=db,
        )
        assert not ok_od, "Overdraft must be blocked"
        print(f"✅ Overdraft blocked properly: {msg_od}")

        # Step D: Drop Expiry and Refund test
        ok_exp, _, exp_drop = await drop_engine.create_money_drop(
            donor_id=donor_id,
            donor_name="DonorAnon",
            board_id="b",
            amount=500,
            db_lock=db_lock,
            db_conn=db,
            timeout_sec=0.1,
        )
        assert ok_exp and exp_drop is not None
        # Fast-forward time
        exp_drop.expires_at = time.time() - 1.0
        expired_drops = await drop_engine.expire_unclaimed_drops_step(db_lock, db)
        assert len(expired_drops) == 1, "Expected 1 expired drop"
        
        # Verify refund
        cur = await db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,))
        row = await cur.fetchone()
        assert row[0] == 4000, f"Donor refunded back to 4000, got {row[0]}"
        print(f"✅ Drop expiry refund verified: Donor balance restored to {row[0]} ₪.")

    print("\n🎉 ALL TESTS PASSED WITH 100% SUCCESS!")

if __name__ == "__main__":
    asyncio.run(run_tests())
