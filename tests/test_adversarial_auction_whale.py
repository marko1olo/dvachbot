# -*- coding: utf-8 -*-
"""
tests/test_adversarial_auction_whale.py
Adversarial verification suite for Milestone 3 (Auctions & Whale Safes):
1. Concurrency Test: 20 concurrent async tasks trying to place bids on the same auction with varying amounts.
   Verifies:
   - Exactly the highest valid bidder wins.
   - All outbid amounts are refunded 100%.
   - No deadlocks or SQLite 'database is locked' errors occur.
   - Money conservation holds strictly: sum(user_balances) + current_bid == initial_total.
2. Whale Safe Price & Burn Test: Simulate 10 consecutive safe openings.
   Verifies:
   - P(n) = 50000 * 1.5^n progression for all n in [0..9].
   - Exactly 70% of each purchase is burned into Abu Yacht Fund.
   - opened_today counter increments consecutively from 1 to 10.
   - Correct handling of rewards/cashback and rejection on insufficient funds.
3. Chaos Concurrency Test: 20 concurrent tasks with collision bids, under-bids, insufficient balances, and out-of-order amounts.
4. Auction Finalization: 100% of winning bid burned into Abu Yacht Fund upon auction finish.
"""

import asyncio
import json
import math
import random
import time
from typing import Any, Dict, List

import pytest

import common.config
import common.database
import common.db_pool
import lootbox_engine
import whale_economy_engine
from auction_engine import (
    create_auction,
    ensure_auction_schema,
    finish_active_auctions,
    get_active_auctions,
    place_auction_bid,
)
from whale_economy_engine import (
    buy_whale_safe,
    calculate_whale_safe_price,
    roll_whale_safe,
)


# =============================================================================
# 1. CONCURRENCY TESTS: 20 CONCURRENT ASYNC BIDDERS
# =============================================================================

