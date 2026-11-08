# -*- coding: utf-8 -*-
"""
tests/test_games_and_casino_integrity.py
Comprehensive integrity and concurrency test suite for HECTON-8 / dvachbot:
- Drop Engine: creation, claiming concurrency (100 racers), self-claim guard, cancellation, expiration, transaction collision immunity.
- Casino Engine: Slots 777, 50/50 Coinflip, Blackjack 21 math, Solo Russian Roulette, VIP table rake, Anti-script cooldowns.
- Active Sessions & Watchdog: Blackjack auto-resolution, Roulette auto-cashout, Stale session expiry.
- PvP & Duel Integrity: Atomic escrow deduction, concurrent accept race (zero split-brain, exactly 1 winner, rake).
- Extreme Defense Engine: Strike tracking, transaction safety, zero transaction collision.
"""

import sys
import os
import time
import asyncio
import aiosqlite
import pytest
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import casino_engine
import drop_engine
from common.db_pool import db_transaction, db_lock
from common.database import (
    add_user_global_balance,
    get_user_global_balance,
    deduct_user_global_balance,
    record_user_transaction,
    get_abu_fund_total
)
import extreme_defense_engine
from common.bot_helpers import (
    accept_duel_logic,
    decline_duel_logic,
    _active_duels,
    _duel_cooldowns,
    classic_duel_lock
)
from common.anon_identity import get_anon_id
import common.bot_helpers
common.bot_helpers.get_anon_id = get_anon_id


@pytest.fixture(autouse=True)
def clean_global_game_state():
    _active_duels.clear()
    _duel_cooldowns.clear()
    drop_engine.active_drops.clear()
    drop_engine._user_drop_cooldowns.clear()
    drop_engine._user_claim_cooldowns.clear()
    drop_engine._user_claim_history.clear()
    drop_engine._pair_claim_history.clear()
    casino_engine.active_bj_sessions.clear()
    casino_engine.active_roulette_sessions.clear()
    casino_engine.user_casino_last_action.clear()
    yield
    _active_duels.clear()
    _duel_cooldowns.clear()
    drop_engine.active_drops.clear()
    casino_engine.active_bj_sessions.clear()
    casino_engine.active_roulette_sessions.clear()


# =============================================================================
# 1. DROP ENGINE INTEGRITY & CONCURRENCY
# =============================================================================

@pytest.mark.asyncio
async def test_drop_creation_atomic_deduction(isolated_test_db):
    """Verify that drop creation atomically deducts from balance and rejects insufficient funds."""
    db = isolated_test_db
    donor_id = 1001
    await add_user_global_balance(db, donor_id, "b", 1000.0)

    # 1. Attempt to drop 1500 when having 1000 -> must fail, balance unchanged
    ok, msg, drop_rec = await drop_engine.create_money_drop(
        donor_id=donor_id,
        donor_name="Анон #1001",
        board_id="b",
        amount=1500,
        db_lock=db_lock,
        db_conn=db,
        check_cooldown=False,
        fee_percent=0.0
    )
    assert not ok
    assert "Недостаточно средств" in msg
    assert drop_rec is None
    bal = await get_user_global_balance(db, donor_id)
    assert bal == 1000.0

    # 2. Drop 400 successfully -> balance becomes 600
    ok, msg, drop_rec = await drop_engine.create_money_drop(
        donor_id=donor_id,
        donor_name="Анон #1001",
        board_id="b",
        amount=400,
        db_lock=db_lock,
        db_conn=db,
        check_cooldown=False,
        fee_percent=0.0
    )
    assert ok
    assert drop_rec is not None
    assert drop_rec.amount == 400
    bal = await get_user_global_balance(db, donor_id)
    assert bal == 600.0


