# -*- coding: utf-8 -*-
"""
tests/run_adversarial_verification.py
Standalone verification runner for Whale Safes & Auction Concurrency.
Executes isolated adversarial test scenarios with detailed step-by-step logging.
"""

import asyncio
import contextlib
import io
import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


import aiosqlite
import common.config
import common.database
import common.db_pool
import lootbox_engine
import whale_economy_engine
from auction_engine import (
    create_auction,
    ensure_auction_schema,
    finish_active_auctions,
    place_auction_bid,
)
from whale_economy_engine import (
    buy_whale_safe,
    calculate_whale_safe_price,
    roll_whale_safe,
)


async def setup_isolated_db(tmp_dir: str):
    """Sets up an isolated test database with full schema and WAL mode."""
    db_path = os.path.join(tmp_dir, "standalone_adversarial.db")
    db = await aiosqlite.connect(db_path, timeout=30.0, isolation_level=None)
    await db.execute("PRAGMA busy_timeout = 30000;")
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys = ON;")
    await db.execute("BEGIN IMMEDIATE")
    with contextlib.redirect_stdout(io.StringIO()):
        await common.database._create_tables(db)
        await common.database._apply_migrations(db)
        await common.database._create_indices(db)
        await common.database._create_triggers(db)
        await common.database._insert_initial_data(db)
    await db.execute("COMMIT")

    # Patch db_pool connection
    common.db_pool._db_connection = db
    common.db_pool.get_pool = lambda: db
    common.database.get_pool = lambda: db
    return db


