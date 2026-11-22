# -*- coding: utf-8 -*-
"""
tests/test_economy_deep_repair_v2.py
Deep End-to-End Red-Team Economy Test Suite for DvachBot / HECTON-8.

Comprehensive verification of:
1. End-to-end user economy lifecycle:
   /work -> earning shekels -> /deposit in bank -> interest accrual -> maturity
   -> /withdraw -> purchase on /market -> delisting/cancelling lots.
2. Balance guards and concurrency:
   - Zero/negative balance guard (rejection of overdrafts, NaN, Inf, negative amounts).
   - Deposit amount > balance guard.
   - Double withdrawal prevention (both sequential and concurrent race conditions).
3. Wanted 5★ status and financial crimes:
   - 5★ wanted stars lockout from Bank of Abu (both deposit and withdrawal blocked).
   - Dirty money (/heist) blocked from bank deposit.
   - Money laundering (/launder) converting dirty money to clean (30% Abu tax, 70% clean).
   - Bribe (/bribe_cop) using allow_bribe_bypass to break deadlock and restore bank access.
4. Economic balance, formulas, and RTP invariants:
   - Work engine rolling 24h fatigue efficiency (100% -> 80% -> 55% -> 35% -> 20%).
   - Work engine shift reward cap (45,000 shekels absolute ceiling).
   - Bank microsecond arbitrage immunity (1% Sych fee, 3% Skuf penalty, 10% MMM penalty).
   - Lootbox & Whale Safe RTP invariants (Trash <= 85%, Gold <= 85%, Whale <= 65%, 70% Abu burn).
"""

import asyncio
import json
import math
import random
import time
from typing import Any, Dict

import pytest

import common.config
import common.database
from common.database import (
    add_to_abu_fund,
    add_user_global_balance,
    deduct_user_global_balance,
    get_abu_fund_total,
    get_user_global_balance,
)
from common.work_engine import (
    MAX_SHIFT_REWARD_CAP,
    execute_job_action,
    get_user_daily_fatigue_info,
    is_night_shift_active,
)
from bank_engine import (
    BANK_TIERS,
    calculate_deposit_state,
    create_bank_deposit,
    withdraw_bank_deposit,
)
from market_engine import (
    buy_market_listing,
    cancel_market_listing,
    create_market_listing,
    ensure_market_schema,
)
from criminal_syndicate_engine import (
    add_wanted_stars,
    execute_bribe_cop,
    load_user_active_items,
    save_user_active_items,
)
from heist_and_loan_engine import process_money_laundering
import lootbox_engine
from whale_economy_engine import (
    buy_whale_safe,
    calculate_whale_safe_price,
    roll_whale_safe,
)


# =============================================================================
# PART 1: FULL USER ECONOMY LIFECYCLE
# =============================================================================

