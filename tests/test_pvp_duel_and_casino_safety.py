# -*- coding: utf-8 -*-
"""
tests/test_pvp_duel_and_casino_safety.py

Comprehensive test suite verifying:
1. PvP Duel Race Conditions:
   - Creator cancels lobby at the exact moment another player accepts.
   - Atomic escrow rollback: creator refunded, second player receives clear alert
     'Дуэль была отозвана создателем', zero shekels lost or frozen.
2. Duel Timeout & Auto-Refund:
   - Unaccepted challenge in chat or PM expires after timeout.
   - Guaranteed atomic escrow refund without loss of funds.
3. Dual-Channel Fanout:
   - Both winner and loser receive notifications (winner: congratulatory with payout,
     loser: parting words with loss info) across chat + PM.
4. Casino & Slots Debounce & Spam-Click Protection:
   - In-flight lock and debounce prevent duplicate bets on slow connections when
     spamming 'Крутить еще' or '2x / Удвоить'.
5. Strict Anonymity:
   - Zero raw Telegram IDs in any duel cards or announcements.
"""

import sys
import time
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import casino_engine
import dice_duel_engine
import russian_roulette_pvp
import ttt_engine
import shared_state
from shared_state import (
    _active_duels,
    _duel_cooldowns,
    is_duel_cancelled_by_creator,
    record_duel_cancelled_by_creator,
)
from common.bot_helpers import (
    accept_duel_logic,
    decline_duel_logic,
    classic_duel_lock,
)
from common.database import (
    add_user_global_balance,
    get_user_global_balance,
    deduct_user_global_balance,
    record_user_transaction,
)
from common.db_pool import db_transaction, db_lock
from common.anon_identity import get_anon_id


@pytest.fixture(autouse=True)
def clean_duel_state():
    _active_duels.clear()
    _duel_cooldowns.clear()
    shared_state._cancelled_duels_by_creator.clear()
    dice_duel_engine.active_dice_games.clear()
    dice_duel_engine.user_active_dice_game.clear()
    dice_duel_engine._cancelled_dice_games.clear()
    russian_roulette_pvp.active_rr_games.clear()
    russian_roulette_pvp.user_active_rr_game.clear()
    russian_roulette_pvp._cancelled_rr_games.clear()
    ttt_engine.active_ttt_games.clear()
    ttt_engine.user_active_ttt_session.clear()
    ttt_engine._cancelled_ttt_games.clear()
    casino_engine.user_casino_last_action.clear()
    casino_engine._inflight_in_progress.clear()
    yield
    _active_duels.clear()
    _duel_cooldowns.clear()
    shared_state._cancelled_duels_by_creator.clear()
    dice_duel_engine.active_dice_games.clear()
    dice_duel_engine.user_active_dice_game.clear()
    dice_duel_engine._cancelled_dice_games.clear()
    russian_roulette_pvp.active_rr_games.clear()
    russian_roulette_pvp.user_active_rr_game.clear()
    russian_roulette_pvp._cancelled_rr_games.clear()
    ttt_engine.active_ttt_games.clear()
    ttt_engine.user_active_ttt_session.clear()
    ttt_engine._cancelled_ttt_games.clear()
    casino_engine.user_casino_last_action.clear()
    casino_engine._inflight_in_progress.clear()


# =============================================================================
# 1. RACE CONDITION: CANCEL VS ACCEPT AT THE SAME MOMENT
# =============================================================================