async def verify_auction_concurrency(db):
    print("=" * 70)
    print("SCENARIO 1: 20 CONCURRENT ASYNC BIDDERS ON AUCTION")
    print("=" * 70)

    await ensure_auction_schema(db)
    start_price = 50000.0
    min_step = 5000.0
    auc_id = await create_auction(
        db, "custom_role", "Корона Двача", "Лот #1", start_price, min_step, 3600.0, "b"
    )
    print(f"[+] Created Auction #{auc_id} (Start: {start_price:,.0f} ₪, Step: +{min_step:,.0f} ₪)")

    num_bidders = 20
    bidders = [90000 + i for i in range(num_bidders)]
    initial_balance = 1000000.0  # 1M ₪ each
    initial_total = num_bidders * initial_balance

    for uid in bidders:
        await common.database.add_user_global_balance(db, uid, "b", initial_balance)

    # 20 distinct bid amounts: 60k, 70k, ... 250k
    bids = []
    for i, uid in enumerate(bidders):
        amt = start_price + (i + 1) * 10000.0
        bids.append((uid, f"Anon_{uid}", amt))

    highest_uid, highest_name, highest_amt = max(bids, key=lambda x: x[2])
    print(f"[+] Highest planned bidder: {highest_name} with bid: {highest_amt:,.0f} ₪")

    # Shuffle to maximize concurrent contention
    random.seed(1337)
    shuffled_bids = list(bids)
    random.shuffle(shuffled_bids)

    print(f"[+] Launching {num_bidders} concurrent async bid tasks via asyncio.gather()...")
    start_time = time.perf_counter()

    tasks = [
        asyncio.create_task(place_auction_bid(db, auc_id, uid, name, amt, "b"))
        for uid, name, amt in shuffled_bids
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.perf_counter() - start_time

    print(f"[+] All {num_bidders} tasks completed in {elapsed*1000:.2f} ms")

    # Check for exceptions
    for idx, r in enumerate(results):
        if isinstance(r, Exception):
            raise AssertionError(f"Task {idx} failed with exception: {r}")

    # Verify winning bidder in Auctions table
    async with db.execute("SELECT current_bid, current_winner_id, current_winner_name FROM Auctions WHERE id = ?", (auc_id,)) as c:
        row = await c.fetchone()
        cur_bid, cur_winner_id, cur_winner_name = row

    print(f"[+] Final Auction State -> Winner: User {cur_winner_id} ({cur_winner_name}), Winning Bid: {cur_bid:,.0f} ₪")
    assert cur_winner_id == highest_uid, f"Winner mismatch! Expected {highest_uid}, got {cur_winner_id}"
    assert cur_bid == highest_amt, f"Bid mismatch! Expected {highest_amt}, got {cur_bid}"

    # Verify balances: Winner deducted, all others 100% refunded
    refund_verified_count = 0
    for uid in bidders:
        bal = await common.database.get_user_global_balance(db, uid)
        if uid == highest_uid:
            assert bal == initial_balance - highest_amt, f"Winner balance wrong: {bal}"
        else:
            assert bal == initial_balance, f"Outbid user {uid} was not 100% refunded! Bal: {bal}"
            refund_verified_count += 1

    print(f"[+] 100% Refund verification passed: {refund_verified_count}/{num_bidders-1} outbid users restored to exactly {initial_balance:,.0f} ₪")

    # Verify Money Conservation
    current_total = sum([await common.database.get_user_global_balance(db, uid) for uid in bidders])
    assert round(current_total + cur_bid, 2) == round(initial_total, 2)
    print(f"[+] Conservation Invariant: sum(balances) + escrow = {current_total + cur_bid:,.2f} ₪ == initial {initial_total:,.2f} ₪ (PASS)")
    print("[+] Zero Deadlocks, Zero 'database is locked' errors! (PASS)")


async def verify_whale_safe_progression_and_burn(db):
    print("\n" + "=" * 70)
    print("SCENARIO 2: WHALE SAFE 10 CONSECUTIVE OPENINGS (P(n) = 50000 * 1.5^n & 70% BURN)")
    print("=" * 70)

    user_id = 95001
    await common.database.add_user_global_balance(db, user_id, "b", 20000000.0)

    fund_initial = await common.database.get_abu_fund_total(db)
    print(f"[+] Initial Abu Yacht Fund Balance: {fund_initial:,.2f} ₪")

    cumulative_expected_burn = 0.0
    total_spent_gross = 0

    print(f"{'#':<3} | {'n':<2} | {'Expected P(n)':<15} | {'Actual Price':<14} | {'70% Burn':<12} | {'Fund Diff':<12} | {'Drop Title'}")
    print("-" * 90)

    for step in range(10):
        n = step
        expected_price = calculate_whale_safe_price(n)
        expected_burn = round(expected_price * 0.70, 2)
        total_spent_gross += expected_price
        cumulative_expected_burn += expected_burn

        fund_before_step = await common.database.get_abu_fund_total(db)
        res = await buy_whale_safe(db, user_id, "b")

        assert res["ok"] is True, f"Failed at opening {step}: {res.get('error')}"
        assert res["price"] == expected_price, f"Price mismatch at n={n}"
        assert res["burned_to_abu"] == expected_burn, f"Burn mismatch at n={n}"
        assert res["opened_today"] == n + 1, f"Counter mismatch at n={n}"

        fund_after_step = await common.database.get_abu_fund_total(db)
        diff = round(fund_after_step - fund_before_step, 2)
        assert diff == expected_burn, f"Fund did not receive exact 70% burn at n={n}"

        print(f"{step+1:<3} | {n:<2} | {expected_price:<15,d} ₪ | {res['price']:<14,d} ₪ | {res['burned_to_abu']:<12,.2f} ₪ | {diff:<12,.2f} ₪ | {res['title'][:30]}")

    fund_final = await common.database.get_abu_fund_total(db)
    total_burned = round(fund_final - fund_initial, 2)

    print("-" * 90)
    print(f"[+] Total Gross Spent across 10 safes: {total_spent_gross:,.0f} ₪")
    print(f"[+] Total 70% Burned to Abu Yacht Fund: {total_burned:,.2f} ₪ (Expected: {cumulative_expected_burn:,.2f} ₪)")
    assert total_burned == round(cumulative_expected_burn, 2)
    assert total_burned == 3966550.70
    print("[+] Whale Safe P(n) and 70% burn to Abu Yacht Fund strictly verified! (PASS)")


async def main():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db = await setup_isolated_db(tmp_dir)
        try:
            await verify_auction_concurrency(db)
            await verify_whale_safe_progression_and_burn(db)
            print("\n" + "=" * 70)
            print("ALL EMPIRICAL ADVERSARIAL VERIFICATIONS PASSED WITH 100% SUCCESS!")
            print("=" * 70)
        finally:
            await db.close()


if __name__ == "__main__":
    asyncio.run(main())