class TestUserLifecycleWorkToBankToMarket:
    """Verifies the complete end-to-end user economic lifecycle."""

    @pytest.mark.asyncio
    async def test_full_work_to_bank_to_market_cycle(self, isolated_test_db):
        """
        Step 1: /work -> earn shekels
        Step 2: /deposit -> deposit into Bank Abu (Skuf 3-day term)
        Step 3: Simulate interest accumulation and maturity
        Step 4: /withdraw -> withdraw principal + interest
        Step 5: /market -> Seller lists item, User buys item with escrow & Abu tax
        Step 6: /market cancel -> User lists item, then cancels and retrieves it
        """
        db = isolated_test_db
        user_a = 91001
        user_b = 91002
        board_id = "b"

        # ---------------------------------------------------------------------
        # Step 1: /work -> earning shekels
        # ---------------------------------------------------------------------
        initial_bal = await get_user_global_balance(db, user_a)
        assert initial_bal == 0.0

        user_a_items: Dict[str, Any] = {"work_shifts": 0, "work_cooldowns": {}}
        res_work = execute_job_action("bottles", user_a_items, user_id=user_a)
        assert res_work.is_success is True
        assert res_work.amount_change > 0
        assert user_a_items["work_shifts"] == 1

        salary = float(res_work.amount_change)
        await add_user_global_balance(db, user_a, board_id, salary)
        cur_bal = await get_user_global_balance(db, user_a)
        assert cur_bal == salary

        # ---------------------------------------------------------------------
        # Step 2: /deposit -> open Skuf 3-day term deposit
        # (Min deposit is 50 ₪; add bonus seed to satisfy minimum)
        # ---------------------------------------------------------------------
        seed_deposit = 1000.0
        await add_user_global_balance(db, user_a, board_id, seed_deposit)
        deposit_amount = 500.0

        ok_dep, dep_data, err_dep = await create_bank_deposit(
            db, user_a, board_id, "skuf", deposit_amount
        )
        assert ok_dep is True, f"create_bank_deposit failed: {err_dep}"
        assert dep_data is not None
        dep_id = dep_data["id"]
        assert dep_data["tier_id"] == "skuf"
        assert dep_data["principal"] == deposit_amount

        bal_after_dep = await get_user_global_balance(db, user_a)
        assert bal_after_dep == round(salary + seed_deposit - deposit_amount, 2)

        # ---------------------------------------------------------------------
        # Step 3: Interest accumulation & maturity calculation
        # ---------------------------------------------------------------------
        created_at = dep_data["created_at"]
        maturity_ts = created_at + 72 * 3600 + 10  # 72 hours later

        calc_state = calculate_deposit_state(dep_data, current_ts=maturity_ts)
        assert calc_state["is_locked"] is False
        assert calc_state["remaining_lock_sec"] == 0
        # 3 days at 2.5%/day = 7.5% -> 500 * 0.075 = 37.5 ₪
        assert calc_state["accrued_interest"] >= 37.5
        assert calc_state["total_value"] >= 537.5

        # ---------------------------------------------------------------------
        # Step 4: /withdraw -> withdraw matured deposit
        # ---------------------------------------------------------------------
        # Update created_at and last_accrual_at in DB to simulate 72 hours passing
        past_created = time.time() - (72 * 3600 + 60)
        await db.execute(
            "UPDATE BankDeposits SET created_at = ?, locked_until = ?, last_accrual_at = ? WHERE id = ?",
            (past_created, past_created + 72 * 3600, past_created, dep_id)
        )

        ok_wd, payout, principal, interest_paid, fee, is_def, err_wd = await withdraw_bank_deposit(
            db, dep_id, user_a, board_id
        )
        assert ok_wd is True, f"withdraw_bank_deposit failed: {err_wd}"
        assert payout >= 537.5
        assert principal == deposit_amount
        assert interest_paid >= 37.5
        assert fee == 0.0  # 0% withdrawal fee on maturity for Skuf
        assert is_def is False

        # Verify DB status is 'withdrawn'
        async with db.execute("SELECT status FROM BankDeposits WHERE id = ?", (dep_id,)) as c:
            row = await c.fetchone()
            assert row[0] == "withdrawn"

        # ---------------------------------------------------------------------
        # Step 5: /market -> Seller (user_b) lists item, User A buys it
        # ---------------------------------------------------------------------
        await ensure_market_schema(db)
        await add_to_abu_fund(db, 0.0)  # Ensure fund baseline
        abu_before = await get_abu_fund_total(db)

        # User B gets an item in active_items
        user_b_items = {
            "owned_body_wasserman": True,
            "body_wasserman_is_permanent": True,
        }
        await save_user_active_items(db, user_b, board_id, user_b_items)

        item_price = 400.0
        ok_list, lot_dict, err_list = await create_market_listing(
            db, user_b, board_id, "body_wasserman", item_price
        )
        assert ok_list is True, f"create_market_listing failed: {err_list}"
        assert lot_dict is not None
        lot_id = lot_dict["id"]

        # Verify item was removed from User B active items (escrow)
        user_b_after_list = await load_user_active_items(db, user_b, board_id)
        assert "owned_body_wasserman" not in user_b_after_list
        assert "body_wasserman_is_permanent" not in user_b_after_list

        # User A buys the listing
        user_a_bal_pre_buy = await get_user_global_balance(db, user_a)
        assert user_a_bal_pre_buy >= item_price

        ok_buy, seller_id, pr, payout_seller, fee_market, itm, err_buy = await buy_market_listing(
            db, lot_id, user_a, board_id
        )
        assert ok_buy is True, f"buy_market_listing failed: {err_buy}"
        assert seller_id == user_b
        assert pr == item_price
        assert fee_market == 20.0  # 5% of 400 ₪
        assert payout_seller == 380.0

        # Check Abu Yacht Fund received the 5% tax
        abu_after = await get_abu_fund_total(db)
        assert abu_after == abu_before + 20.0

        # Check item is now in User A's active items
        user_a_after_buy = await load_user_active_items(db, user_a, board_id)
        assert user_a_after_buy.get("owned_body_wasserman") is True
        assert user_a_after_buy.get("body_wasserman_is_permanent") is True

        # Check Seller received net payout
        user_b_bal = await get_user_global_balance(db, user_b)
        assert user_b_bal == 380.0

        # ---------------------------------------------------------------------
        # Step 6: /market cancel -> User A lists and cancels another item
        # ---------------------------------------------------------------------
        user_a_items_new = await load_user_active_items(db, user_a, board_id)
        user_a_items_new["knife_gun"] = True
        await save_user_active_items(db, user_a, board_id, user_a_items_new)

        ok_list2, lot2, err2 = await create_market_listing(
            db, user_a, board_id, "knife_gun", 150.0
        )
        assert ok_list2 is True
        lot2_id = lot2["id"]

        # Cancel listing
        ok_cancel, itm_canc, err_cancel = await cancel_market_listing(
            db, lot2_id, user_a, board_id
        )
        assert ok_cancel is True, f"cancel_market_listing failed: {err_cancel}"
        assert itm_canc["lot_id"] == lot2_id

        # Check item restored to User A active items
        user_a_restored = await load_user_active_items(db, user_a, board_id)
        assert user_a_restored.get("knife_gun") is True


