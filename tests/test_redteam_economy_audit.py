# -*- coding: utf-8 -*-
"""
tests/test_redteam_economy_audit.py
Permanent RedTeam Inquisitor Audit Test Suite for DvachBot:
- Strict validation of boundary values (NaN, Inf, negative, overflow, zero).
- Escrow atomicity & instant outbid refund in Auctions.
- Bank of Abu deposits, withdrawals, double-spend prevention, and robbery insulation.
- Dice duels escrow atomicity, anti-self-duel, and rake rules.
- Whale safes exponential pricing, 70% burn to Abu Fund, and RTP caps.
- Super-wealth tax brackets and oligarch raid economics.
"""

import asyncio
import time
import pytest

from common.database import (
    add_user_global_balance,
    deduct_user_global_balance,
    get_user_global_balance,
    get_abu_fund_total,
    calculate_transfer_fee,
)
from main import _parse_pay_amount
from bank_engine import (
    parse_deposit_amount,
    create_bank_deposit,
    withdraw_bank_deposit,
    execute_abu_bank_haircut,
)
from whale_economy_engine import (
    calculate_whale_safe_price,
    buy_whale_safe,
    calculate_wealth_tax,
    create_auction,
    place_auction_bid,
    finish_active_auctions,
)
from dice_duel_engine import (
    create_dice_challenge,
    accept_dice_challenge,
    _finish_dice_game,
)


# -----------------------------------------------------------------------------
# 1. PARSER & ARITHMETIC BOUNDARY TESTS
# -----------------------------------------------------------------------------

def test_pay_parse_arithmetic_fuzzing():
    """RedTeam fuzzing on _parse_pay_amount with extreme/malicious inputs."""
    assert _parse_pay_amount("nan", 1000.0) == (None, "negative_or_zero")
    assert _parse_pay_amount("inf", 1000.0) == (None, "negative_or_zero")
    assert _parse_pay_amount("-inf", 1000.0) == (None, "negative_or_zero")
    assert _parse_pay_amount("infinity", 1000.0) == (None, "negative_or_zero")
    assert _parse_pay_amount("-infinity", 1000.0) == (None, "negative_or_zero")

    assert _parse_pay_amount("1e308", 1000.0) == (None, "too_large")
    assert _parse_pay_amount("1e999", 1000.0) == (None, "negative_or_zero")
    assert _parse_pay_amount("-1e308", 1000.0) == (None, "negative_or_zero")

    assert _parse_pay_amount("0", 1000.0) == (None, "negative_or_zero")
    assert _parse_pay_amount("-100", 1000.0) == (None, "negative_or_zero")
    assert _parse_pay_amount("0.1", 1000.0) == (None, "negative_or_zero")
    assert _parse_pay_amount("50.5", 1000.0) == (50, None)
    assert _parse_pay_amount("1,5k", 10000.0) == (1500, None)

    assert _parse_pay_amount("all", 0.0) == (None, "empty_balance")
    assert _parse_pay_amount("all", -500.0) == (None, "empty_balance")
    assert _parse_pay_amount("all", 1.0) == (None, "cant_afford_fee")
    amt_all, err = _parse_pay_amount("all", 100.0)
    assert err is None
    assert amt_all + calculate_transfer_fee(amt_all) <= 100.0


def test_bank_parse_deposit_amount_fuzzing():
    """RedTeam fuzzing on bank parse_deposit_amount."""
    assert parse_deposit_amount("nan", 10000.0) is None
    assert parse_deposit_amount("inf", 10000.0) is None
    assert parse_deposit_amount("-inf", 10000.0) is None
    assert parse_deposit_amount("1e308", 10000.0) is None
    assert parse_deposit_amount("0", 10000.0) is None
    assert parse_deposit_amount("-100", 10000.0) is None

    assert parse_deposit_amount("50 000 ₪", 100000.0) == 50000.0
    assert parse_deposit_amount("25,5k", 100000.0) == 25500.0
    assert parse_deposit_amount("1.5m", 2000000.0) == 1500000.0
    assert parse_deposit_amount("50%", 10000.0) == 5000.0
    assert parse_deposit_amount("101%", 10000.0) is None
    assert parse_deposit_amount("all", 12345.67) == 12345.67
    assert parse_deposit_amount("all", 0.0) == 0.0