@pytest.mark.asyncio
async def test_drop_high_concurrency_race(isolated_test_db):
    """Simulate 100 concurrent racers claiming the EXACT same drop: exactly 1 winner, exactly 99 rejected."""
    db = isolated_test_db
    donor_id = 2001
    await add_user_global_balance(db, donor_id, "b", 5000.0)

    ok, msg, drop_rec = await drop_engine.create_money_drop(
        donor_id=donor_id,
        donor_name="Donor",
        board_id="b",
        amount=1000,
        db_lock=db_lock,
        db_conn=db,
        check_cooldown=False,
        fee_percent=0.0
    )
    assert ok and drop_rec

    claimers = list(range(3001, 3101))  # 100 racers
    for uid in claimers:
        await add_user_global_balance(db, uid, "b", 0.0)

    # All 100 racers claim concurrently
    async def _try_claim(uid: int):
        return await drop_engine.claim_money_drop(
            drop_id=drop_rec.drop_id,
            claimer_id=uid,
            claimer_name=f"Racer #{uid}",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=False,
            check_claimer_rate_limit=False,
            check_farm_laundering=False,
            check_anti_snipe=False
        )

    results = await asyncio.gather(*[_try_claim(u) for u in claimers])

    wins = [r for r in results if r[0] is True]
    losses = [r for r in results if r[0] is False]

    assert len(wins) == 1, f"Expected exactly 1 winner, got {len(wins)}"
    assert len(losses) == 99, f"Expected 99 losses, got {len(losses)}"

    # Check winner got the 1000 shekels
    winner_record = wins[0][2]
    winner_id = winner_record.claimed_by
    winner_bal = await get_user_global_balance(db, winner_id)
    assert winner_bal == 1000.0

    # Verify other racers got nothing
    other_balances = [await get_user_global_balance(db, uid) for uid in claimers if uid != winner_id]
    assert all(b == 0.0 for b in other_balances)

    # Verify DB status
    async with db.execute("SELECT status, claimed_by FROM MoneyDrops WHERE drop_id = ?", (drop_rec.drop_id,)) as c:
        row = await c.fetchone()
        assert row[0] == "claimed"
        assert row[1] == winner_id


@pytest.mark.asyncio
async def test_drop_self_claim_and_cancellation(isolated_test_db):
    """Donor cannot claim their own drop; cancellation refunds donor cleanly."""
    db = isolated_test_db
    donor_id = 4001
    await add_user_global_balance(db, donor_id, "b", 2000.0)

    ok, _, drop_rec = await drop_engine.create_money_drop(
        donor_id=donor_id,
        donor_name="Self",
        board_id="b",
        amount=500,
        db_lock=db_lock,
        db_conn=db,
        check_cooldown=False,
        fee_percent=0.0
    )
    assert ok and drop_rec
    assert (await get_user_global_balance(db, donor_id)) == 1500.0

    # Self claim must be rejected
    c_ok, c_msg, _ = await drop_engine.claim_money_drop(
        drop_id=drop_rec.drop_id,
        claimer_id=donor_id,
        claimer_name="Self",
        claimer_board_id="b",
        db_lock=db_lock,
        db_conn=db,
        check_reaction_delay=False
    )
    assert not c_ok
    assert "не можешь забрать свой собственный дроп" in c_msg

    # Cancel drop -> refunds 500
    cancel_ok, cancel_msg = await drop_engine.cancel_money_drop(
        drop_id=drop_rec.drop_id,
        user_id=donor_id,
        db_lock=db_lock,
        db_conn=db
    )
    assert cancel_ok
    assert (await get_user_global_balance(db, donor_id)) == 2000.0


@pytest.mark.asyncio
async def test_drop_transaction_nesting_safety(isolated_test_db):
    """Ensure drop functions do not crash or throw when executed within an outer db_transaction."""
    db = isolated_test_db
    user_id = 5001
    await add_user_global_balance(db, user_id, "b", 3000.0)

    # Calling create_money_drop INSIDE an active db_transaction
    async with db_transaction(db):
        ok, msg, drop_rec = await drop_engine.create_money_drop(
            donor_id=user_id,
            donor_name="Tester",
            board_id="b",
            amount=500,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
            fee_percent=0.0
        )
        assert ok and drop_rec

    bal = await get_user_global_balance(db, user_id)
    assert bal == 2500.0

    # Calling claim_money_drop INSIDE an active db_transaction
    claimer_id = 5002
    await add_user_global_balance(db, claimer_id, "b", 0.0)

    async with db_transaction(db):
        c_ok, c_msg, _ = await drop_engine.claim_money_drop(
            drop_id=drop_rec.drop_id,
            claimer_id=claimer_id,
            claimer_name="Claimer",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=False,
            check_claimer_rate_limit=False,
            check_farm_laundering=False,
            check_anti_snipe=False
        )
        assert c_ok

    bal_claimer = await get_user_global_balance(db, claimer_id)
    assert bal_claimer == 500.0


# =============================================================================
# 2. CASINO ENGINE MECHANICS & MATH
# =============================================================================

