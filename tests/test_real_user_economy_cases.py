# -*- coding: utf-8 -*-
"""
tests/test_real_user_economy_cases.py — Deep resilience tests covering:
1. Bank of Abu (bank_engine.py):
   - calculate_deposit_state with zero principal (wealth tax), malformed inputs, expired/negative lockup
   - atomic withdrawal and balance replenishment via db_transaction
   - zero-value deposit withdrawal safety
2. Work Engine (common/work_engine.py & cb_work_do logic):
   - cooldown spam protection returning human-readable time without exceptions
   - shift fine soft overdraft protection for zero and partial balances
3. Market Engine (market_engine.py):
   - lot cancellation (/market cancel) returning items cleanly without loss or duplication
   - repeated cancellation idempotency and anti-duplication
   - non-owner cancellation rejection
"""

import math
import time
from unittest.mock import AsyncMock, patch
import pytest

from bank_engine import (
    calculate_deposit_state,
    create_bank_deposit,
    withdraw_bank_deposit,
    get_tier_info,
    BANK_TIERS,
)
from common.work_engine import execute_job_action, WORK_VACANCIES
from market_engine import (
    ensure_market_schema,
    create_market_listing,
    cancel_market_listing,
    _load_user_active_items_for_update,
    _save_user_active_items,
    restore_item_to_active_items,
    extract_item_for_escrow,
)
from common.database import (
    add_user_global_balance,
    deduct_user_global_balance,
    get_user_global_balance,
)


# =============================================================================
# 1. BANK ENGINE TESTS
# =============================================================================