@pytest.mark.asyncio
async def test_classic_duel_cancel_vs_accept_race(isolated_test_db):
    """
    Test that when creator cancels a classic /duel lobby,
    creator gets escrow refunded, and acceptor gets a clear alert
    'Дуэль была отозвана создателем' with zero double deduction.
    """
    db = isolated_test_db
    ch_id = 11101
    op_id = 11102
    bet = 5000
    board_id = "b"

    await add_user_global_balance(db, ch_id, board_id, 20000)
    await add_user_global_balance(db, op_id, board_id, 20000)

    # 1. Creator creates challenge and funds are escrowed
    ok, _ = await deduct_user_global_balance(db, ch_id, board_id, bet)
    assert ok is True
    _active_duels[ch_id] = {
        "board_id": board_id,
        "amount": bet,
        "target_id": None,
        "ts": time.time(),
        "escrowed": True,
        "broadcast_msgs": []
    }

    bal_ch_after_create = await get_user_global_balance(db, ch_id)
    assert bal_ch_after_create == 15000

    # 2. Creator clicks Cancel
    mock_msg_cancel = AsyncMock()
    mock_msg_cancel.from_user.id = ch_id
    mock_msg_cancel.answer = AsyncMock()

    cancel_res = await decline_duel_logic(mock_msg_cancel, challenger_id=ch_id, user_id=ch_id)
    assert cancel_res is True
    assert is_duel_cancelled_by_creator(ch_id) is True

    # Creator must have their bet refunded immediately
    bal_ch_after_cancel = await get_user_global_balance(db, ch_id)
    assert bal_ch_after_cancel == 20000

    # 3. Acceptor clicks Accept right at this moment
    mock_msg_accept = AsyncMock()
    mock_msg_accept.from_user.id = op_id
    mock_msg_accept.answer = AsyncMock()

    await accept_duel_logic(mock_msg_accept, challenger_id=ch_id, board_id=board_id, user_id=op_id)

    # Acceptor must receive clear alert that creator revoked the duel
    mock_msg_accept.answer.assert_called_once()
    alert_text = mock_msg_accept.answer.call_args[0][0]
    assert "отозвана создателем" in alert_text

    # Acceptor balance must NOT be debited
    bal_op_after_accept = await get_user_global_balance(db, op_id)
    assert bal_op_after_accept == 20000


@pytest.mark.asyncio
async def test_dice_duel_cancel_during_in_flight_accept(isolated_test_db):
    """
    Test in dice_duel_engine:
    Acceptor is in the middle of accept transaction while creator cancels.
    Ensures safe atomic escrow rollback for both players and returns
    '❌ Дуэль была отозвана создателем.'
    """
    db = isolated_test_db
    p1 = 22201
    p2 = 22202
    bet = 1000
    board_id = "b"

    await add_user_global_balance(db, p1, board_id, 10000)
    await add_user_global_balance(db, p2, board_id, 10000)

    # 1. Create challenge
    ok, msg, gid = await dice_duel_engine.create_dice_challenge(board_id, p1, bet)
    assert ok is True
    assert gid is not None

    # Simulate creator calling cancel right as state became 'accepting'
    game = dice_duel_engine.active_dice_games[gid]
    game["state"] = "accepting"

    # Creator cancels while state is 'accepting'
    can_ok, can_msg = await dice_duel_engine.cancel_dice_challenge(gid, p1)
    assert can_ok is True
    assert game.get("cancel_requested") is True
    assert game.get("state") == "cancelled"

    # Now acceptor finishes accept_dice_challenge execution
    acc_ok, acc_msg, acc_game = await dice_duel_engine.accept_dice_challenge(gid, p2)
    assert acc_ok is False
    assert "отозвана создателем" in acc_msg

    # Verify both balances are intact (100% atomic safety)
    bal1 = await get_user_global_balance(db, p1)
    bal2 = await get_user_global_balance(db, p2)
    assert bal1 == 10000
    assert bal2 == 10000


@pytest.mark.asyncio
async def test_russian_roulette_cancel_during_in_flight_accept(isolated_test_db):
    """
    Test in russian_roulette_pvp:
    Creator cancels while state is 'accepting'.
    Ensures atomic rollback and returns '❌ Дуэль была отозвана создателем.'
    """
    db = isolated_test_db
    ch_id = 33301
    ac_id = 33302
    bet = 2000
    board_id = "b"

    await add_user_global_balance(db, ch_id, board_id, 15000)
    await add_user_global_balance(db, ac_id, board_id, 15000)

    ok, msg, gid = await russian_roulette_pvp.create_rr_challenge(board_id, ch_id, bet)
    assert ok is True

    game = russian_roulette_pvp.active_rr_games[gid]
    game["state"] = "accepting"

    # Creator cancels concurrently
    can_ok, can_msg = await russian_roulette_pvp.decline_or_cancel_rr_challenge(gid, ch_id)
    assert can_ok is True
    assert game.get("cancel_requested") is True

    # Acceptor runs accept_rr_challenge
    acc_ok, acc_msg, acc_game = await russian_roulette_pvp.accept_rr_challenge(gid, ac_id)
    assert acc_ok is False
    assert "отозвана создателем" in acc_msg

    bal1 = await get_user_global_balance(db, ch_id)
    bal2 = await get_user_global_balance(db, ac_id)
    assert bal1 == 15000
    assert bal2 == 15000


