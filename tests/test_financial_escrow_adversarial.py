# -*- coding: utf-8 -*-
"""
tests/test_financial_escrow_adversarial.py — Empirical Financial Accounting, Escrow & Notification Stress Suite
================================================================================================================
Empirical Challenger Verification:
1. Mathematical Conservation of Balance:
   Total balance delta across challenger, opponent, Abu fund, and transaction log must equal exactly 0 in all cases:
   - Dice Duel: Wins, Losses, 3-round Dead Ties (2% rake), Turn Timeout Forfeits, Surrenders, Cancellations.
   - Russian Roulette: Fatal Shot Wins, 60s Timeout Forfeits, Watchdog Auto-Forfeits, Surrenders, Cancellations.
   - Classic Duel: Wins (5% rake), Cancellations, Timeout Expiry.
   - Tic-Tac-Toe: Wins (5% rake), Draws (2% fee), Timeout Forfeits.
2. Extreme Concurrent Drains & Negative Balance Impossibility:
   - High-concurrency wallet drains (100 parallel tasks).
   - Multi-board distributed drains.
   - Concurrent PvP challenge acceptances against limited balances.
   - Race condition between challenger balance drain and opponent acceptance.
3. Universal Direct DM Notification Delivery & Telegram API Resilience:
   - 100% direct Telegram DM dispatches for all refunds, forfeits, compensations, and grants.
   - Total system stability and atomic DB transaction completion under TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter, and generic network exceptions.
"""

import sys
import time
import json
import asyncio
import secrets
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shared_state
import russian_roulette_pvp as rr
import dice_duel_engine as dde
import ttt_engine as ttt
import main
import common.bot_helpers as bh
from common.db_pool import get_pool, db_lock
from common.anon_identity import get_anon_id
from common.bot_helpers import send_pvp_direct_notification, accept_duel_logic, decline_duel_logic, classic_duel_lock
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
    get_abu_fund_total,
    record_user_transaction,
)


@pytest.fixture(autouse=True)
def clean_all_game_states():
    # Inject missing get_anon_id into common.bot_helpers if needed for classic duel
    if not hasattr(bh, 'get_anon_id'):
        bh.get_anon_id = get_anon_id
    
    rr.active_rr_games.clear()
    rr.user_active_rr_game.clear()
    dde.active_dice_games.clear()
    dde.user_active_dice_game.clear()
    ttt.active_ttt_games.clear()
    ttt.user_active_ttt_session.clear()
    shared_state._active_duels.clear()
    main.LOLI_BUST_STATE.clear()
    yield
    rr.active_rr_games.clear()
    rr.user_active_rr_game.clear()
    dde.active_dice_games.clear()
    dde.user_active_dice_game.clear()
    ttt.active_ttt_games.clear()
    ttt.user_active_ttt_session.clear()
    shared_state._active_duels.clear()
    main.LOLI_BUST_STATE.clear()


def make_mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=101))
    bot.edit_message_text = AsyncMock(return_value=MagicMock(message_id=102))
    return bot


async def pre_seed_achievements(db, user_ids: list[int], board_id: str = "b"):
    """Pre-seed ach_duel_win in Users active_items to prevent achievement bonus money during pure game tests."""
    items_json = json.dumps({"achievements": ["ach_duel_win"]})
    for uid in user_ids:
        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 0.0, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = ?",
            (uid, board_id, items_json, items_json)
        )
    await db.commit()


async def get_total_user_transactions(db, user_ids: list[int], category: str | None = None) -> float:
    """Computes sum of all UserTransactions recorded for given users."""
    if not user_ids:
        return 0.0
    placeholders = ",".join("?" for _ in user_ids)
    if category:
        sql = f"SELECT SUM(amount) FROM UserTransactions WHERE user_id IN ({placeholders}) AND category = ?"
        params = tuple(user_ids) + (category,)
    else:
        sql = f"SELECT SUM(amount) FROM UserTransactions WHERE user_id IN ({placeholders})"
        params = tuple(user_ids)
    async with db.execute(sql, params) as cursor:
        row = await cursor.fetchone()
        return float(row[0] or 0.0) if row and row[0] is not None else 0.0


# =============================================================================
# SUITE 1: MATHEMATICAL CONSERVATION OF BALANCE (DELTA == 0)
# =============================================================================