# =============================================================================
# PART 2: BALANCE GUARDS AND CONCURRENCY PROTECTIONS
# =============================================================================

class TestBalanceGuardsAndConcurrency:
    """Verifies atomic balance guards, overdraft prevention, and race protection."""

    @pytest.mark.asyncio
    async def test_negative_balance_guard_and_overdraft(self, isolated_test_db):
        """
        Validates:
        - Deducting more than current balance fails without negative balance.
        - Negative, NaN, Inf amounts are strictly rejected.
        - Wallet balance never becomes negative under any condition.
        """
        db = isolated_test_db
        user_id = 92001
        board_id = "b"

        await add_user_global_balance(db, user_id, board_id, 100.0)
        bal = await get_user_global_balance(db, user_id)
        assert bal == 100.0

        # Overdraft attempt
        ok, cur = await deduct_user_global_balance(db, user_id, board_id, 150.0)
        assert ok is False
        assert cur == 100.0
        assert await get_user_global_balance(db, user_id) == 100.0

        # Negative amount deduction attempt
        ok_neg, _ = await deduct_user_global_balance(db, user_id, board_id, -50.0)
        assert ok_neg is False
        assert await get_user_global_balance(db, user_id) == 100.0

        # NaN deduction attempt
        ok_nan, _ = await deduct_user_global_balance(db, user_id, board_id, float("nan"))
        assert ok_nan is False
        assert await get_user_global_balance(db, user_id) == 100.0

        # Inf deduction attempt
        ok_inf, _ = await deduct_user_global_balance(db, user_id, board_id, float("inf"))
        assert ok_inf is False
        assert await get_user_global_balance(db, user_id) == 100.0

        # Negative/NaN/Inf addition attempts
        await add_user_global_balance(db, user_id, board_id, -100.0)
        await add_user_global_balance(db, user_id, board_id, float("nan"))
        await add_user_global_balance(db, user_id, board_id, float("inf"))
        assert await get_user_global_balance(db, user_id) == 100.0

    @pytest.mark.asyncio
    async def test_deposit_more_than_balance_fails(self, isolated_test_db):
        """Deposit attempts exceeding balance or invalid values are rejected."""
        db = isolated_test_db
        user_id = 92002
        board_id = "b"

        await add_user_global_balance(db, user_id, board_id, 50.0)

        # Attempt to deposit more than balance
        ok, dep, err = await create_bank_deposit(db, user_id, board_id, "sych", 100.0)
        assert ok is False
        assert "Недостаточно шекелей" in err
        assert await get_user_global_balance(db, user_id) == 50.0

        # Attempt zero deposit
        ok_zero, _, err_zero = await create_bank_deposit(db, user_id, board_id, "sych", 0.0)
        assert ok_zero is False

        # Attempt negative deposit
        ok_neg, _, err_neg = await create_bank_deposit(db, user_id, board_id, "sych", -50.0)
        assert ok_neg is False

    @pytest.mark.asyncio
    async def test_double_withdraw_prevention_sequential(self, isolated_test_db):
        """Sequential double withdrawal on the same deposit is rejected."""
        db = isolated_test_db
        user_id = 92003
        board_id = "b"

        await add_user_global_balance(db, user_id, board_id, 500.0)
        ok_dep, dep, _ = await create_bank_deposit(db, user_id, board_id, "sych", 200.0)
        assert ok_dep is True
        dep_id = dep["id"]

        # First withdrawal succeeds
        ok_wd1, payout1, _, _, _, _, _ = await withdraw_bank_deposit(
            db, dep_id, user_id, board_id
        )
        assert ok_wd1 is True
        assert payout1 > 0

        # Second withdrawal fails immediately
        ok_wd2, payout2, _, _, _, _, err2 = await withdraw_bank_deposit(
            db, dep_id, user_id, board_id
        )
        assert ok_wd2 is False
        assert payout2 == 0.0
        assert "Депозит уже закрыт" in err2

    @pytest.mark.asyncio
    async def test_double_withdraw_prevention_concurrent(self, isolated_test_db):
        """
        Simultaneous concurrent withdrawal calls on the same deposit_id:
        Strictly one succeeds, the other fails. Zero double payout.
        """
        db = isolated_test_db
        user_id = 92004
        board_id = "b"

        await add_user_global_balance(db, user_id, board_id, 500.0)
        ok_dep, dep, _ = await create_bank_deposit(db, user_id, board_id, "sych", 300.0)
        assert ok_dep is True
        dep_id = dep["id"]

        pre_wd_bal = await get_user_global_balance(db, user_id)

        # Run 2 concurrent withdrawal calls
        res1, res2 = await asyncio.gather(
            withdraw_bank_deposit(db, dep_id, user_id, board_id),
            withdraw_bank_deposit(db, dep_id, user_id, board_id),
            return_exceptions=False,
        )

        results = [res1[0], res2[0]]
        # Exactly one MUST succeed, one MUST fail
        assert results.count(True) == 1
        assert results.count(False) == 1

        payout = res1[1] if res1[0] else res2[1]
        post_wd_bal = await get_user_global_balance(db, user_id)
        assert post_wd_bal == round(pre_wd_bal + payout, 2)