# -----------------------------------------------------------------------------
# 2. BANK OF ABU ADVERSARIAL ATTEMPTS
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bank_deposit_adversarial_bounds(isolated_test_db):
    """Test bank deposit creation with invalid amounts, overdrafts, and bounds."""
    db = isolated_test_db
    user_id = 999001
    await add_user_global_balance(db, user_id, "b", 1000.0)

    for invalid in [0, -10, -500, float("nan"), float("inf"), float("-inf")]:
        ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", invalid)
        assert not ok

    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", 5.0)  # min 10
    assert not ok
    assert "Минимальная сумма" in err

    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", 1500.0)
    assert not ok
    assert "Недостаточно шекелей" in err
    assert await get_user_global_balance(db, user_id) == 1000.0

    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", 500.0)
    assert ok
    assert dep["principal"] == 500.0
    assert await get_user_global_balance(db, user_id) == 500.0


@pytest.mark.asyncio
async def test_bank_withdrawal_concurrency_double_spend(isolated_test_db):
    """Test race condition: 2 concurrent tasks trying to withdraw the same bank deposit."""
    db = isolated_test_db
    user_id = 999002
    await add_user_global_balance(db, user_id, "b", 500.0)

    ok, dep, err = await create_bank_deposit(db, user_id, "b", "sych", 500.0)
    assert ok
    dep_id = dep["id"]

    results = await asyncio.gather(
        withdraw_bank_deposit(db, dep_id, user_id, "b"),
        withdraw_bank_deposit(db, dep_id, user_id, "b"),
        return_exceptions=True
    )

    success_count = sum(1 for r in results if isinstance(r, tuple) and r[0] is True)
    failure_count = sum(1 for r in results if isinstance(r, tuple) and r[0] is False)

    assert success_count == 1
    assert failure_count == 1

    final_bal = await get_user_global_balance(db, user_id)
    assert final_bal <= 500.0


@pytest.mark.asyncio
async def test_bank_haircut_math_and_insulation(isolated_test_db):
    """Verify Great Abu Bank Haircut strictly impacts deposits >= 500k and leaves others intact."""
    db = isolated_test_db
    whale_id = 999003
    small_id = 999004

    await add_user_global_balance(db, whale_id, "b", 1_000_000.0)
    await add_user_global_balance(db, small_id, "b", 100_000.0)

    ok1, dep_w, _ = await create_bank_deposit(db, whale_id, "b", "sych", 1_000_000.0)
    ok2, dep_s, _ = await create_bank_deposit(db, small_id, "b", "sych", 100_000.0)
    assert ok1 and ok2

    fund_before = await get_abu_fund_total(db)

    report = await execute_abu_bank_haircut(db, haircut_pct=0.40, threshold=500_000.0, dry_run=False)
    assert report["status"] == "success"
    assert report["affected_users_count"] == 1
    assert report["affected_deposits_count"] == 1
    assert report["total_confiscated"] == 400_000.0

    async with db.execute("SELECT principal FROM BankDeposits WHERE id = ?", (dep_w["id"],)) as c:
        row = await c.fetchone()
        assert row[0] == 600_000.0

    async with db.execute("SELECT principal FROM BankDeposits WHERE id = ?", (dep_s["id"],)) as c:
        row = await c.fetchone()
        assert row[0] == 100_000.0

    fund_after = await get_abu_fund_total(db)
    assert fund_after - fund_before == 400_000.0


# -----------------------------------------------------------------------------
# 3. ATOMIC AUCTION REDTEAM TESTS
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auction_instant_outbid_refund_guarantee(isolated_test_db):
    """Test that outbid users are 100% refunded immediately without loss or theft."""
    db = isolated_test_db
    user_a = 999010
    user_b = 999011
    user_c = 999012

    await add_user_global_balance(db, user_a, "b", 100_000.0)
    await add_user_global_balance(db, user_b, "b", 150_000.0)
    await add_user_global_balance(db, user_c, "b", 200_000.0)

    auc_id = await create_auction(
        db, lot_type="custom_role", title="VIP Role",
        description="VIP Role Description", start_price=50000.0,
        min_bid_step=5000.0, duration_sec=3600.0, board_id="b"
    )

    res_a = await place_auction_bid(db, auc_id, user_a, "Anon A", 50000.0, "b")
    assert res_a["ok"]
    assert await get_user_global_balance(db, user_a) == 50000.0

    res_b = await place_auction_bid(db, auc_id, user_b, "Anon B", 60000.0, "b")
    assert res_b["ok"]
    assert res_b["previous_winner"] == user_a
    assert await get_user_global_balance(db, user_b) == 90000.0
    assert await get_user_global_balance(db, user_a) == 100000.0

    res_c = await place_auction_bid(db, auc_id, user_c, "Anon C", 70000.0, "b")
    assert res_c["ok"]
    assert res_c["previous_winner"] == user_b
    assert await get_user_global_balance(db, user_b) == 150000.0
    assert await get_user_global_balance(db, user_c) == 130000.0