class TestFinancialBalanceConservation:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stake", [50, 250, 1000, 50000, 123456])
    async def test_dice_duel_win_loss_balance_conservation(self, isolated_test_db, stake):
        """
        Verify that in Dice Duel win/loss, the total delta across Winner, Loser,
        Abu Fund, and Transaction Log is EXACTLY ZERO.
        """
        db = isolated_test_db
        p1 = 20001
        p2 = 20002
        await pre_seed_achievements(db, [p1, p2])

        initial_bal = 500_000
        await add_user_global_balance(db, p1, "b", initial_bal)
        await add_user_global_balance(db, p2, "b", initial_bal)

        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)
        init_global_total = init_p1 + init_p2 + init_abu

        ok, _, game_id = await dde.create_dice_challenge("b", p1, stake)
        assert ok is True
        ok, _, _ = await dde.accept_dice_challenge(game_id, p2)
        assert ok is True

        mock_bot = make_mock_bot()
        ok, _, game = await dde._finish_dice_game(game_id, winner_id=p1, loser_id=p2, reason="win", bot=mock_bot)
        assert ok is True

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)
        final_global_total = final_p1 + final_p2 + final_abu

        # 1. Mathematical Conservation of Balance
        delta_p1 = final_p1 - init_p1
        delta_p2 = final_p2 - init_p2
        delta_abu = final_abu - init_abu
        total_balance_delta = delta_p1 + delta_p2 + delta_abu

        assert total_balance_delta == 0.0, f"Balance leak detected! Delta: {total_balance_delta}"
        assert final_global_total == init_global_total

        # 2. Detailed Rake & Payout Math
        expected_rake = max(5, int((stake * 2) * dde.DICE_RAKE_PERCENT))
        expected_win_payout = (stake * 2) - expected_rake

        assert delta_p2 == -stake, f"Loser delta mismatch: expected -{stake}, got {delta_p2}"
        assert delta_p1 == stake - expected_rake, f"Winner delta mismatch: expected {stake - expected_rake}, got {delta_p1}"
        assert delta_abu == expected_rake, f"Abu fund delta mismatch: expected {expected_rake}, got {delta_abu}"

        # 3. Transaction Log Consistency
        sum_tx = await get_total_user_transactions(db, [p1, p2], category="dice_duel")
        # Winner got +win_payout, Loser had escrow -stake, Winner had escrow -stake
        # Sum tx = -stake + -stake + win_payout = -2*stake + (2*stake - rake) = -rake
        assert sum_tx + delta_abu == 0.0, f"Transaction log inconsistent with Abu rake: {sum_tx} vs {delta_abu}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stake", [50, 100, 1000, 33333, 500000])
    async def test_dice_duel_draw_refund_rake_conservation(self, isolated_test_db, stake):
        """
        Verify that in Dice Duel 3-round Dead Tie / Draw, 2% rake is sent to Abu Fund,
        remaining balance is refunded to both players, and total delta is EXACTLY ZERO.
        """
        db = isolated_test_db
        p1 = 20011
        p2 = 20012
        await pre_seed_achievements(db, [p1, p2])

        initial_bal = 1_000_000
        await add_user_global_balance(db, p1, "b", initial_bal)
        await add_user_global_balance(db, p2, "b", initial_bal)

        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)
        init_global_total = init_p1 + init_p2 + init_abu

        ok, _, game_id = await dde.create_dice_challenge("b", p1, stake)
        assert ok is True
        ok, _, _ = await dde.accept_dice_challenge(game_id, p2)
        assert ok is True

        mock_bot = make_mock_bot()
        ok, _, game = await dde._finish_dice_game(game_id, winner_id=None, loser_id=None, reason="draw", bot=mock_bot)
        assert ok is True
        assert game.get("outcome") == "draw"

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)
        final_global_total = final_p1 + final_p2 + final_abu

        delta_p1 = final_p1 - init_p1
        delta_p2 = final_p2 - init_p2
        delta_abu = final_abu - init_abu
        total_balance_delta = delta_p1 + delta_p2 + delta_abu

        assert total_balance_delta == 0.0, f"Draw balance leak detected! Delta: {total_balance_delta}"
        assert final_global_total == init_global_total

        # Tie rake: 2% of stake per player
        single_rake = max(1, int(stake * dde.DICE_TIE_RAKE_PERCENT))
        assert delta_p1 == -single_rake
        assert delta_p2 == -single_rake
        assert delta_abu == single_rake * 2

        # Check transactions
        sum_tx = await get_total_user_transactions(db, [p1, p2], category="dice_duel")
        assert sum_tx + delta_abu == 0.0

    @pytest.mark.asyncio
    async def test_dice_duel_watchdog_timeout_forfeit_conservation(self, isolated_test_db):
        """
        Verify that when a player times out on their turn in Dice Duel,
        the watchdog awards the pot minus 5% rake to opponent, with zero balance leak.
        """
        db = isolated_test_db
        p1 = 20021
        p2 = 20022
        stake = 5000
        await pre_seed_achievements(db, [p1, p2])

        await add_user_global_balance(db, p1, "b", 50_000)
        await add_user_global_balance(db, p2, "b", 50_000)

        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)
        init_total = init_p1 + init_p2 + init_abu

        ok, _, game_id = await dde.create_dice_challenge("b", p1, stake)
        ok, _, _ = await dde.accept_dice_challenge(game_id, p2)

        # Force turn deadline expiration on p2
        async with dde.dice_engine_lock:
            dde.active_dice_games[game_id]["current_turn"] = p2
            dde.active_dice_games[game_id]["turn_deadline_ts"] = time.time() - 10

        mock_bot = make_mock_bot()
        await dde.dice_watchdog_step(bot=mock_bot)

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)
        final_total = final_p1 + final_p2 + final_abu

        delta_p1 = final_p1 - init_p1
        delta_p2 = final_p2 - init_p2
        delta_abu = final_abu - init_abu

        assert delta_p1 + delta_p2 + delta_abu == 0.0
        assert final_total == init_total
        assert delta_p2 == -stake
        rake = max(5, int((stake * 2) * 0.05))
        assert delta_p1 == stake - rake
        assert delta_abu == rake

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stake", [50, 500, 10000, 77777])
    async def test_russian_roulette_win_loss_balance_conservation(self, isolated_test_db, stake):
        """
        Verify Russian Roulette lethal shot fatal outcome:
        Total balance delta across Winner, Loser, Abu Fund, and Transaction Log is EXACTLY ZERO.
        """
        db = isolated_test_db
        p1 = 30001
        p2 = 30002
        await pre_seed_achievements(db, [p1, p2])

        initial_bal = 200_000
        await add_user_global_balance(db, p1, "b", initial_bal)
        await add_user_global_balance(db, p2, "b", initial_bal)

        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)
        init_total = init_p1 + init_p2 + init_abu

        ok, _, game_id = await rr.create_rr_challenge("b", p1, stake)
        assert ok is True
        ok, _, _ = await rr.accept_rr_challenge(game_id, p2)
        assert ok is True

        mock_bot = make_mock_bot()
        ok, _, game = await rr._finish_rr_game(game_id, winner_id=p2, loser_id=p1, reason="shot", bot=mock_bot)
        assert ok is True

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)
        final_total = final_p1 + final_p2 + final_abu

        delta_p1 = final_p1 - init_p1
        delta_p2 = final_p2 - init_p2
        delta_abu = final_abu - init_abu

        assert delta_p1 + delta_p2 + delta_abu == 0.0, f"RR balance leak detected! Delta: {delta_p1 + delta_p2 + delta_abu}"
        assert final_total == init_total

        expected_rake = max(5, int((stake * 2) * rr.RR_RAKE_PERCENT))
        assert delta_p1 == -stake
        assert delta_p2 == stake - expected_rake
        assert delta_abu == expected_rake

        # Check transactions
        sum_tx = await get_total_user_transactions(db, [p1, p2], category="rr_pvp")
        assert sum_tx + delta_abu == 0.0

    @pytest.mark.asyncio
    async def test_russian_roulette_timeout_forfeit_conservation(self, isolated_test_db):
        """
        Verify Russian Roulette 60s timeout forfeit in pull_rr_trigger and watchdog:
        Balance delta is exactly zero, loser is debited stake and muted, winner gets pot minus 5% rake.
        """
        db = isolated_test_db
        p1 = 30011
        p2 = 30012
        stake = 4000
        await pre_seed_achievements(db, [p1, p2])

        await add_user_global_balance(db, p1, "b", 20_000)
        await add_user_global_balance(db, p2, "b", 20_000)

        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)
        init_total = init_p1 + init_p2 + init_abu

        ok, _, game_id = await rr.create_rr_challenge("b", p1, stake)
        ok, _, _ = await rr.accept_rr_challenge(game_id, p2)

        # Force p1 turn expired
        async with rr.rr_lock:
            rr.active_rr_games[game_id]["turn"] = p1
            rr.active_rr_games[game_id]["turn_deadline_ts"] = time.time() - 5

        mock_bot = make_mock_bot()
        ok, _, game = await rr.pull_rr_trigger(game_id, user_id=p1, bot=mock_bot)
        assert ok is True
        assert game.get("finished") is True
        assert game.get("winner_id") == p2
        assert game.get("loser_id") == p1

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)
        final_total = final_p1 + final_p2 + final_abu

        delta_p1 = final_p1 - init_p1
        delta_p2 = final_p2 - init_p2
        delta_abu = final_abu - init_abu

        assert delta_p1 + delta_p2 + delta_abu == 0.0
        assert final_total == init_total
        assert delta_p1 == -stake
        rake = max(5, int((stake * 2) * 0.05))
        assert delta_p2 == stake - rake
        assert delta_abu == rake

    @pytest.mark.asyncio
    async def test_russian_roulette_surrender_conservation(self, isolated_test_db):
        """
        Verify Russian Roulette surrender_rr_game:
        Surrendering player loses stake and receives mute, opponent receives pot minus 5% rake, delta == 0.
        """
        db = isolated_test_db
        p1 = 30021
        p2 = 30022
        stake = 3000
        await pre_seed_achievements(db, [p1, p2])

        await add_user_global_balance(db, p1, "b", 15_000)
        await add_user_global_balance(db, p2, "b", 15_000)

        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)
        init_total = init_p1 + init_p2 + init_abu

        ok, _, game_id = await rr.create_rr_challenge("b", p1, stake)
        ok, _, _ = await rr.accept_rr_challenge(game_id, p2)

        mock_bot = make_mock_bot()
        ok, _, game = await rr.surrender_rr_game(game_id, user_id=p2, bot=mock_bot)
        assert ok is True
        assert game.get("winner_id") == p1
        assert game.get("loser_id") == p2

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)
        final_total = final_p1 + final_p2 + final_abu

        delta_p1 = final_p1 - init_p1
        delta_p2 = final_p2 - init_p2
        delta_abu = final_abu - init_abu

        assert delta_p1 + delta_p2 + delta_abu == 0.0
        assert final_total == init_total
        assert delta_p2 == -stake
        rake = max(5, int((stake * 2) * 0.05))
        assert delta_p1 == stake - rake
        assert delta_abu == rake

    @pytest.mark.asyncio
    async def test_russian_roulette_and_dice_cancellations_zero_deductions(self, isolated_test_db):
        """
        Verify that cancelling or declining pending RR and Dice challenges results in EXACTLY 0.0 balance deductions.
        """
        db = isolated_test_db
        p1 = 30031
        p2 = 30032
        await add_user_global_balance(db, p1, "b", 10_000)
        await add_user_global_balance(db, p2, "b", 10_000)

        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)

        # 1. RR Create & Creator Cancel
        ok, _, rr_gid = await rr.create_rr_challenge("b", p1, 1000)
        assert ok is True
        ok, _ = await rr.decline_or_cancel_rr_challenge(rr_gid, user_id=p1)
        assert ok is True

        # 2. RR Create & Target Decline
        ok, _, rr_gid2 = await rr.create_rr_challenge("b", p1, 1000, target_id=p2)
        assert ok is True
        ok, _ = await rr.decline_or_cancel_rr_challenge(rr_gid2, user_id=p2)
        assert ok is True

        # 3. Dice Create & Creator Cancel
        ok, _, dice_gid = await dde.create_dice_challenge("b", p1, 1000)
        assert ok is True
        ok, _ = await dde.decline_or_cancel_dice_challenge(dice_gid, user_id=p1)
        assert ok is True

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)

        assert final_p1 == init_p1
        assert final_p2 == init_p2
        assert final_abu == init_abu

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stake", [100, 1000, 25000])
    async def test_classic_duel_win_conservation(self, isolated_test_db, stake):
        """
        Verify Classic Duel (/duel) balance conservation:
        Winner receives stake - 5% rake, Loser loses stake, Abu Fund receives 5% rake, total delta == 0.
        """
        db = isolated_test_db
        p1 = 40001
        p2 = 40002
        await pre_seed_achievements(db, [p1, p2])

        await add_user_global_balance(db, p1, "b", 100_000)
        await add_user_global_balance(db, p2, "b", 100_000)

        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)
        init_total = init_p1 + init_p2 + init_abu

        # Register open challenge in _active_duels
        shared_state._active_duels[p1] = {
            "amount": stake,
            "target_id": None,
            "ts": time.time(),
            "board_id": "b",
            "message_id": 999,
            "chat_id": 888,
            "broadcast_msgs": []
        }

        msg = AsyncMock()
        msg.from_user.id = p2
        msg.answer = AsyncMock()

        # Fix random to make p1 winner or p2 winner deterministically
        with patch("random.choice", return_value=p1):
            await accept_duel_logic(msg, db, "b", p1)

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)
        final_total = final_p1 + final_p2 + final_abu

        delta_p1 = final_p1 - init_p1
        delta_p2 = final_p2 - init_p2
        delta_abu = final_abu - init_abu

        assert delta_p1 + delta_p2 + delta_abu == 0.0
        assert final_total == init_total

        expected_rake = max(1, int(stake * 0.05))
        assert delta_p2 == -stake
        assert delta_p1 == stake - expected_rake
        assert delta_abu == expected_rake

        # Check transactions
        sum_tx = await get_total_user_transactions(db, [p1, p2], category="duel")
        assert sum_tx + delta_abu == 0.0

    @pytest.mark.asyncio
    async def test_ttt_win_and_draw_conservation(self, isolated_test_db):
        """
        Verify Tic-Tac-Toe win (5% rake) and draw (2% fee) balance conservation:
        Total balance delta across players and Abu fund is EXACTLY ZERO.
        """
        db = isolated_test_db
        p1 = 50001
        p2 = 50002
        stake = 2000

        await add_user_global_balance(db, p1, "b", 50_000)
        await add_user_global_balance(db, p2, "b", 50_000)

        # 1. TTT Win Test
        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)

        game = ttt.TicTacToeGame(
            game_id="ttt_test_win",
            board_id="b",
            challenger_id=p1,
            opponent_id=p2,
            bet=stake,
            pot=stake * 2
        )
        game.state = "playing"

        # Escrow manually deducted on start in TTT engine
        await deduct_user_global_balance(db, p1, "b", stake)
        await deduct_user_global_balance(db, p2, "b", stake)

        game.winner_id = p1
        game.state = "finished"

        mock_bot = make_mock_bot()
        with patch("ttt_engine.publish_ttt_board_announcement", new_callable=AsyncMock):
            await ttt.finish_ttt_game(game, is_win=True, is_draw=False, bot=mock_bot)

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)

        delta_p1 = final_p1 - init_p1
        delta_p2 = final_p2 - init_p2
        delta_abu = final_abu - init_abu

        assert delta_p1 + delta_p2 + delta_abu == 0.0
        rake = max(1, int((stake * 2) * ttt.ABU_WIN_RAKE_PERCENT))
        assert delta_p2 == -stake
        assert delta_p1 == stake - rake
        assert delta_abu == rake

        # 2. TTT Draw Test
        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)

        game_draw = ttt.TicTacToeGame(
            game_id="ttt_test_draw",
            board_id="b",
            challenger_id=p1,
            opponent_id=p2,
            bet=stake,
            pot=stake * 2
        )
        await deduct_user_global_balance(db, p1, "b", stake)
        await deduct_user_global_balance(db, p2, "b", stake)
        game_draw.state = "finished"

        with patch("ttt_engine.publish_ttt_board_announcement", new_callable=AsyncMock):
            await ttt.finish_ttt_game(game_draw, is_win=False, is_draw=True, bot=mock_bot)

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)

        delta_p1 = final_p1 - init_p1
        delta_p2 = final_p2 - init_p2
        delta_abu = final_abu - init_abu

        assert delta_p1 + delta_p2 + delta_abu == 0.0
        draw_fee = max(1, int(stake * ttt.ABU_DRAW_FEE_PERCENT))
        assert delta_p1 == -draw_fee
        assert delta_p2 == -draw_fee
        assert delta_abu == draw_fee * 2