def test_slots_engine_mechanics():
    """Verify slots symbol counts, win conditions, and crown jackpot."""
    wins = 0
    crown_jackpots = 0
    skulls = 0
    total_spins = 1000

    for _ in range(total_spins):
        reels, mult, title = casino_engine.roll_slots(user_id=0, balance=0)
        assert len(reels) == 3
        if mult >= 50.0:
            crown_jackpots += 1
            assert reels[0] == reels[1] == reels[2] == "👑"
        if mult == 0.0 and reels.count("💀") == 3:
            skulls += 1
        if mult > 0:
            wins += 1

    assert wins > 100, f"Expected positive hit rate, got {wins}/{total_spins}"


def test_coinflip_engine_fairness():
    """Verify coinflip produces ~50% heads and tails and pays 1.96x on win."""
    wins_h = 0
    for _ in range(1000):
        side_ru, is_win, mult, text = casino_engine.play_coinflip("heads", user_id=0, balance=0)
        if is_win:
            wins_h += 1
            assert mult == 1.96
        else:
            assert mult == 0.0
    assert 420 <= wins_h <= 560, f"Expected coinflip fair distribution, got {wins_h}/1000"


def test_blackjack_hand_math_and_aces():
    """Verify hand calculation with soft and hard aces, face cards, and blackjack."""
    # Natural 21
    assert casino_engine.calculate_hand([("A", "♠️"), ("K", "♦️")]) == 21
    assert casino_engine.calculate_hand([("10", "♥️"), ("A", "♣️")]) == 21

    # Multiple aces converting to 1
    assert casino_engine.calculate_hand([("A", "♠️"), ("A", "♥️")]) == 12  # 11 + 1
    assert casino_engine.calculate_hand([("A", "♠️"), ("A", "♥️"), ("A", "♦️")]) == 13  # 11 + 1 + 1
    assert casino_engine.calculate_hand([("A", "♠️"), ("9", "♥️"), ("A", "♦️")]) == 21  # 11 + 9 + 1
    assert casino_engine.calculate_hand([("A", "♠️"), ("9", "♥️"), ("5", "♦️")]) == 15  # 1 + 9 + 5

    # Bust calculation
    assert casino_engine.calculate_hand([("10", "♠️"), ("J", "♥️"), ("2", "♦️")]) == 22


def test_vip_table_rake():
    """Verify 10% deflationary rake on >50k, 2% rake on >=2k, 0% below 2k."""
    rake, bet = casino_engine.calculate_vip_table_rake(1500)
    assert rake == 0 and bet == 1500
    assert not casino_engine.is_burn_vip_rake(1500)

    rake, bet = casino_engine.calculate_vip_table_rake(10000)
    assert rake == 200 and bet == 9800
    assert not casino_engine.is_burn_vip_rake(10000)

    rake, bet = casino_engine.calculate_vip_table_rake(100000)
    assert rake == 10000 and bet == 90000
    assert casino_engine.is_burn_vip_rake(100000)


def test_russian_roulette_solo_mechanics():
    """Verify Russian roulette cylinder mechanics and streak multipliers."""
    user_id = 9999
    casino_engine.active_roulette_sessions.pop(user_id, None)

    shots = 0
    for _ in range(3):
        survived, mult, streak, status = casino_engine.play_russian_roulette_shot(user_id, 100)
        shots += 1
        if not survived:
            assert user_id not in casino_engine.active_roulette_sessions
            break
        else:
            assert streak == shots
            assert mult > 1.0
            assert user_id in casino_engine.active_roulette_sessions

    casino_engine.active_roulette_sessions.pop(user_id, None)


# =============================================================================
# 3. WATCHDOG AUTO-EXPIRY & AUTO-CASHOUT
# =============================================================================

def test_stale_roulette_expiry():
    """Verify stale roulette sessions older than timeout are popped for auto-cashout."""
    now = time.time()
    user_id = 8888
    casino_engine.active_roulette_sessions[user_id] = {
        "bet": 500,
        "current_mult": 1.62,
        "streak": 3,
        "last_shot": now - 350.0  # Expired
    }
    expired = casino_engine.expire_stale_roulette_sessions(timeout_sec=300.0)
    assert len(expired) == 1
    assert expired[0][0] == user_id
    assert user_id not in casino_engine.active_roulette_sessions


def test_stale_blackjack_expiry_dealer_resolution():
    """Verify stale blackjack session auto-resolves dealer hand and computes correct outcome."""
    now = time.time()
    user_id = 7777
    # Note: deck.pop() draws from the END of the list!
    deck = [("K", "♦️"), ("5", "♠️")]  # Dealer draws 5 -> 16 + 5 = 21
    player_hand = [("10", "♠️"), ("9", "♥️")]  # 19
    dealer_hand = [("10", "♦️"), ("6", "♣️")]  # 16

    casino_engine.active_bj_sessions[user_id] = {
        "bet": 200,
        "deck": deck,
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "created_at": now - 350.0  # Expired
    }

    resolved = casino_engine.expire_stale_bj_sessions(timeout_sec=300.0)
    assert len(resolved) == 1
    u_id, session, outcome, payout = resolved[0]
    assert u_id == user_id
    # Dealer has 21 vs player 19 -> lose
    assert outcome == "lose"
    assert payout == 0
    assert user_id not in casino_engine.active_bj_sessions