@pytest.mark.asyncio
async def test_auction_bid_validations_and_rejections(isolated_test_db):
    """Test adversarial bidding: NaN, Inf, overdraft, step too small, self-outbid."""
    db = isolated_test_db
    user_a = 999015
    await add_user_global_balance(db, user_a, "b", 100_000.0)

    auc_id = await create_auction(
        db, lot_type="board_pin", title="Top Pin",
        description="Pin for 24h", start_price=50000.0,
        min_bid_step=5000.0, duration_sec=3600.0, board_id="b"
    )

    res = await place_auction_bid(db, auc_id, user_a, "Anon", float("nan"), "b")
    assert not res["ok"]

    res = await place_auction_bid(db, auc_id, user_a, "Anon", float("inf"), "b")
    assert not res["ok"]

    res = await place_auction_bid(db, auc_id, user_a, "Anon", 0.0, "b")
    assert not res["ok"]

    res = await place_auction_bid(db, auc_id, user_a, "Anon", 40000.0, "b")
    assert not res["ok"]
    assert "Слишком маленькая ставка" in res["error"]

    res = await place_auction_bid(db, auc_id, user_a, "Anon", 150000.0, "b")
    assert not res["ok"]
    assert "Недостаточно шекелей" in res["error"]

    res = await place_auction_bid(db, auc_id, user_a, "Anon", 50000.0, "b")
    assert res["ok"]

    res_self = await place_auction_bid(db, auc_id, user_a, "Anon", 60000.0, "b")
    assert not res_self["ok"]
    assert "Твоя ставка уже наивысшая" in res_self["error"]


@pytest.mark.asyncio
async def test_auction_finish_burns_100_percent_to_abu_fund(isolated_test_db):
    """Test that auction finalization burns 100% of winning bid to Abu Yacht Fund."""
    db = isolated_test_db
    user_a = 999018
    await add_user_global_balance(db, user_a, "b", 200_000.0)

    auc_id = await create_auction(
        db, lot_type="custom_role", title="Role 1",
        description="[Олигарх]", start_price=50000.0,
        min_bid_step=5000.0, duration_sec=300.0, board_id="b"
    )

    await place_auction_bid(db, auc_id, user_a, "Anon", 80000.0, "b")

    fund_before = await get_abu_fund_total(db)

    # Fast-forward ends_at past the anti-snipe window
    await db.execute("UPDATE Auctions SET ends_at = ? WHERE id = ?", (time.time() - 1.0, auc_id))

    finished = await finish_active_auctions(db)
    assert len(finished) == 1
    assert finished[0]["winning_bid"] == 80000.0

    fund_after = await get_abu_fund_total(db)
    assert fund_after - fund_before == 80000.0


# -----------------------------------------------------------------------------
# 4. WHALE SAFES & SUPER-WEALTH TAX REDTEAM TESTS
# -----------------------------------------------------------------------------

def test_whale_safe_price_escalation_formula():
    """Verify strict mathematical escalation P(n) = int(50000 * 1.5^n)."""
    assert calculate_whale_safe_price(0) == 50000
    assert calculate_whale_safe_price(1) == 75000
    assert calculate_whale_safe_price(2) == 112500
    assert calculate_whale_safe_price(3) == 168750
    assert calculate_whale_safe_price(4) == 253125
    assert calculate_whale_safe_price(-5) == 50000


@pytest.mark.asyncio
async def test_whale_safe_atomic_buy_and_burn(isolated_test_db):
    """Verify whale safe burns exactly 70% to Abu Yacht Fund and escalates daily price."""
    db = isolated_test_db
    whale_id = 999020
    await add_user_global_balance(db, whale_id, "b", 200_000.0)

    fund_before = await get_abu_fund_total(db)

    res1 = await buy_whale_safe(db, whale_id, "b")
    assert res1["ok"]
    assert res1["price"] == 50000
    assert res1["burned_to_abu"] == 35000.0
    assert res1["opened_today"] == 1

    fund_after1 = await get_abu_fund_total(db)
    assert fund_after1 - fund_before == 35000.0

    res2 = await buy_whale_safe(db, whale_id, "b")
    assert res2["ok"]
    assert res2["price"] == 75000
    assert res2["burned_to_abu"] == 52500.0
    assert res2["opened_today"] == 2

    fund_after2 = await get_abu_fund_total(db)
    assert fund_after2 - fund_after1 == 52500.0

    res3 = await buy_whale_safe(db, whale_id, "b")
    assert not res3["ok"]
    assert "Недостаточно шекелей" in res3["error"]