@pytest.mark.asyncio
async def test_ttt_cancel_during_in_flight_accept(isolated_test_db):
    """
    Test in ttt_engine:
    Creator cancels while status is 'accepting'.
    Ensures atomic rollback and returns '❌ Дуэль была отозвана создателем.'
    """
    db = isolated_test_db
    ch_id = 44401
    op_id = 44402
    bet = 1500
    board_id = "b"

    await add_user_global_balance(db, ch_id, board_id, 20000)
    await add_user_global_balance(db, op_id, board_id, 20000)

    mock_bot = AsyncMock()
    ok, msg, game = await ttt_engine.create_ttt_challenge(mock_bot, 12345, board_id, ch_id, bet)
    assert ok is True
    gid = game.game_id

    game.status = "accepting"

    # Creator cancels concurrently
    can_ok, can_msg = await ttt_engine.cancel_ttt_challenge(gid, ch_id)
    assert can_ok is True
    assert getattr(game, "cancel_requested", False) is True

    # Opponent accepts
    acc_ok, acc_msg, acc_game = await ttt_engine.accept_ttt_challenge(mock_bot, gid, op_id)
    assert acc_ok is False
    assert "отозвана создателем" in acc_msg

    bal1 = await get_user_global_balance(db, ch_id)
    bal2 = await get_user_global_balance(db, op_id)
    assert bal1 == 20000
    assert bal2 == 20000


# =============================================================================
# 2. DUEL TIMEOUT & AUTO-REFUND ESCROW
# =============================================================================

@pytest.mark.asyncio
async def test_classic_duel_timeout_auto_refund_escrow(isolated_test_db):
    """
    Test classic /duel watchdog:
    If duel is not accepted within timeout, escrow is 100% refunded to creator
    and notification is sent.
    """
    from main import classic_duel_watchdog_step

    db = isolated_test_db
    ch_id = 55501
    bet = 8000
    board_id = "b"

    await add_user_global_balance(db, ch_id, board_id, 10000)
    ok, _ = await deduct_user_global_balance(db, ch_id, board_id, bet)
    assert ok is True

    mock_bot = AsyncMock()
    mock_bot.edit_message_text = AsyncMock()
    mock_bot.send_message = AsyncMock()

    # Create expired duel (elapsed 605 seconds > 600s timeout)
    _active_duels[ch_id] = {
        "board_id": board_id,
        "amount": bet,
        "target_id": None,
        "ts": time.time() - 605,
        "chat_id": 99999,
        "msg_id": 123,
        "broadcast_msgs": [(99999, 123)],
        "escrowed": True
    }

    await classic_duel_watchdog_step(bot=mock_bot)

    # 1. Creator must be removed from active duels
    assert ch_id not in _active_duels

    # 2. Escrow must be fully refunded to creator
    bal_after = await get_user_global_balance(db, ch_id)
    assert bal_after == 10000

    # 3. Message in chat must be edited to announce expiration
    mock_bot.edit_message_text.assert_called_once()
    edit_text = mock_bot.edit_message_text.call_args[1]["text"]
    assert "ИСТЕК" in edit_text or "истёк" in edit_text.lower()


@pytest.mark.asyncio
async def test_dice_duel_timeout_watchdog_clean_and_refund(isolated_test_db):
    """
    Test dice_duel_engine watchdog expires pending challenges
    and refunds escrow if held.
    """
    db = isolated_test_db
    p1 = 66601
    bet = 3000
    board_id = "b"

    await add_user_global_balance(db, p1, board_id, 10000)

    ok, msg, gid = await dice_duel_engine.create_dice_challenge(board_id, p1, bet)
    assert ok is True
    game = dice_duel_engine.active_dice_games[gid]

    # Mark as expired in time and simulate escrow held
    game["created_ts"] = time.time() - 650
    game["escrowed"] = True
    await deduct_user_global_balance(db, p1, board_id, bet)

    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    with patch("dice_duel_engine.safe_edit_dice_message", new_callable=AsyncMock):
        await dice_duel_engine.dice_watchdog_step(bot=mock_bot)

    # Game should be marked expired
    assert game.get("finished") is True
    assert game.get("state") == "expired"

    # Creator escrow refunded
    bal = await get_user_global_balance(db, p1)
    assert bal == 10000


# =============================================================================
# 3. DUAL-CHANNEL FANOUT (NOTIFICATIONS TO WINNER & LOSER)
# =============================================================================