class TestBankEngineCases:
    def test_calculate_deposit_state_zero_principal_wealth_tax(self):
        """
        Verify that a deposit whose principal was reduced to 0 by wealth tax
        does not divide by zero, does not return NaN, and preserves accrued interest.
        """
        raw_dep = {
            "id": 156,
            "user_id": 5536235634,
            "tier_id": "mmm_abu",
            "principal": 0.0,
            "daily_rate": 0.06,
            "created_at": 1789548142.0,
            "locked_until": 1789634542.0,
            "last_accrual_at": 1795309201.0,
            "accrued_interest": 4229189.75,
            "status": "active"
        }
        state = calculate_deposit_state(raw_dep, current_ts=1795309300.0)

        assert state["principal"] == 0.0
        assert not math.isnan(state["accrued_interest"])
        assert not math.isinf(state["accrued_interest"])
        assert state["accrued_interest"] == 4229189.75
        assert state["total_value"] == 4229189.75
        assert state["is_locked"] is False
        assert state["remaining_lock_sec"] == 0

    def test_calculate_deposit_state_malformed_inputs(self):
        """
        Verify that malformed inputs (NaN, Inf, negative rates, None) are sanitized
        and do not crash or propagate NaN into financial records.
        """
        malformed_dep = {
            "id": 999,
            "principal": float("nan"),
            "daily_rate": -0.5,
            "accrued_interest": float("inf"),
            "created_at": None,
            "locked_until": -100.0,
            "last_accrual_at": float("nan"),
        }
        state = calculate_deposit_state(malformed_dep, current_ts=float("nan"))

        assert state["principal"] == 0.0
        assert not math.isnan(state["total_value"])
        assert not math.isinf(state["total_value"])
        assert state["total_value"] >= 0.0
        assert state["remaining_lock_sec"] >= 0

    def test_calculate_deposit_state_expired_and_negative_lock(self):
        """
        Verify that expired deposits correctly transition lock status and calculate remaining time as 0.
        """
        now = time.time()
        expired_dep = {
            "id": 101,
            "tier_id": "skuf",
            "principal": 1000.0,
            "daily_rate": 0.025,
            "created_at": now - 300000,
            "locked_until": now - 50000,
            "last_accrual_at": now - 10000,
            "accrued_interest": 75.0,
            "status": "active"
        }
        state = calculate_deposit_state(expired_dep, current_ts=now)

        assert state["is_locked"] is False
        assert state["remaining_lock_sec"] == 0
        assert state["remaining_lock_text"] == "0 сек."
        assert state["total_value"] >= 1075.0

    @pytest.mark.asyncio
    async def test_bank_withdraw_atomic_balance_replenishment(self, isolated_test_db):
        """
        Verify that closing an unlocked deposit atomically credits the user's wallet
        and updates BankDeposits status to 'withdrawn'.
        """
        user_id = 88001
        board_id = "b"
        deposit_amount = 500.0

        # Fund user wallet
        await add_user_global_balance(isolated_test_db, user_id, board_id, 1000.0)

        # Create deposit
        ok, dep, err = await create_bank_deposit(
            db=isolated_test_db,
            user_id=user_id,
            board_id=board_id,
            tier_id="sych",  # sych is flexible, no lockup
            amount=deposit_amount
        )
        assert ok is True
        dep_id = dep["id"]

        bal_after_dep = await get_user_global_balance(isolated_test_db, user_id)
        assert bal_after_dep == 500.0

        # Withdraw deposit
        ok_w, payout, principal, interest, fee, is_def, err_w = await withdraw_bank_deposit(
            db=isolated_test_db,
            deposit_id=dep_id,
            user_id=user_id,
            board_id=board_id
        )
        assert ok_w is True
        assert payout > 0
        assert principal == deposit_amount

        bal_after_with = await get_user_global_balance(isolated_test_db, user_id)
        assert bal_after_with == 500.0 + payout

    @pytest.mark.asyncio
    async def test_bank_withdraw_zero_payout_safety(self, isolated_test_db):
        """
        Verify that withdrawing a deposit with 0 total value (e.g. completely taxed)
        succeeds cleanly, updates status, and does not crash or corrupt balance.
        """
        user_id = 88002
        board_id = "b"

        now = time.time()
        # Insert a 0-principal 0-accrued active deposit directly
        async with isolated_test_db.execute(
            """
            INSERT INTO BankDeposits (
                user_id, board_id, tier_id, principal, daily_rate,
                created_at, locked_until, last_accrual_at, accrued_interest, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, board_id, "sych", 0.0, 0.005, now - 1000, now - 1000, now - 10, 0.0, "active")
        ) as cur:
            dep_id = cur.lastrowid

        ok_w, payout, principal, interest, fee, is_def, err_w = await withdraw_bank_deposit(
            db=isolated_test_db,
            deposit_id=dep_id,
            user_id=user_id,
            board_id=board_id
        )
        assert ok_w is True
        assert payout == 0.0
        assert principal == 0.0

        # Check DB status is withdrawn
        async with isolated_test_db.execute(
            "SELECT status, withdrawn_amount FROM BankDeposits WHERE id = ?", (dep_id,)
        ) as c:
            row = await c.fetchone()
            assert row[0] == "withdrawn"
            assert row[1] == 0.0


# =============================================================================
# 2. WORK ENGINE TESTS
# =============================================================================

class TestWorkEngineCases:
    def test_work_cooldown_spam_clear_error_message(self):
        """
        Verify that spamming a job during cooldown returns a clear, helpful message
        with exact countdown format instead of an unhandled error or None.
        """
        user_id = 77001
        job_id = "bottles"
        now = int(time.time())

        # First shift succeeds
        items = {"work_shifts": 0, "work_cooldowns": {}}
        res1 = execute_job_action(job_id, items, user_id=user_id)
        assert res1[0] is True or res1[1] > 0  # Either success or fine

        # Immediate second call during cooldown
        res2 = execute_job_action(job_id, items, user_id=user_id)
        is_success, amount, msg, dropped = res2

        assert is_success is False
        assert amount == 0
        assert "⏳ Кулдаун!" in msg
        assert ("сек" in msg or "мин" in msg or "ч" in msg)

    @pytest.mark.asyncio
    async def test_work_fine_soft_overdraft_zero_balance(self, isolated_test_db):
        """
        Verify that a work failure penalty on a zero balance wallet does not drive
        balance negative (soft overdraft protection).
        """
        user_id = 77002
        board_id = "b"
        penalty_amount = 50.0

        # Ensure user balance is 0
        cur_bal = await get_user_global_balance(isolated_test_db, user_id)
        assert cur_bal == 0.0

        # Simulate the exact deduction logic from cb_work_do (main.py:13072-13086)
        ok, rem_bal = await deduct_user_global_balance(isolated_test_db, user_id, board_id, penalty_amount)
        if not ok and penalty_amount > 0:
            cur_bal = await get_user_global_balance(isolated_test_db, user_id)
            if cur_bal > 0:
                await deduct_user_global_balance(isolated_test_db, user_id, board_id, cur_bal)

        final_bal = await get_user_global_balance(isolated_test_db, user_id)
        assert final_bal == 0.0
        assert final_bal >= 0.0

    @pytest.mark.asyncio
    async def test_work_fine_soft_overdraft_partial_balance(self, isolated_test_db):
        """
        Verify that when user has positive balance less than the fine,
        only the available balance is deducted, clamping the wallet to exactly 0.
        """
        user_id = 77003
        board_id = "b"
        initial_balance = 20.0
        penalty_amount = 60.0

        await add_user_global_balance(isolated_test_db, user_id, board_id, initial_balance)

        # Simulate the exact deduction logic from cb_work_do (main.py:13072-13086)
        ok, rem_bal = await deduct_user_global_balance(isolated_test_db, user_id, board_id, penalty_amount)
        if not ok and penalty_amount > 0:
            cur_bal = await get_user_global_balance(isolated_test_db, user_id)
            if cur_bal > 0:
                await deduct_user_global_balance(isolated_test_db, user_id, board_id, cur_bal)

        final_bal = await get_user_global_balance(isolated_test_db, user_id)
        assert final_bal == 0.0


# =============================================================================
# 3. MARKET ENGINE TESTS
# =============================================================================

class TestMarketEngineCases:
    @pytest.mark.asyncio
    async def test_market_cancel_returns_item_to_inventory(self, isolated_test_db):
        """
        Verify that listing an item and cancelling it restores the item to the seller's inventory.
        """
        await ensure_market_schema(isolated_test_db)
        user_id = 66001
        board_id = "b"

        # Give seller a permanent apparel item and a weapon
        initial_items = {
            "owned_body_tracksuit": True,
            "body_tracksuit_is_permanent": True,
            "knife_gun": True,
        }
        await _save_user_active_items(isolated_test_db, user_id, board_id, initial_items)

        # Create listing for tracksuit
        ok_list, listing, err_list = await create_market_listing(
            db=isolated_test_db,
            seller_id=user_id,
            seller_board_id=board_id,
            item_id="body_tracksuit",
            price=250.0
        )
        assert ok_list is True
        lot_id = listing["id"]

        # Verify item was removed from inventory (escrow locked)
        items_escrow = await _load_user_active_items_for_update(isolated_test_db, user_id, board_id)
        assert not items_escrow.get("owned_body_tracksuit")
        assert not items_escrow.get("body_tracksuit_is_permanent")

        # Cancel listing
        ok_cancel, item_dict, err_cancel = await cancel_market_listing(
            db=isolated_test_db,
            lot_id=lot_id,
            user_id=user_id,
            board_id=board_id
        )
        assert ok_cancel is True
        assert err_cancel == ""

        # Verify item returned to inventory
        items_restored = await _load_user_active_items_for_update(isolated_test_db, user_id, board_id)
        assert items_restored.get("owned_body_tracksuit") is True
        assert items_restored.get("body_tracksuit_is_permanent") is True

    @pytest.mark.asyncio
    async def test_market_cancel_no_duplication_on_repeated_cancel(self, isolated_test_db):
        """
        Verify that double-cancelling a lot fails on the second attempt
        and does NOT duplicate the item in inventory.
        """
        await ensure_market_schema(isolated_test_db)
        user_id = 66002
        board_id = "b"

        # Setup consumable pills (starts with 1)
        initial_items = {"pills_count": 1, "pills_gun": True}
        await _save_user_active_items(isolated_test_db, user_id, board_id, initial_items)

        ok_list, listing, _ = await create_market_listing(
            db=isolated_test_db,
            seller_id=user_id,
            seller_board_id=board_id,
            item_id="pills",
            price=100.0
        )
        assert ok_list is True
        lot_id = listing["id"]

        # First cancellation succeeds
        ok1, _, _ = await cancel_market_listing(isolated_test_db, lot_id, user_id, board_id)
        assert ok1 is True

        items_after_first = await _load_user_active_items_for_update(isolated_test_db, user_id, board_id)
        assert items_after_first.get("pills_count") == 1

        # Second cancellation fails immediately
        ok2, _, err2 = await cancel_market_listing(isolated_test_db, lot_id, user_id, board_id)
        assert ok2 is False
        assert "уже не активен" in err2

        # Item count must remain 1 (no duplication)
        items_after_second = await _load_user_active_items_for_update(isolated_test_db, user_id, board_id)
        assert items_after_second.get("pills_count") == 1

    @pytest.mark.asyncio
    async def test_market_cancel_non_owner_rejection(self, isolated_test_db):
        """
        Verify that a non-owner cannot cancel another user's lot.
        """
        await ensure_market_schema(isolated_test_db)
        owner_id = 66003
        hacker_id = 66004
        board_id = "b"

        initial_items = {"knife_gun": True}
        await _save_user_active_items(isolated_test_db, owner_id, board_id, initial_items)

        ok_list, listing, _ = await create_market_listing(
            db=isolated_test_db,
            seller_id=owner_id,
            seller_board_id=board_id,
            item_id="knife",
            price=300.0
        )
        assert ok_list is True
        lot_id = listing["id"]

        # Hacker tries to cancel
        ok_cancel, _, err = await cancel_market_listing(isolated_test_db, lot_id, hacker_id, board_id)
        assert ok_cancel is False
        assert "не являетесь владельцем" in err

        # Verify lot remains active
        async with isolated_test_db.execute(
            "SELECT status FROM MarketListings WHERE id = ?", (lot_id,)
        ) as c:
            row = await c.fetchone()
            assert row[0] == "active"