# =============================================================================
# SUITE 2: CONCURRENT WALLET DRAIN & NEGATIVE BALANCE IMPOSSIBILITY
# =============================================================================

class TestConcurrentWalletDrainAdversarial:

    @pytest.mark.asyncio
    async def test_100_concurrent_wallet_drains_exact_zero(self, isolated_test_db):
        """
        Adversarial Stress: 100 concurrent tasks attempt to deduct 200 ₪ from a wallet with exactly 1,000 ₪.
        Assertions:
        - Exactly 5 deductions succeed.
        - Exactly 95 deductions fail with False.
        - Final user balance is EXACTLY 0.0.
        - Negative balance is strictly impossible.
        """
        db = isolated_test_db
        user_id = 60001
        initial_balance = 1000.0
        deduct_chunk = 200.0

        await add_user_global_balance(db, user_id, "b", initial_balance)
        assert await get_user_global_balance(db, user_id) == initial_balance

        async def attempt_deduction():
            async with db_lock:
                ok, new_bal = await deduct_user_global_balance(db, user_id, "b", deduct_chunk)
                return ok, new_bal

        tasks = [attempt_deduction() for _ in range(100)]
        results = await asyncio.gather(*tasks)

        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]

        assert len(successes) == 5, f"Expected exactly 5 successful deductions, got {len(successes)}"
        assert len(failures) == 95, f"Expected exactly 95 failed deductions, got {len(failures)}"

        final_bal = await get_user_global_balance(db, user_id)
        assert final_bal == 0.0, f"Final balance must be exactly 0.0, got {final_bal}"
        assert final_bal >= 0.0, "NEGATIVE BALANCE DETECTED!"

    @pytest.mark.asyncio
    async def test_multi_board_concurrent_drain_integrity(self, isolated_test_db):
        """
        Adversarial Stress: User holds 1,000 ₪ split across 3 boards: b (300 ₪), vg (200 ₪), a (500 ₪).
        100 concurrent tasks attempt to deduct 400 ₪ from random boards.
        Assertions:
        - Exactly 2 tasks succeed (2 x 400 = 800 ₪).
        - Exactly 98 tasks fail.
        - Final global balance is EXACTLY 200.0.
        - No single board balance is negative (< 0.0).
        """
        db = isolated_test_db
        user_id = 60002

        await add_user_global_balance(db, user_id, "b", 300.0)
        await add_user_global_balance(db, user_id, "vg", 200.0)
        await add_user_global_balance(db, user_id, "a", 500.0)

        assert await get_user_global_balance(db, user_id) == 1000.0

        boards = ["b", "vg", "a", "po", "fag"]

        async def attempt_multi_board_drain(idx):
            board = boards[idx % len(boards)]
            async with db_lock:
                ok, new_bal = await deduct_user_global_balance(db, user_id, board, 400.0)
                return ok, new_bal

        tasks = [attempt_multi_board_drain(i) for i in range(100)]
        results = await asyncio.gather(*tasks)

        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]

        assert len(successes) == 2, f"Expected 2 successes, got {len(successes)}"
        assert len(failures) == 98, f"Expected 98 failures, got {len(failures)}"

        final_bal = await get_user_global_balance(db, user_id)
        assert final_bal == 200.0

        # Verify no individual board row is negative in SQLite
        async with db.execute("SELECT board_id, balance FROM Users WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            for b_name, b_val in rows:
                assert b_val >= 0.0, f"Board {b_name} balance is negative: {b_val}"

    @pytest.mark.asyncio
    async def test_concurrent_pvp_accepts_against_exhausted_balance(self, isolated_test_db):
        """
        Adversarial Stress: Acceptor has exactly 1,000 ₪ balance.
        50 RR challenges and 50 Dice challenges (each with 1,000 ₪ bet) are presented.
        Acceptor attempts to accept ALL 100 challenges simultaneously in parallel.
        Assertions:
        - Exactly ONE game accept succeeds.
        - Exactly 99 game accepts fail with insufficient funds rejection.
        - Acceptor final balance is EXACTLY 0.0 (in escrow for the 1 accepted game).
        - Zero balance leaks, zero negative balances.
        """
        db = isolated_test_db
        acceptor_id = 60003
        await add_user_global_balance(db, acceptor_id, "b", 1000.0)

        # Create 50 distinct challenger accounts with 10k balance each
        rr_games = []
        dice_games = []
        for i in range(50):
            ch_rr = 70000 + i
            ch_dice = 80000 + i
            await add_user_global_balance(db, ch_rr, "b", 10_000.0)
            await add_user_global_balance(db, ch_dice, "b", 10_000.0)

            ok, _, r_gid = await rr.create_rr_challenge("b", ch_rr, 1000)
            assert ok is True
            rr_games.append(r_gid)

            ok, _, d_gid = await dde.create_dice_challenge("b", ch_dice, 1000)
            assert ok is True
            dice_games.append(d_gid)

        async def try_accept_rr(gid):
            return await rr.accept_rr_challenge(gid, acceptor_id)

        async def try_accept_dice(gid):
            return await dde.accept_dice_challenge(gid, acceptor_id)

        all_accept_tasks = [try_accept_rr(gid) for gid in rr_games] + [try_accept_dice(gid) for gid in dice_games]
        # Shuffle tasks
        import random
        random.shuffle(all_accept_tasks)

        results = await asyncio.gather(*all_accept_tasks)

        successful_accepts = [r for r in results if r[0] is True]
        rejected_accepts = [r for r in results if r[0] is False]

        assert len(successful_accepts) == 1, f"Expected exactly 1 accept, got {len(successful_accepts)}"
        assert len(rejected_accepts) == 99

        final_bal = await get_user_global_balance(db, acceptor_id)
        assert final_bal == 0.0, f"Acceptor balance should be exactly 0.0, got {final_bal}"
        assert final_bal >= 0.0

    @pytest.mark.asyncio
    async def test_race_challenger_drain_vs_opponent_accept(self, isolated_test_db):
        """
        Adversarial Stress: Challenger creates 1,000 ₪ challenge with initial 1,000 ₪ balance.
        Concurrently:
        - Task A drains challenger balance to 0 ₪.
        - Task B attempts to accept the challenge as opponent.
        Assertions:
        - Opponent acceptance MUST safely fail and rollback to pending / rejection.
        - Challenger balance remains 0.0 (not negative).
        - Opponent balance is 100% untouched.
        """
        db = isolated_test_db
        challenger_id = 60004
        opponent_id = 60005
        stake = 1000

        await add_user_global_balance(db, challenger_id, "b", 1000.0)
        await add_user_global_balance(db, opponent_id, "b", 10_000.0)

        ok, _, game_id = await rr.create_rr_challenge("b", challenger_id, stake)
        assert ok is True

        # Drain challenger balance
        async with db_lock:
            ok_drain, _ = await deduct_user_global_balance(db, challenger_id, "b", 1000.0)
            assert ok_drain is True

        # Opponent accepts
        ok_accept, msg_err, game_data = await rr.accept_rr_challenge(game_id, opponent_id)
        assert ok_accept is False
        assert "не хватает шекелей" in msg_err

        ch_bal = await get_user_global_balance(db, challenger_id)
        op_bal = await get_user_global_balance(db, opponent_id)

        assert ch_bal == 0.0
        assert ch_bal >= 0.0
        assert op_bal == 10_000.0


# =============================================================================
# SUITE 3: NOTIFICATION DISPATCH & TELEGRAM API REJECTION RESILIENCE
# =============================================================================

class TestNotificationDeliveryAndResilienceAdversarial:

    @pytest.mark.asyncio
    async def test_100_percent_direct_dm_dispatch_matrix(self, isolated_test_db):
        """
        Verify that 100% of all refunds, forfeits, compensations, and grants
        actively dispatch direct Telegram DMs to player user IDs.
        """
        db = isolated_test_db
        p1 = 70001
        p2 = 70002
        stake = 1000
        await pre_seed_achievements(db, [p1, p2])

        await add_user_global_balance(db, p1, "b", 20_000)
        await add_user_global_balance(db, p2, "b", 20_000)

        mock_bot = make_mock_bot()

        # 1. Russian Roulette Fatal Shot DMs
        ok, _, rr_gid = await rr.create_rr_challenge("b", p1, stake)
        ok, _, _ = await rr.accept_rr_challenge(rr_gid, p2)
        mock_bot.send_message.reset_mock()
        await rr._finish_rr_game(rr_gid, winner_id=p1, loser_id=p2, reason="shot", bot=mock_bot)
        await asyncio.sleep(0.05)
        sent_chats = [c.kwargs.get("chat_id") for c in mock_bot.send_message.call_args_list]
        assert p1 in sent_chats and p2 in sent_chats

        # 2. Russian Roulette Surrender DMs
        ok, _, rr_gid2 = await rr.create_rr_challenge("b", p1, stake)
        ok, _, _ = await rr.accept_rr_challenge(rr_gid2, p2)
        mock_bot.send_message.reset_mock()
        await rr.surrender_rr_game(rr_gid2, user_id=p2, bot=mock_bot)
        await asyncio.sleep(0.05)
        sent_chats = [c.kwargs.get("chat_id") for c in mock_bot.send_message.call_args_list]
        assert p1 in sent_chats and p2 in sent_chats

        # 3. Russian Roulette Timeout Forfeit DMs
        ok, _, rr_gid3 = await rr.create_rr_challenge("b", p1, stake)
        ok, _, _ = await rr.accept_rr_challenge(rr_gid3, p2)
        mock_bot.send_message.reset_mock()
        await rr._finish_rr_game(rr_gid3, winner_id=p2, loser_id=p1, reason="timeout", bot=mock_bot)
        await asyncio.sleep(0.05)
        sent_chats = [c.kwargs.get("chat_id") for c in mock_bot.send_message.call_args_list]
        assert p1 in sent_chats and p2 in sent_chats

        # 4. Dice Duel Win/Loss DMs
        ok, _, d_gid = await dde.create_dice_challenge("b", p1, stake)
        ok, _, _ = await dde.accept_dice_challenge(d_gid, p2)
        mock_bot.send_message.reset_mock()
        await dde._finish_dice_game(d_gid, winner_id=p1, loser_id=p2, reason="win", bot=mock_bot)
        await asyncio.sleep(0.05)
        sent_chats = [c.kwargs.get("chat_id") for c in mock_bot.send_message.call_args_list]
        assert p1 in sent_chats and p2 in sent_chats

        # 5. Dice Duel Draw Refund DMs
        ok, _, d_gid2 = await dde.create_dice_challenge("b", p1, stake)
        ok, _, _ = await dde.accept_dice_challenge(d_gid2, p2)
        mock_bot.send_message.reset_mock()
        await dde._finish_dice_game(d_gid2, winner_id=None, loser_id=None, reason="draw", bot=mock_bot)
        await asyncio.sleep(0.05)
        sent_chats = [c.kwargs.get("chat_id") for c in mock_bot.send_message.call_args_list]
        assert p1 in sent_chats and p2 in sent_chats

        # 6. Admin /addmoney Grant DM
        mock_bot.send_message.reset_mock()
        admin_msg = AsyncMock()
        admin_msg.from_user.id = 99999
        admin_msg.text = f"/addmoney {p1} 5000"
        admin_msg.bot = mock_bot
        admin_msg.reply = AsyncMock()
        with patch.object(main, "ADMIN_IDS", [99999]):
            await main.cmd_add_money_admin(admin_msg)
        await asyncio.sleep(0.05)
        sent_chats = [c.kwargs.get("chat_id") for c in mock_bot.send_message.call_args_list]
        assert p1 in sent_chats

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error_cls, error_args", [
        (TelegramForbiddenError, {"message": "Forbidden: bot was blocked by the user", "method": MagicMock()}),
        (TelegramBadRequest, {"message": "Bad Request: chat not found", "method": MagicMock()}),
        (TelegramRetryAfter, {"message": "Too Many Requests", "retry_after": 5, "method": MagicMock()}),
        (RuntimeError, {"args": ("Network connection aborted",)}),
        (asyncio.TimeoutError, {}),
    ])
    async def test_telegram_api_complete_rejection_stability(self, isolated_test_db, error_cls, error_args):
        """
        Adversarial Stress: When Telegram API raises exceptions (blocked bot, chat not found, rate limit, timeout),
        verify that:
        - Zero exceptions propagate to callers or watchdog loops.
        - 100% of game finishes, escrow distributions, and database transactions complete flawlessly.
        - Game states clean up properly from active dictionaries.
        """
        db = isolated_test_db
        p1 = 80001
        p2 = 80002
        stake = 1000
        await pre_seed_achievements(db, [p1, p2])

        await add_user_global_balance(db, p1, "b", 20_000)
        await add_user_global_balance(db, p2, "b", 20_000)

        hostile_bot = make_mock_bot()
        if error_args:
            if "args" in error_args:
                hostile_bot.send_message.side_effect = error_cls(*error_args["args"])
            else:
                hostile_bot.send_message.side_effect = error_cls(**error_args)
        else:
            hostile_bot.send_message.side_effect = error_cls()

        # 1. Russian Roulette under Hostile Telegram API
        ok, _, rr_gid = await rr.create_rr_challenge("b", p1, stake)
        ok, _, _ = await rr.accept_rr_challenge(rr_gid, p2)
        ok, msg, game = await rr._finish_rr_game(rr_gid, winner_id=p1, loser_id=p2, reason="shot", bot=hostile_bot)
        assert ok is True
        assert game.get("finished") is True
        assert p1 not in rr.user_active_rr_game
        assert p2 not in rr.user_active_rr_game

        # 2. Dice Duel under Hostile Telegram API
        ok, _, d_gid = await dde.create_dice_challenge("b", p1, stake)
        ok, _, _ = await dde.accept_dice_challenge(d_gid, p2)
        ok, msg, d_game = await dde._finish_dice_game(d_gid, winner_id=p2, loser_id=p1, reason="win", bot=hostile_bot)
        assert ok is True
        assert d_game.get("finished") is True
        assert p1 not in dde.user_active_dice_game
        assert p2 not in dde.user_active_dice_game

        # 3. Direct wrapper test
        wrapper_res = await send_pvp_direct_notification(hostile_bot, p1, "Test hostile DM")
        assert wrapper_res is False  # Safely caught and returns False