@pytest.mark.asyncio
async def test_dual_channel_fanout_classic_duel(isolated_test_db):
    """
    Test that when classic duel concludes:
    - Winner gets congratulatory PM with payout sum
    - Loser gets parting words with loss info
    - Chat message is edited to show result
    """
    db = isolated_test_db
    ch_id = 77701
    op_id = 77702
    bet = 4000
    board_id = "b"

    await add_user_global_balance(db, ch_id, board_id, 10000)
    await add_user_global_balance(db, op_id, board_id, 10000)

    _active_duels[ch_id] = {
        "board_id": board_id,
        "amount": bet,
        "target_id": None,
        "ts": time.time(),
        "chat_id": 88888,
        "msg_id": 555,
        "broadcast_msgs": [(88888, 555)],
        "escrowed": False
    }

    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()
    mock_bot.send_photo = AsyncMock()

    mock_msg = AsyncMock()
    mock_msg.bot = mock_bot
    mock_msg.chat.id = 88888
    mock_msg.message_id = 555
    mock_msg.from_user.id = op_id

    with patch("common.bot_helpers.safe_edit_message", new_callable=AsyncMock) as mock_safe_edit, \
         patch("combat_visuals.draw_duel_poster", return_value=MagicMock(getvalue=lambda: b"fake_png")):
        duel_res = await accept_duel_logic(mock_msg, challenger_id=ch_id, board_id=board_id, user_id=op_id)

    assert duel_res is not None
    winner_id = duel_res["winner_id"]
    loser_id = duel_res["loser_id"]
    assert winner_id in (ch_id, op_id)
    assert loser_id in (ch_id, op_id)
    assert winner_id != loser_id

    # 1. Chat card was edited with result
    mock_safe_edit.assert_called_once()
    chat_card_text = mock_safe_edit.call_args[0][3]
    assert "ДУЭЛЬ ЗАВЕРШЕНА" in chat_card_text
    assert f"[{get_anon_id(winner_id)}]" in chat_card_text
    assert f"[{get_anon_id(loser_id)}]" in chat_card_text

    # 2. Both winner and loser received personal PMs
    # In accept_duel_logic: send_photo or send_message is sent to both winner_id and loser_id
    notified_users = set()
    for call in mock_bot.send_message.call_args_list:
        notified_users.add(call[1].get("chat_id") or (call[0][0] if call[0] else None))
    for call in mock_bot.send_photo.call_args_list:
        notified_users.add(call[1].get("chat_id") or (call[0][0] if call[0] else None))

    assert winner_id in notified_users
    assert loser_id in notified_users


@pytest.mark.asyncio
async def test_dual_channel_fanout_dice_duel(isolated_test_db):
    """
    Test that when dice duel concludes via _finish_dice_game:
    - Winner receives victory notification with net payout
    - Loser receives defeat notification with parting words
    """
    db = isolated_test_db
    p1 = 88801
    p2 = 88802
    bet = 2500
    board_id = "b"

    await add_user_global_balance(db, p1, board_id, 10000)
    await add_user_global_balance(db, p2, board_id, 10000)

    ok, msg, gid = await dice_duel_engine.create_dice_challenge(board_id, p1, bet)
    assert ok is True
    ok, msg, game = await dice_duel_engine.accept_dice_challenge(gid, p2)
    assert ok is True

    mock_bot = AsyncMock()

    with patch("dice_duel_engine.send_pvp_direct_notification", new_callable=AsyncMock) as mock_notify, \
         patch("dice_duel_engine.broadcast_dice_announcement", new_callable=AsyncMock), \
         patch("dice_duel_engine.sync_dice_screens", new_callable=AsyncMock):
        fin_ok, fin_msg, fin_game = await dice_duel_engine._finish_dice_game(
            gid, winner_id=p1, loser_id=p2, reason="points", bot=mock_bot
        )

    assert fin_ok is True

    # Check that both p1 (winner) and p2 (loser) were notified
    notified_uids = [call[0][1] for call in mock_notify.call_args_list]
    assert p1 in notified_uids
    assert p2 in notified_uids

    # Check notification texts
    win_call = [c for c in mock_notify.call_args_list if c[0][1] == p1][0]
    lose_call = [c for c in mock_notify.call_args_list if c[0][1] == p2][0]

    assert "ПОБЕДА В ДАЙС-ДУЭЛИ" in win_call[0][2]
    assert "ПОРАЖЕНИЕ В ДАЙС-ДУЭЛИ" in lose_call[0][2]


# =============================================================================
# 4. CASINO & SLOTS DEBOUNCE & SPAM-CLICK PROTECTION
# =============================================================================