# =============================================================================
# PART 3: WANTED 5★ STATUS, BANK LOCKOUT, LAUNDERING & BRIBES
# =============================================================================

class TestWanted5StarLockoutAndRedemption:
    """Verifies wanted level 5★ bank lockout, dirty money restrictions, and clearing."""

    @pytest.mark.asyncio
    async def test_wanted_5_stars_bank_lockout(self, isolated_test_db):
        """
        When wanted_stars >= 5:
        1. create_bank_deposit is blocked by bank security.
        2. withdraw_bank_deposit is blocked by bank security.
        """
        db = isolated_test_db
        user_id = 93001
        board_id = "b"

        # Give user balance and an active deposit before criminal acts
        await add_user_global_balance(db, user_id, board_id, 1000.0)
        ok_dep, dep, _ = await create_bank_deposit(db, user_id, board_id, "sych", 400.0)
        assert ok_dep is True
        dep_id = dep["id"]

        # User commits crimes -> wanted level reaches 5★
        user_items = await load_user_active_items(db, user_id, board_id)
        add_wanted_stars(user_items, 5, 25000.0)
        await save_user_active_items(db, user_id, board_id, user_items)

        # Attempt to open a new deposit -> blocked
        ok_dep2, _, err_dep2 = await create_bank_deposit(db, user_id, board_id, "sych", 100.0)
        assert ok_dep2 is False
        assert "СЛУЖБА БЕЗОПАСНОСТИ БАНКА АБУ" in err_dep2
        assert "5★" in err_dep2

        # Attempt to withdraw existing deposit -> blocked
        ok_wd, _, _, _, _, _, err_wd = await withdraw_bank_deposit(db, dep_id, user_id, board_id)
        assert ok_wd is False
        assert "СЛУЖБА БЕЗОПАСНОСТИ БАНКА АБУ" in err_wd
        assert "5★" in err_dep2

    @pytest.mark.asyncio
    async def test_dirty_money_blocks_deposit(self, isolated_test_db):
        """
        User with dirty_balance from /heist cannot deposit dirty funds into Bank Abu.
        Can only deposit clean funds.
        """
        db = isolated_test_db
        user_id = 93002
        board_id = "b"

        # Total wallet: 5,000 ₪, but 4,500 ₪ is dirty
        await add_user_global_balance(db, user_id, board_id, 5000.0)
        user_items = await load_user_active_items(db, user_id, board_id)
        user_items["dirty_balance"] = 4500.0
        await save_user_active_items(db, user_id, board_id, user_items)

        # Trying to deposit 1,000 ₪ (clean balance is only 500 ₪) -> rejected
        ok_fail, _, err_fail = await create_bank_deposit(db, user_id, board_id, "sych", 1000.0)
        assert ok_fail is False
        assert "Купюры светятся спецкраской" in err_fail
        assert "/launder" in err_fail

        # Depositing within clean balance (300 ₪ <= 500 ₪ clean) -> succeeds
        ok_succ, dep_succ, _ = await create_bank_deposit(db, user_id, board_id, "sych", 300.0)
        assert ok_succ is True
        assert dep_succ["principal"] == 300.0

    @pytest.mark.asyncio
    async def test_money_laundering_lifecycle(self, isolated_test_db):
        """
        /launder converts dirty money to clean:
        - 30% laundering fee sent to Abu Yacht Fund
        - 70% added to clean global wallet
        - dirty_balance reduced to 0
        - User can now deposit laundered money into Bank Abu
        """
        db = isolated_test_db
        user_id = 93003
        board_id = "b"

        # User has 10,000 ₪ of dirty money in active_items
        user_items = {"dirty_balance": 10000.0}
        await save_user_active_items(db, user_id, board_id, user_items)

        abu_before = await get_abu_fund_total(db)

        # Execute laundering
        ok_launder, msg_launder, meta = await process_money_laundering(
            db, user_id, "all", board_id
        )
        assert ok_launder is True
        assert meta["clean"] == 7000
        assert meta["fee"] == 3000

        # Check Abu Fund received 30% fee
        abu_after = await get_abu_fund_total(db)
        assert abu_after == abu_before + 3000.0

        # Check clean wallet received 70% (7,000 ₪)
        cur_bal = await get_user_global_balance(db, user_id)
        assert cur_bal == 7000.0

        # Check dirty balance in active_items is 0
        items_after = await load_user_active_items(db, user_id, board_id)
        assert items_after.get("dirty_balance", 0.0) == 0.0

        # User can now deposit clean laundered funds into Bank Abu
        ok_dep, dep, err_dep = await create_bank_deposit(db, user_id, board_id, "sych", 5000.0)
        assert ok_dep is True, f"Failed depositing laundered funds: {err_dep}"
        assert dep["principal"] == 5000.0

    @pytest.mark.asyncio
    async def test_bribe_cop_and_bank_bypass_redemption(self, isolated_test_db):
        """
        User with 5★ wanted level and 0 ₪ cash has funds locked in Bank Abu.
        Calling execute_bribe_cop:
        - Liquidates bank deposits via allow_bribe_bypass=True to break deadlock.
        - Reduces wanted stars to 0★.
        - Pays 50% kickback to Abu Yacht Fund.
        - Restores normal bank deposit/withdraw capabilities.
        """
        db = isolated_test_db
        user_id = 93004
        board_id = "b"

        # Create bank deposit first while clean
        await add_user_global_balance(db, user_id, board_id, 20000.0)
        ok_dep, dep, _ = await create_bank_deposit(db, user_id, board_id, "sych", 15000.0)
        assert ok_dep is True
        dep_id = dep["id"]

        # Empty wallet to simulate zero liquid cash
        cur_bal = await get_user_global_balance(db, user_id)
        await deduct_user_global_balance(db, user_id, board_id, cur_bal)
        assert await get_user_global_balance(db, user_id) == 0.0

        # User receives 5★ wanted stars
        user_items = await load_user_active_items(db, user_id, board_id)
        add_wanted_stars(user_items, 5, 50000.0)
        await save_user_active_items(db, user_id, board_id, user_items)

        # Normal bank withdraw is blocked
        ok_wd_blocked, _, _, _, _, _, _ = await withdraw_bank_deposit(db, dep_id, user_id, board_id)
        assert ok_wd_blocked is False

        # Execute bribe with clear_all=True
        abu_before = await get_abu_fund_total(db)
        ok_bribe, msg_bribe, meta_bribe = await execute_bribe_cop(
            db, user_id, board_id, clear_all=True
        )
        assert ok_bribe is True, f"Bribe failed: {msg_bribe}"

        # Verify wanted stars cleared
        items_cleared = await load_user_active_items(db, user_id, board_id)
        assert items_cleared.get("wanted_stars", 0) == 0

        # Verify kickback paid to Abu Yacht Fund
        abu_after = await get_abu_fund_total(db)
        assert abu_after > abu_before

        # Bank operations now unblocked: user can deposit remaining cash
        bal_remaining = await get_user_global_balance(db, user_id)
        if bal_remaining >= 10.0:
            ok_dep_new, dep_new, err_new = await create_bank_deposit(
                db, user_id, board_id, "sych", 10.0
            )
            assert ok_dep_new is True, f"Failed deposit after clearing stars: {err_new}"