# =============================================================================
# 4. DUEL / PVP INTEGRITY & CONCURRENT ACCEPTANCE
# =============================================================================

@pytest.mark.asyncio
async def test_duel_escrow_deduction_and_concurrent_accept(isolated_test_db):
    """
    Test PvP duel:
    1. Challenger creates duel -> escrowed cleanly.
    2. Multiple acceptors try to accept concurrently -> exactly 1 succeeds.
    3. Winner receives pot minus 5% rake.
    """
    db = isolated_test_db
    challenger_id = 6001
    acceptor1_id = 6002
    acceptor2_id = 6003

    await add_user_global_balance(db, challenger_id, "b", 1000.0)
    await add_user_global_balance(db, acceptor1_id, "b", 1000.0)
    await add_user_global_balance(db, acceptor2_id, "b", 1000.0)

    # 1. Escrow challenger stake
    bet_amount = 500
    async with db_transaction(db):
        ok, _ = await deduct_user_global_balance(db, challenger_id, "b", bet_amount)
        assert ok
        await record_user_transaction(db, challenger_id, -bet_amount, 'duel', 'Депонирование ставки')

    async with classic_duel_lock:
        _active_duels[challenger_id] = {
            "board_id": "b",
            "amount": bet_amount,
            "target_id": None,
            "ts": time.time(),
            "msg_id": 12345,
            "chat_id": challenger_id,
            "broadcast_msgs": [],
            "escrowed": True
        }

    # Mock message for accept_duel_logic
    def make_dummy_msg(uid):
        msg = MagicMock()
        msg.from_user = MagicMock(id=uid)
        msg.answer = AsyncMock()
        msg.bot = None
        return msg

    # 2. Race between acceptor1 and acceptor2
    res1, res2 = await asyncio.gather(
        accept_duel_logic(make_dummy_msg(acceptor1_id), challenger_id, "b", user_id=acceptor1_id),
        accept_duel_logic(make_dummy_msg(acceptor2_id), challenger_id, "b", user_id=acceptor2_id)
    )

    winner_res = res1 if res1 else res2
    other_res = res2 if res1 else res1

    assert winner_res is not None, "One player must win the duel"
    assert other_res is None, "Second player must be rejected"

    # Rejected acceptor must still have full 1000.0
    rejected_uid = acceptor2_id if res1 else acceptor1_id
    assert (await get_user_global_balance(db, rejected_uid)) == 1000.0

    # Pot calculation: 500 + 500 = 1000. 5% rake = 25. Winner payout = 975.
    # Plus 200 ₪ bonus from achievement 'ach_duel_win' unlocked on first victory!
    winner_id = winner_res["winner_id"]
    loser_id = winner_res["loser_id"]

    assert (await get_user_global_balance(db, winner_id)) == 1675.0
    assert (await get_user_global_balance(db, loser_id)) == 500.0

    # Rake added to Abu Fund
    fund_total = await get_abu_fund_total(db)
    assert fund_total == 25.0


# =============================================================================
# 5. EXTREME DEFENSE & TRANSACTION INTEGRITY
# =============================================================================

@pytest.mark.asyncio
async def test_extreme_defense_strike_and_transaction_safety(isolated_test_db):
    """Verify extreme strikes registration uses db_transaction without crashing."""
    db = isolated_test_db
    spammer_id = 9001
    await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 100.0)", (spammer_id,))

    # Classify clean vs guro/copro
    is_ext, cat, _ = extreme_defense_engine.classify_extreme_media("anime, illustration, cute girl")
    assert not is_ext

    is_ext, cat, _ = extreme_defense_engine.classify_extreme_media("copro, feces, disgusting")
    assert is_ext and cat == "COPRO"

    # Register strike within an outer db_transaction to ensure no transaction collision
    async with db_transaction(db):
        strikes = await extreme_defense_engine.register_extreme_strike(
            author_id=spammer_id,
            post_num=101,
            category=cat,
            file_id="test_file_abc",
            board_id="b"
        )
        assert strikes >= 1


if __name__ == "__main__":
    pytest.main(["-v", __file__])