@pytest.mark.asyncio
async def test_slots_spin_in_flight_blocks_rapid_spam_click(isolated_test_db):
    """
    Test slots debounce and in-flight protection:
    Rapid clicking 'Крутить еще' or '2x Ставка' during spin animation
    is blocked and does NOT deduct double bets.
    """
    from main import _execute_slots_spin

    db = isolated_test_db
    user_id = 99901
    board_id = "b"
    bet = 500

    await add_user_global_balance(db, user_id, board_id, 10000)

    mock_bot = AsyncMock()
    mock_msg = AsyncMock()
    mock_msg.chat.id = 12345
    mock_msg.message_id = 777
    mock_msg.edit_text = AsyncMock()

    casino_engine.user_casino_last_action.pop(user_id, None)

    async def run_spin():
        await _execute_slots_spin(
            bot=mock_bot,
            chat_id=12345,
            user_id=user_id,
            board_id=board_id,
            bet=bet,
            message_to_edit=mock_msg
        )

    with patch("main.get_pool", return_value=db), \
         patch("common.db_pool.get_pool", return_value=db):
        # Launch spin 1
        task1 = asyncio.create_task(run_spin())
        await asyncio.sleep(0.02)

        # User spam-clicks 'Крутить еще' or '2x' while spin 1 is in-flight
        assert casino_engine.is_casino_in_flight(user_id) is True

        # Launch spin 2 concurrently
        task2 = asyncio.create_task(run_spin())

        await asyncio.gather(task1, task2)

    # Balance must reflect EXACTLY 1 spin deducted (and possible winnings),
    # but NOT two concurrent deductions!
    bal = await get_user_global_balance(db, user_id)
    # If 1 spin of 500 occurred: balance changed by (win - 500).
    # Two bets would have deducted 1000.
    # Check transaction log to verify exactly 1 casino bet transaction was written
    async with db.execute("SELECT count(*) FROM UserTransactions WHERE user_id=? AND category='casino' AND amount < 0", (user_id,)) as cur:
        row = await cur.fetchone()
        deduct_tx_count = row[0]

    assert deduct_tx_count == 1


def test_casino_action_debounce_blocks_rapid_clicks():
    """Verify check_action_debounce blocks clicks within min_interval."""
    uid = 99902
    casino_engine.user_casino_last_action.pop(uid, None)

    # Click 1: allowed
    ok1, msg1 = casino_engine.check_action_debounce(uid, action="spin", min_interval=1.0)
    assert ok1 is True
    assert msg1 == ""

    # Click 2 (immediate): blocked
    ok2, msg2 = casino_engine.check_action_debounce(uid, action="spin", min_interval=1.0)
    assert ok2 is False
    assert "Не части" in msg2


# =============================================================================
# 5. STRICT ANONYMITY: ZERO RAW TELEGRAM IDS IN DUEL CARDS
# =============================================================================

def test_pvp_duel_cards_have_zero_raw_telegram_ids():
    """
    Verify all duel cards (Dice, Russian Roulette, TicTacToe)
    use get_anon_id and never leak raw numeric Telegram IDs.
    """
    raw_uid1 = 987654321
    raw_uid2 = 123456789
    bet = 1000

    # 1. Dice duel card
    game_dice = {
        "game_id": "test_dice",
        "player_1": raw_uid1,
        "player_2": raw_uid2,
        "target_id": raw_uid2,
        "bet": bet,
        "state": "pending",
        "num_dice": 2,
        "round": 1,
        "turn_deadline_ts": time.time() + 600,
        "p1_rolls": {},
        "p2_rolls": {}
    }
    dice_card = dice_duel_engine.format_dice_game_message(game_dice)
    assert str(raw_uid1) not in dice_card
    assert str(raw_uid2) not in dice_card
    assert get_anon_id(raw_uid1) in dice_card

    # 2. Russian roulette card
    game_rr = {
        "game_id": "test_rr",
        "challenger_id": raw_uid1,
        "acceptor_id": raw_uid2,
        "target_id": raw_uid2,
        "bet": bet,
        "state": "pending",
        "current_chamber": 0,
        "turn": raw_uid1,
        "turn_deadline_ts": time.time() + 600,
        "created_ts": time.time(),
        "finished": False
    }
    rr_card = russian_roulette_pvp.format_rr_challenge_message(game_rr)
    assert str(raw_uid1) not in rr_card
    assert str(raw_uid2) not in rr_card
    assert get_anon_id(raw_uid1) in rr_card

    # 3. Tic-Tac-Toe card
    game_ttt = ttt_engine.TicTacToeGame(
        game_id="test_ttt",
        board_id="b",
        chat_id=123,
        challenger_id=raw_uid1,
        bet=bet,
        target_user_id=raw_uid2,
        status="waiting"
    )
    ttt_card = ttt_engine.render_game_text(game_ttt)
    assert str(raw_uid1) not in ttt_card
    assert str(raw_uid2) not in ttt_card
    assert get_anon_id(raw_uid1) in ttt_card