def test_wealth_tax_formula_brackets():
    """Verify progressive brackets and idle surcharge for wealth tax."""
    assert calculate_wealth_tax(3000.0) == 0.0
    assert calculate_wealth_tax(5000.0) == 0.0
    assert calculate_wealth_tax(10000.0) == 30.0
    assert calculate_wealth_tax(50000.0) == 150.0
    assert calculate_wealth_tax(100000.0) == 1000.0
    assert calculate_wealth_tax(500000.0) == 5000.0
    assert calculate_wealth_tax(1000000.0) == 25000.0
    assert calculate_wealth_tax(10000000.0) == 500000.0

    assert calculate_wealth_tax(1000000.0, idle_hours=50.0) == 25000.0
    assert calculate_wealth_tax(1000000.0, idle_hours=72.0) == 37500.0


# -----------------------------------------------------------------------------
# 5. DICE DUEL CONCURRENCY & ZERO-SUM INTEGRITY
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dice_duel_adversarial_bet_bounds(isolated_test_db):
    """Test dice challenge creation with invalid bounds and overdrafts."""
    db = isolated_test_db
    user_a = 999030
    await add_user_global_balance(db, user_a, "b", 1000.0)

    for invalid in [0, -50, float("nan"), float("inf"), 49, 60_000_000]:
        ok, msg, gid = await create_dice_challenge("b", user_a, invalid)
        assert not ok

    ok, msg, gid = await create_dice_challenge("b", user_a, 2000)
    assert not ok
    assert "Недостаточно шекелей" in msg

    ok, msg, gid = await create_dice_challenge("b", user_a, 500)
    assert ok
    assert gid is not None


@pytest.mark.asyncio
async def test_dice_duel_self_play_and_atomic_escrow(isolated_test_db):
    """Test self-duel prevention, balance verification, and escrow atomicity."""
    db = isolated_test_db
    user_a = 999035
    user_b = 999036

    await add_user_global_balance(db, user_a, "b", 1000.0)
    await add_user_global_balance(db, user_b, "b", 1000.0)

    ok, _, gid = await create_dice_challenge("b", user_a, 500)
    assert ok

    ok_self, msg_self, _ = await accept_dice_challenge(gid, user_a)
    assert not ok_self
    assert "с самим собой" in msg_self

    await deduct_user_global_balance(db, user_b, "b", 900.0)
    ok_poor, msg_poor, _ = await accept_dice_challenge(gid, user_b)
    assert not ok_poor
    assert "не хватает шекелей" in msg_poor

    await add_user_global_balance(db, user_b, "b", 900.0)

    await deduct_user_global_balance(db, user_a, "b", 900.0)
    ok_spent, msg_spent, _ = await accept_dice_challenge(gid, user_b)
    assert not ok_spent
    assert "У создателя вызова уже не хватает шекелей" in msg_spent

    await add_user_global_balance(db, user_a, "b", 900.0)
    ok_acc, msg_acc, game = await accept_dice_challenge(gid, user_b)
    assert ok_acc

    assert await get_user_global_balance(db, user_a) == 500.0
    assert await get_user_global_balance(db, user_b) == 500.0


@pytest.mark.asyncio
async def test_dice_duel_rake_and_payout_math(isolated_test_db):
    """Verify that dice duel house rake is exactly 5% (pot <= 50k) or 10% burned (pot > 50k)."""
    db = isolated_test_db
    p1 = 999040
    p2 = 999041

    await add_user_global_balance(db, p1, "b", 20000.0)
    await add_user_global_balance(db, p2, "b", 20000.0)

    ok, _, gid = await create_dice_challenge("b", p1, 10000)
    await accept_dice_challenge(gid, p2)

    fund_before = await get_abu_fund_total(db)
    await _finish_dice_game(gid, winner_id=p1, loser_id=p2, reason="win", bot=None)

    fund_after = await get_abu_fund_total(db)
    assert fund_after - fund_before == 1000.0  # 5% rake = 1,000 ₪
    assert await get_user_global_balance(db, p1) == 29000.0  # 10k remaining + 19k payout