class TestAdversarialAuctionConcurrency:
    """Adversarial stress-testing of auction bidding concurrency."""

    @pytest.mark.asyncio
    async def test_20_concurrent_bids_highest_wins_and_all_refunded(self, isolated_test_db):
        """
        Concurrency verification:
        - 20 concurrent async tasks placing bids on the same auction with varying amounts.
        - Verifies:
          1. Zero deadlocks and zero SQLite 'database is locked' errors.
          2. Exactly the highest valid bidder wins.
          3. All outbid amounts are refunded 100%.
          4. Total money conservation invariant holds: sum(balances) + current_bid == initial_total.
        """
        db = isolated_test_db
        await ensure_auction_schema(db)

        # Create auction: lot_type, title, description, start_price, min_bid_step, duration_sec
        start_price = 50000.0
        min_bid_step = 5000.0
        auc_id = await create_auction(
            db,
            lot_type="custom_role",
            title="[Король Борды]",
            description="Кастомная роль победителя",
            start_price=start_price,
            min_bid_step=min_bid_step,
            duration_sec=3600.0,
            board_id="b",
        )
        assert auc_id > 0

        # Setup 20 distinct bidders, each funded with 1,000,000 ₪
        num_bidders = 20
        initial_balance_per_user = 1000000.0
        bidders = [80000 + i for i in range(num_bidders)]

        for uid in bidders:
            await common.database.add_user_global_balance(db, uid, "b", initial_balance_per_user)

        initial_total_money = num_bidders * initial_balance_per_user

        # Generate 20 distinct valid bid amounts, strictly above start_price + step
        # Amounts: 60,000 ₪, 70,000 ₪, 80,000 ₪, ... up to 250,000 ₪
        # We assign a unique bid to each bidder, then shuffle the launch order
        # to maximize concurrent racing and interleaved execution.
        bid_plan = []
        for i, uid in enumerate(bidders):
            bid_amount = start_price + (i + 1) * 10000.0  # 60k, 70k, ... 250k
            bid_plan.append((uid, f"Anon_{uid}", bid_amount))

        # Identify the expected highest bidder and amount
        highest_bidder, highest_name, highest_amount = max(bid_plan, key=lambda x: x[2])
        assert highest_amount == start_price + num_bidders * 10000.0  # 250,000 ₪

        # Shuffle execution tasks
        random.seed(42)
        shuffled_plan = list(bid_plan)
        random.shuffle(shuffled_plan)

        async def place_single_bid(uid: int, uname: str, amount: float):
            return await place_auction_bid(db, auc_id, uid, uname, amount, board_id="b")

        # Launch all 20 tasks concurrently
        tasks = [
            asyncio.create_task(place_single_bid(uid, uname, amount))
            for uid, uname, amount in shuffled_plan
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 1. Verify no task threw an exception (deadlock, lock timeout, SQLite error)
        for idx, res in enumerate(results):
            assert not isinstance(res, Exception), f"Task {idx} failed with exception: {res}"
            assert isinstance(res, dict), f"Task {idx} returned non-dict: {res}"

        # 2. Verify auction final state in database
        async with db.execute(
            "SELECT current_bid, current_winner_id, current_winner_name, status FROM Auctions WHERE id = ?",
            (auc_id,)
        ) as c:
            row = await c.fetchone()
            current_bid, current_winner_id, current_winner_name, status = row

        assert status == "active"
        assert current_winner_id == highest_bidder, (
            f"Expected winner {highest_bidder}, but got {current_winner_id}"
        )
        assert current_bid == highest_amount, (
            f"Expected winning bid {highest_amount}, but got {current_bid}"
        )

        # 3. Verify all outbid amounts are refunded 100%
        for uid in bidders:
            bal = await common.database.get_user_global_balance(db, uid)
            if uid == highest_bidder:
                expected_bal = initial_balance_per_user - highest_amount
                assert bal == expected_bal, (
                    f"Winner balance mismatch: got {bal}, expected {expected_bal}"
                )
            else:
                assert bal == initial_balance_per_user, (
                    f"Outbid user {uid} was NOT fully refunded 100%! Balance: {bal}, expected: {initial_balance_per_user}"
                )

        # 4. Strict money conservation: sum of all balances + escrow in auction == initial total
        current_total_money = sum([
            await common.database.get_user_global_balance(db, uid) for uid in bidders
        ])
        assert round(current_total_money + current_bid, 2) == round(initial_total_money, 2), (
            f"Money leak or inflation detected! Initial: {initial_total_money}, now: {current_total_money + current_bid}"
        )

    @pytest.mark.asyncio
    async def test_20_concurrent_bids_adversarial_chaos_and_collisions(self, isolated_test_db):
        """
        Adversarial chaos test with 20 concurrent tasks:
        - 5 tasks attempt the exact same bid amount (race collision on same value).
        - 5 tasks attempt bids below minimum step (invalid bids).
        - 2 tasks have insufficient balance.
        - 8 tasks place escalating valid bids up to 500,000 ₪.
        Verifies:
        - Exactly the highest eligible bidder wins.
        - Non-winners retain exactly 100% of their money.
        - Ineligible/rejected tasks cause 0 financial distortion.
        - No SQLite errors or deadlocks.
        """
        db = isolated_test_db
        await ensure_auction_schema(db)

        start_price = 100000.0
        min_step = 10000.0
        auc_id = await create_auction(
            db, "board_pin", "Топ-пин", "Закреп", start_price, min_step, 3600.0, "b"
        )

        # 20 distinct users
        num_users = 20
        users = [81000 + i for i in range(num_users)]
        initial_balances = {}

        for i, uid in enumerate(users):
            if i in (18, 19):  # Insufficient balance users
                bal = 5000.0
            else:
                bal = 1000000.0
            await common.database.add_user_global_balance(db, uid, "b", bal)
            initial_balances[uid] = bal

        initial_total = sum(initial_balances.values())

        # Construct chaotic bid tasks
        actions = []
        # Group 1: 5 tasks competing for the exact same amount 120,000 ₪
        for i in range(5):
            actions.append((users[i], f"Collision_{i}", 120000.0))

        # Group 2: 5 tasks bidding below minimum (10,000 ₪, 20,000 ₪, 50,000 ₪, 99,000 ₪, 105,000 ₪)
        for i, low_amt in enumerate([10000.0, 20000.0, 50000.0, 99000.0, 105000.0]):
            actions.append((users[5 + i], f"Low_{i}", low_amt))

        # Group 3: 2 tasks with only 5,000 ₪ balance trying to bid 200,000 ₪
        actions.append((users[18], "Poor_1", 200000.0))
        actions.append((users[19], "Poor_2", 250000.0))

        # Group 4: 8 tasks placing escalating valid bids up to 500,000 ₪
        # Users 10..17
        escalating_amounts = [150000.0, 180000.0, 220000.0, 270000.0, 330000.0, 400000.0, 450000.0, 500000.0]
        for i, amt in enumerate(escalating_amounts):
            actions.append((users[10 + i], f"Escalating_{i}", amt))

        expected_winner = users[17]  # Placed 500,000 ₪
        expected_winning_bid = 500000.0

        # Shuffle tasks
        random.seed(999)
        random.shuffle(actions)

        tasks = [
            asyncio.create_task(place_auction_bid(db, auc_id, uid, name, amt, "b"))
            for uid, name, amt in actions
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify no crash
        for r in results:
            assert not isinstance(r, Exception)
            assert isinstance(r, dict)

        # Check winner
        async with db.execute("SELECT current_bid, current_winner_id FROM Auctions WHERE id = ?", (auc_id,)) as c:
            row = await c.fetchone()
            cur_bid, cur_winner = row[0], row[1]

        assert cur_winner == expected_winner
        assert cur_bid == expected_winning_bid

        # Check all balances
        for uid in users:
            bal = await common.database.get_user_global_balance(db, uid)
            if uid == expected_winner:
                assert bal == initial_balances[uid] - expected_winning_bid
            else:
                assert bal == initial_balances[uid]

        # Check conservation
        total_now = sum([await common.database.get_user_global_balance(db, uid) for uid in users])
        assert round(total_now + cur_bid, 2) == round(initial_total, 2)


# =============================================================================
# 2. WHALE SAFE PRICE & BURN TESTS: 10 CONSECUTIVE OPENINGS
# =============================================================================

class TestAdversarialWhaleSafePricingAndBurn:
    """Adversarial verification of Whale Safe exponential pricing and 70% burn."""

    def test_whale_safe_price_formula_mathematical_precision(self):
        """
        Validates exact mathematical formula P(n) = int(50000 * (1.5 ** n))
        for 10 consecutive openings (n = 0 to 9).
        """
        expected_progression = [
            (0, 50000),
            (1, 75000),
            (2, 112500),
            (3, 168750),
            (4, 253125),
            (5, 379687),
            (6, 569531),
            (7, 854296),
            (8, 1281445),
            (9, 1922167),
        ]

        for n, expected_price in expected_progression:
            calculated = calculate_whale_safe_price(n)
            assert calculated == expected_price, (
                f"Price mismatch at n={n}: calculated {calculated}, expected {expected_price}"
            )
            # Verify formula match
            exact_formula = int(50000 * (1.5 ** n))
            assert calculated == exact_formula

    @pytest.mark.asyncio
    async def test_whale_safe_10_consecutive_openings_pricing_and_70pct_burn(self, isolated_test_db):
        """
        Simulate 10 consecutive safe openings by a single whale user.
        Verifies:
        1. For each opening n in [0..9]:
           - Price charged equals exactly P(n) = int(50000 * 1.5^n).
           - Exactly 70% (round(price * 0.70, 2)) is burned into Abu Yacht Fund.
           - opened_today counter increments from 1 up to 10.
        2. Cumulative Abu Yacht Fund burn matches sum of 70% of each price.
        3. User balance decreases by net cost (price - cashback/prizes).
        4. Zero deadlocks or errors during execution.
        """
        db = isolated_test_db
        user_id = 82001

        # Calculate total price required for 10 safes
        expected_prices = [calculate_whale_safe_price(n) for n in range(10)]
        total_gross_cost = sum(expected_prices)
        assert total_gross_cost == 5666501  # Sum of all 10 prices

        # Fund user with 20,000,000 ₪
        initial_balance = 20000000.0
        await common.database.add_user_global_balance(db, user_id, "b", initial_balance)

        fund_initial = await common.database.get_abu_fund_total(db)
        cumulative_expected_burn = 0.0
        cumulative_cashback = 0.0

        for n in range(10):
            exp_price = expected_prices[n]
            exp_burn = round(exp_price * 0.70, 2)
            cumulative_expected_burn += exp_burn

            bal_before_step = await common.database.get_user_global_balance(db, user_id)
            fund_before_step = await common.database.get_abu_fund_total(db)

            # Purchase safe
            res = await buy_whale_safe(db, user_id, "b")

            # Assert operation succeeded
            assert res["ok"] is True, f"Failed at opening #{n+1}: {res.get('error')}"
            assert res["price"] == exp_price, (
                f"Opening #{n+1}: expected price {exp_price}, got {res['price']}"
            )
            assert res["burned_to_abu"] == exp_burn, (
                f"Opening #{n+1}: expected 70% burn {exp_burn}, got {res['burned_to_abu']}"
            )
            assert res["opened_today"] == n + 1, (
                f"Opening #{n+1}: expected opened_today {n+1}, got {res['opened_today']}"
            )

            # Check immediate Abu Fund increment
            fund_after_step = await common.database.get_abu_fund_total(db)
            step_fund_diff = round(fund_after_step - fund_before_step, 2)
            assert step_fund_diff == exp_burn, (
                f"Opening #{n+1}: Abu Fund increased by {step_fund_diff}, expected {exp_burn}"
            )

            # Check user balance change
            cashback = res.get("final_cash", 0)
            cumulative_cashback += cashback
            bal_after_step = await common.database.get_user_global_balance(db, user_id)
            expected_bal = bal_before_step - exp_price + cashback
            assert round(bal_after_step, 2) == round(expected_bal, 2), (
                f"Opening #{n+1}: User balance was {bal_after_step}, expected {expected_bal}"
            )

        # Verify cumulative total burn into Abu Yacht Fund across all 10 openings
        fund_final = await common.database.get_abu_fund_total(db)
        total_fund_increase = round(fund_final - fund_initial, 2)
        assert total_fund_increase == round(cumulative_expected_burn, 2), (
            f"Cumulative burn mismatch: {total_fund_increase} vs expected {cumulative_expected_burn}"
        )

        # Expected total burned: 70% of 5,666,501 = 3,966,550.70 ₪
        assert total_fund_increase == 3966550.70

        # Verify final user balance matches initial - gross_cost + all_cashbacks
        final_balance = await common.database.get_user_global_balance(db, user_id)
        expected_final_balance = initial_balance - total_gross_cost + cumulative_cashback
        assert round(final_balance, 2) == round(expected_final_balance, 2)

    @pytest.mark.asyncio
    async def test_whale_safe_11th_opening_rejection_on_insufficient_funds(self, isolated_test_db):
        """
        Verifies rejection when user has enough balance for 10 safes but not the 11th.
        - First 10 succeed with escalating prices and 70% burn.
        - 11th safe costs P(10) = int(50000 * 1.5^10) = 2,883,251 ₪.
        - Attempting 11th safe with insufficient balance returns ok=False and leaves Abu Fund untouched.
        """
        db = isolated_test_db
        user_id = 82002

        prices = [calculate_whale_safe_price(n) for n in range(10)]
        price_10th = calculate_whale_safe_price(10)
        assert price_10th == 2883251

        # Fund user with exact sum of first 10 prices (any cashback is ignored by subtracting it)
        # Give them 5,666,501 ₪
        await common.database.add_user_global_balance(db, user_id, "b", 5666501.0)

        for n in range(10):
            res = await buy_whale_safe(db, user_id, "b")
            assert res["ok"] is True
            # Deduct cashback if any to keep balance below 11th price
            if res.get("final_cash", 0) > 0:
                await common.database.deduct_user_global_balance(
                    db, user_id, "b", res["final_cash"]
                )

        # Balance is now 0 ₪
        bal = await common.database.get_user_global_balance(db, user_id)
        assert bal == 0.0

        fund_before_11 = await common.database.get_abu_fund_total(db)

        # 11th safe attempt must fail
        res_fail = await buy_whale_safe(db, user_id, "b")
        assert res_fail["ok"] is False
        assert "Недостаточно шекелей" in res_fail["error"]
        assert "2,883,251" in res_fail["error"]

        # Abu Fund must not change
        fund_after_11 = await common.database.get_abu_fund_total(db)
        assert fund_after_11 == fund_before_11


# =============================================================================
# 3. AUCTION FINALIZATION & 100% BURN INTEGRATION
# =============================================================================

class TestAuctionFinalizationIntegration:
    """Verifies auction lifecycle completion after concurrency races."""

    @pytest.mark.asyncio
    async def test_auction_completion_burns_100_percent_of_winning_bid(self, isolated_test_db):
        """
        After concurrent bids, when the auction expires:
        - finish_active_auctions() marks status = 'finished'.
        - Exactly 100% of the winning bid is burned into Abu Yacht Fund.
        - The winning user is awarded the lot.
        """
        db = isolated_test_db
        await ensure_auction_schema(db)

        auc_id = await create_auction(
            db, "custom_role", "Архимаг", "[Архимаг Двача]", 100000.0, 10000.0, 1.0
        )
        winner_id = 83001
        await common.database.add_user_global_balance(db, winner_id, "b", 300000.0)

        # Place winning bid of 250,000 ₪
        res = await place_auction_bid(db, auc_id, winner_id, "Archmage", 250000.0)
        assert res["ok"] is True

        # Expire auction
        past = time.time() - 10
        await db.execute("UPDATE Auctions SET ends_at = ? WHERE id = ?", (past, auc_id))

        fund_before = await common.database.get_abu_fund_total(db)
        finished = await finish_active_auctions(db)

        assert len(finished) == 1
        assert finished[0]["auction_id"] == auc_id
        assert finished[0]["winning_bid"] == 250000.0
        assert finished[0]["winner_id"] == winner_id

        # 100% of winning bid burned
        fund_after = await common.database.get_abu_fund_total(db)
        assert round(fund_after - fund_before, 2) == 250000.0

        # Status updated in DB
        async with db.execute("SELECT status FROM Auctions WHERE id = ?", (auc_id,)) as c:
            row = await c.fetchone()
            assert row[0] == "finished"

        # Winner custom prefix updated
        async with db.execute("SELECT custom_prefix FROM Users WHERE user_id = ?", (winner_id,)) as c:
            row = await c.fetchone()
            assert row[0] == "[Архимаг Двача]"