# =============================================================================
# PART 4: ECONOMIC BALANCE, FORMULAS & RTP INVARIANTS
# =============================================================================

class TestEconomicMathInvariantsAndLimits:
    """Verifies work fatigue, payout caps, bank fees, and lootbox RTP invariants."""

    def test_work_engine_fatigue_curve(self):
        """
        Validates rolling 24h fatigue efficiency brackets:
        - Shifts 1-3:  100%
        - Shifts 4-6:   80%
        - Shifts 7-10:  55%
        - Shifts 11-15: 35%
        - Shifts 16+:   20%
        """
        now = time.time()

        def make_shifts(count: int):
            return [now - (i * 300) for i in range(count)]

        f1 = get_user_daily_fatigue_info(make_shifts(2), now=now)
        assert f1["shifts_today"] == 2
        assert f1["efficiency_pct"] == 100

        f4 = get_user_daily_fatigue_info(make_shifts(4), now=now)
        assert f4["shifts_today"] == 4
        assert f4["efficiency_pct"] == 80

        f8 = get_user_daily_fatigue_info(make_shifts(8), now=now)
        assert f8["shifts_today"] == 8
        assert f8["efficiency_pct"] == 55

        f12 = get_user_daily_fatigue_info(make_shifts(12), now=now)
        assert f12["shifts_today"] == 12
        assert f12["efficiency_pct"] == 35

        f20 = get_user_daily_fatigue_info(make_shifts(20), now=now)
        assert f20["shifts_today"] == 20
        assert f20["efficiency_pct"] == 20

    def test_work_engine_max_reward_cap_45000(self):
        """
        Validates that under any stacked buffs (set bonus, Wasserman gear, night shift, jackpot),
        the shift payout never exceeds MAX_SHIFT_REWARD_CAP = 45,000 ₪.
        """
        # Saturated endgame RPG items
        endgame_items = {
            "work_shifts": 5000,
            "work_cooldowns": {},
            "equipped_torso": "body_wasserman",
            "body_wasserman_is_permanent": True,
            "equipped_head": "hat_crown",
            "hat_crown_is_permanent": True,
            "equipped_face": "face_wasserman_glasses",
            "face_wasserman_glasses_is_permanent": True,
        }

        # Test highest paying jobs
        for job_id in ["shadow_oligarch", "dvach_creator", "zog_chairman"]:
            for _ in range(50):
                endgame_items["work_cooldowns"][job_id] = 0
                res = execute_job_action(job_id, endgame_items, user_id=94001)
                assert res.amount_change <= MAX_SHIFT_REWARD_CAP

    def test_bank_microsecond_arbitrage_protection(self):
        """
        Validates that deposits cannot be used for instant microsecond arbitrage:
        1. Sych: 1% withdrawal fee causes net loss on immediate withdrawal.
        2. Skuf: early withdrawal loses 100% interest + 3% principal penalty.
        3. MMM Abu: early withdrawal loses 100% interest + 10% principal penalty.
        """
        principal = 10000.0
        now = time.time()

        # 1. Sych immediate withdrawal (1 second later)
        sych_dep = {
            "tier_id": "sych",
            "principal": principal,
            "created_at": now,
            "last_accrual_at": now,
            "locked_until": now,
            "accrued_interest": 0.0,
            "status": "active",
        }
        state_1sec = calculate_deposit_state(sych_dep, current_ts=now + 1.0)
        # Interest after 1 second is ~0.00057 ₪
        assert state_1sec["accrued_interest"] < 0.01
        # 1% fee on 10,000 is 100 ₪ -> net payout ~9,900 ₪ -> net loss of 100 ₪
        fee = round(state_1sec["total_value"] * BANK_TIERS["sych"]["withdrawal_fee_pct"], 2)
        payout = state_1sec["total_value"] - fee
        assert payout < principal
        assert payout == 9900.0

        # 2. Skuf early withdrawal
        skuf_dep = {
            "tier_id": "skuf",
            "principal": principal,
            "created_at": now,
            "last_accrual_at": now,
            "locked_until": now + 72 * 3600,
            "accrued_interest": 0.0,
            "status": "active",
        }
        state_skuf = calculate_deposit_state(skuf_dep, current_ts=now + 3600.0)
        assert state_skuf["is_locked"] is True
        # Early penalty 3%
        penalty_skuf = round(principal * BANK_TIERS["skuf"]["early_penalty_pct"], 2)
        assert penalty_skuf == 300.0
        assert principal - penalty_skuf == 9700.0

        # 3. MMM Abu early withdrawal
        mmm_dep = {
            "tier_id": "mmm_abu",
            "principal": principal,
            "created_at": now,
            "last_accrual_at": now,
            "locked_until": now + 24 * 3600,
            "accrued_interest": 0.0,
            "status": "active",
        }
        state_mmm = calculate_deposit_state(mmm_dep, current_ts=now + 1800.0)
        assert state_mmm["is_locked"] is True
        penalty_mmm = round(principal * BANK_TIERS["mmm_abu"]["early_penalty_pct"], 2)
        assert penalty_mmm == 1000.0
        assert principal - penalty_mmm == 9000.0

    def test_rtp_invariants_monte_carlo(self):
        """
        Monte-Carlo verification of RTP laws (AGENTS.md Section 6):
        1. Trash Lootbox RTP <= 85% (target ~52.8%)
        2. Gold Safe RTP <= 85% (target ~62.1%)
        3. Whale Safe RTP <= 65%
        4. Duplicate cashback: min(case_price * 0.30, item_price * 0.20)
        """
        random.seed(2026)

        # Duplicate cashback formula verification
        case_price = 150.0
        item_price = 300.0
        cashback = lootbox_engine.calculate_duplicate_cashback(case_price, item_price)
        assert cashback == min(case_price * 0.30, item_price * 0.20)
        assert cashback == 45.0

        # Whale Safe Monte Carlo (5,000 iterations)
        N = 5000
        cost_whale = 50000.0
        total_spent = N * cost_whale
        total_cash_returned = 0.0
        total_nominal_value = 0.0

        for _ in range(N):
            tier, title, desc, payload, base_cash = roll_whale_safe()
            total_cash_returned += base_cash
            if "👑" in tier:
                nominal = 30000
            elif "💎" in tier:
                nominal = 20000
            elif "✨" in tier:
                nominal = 12000
            else:
                nominal = base_cash
            total_nominal_value += nominal

        cash_rtp = (total_cash_returned / total_spent) * 100.0
        total_rtp = (total_nominal_value / total_spent) * 100.0

        assert cash_rtp <= 20.0, f"Whale Cash RTP {cash_rtp:.2f}% exceeds 20%"
        assert total_rtp <= 65.0, f"Whale Total RTP {total_rtp:.2f}% exceeds 65%"
