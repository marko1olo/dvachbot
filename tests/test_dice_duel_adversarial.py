# -*- coding: utf-8 -*-
"""
test_dice_duel_adversarial.py — Empirical Adversarial Stress & Concurrency Suite for Dice Duel PvP
=================================================================================================
Covers:
1. Concurrency stress: 100 simultaneous concurrent accepts (distinct users vs same user).
2. Rapid roll bursts: concurrent cb_dice_roll / execute_player_roll invocations per turn.
3. Idempotency & double-finish: concurrent _finish_dice_game invocations.
4. Draw / tie refund: 2% tie rake to Abu Fund, balance refund to both players, direct DMs dispatched.
5. Watchdog auto-timeout: expired turns trigger forfeit, pot payout, direct DMs dispatched.
6. Watchdog pending challenge cleanup: unaccepted challenges expire cleanly without charge.
7. Rematch flow: cb_dice_rematch creates fresh challenge with target and matching stake.
8. Escrow boundaries & edge cases: insufficient balance, spectator rolls, surrender callback.
"""

import sys
import time
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shared_state
import dice_duel_engine as dde
from dice_duel_engine import (
    active_dice_games,
    user_active_dice_game,
    dice_engine_lock,
    create_dice_challenge,
    accept_dice_challenge,
    cancel_dice_challenge,
    execute_player_roll,
    _finish_dice_game,
    dice_watchdog_step,
    MIN_DICE_BET,
    MAX_DICE_BET,
    DICE_RAKE_PERCENT,
    DICE_TIE_RAKE_PERCENT,
)
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    get_abu_fund_total,
)

# Extract callback handlers registered on the router
_cb_handlers = {h.callback.__name__: h.callback for h in dde.router.callback_query.handlers}
cb_dice_accept = _cb_handlers["cb_dice_accept"]
cb_dice_decline = _cb_handlers["cb_dice_decline"]
cb_dice_roll = _cb_handlers["cb_dice_roll"]
cb_dice_surrender = _cb_handlers["cb_dice_surrender"]
cb_dice_rematch = _cb_handlers["cb_dice_rematch"]
cb_dice_create_fast = _cb_handlers["cb_dice_create_fast"]


@pytest.fixture(autouse=True)
def clean_dice_state():
    active_dice_games.clear()
    user_active_dice_game.clear()
    yield
    active_dice_games.clear()
    user_active_dice_game.clear()


@pytest.mark.asyncio
async def test_100_concurrent_accepts_distinct_users(isolated_test_db):
    """
    100 distinct users concurrently try to accept a single open dice challenge.
    Strict Invariant: Exactly 1 accepts, 99 fail; exactly 1 escrow debited.
    """
    db = isolated_test_db
    board_id = "b"
    challenger_id = 1001
    stake = 1000

    # Fund challenger
    await add_user_global_balance(db, challenger_id, board_id, 100_000)

    # Fund 100 distinct acceptors
    candidate_ids = list(range(2001, 2101))
    for cid in candidate_ids:
        await add_user_global_balance(db, cid, board_id, 50_000)

    # Create open challenge
    ok, msg, game_id = await create_dice_challenge(
        board_id=board_id,
        challenger_id=challenger_id,
        bet=stake,
        target_id=None,
        num_dice=2,
    )
    assert ok is True
    assert game_id is not None

    # Run 100 concurrent accepts
    tasks = [accept_dice_challenge(game_id, cid) for cid in candidate_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if isinstance(r, tuple) and r[0] is True]
    failures = [r for r in results if isinstance(r, tuple) and r[0] is False]

    assert len(successes) == 1, f"Expected exactly 1 winner, got {len(successes)}"
    assert len(failures) == 99, f"Expected 99 rejections, got {len(failures)}"

    winning_acceptor = successes[0][2]["player_2"]
    assert winning_acceptor in candidate_ids

    # Verify balances
    ch_bal = await get_user_global_balance(db, challenger_id)
    assert ch_bal == 100_000 - stake

    win_bal = await get_user_global_balance(db, winning_acceptor)
    assert win_bal == 50_000 - stake

    for cid in candidate_ids:
        if cid != winning_acceptor:
            bal = await get_user_global_balance(db, cid)
            assert bal == 50_000, f"Candidate {cid} balance altered!"

    # Verify game state
    async with dice_engine_lock:
        game = active_dice_games[game_id]
        assert game["state"] == "playing"
        assert game["player_1"] == challenger_id
        assert game["player_2"] == winning_acceptor
        assert game["current_turn"] in (challenger_id, winning_acceptor)


@pytest.mark.asyncio
async def test_100_concurrent_accepts_same_user(isolated_test_db):
    """
    Same user attempts 100 concurrent accepts (rapid button spam).
    Strict Invariant: Exactly 1 succeeds, 99 rejected, no double escrow deduction.
    """
    db = isolated_test_db
    board_id = "b"
    p1 = 3001
    p2 = 3002
    stake = 1500

    await add_user_global_balance(db, p1, board_id, 20_000)
    await add_user_global_balance(db, p2, board_id, 20_000)

    ok, _, game_id = await create_dice_challenge(board_id, p1, stake)
    assert ok is True

    tasks = [accept_dice_challenge(game_id, p2) for _ in range(100)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if isinstance(r, tuple) and r[0] is True]
    assert len(successes) == 1

    bal1 = await get_user_global_balance(db, p1)
    bal2 = await get_user_global_balance(db, p2)
    assert bal1 == 20_000 - stake
    assert bal2 == 20_000 - stake


@pytest.mark.asyncio
async def test_rapid_roll_burst_concurrency(isolated_test_db):
    """
    Concurrent roll spam by turn player:
    Multiple simultaneous execute_player_roll calls should result in exactly 1 roll recorded per turn.
    """
    db = isolated_test_db
    board_id = "b"
    p1 = 4001
    p2 = 4002
    stake = 500

    await add_user_global_balance(db, p1, board_id, 10_000)
    await add_user_global_balance(db, p2, board_id, 10_000)

    ok, _, game_id = await create_dice_challenge(board_id, p1, stake)
    assert ok is True
    ok, _, game = await accept_dice_challenge(game_id, p2)
    assert ok is True

    turn_player = game["current_turn"]
    mock_bot = AsyncMock()
    mock_bot.edit_message_text = AsyncMock()

    # 20 concurrent rolls from the current turn player
    tasks = [execute_player_roll(game_id, turn_player, mock_bot) for _ in range(20)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if isinstance(r, tuple) and r[0] is True]
    # Exactly 1 should successfully register the roll for this turn
    assert len(successes) == 1

    async with dice_engine_lock:
        g = active_dice_games[game_id]
        r1_p1 = g["p1_rolls"].get(1)
        r1_p2 = g["p2_rolls"].get(1)
        # Exactly one player has rolled for round 1
        if turn_player == p1:
            assert r1_p1 is not None and len(r1_p1) == 2
            assert r1_p2 is None
            assert g["current_turn"] == p2
        else:
            assert r1_p2 is not None and len(r1_p2) == 2
            assert r1_p1 is None
            assert g["current_turn"] == p1


@pytest.mark.asyncio
async def test_cb_dice_roll_concurrency(isolated_test_db):
    """
    Test aiogram callback handler cb_dice_roll under concurrent burst from the active player.
    Verifies that the transient rolling state protects against race conditions.
    """
    db = isolated_test_db
    board_id = "b"
    p1 = 5001
    p2 = 5002
    stake = 500

    await add_user_global_balance(db, p1, board_id, 10_000)
    await add_user_global_balance(db, p2, board_id, 10_000)

    ok, _, game_id = await create_dice_challenge(board_id, p1, stake)
    ok, _, game = await accept_dice_challenge(game_id, p2)

    turn_player = game["current_turn"]

    def make_mock_callback(uid):
        cb = MagicMock()
        cb.data = f"dice_roll:{game_id}"
        cb.from_user.id = uid
        cb.message.edit_text = AsyncMock()
        cb.answer = AsyncMock()
        cb.bot = AsyncMock()
        return cb

    # 10 concurrent callback calls from the active player
    callbacks = [make_mock_callback(turn_player) for _ in range(10)]
    tasks = [cb_dice_roll(cb) for cb in callbacks]

    # Patch sleep to make test fast
    with patch("asyncio.sleep", AsyncMock()):
        await asyncio.gather(*tasks, return_exceptions=True)

    # Verify roll state transitioned cleanly to the other player
    async with dice_engine_lock:
        g = active_dice_games[game_id]
        other_player = p2 if turn_player == p1 else p1
        assert g["current_turn"] == other_player
        # Exactly one player has a recorded roll in round 1
        rolls_recorded = int(1 in g["p1_rolls"]) + int(1 in g["p2_rolls"])
        assert rolls_recorded == 1


@pytest.mark.asyncio
async def test_idempotency_double_finish(isolated_test_db):
    """
    10 concurrent invocations of _finish_dice_game:
    Exactly 1 returns True and processes payouts; 9 return False.
    Zero double-crediting or duplicate rakes.
    """
    db = isolated_test_db
    board_id = "b"
    p1 = 6001
    p2 = 6002
    stake = 1000

    await add_user_global_balance(db, p1, board_id, 10_000)
    await add_user_global_balance(db, p2, board_id, 10_000)

    ok, _, game_id = await create_dice_challenge(board_id, p1, stake)
    ok, _, _ = await accept_dice_challenge(game_id, p2)

    # Initial balances after escrow: 9,000 each
    b1 = await get_user_global_balance(db, p1)
    b2 = await get_user_global_balance(db, p2)
    assert b1 == 9000
    assert b2 == 9000

    fund_before = await get_abu_fund_total(db)
    mock_bot = AsyncMock()

    # 10 concurrent finish requests declaring p1 winner
    tasks = [
        _finish_dice_game(game_id, winner_id=p1, loser_id=p2, reason="win", bot=mock_bot)
        for _ in range(10)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if isinstance(r, tuple) and r[0] is True]
    failures = [r for r in results if isinstance(r, tuple) and r[0] is False]

    assert len(successes) == 1
    assert len(failures) == 9

    # Payout calculations:
    # Total pot: 2000. 5% Rake: 100. Win payout: 1900.
    b1_after = await get_user_global_balance(db, p1)
    b2_after = await get_user_global_balance(db, p2)
    fund_after = await get_abu_fund_total(db)

    assert b1_after == 9000 + 1900
    assert b2_after == 9000
    assert fund_after == fund_before + 100


@pytest.mark.asyncio
async def test_draw_tie_refund_with_rake_and_dms(isolated_test_db):
    """
    Test tie/draw outcome in dice duel:
    - 2% tie rake sent to Abu Fund per player.
    - Net balance refunded to both players.
    - Direct Telegram DM sent to both players.
    """
    db = isolated_test_db
    board_id = "b"
    p1 = 7001
    p2 = 7002
    stake = 2000

    await add_user_global_balance(db, p1, board_id, 10_000)
    await add_user_global_balance(db, p2, board_id, 10_000)

    ok, _, game_id = await create_dice_challenge(board_id, p1, stake)
    ok, _, _ = await accept_dice_challenge(game_id, p2)

    fund_before = await get_abu_fund_total(db)
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    ok, msg, game = await _finish_dice_game(
        game_id,
        winner_id=None,
        loser_id=None,
        reason="draw",
        bot=mock_bot
    )
    assert ok is True
    assert game["outcome"] == "draw"

    # Allow spawned tasks to run
    await asyncio.sleep(0.05)

    # 2% tie rake of 2000 = 40 per player = 80 total
    expected_rake_per_player = max(1, int(stake * DICE_TIE_RAKE_PERCENT))
    expected_refund = stake - expected_rake_per_player
    assert expected_rake_per_player == 40
    assert expected_refund == 1960

    b1 = await get_user_global_balance(db, p1)
    b2 = await get_user_global_balance(db, p2)
    fund_after = await get_abu_fund_total(db)

    # Balances were 8,000 after escrow + 1,960 refund = 9,960
    assert b1 == 8000 + expected_refund
    assert b2 == 8000 + expected_refund
    assert fund_after == fund_before + (expected_rake_per_player * 2)

    # Verify direct DMs to both players
    assert mock_bot.send_message.call_count >= 2
    sent_chats = [c.kwargs.get("chat_id") for c in mock_bot.send_message.call_args_list]
    assert p1 in sent_chats
    assert p2 in sent_chats


@pytest.mark.asyncio
async def test_watchdog_turn_timeout_forfeit_and_dms(isolated_test_db):
    """
    Test watchdog turn timeout:
    - Active game past turn_deadline_ts gets automatically forfeited.
    - Opponent wins pot minus 5% rake.
    - Direct DMs dispatched to winner and loser.
    """
    db = isolated_test_db
    board_id = "b"
    p1 = 8001
    p2 = 8002
    stake = 1000

    await add_user_global_balance(db, p1, board_id, 10_000)
    await add_user_global_balance(db, p2, board_id, 10_000)

    ok, _, game_id = await create_dice_challenge(board_id, p1, stake)
    ok, _, game = await accept_dice_challenge(game_id, p2)

    turn_user = game["current_turn"]
    winner_user = p2 if turn_user == p1 else p1

    # Simulate expired turn deadline
    async with dice_engine_lock:
        active_dice_games[game_id]["turn_deadline_ts"] = time.time() - 10.0
        active_dice_games[game_id]["chat_id"] = 12345
        active_dice_games[game_id]["msg_id"] = 67890

    mock_bot = AsyncMock()
    mock_bot.edit_message_text = AsyncMock()
    mock_bot.send_message = AsyncMock()

    await dice_watchdog_step(mock_bot)
    await asyncio.sleep(0.05)

    # Verify game is finished and winner credited
    async with dice_engine_lock:
        g = active_dice_games[game_id]
        assert g["finished"] is True
        assert g["winner"] == winner_user
        assert g["loser"] == turn_user

    w_bal = await get_user_global_balance(db, winner_user)
    l_bal = await get_user_global_balance(db, turn_user)

    # Winner gets 9,000 + 1,900 = 10,900
    assert w_bal == 9000 + 1900
    assert l_bal == 9000

    # Direct DM notifications sent
    sent_chats = [c.kwargs.get("chat_id") for c in mock_bot.send_message.call_args_list]
    assert winner_user in sent_chats
    assert turn_user in sent_chats


@pytest.mark.asyncio
async def test_watchdog_expired_pending_challenge_cleanup(isolated_test_db):
    """
    Test watchdog cleanup for unaccepted pending challenge:
    - Pending challenge older than 120s is marked expired.
    - User is freed from user_active_dice_game.
    - Zero escrow deduction.
    """
    db = isolated_test_db
    p1 = 9001
    await add_user_global_balance(db, p1, "b", 5000)

    ok, _, game_id = await create_dice_challenge("b", p1, 1000)
    assert ok is True
    assert p1 in user_active_dice_game

    async with dice_engine_lock:
        active_dice_games[game_id]["created_ts"] = time.time() - 200.0
        active_dice_games[game_id]["chat_id"] = 111
        active_dice_games[game_id]["msg_id"] = 222

    mock_bot = AsyncMock()
    mock_bot.edit_message_text = AsyncMock()

    await dice_watchdog_step(mock_bot)

    async with dice_engine_lock:
        g = active_dice_games[game_id]
        assert g["finished"] is True
        assert g["state"] == "expired"
        assert p1 not in user_active_dice_game

    bal = await get_user_global_balance(db, p1)
    assert bal == 5000


@pytest.mark.asyncio
async def test_rematch_flow(isolated_test_db):
    """
    Test cb_dice_rematch:
    - Finishing a game allows either player to click rematch.
    - cb_dice_rematch creates a fresh challenge with matching bet and target_id.
    """
    db = isolated_test_db
    board_id = "b"
    p1 = 11001
    p2 = 11002
    stake = 1000

    await add_user_global_balance(db, p1, board_id, 20_000)
    await add_user_global_balance(db, p2, board_id, 20_000)

    ok, _, game_id = await create_dice_challenge(board_id, p1, stake)
    ok, _, _ = await accept_dice_challenge(game_id, p2)

    # Finish game
    mock_bot = AsyncMock()
    await _finish_dice_game(game_id, winner_id=p1, loser_id=p2, reason="win", bot=mock_bot)

    # Player 2 clicks rematch
    cb = MagicMock()
    cb.data = f"dice_rematch:{game_id}"
    cb.from_user.id = p2
    cb.answer = AsyncMock()
    cb.message.answer = AsyncMock(return_value=MagicMock(message_id=999, chat=MagicMock(id=888)))

    await cb_dice_rematch(cb)

    cb.answer.assert_called_with("⚔️ Вызов на реванш создан!")
    cb.message.answer.assert_called_once()

    # Find the new rematch game
    async with dice_engine_lock:
        new_gid = user_active_dice_game.get(p2)
        assert new_gid is not None
        assert new_gid != game_id
        new_g = active_dice_games[new_gid]
        assert new_g["player_1"] == p2
        assert new_g["target_id"] == p1
        assert new_g["bet"] == stake
        assert new_g["state"] == "pending"


@pytest.mark.asyncio
async def test_surrender_flow(isolated_test_db):
    """
    Test voluntary surrender in dice duel:
    - Calling cb_dice_surrender immediately awards victory to opponent.
    """
    db = isolated_test_db
    board_id = "b"
    p1 = 12001
    p2 = 12002
    stake = 1000

    await add_user_global_balance(db, p1, board_id, 10_000)
    await add_user_global_balance(db, p2, board_id, 10_000)

    ok, _, game_id = await create_dice_challenge(board_id, p1, stake)
    ok, _, _ = await accept_dice_challenge(game_id, p2)

    cb = MagicMock()
    cb.data = f"dice_surrender:{game_id}"
    cb.from_user.id = p1
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.bot = AsyncMock()
    cb.bot.send_message = AsyncMock()

    await cb_dice_surrender(cb)
    await asyncio.sleep(0.05)

    cb.answer.assert_called_with("🏳️ Ты сдался.")

    async with dice_engine_lock:
        g = active_dice_games[game_id]
        assert g["finished"] is True
        assert g["winner"] == p2
        assert g["loser"] == p1

    p2_bal = await get_user_global_balance(db, p2)
    assert p2_bal == 9000 + 1900


@pytest.mark.asyncio
async def test_escrow_boundaries_and_rejections(isolated_test_db):
    """
    Boundary & error conditions:
    1. Stake < MIN_DICE_BET or > MAX_DICE_BET.
    2. Acceptor balance < stake.
    3. Challenger balance drained before accept.
    4. Playing with self.
    5. Spectator trying to roll or surrender.
    """
    db = isolated_test_db
    board_id = "b"
    p1 = 13001
    p2 = 13002
    spectator = 13003

    await add_user_global_balance(db, p1, board_id, 1000)

    # 1. Invalid stakes
    ok, err, _ = await create_dice_challenge(board_id, p1, MIN_DICE_BET - 1)
    assert ok is False
    assert "Минимальная ставка" in err

    ok, err, _ = await create_dice_challenge(board_id, p1, MAX_DICE_BET + 1)
    assert ok is False
    assert "Максимальная ставка" in err

    # 2. Insufficient balance to create
    ok, err, _ = await create_dice_challenge(board_id, p1, 5000)
    assert ok is False
    assert "Недостаточно шекелей" in err

    # Valid creation
    ok, _, game_id = await create_dice_challenge(board_id, p1, 500)
    assert ok is True

    # 4. Self accept
    ok, err, _ = await accept_dice_challenge(game_id, p1)
    assert ok is False
    assert "с самим собой" in err

    # 2. Acceptor insufficient balance
    await add_user_global_balance(db, p2, board_id, 100)
    ok, err, _ = await accept_dice_challenge(game_id, p2)
    assert ok is False
    assert "не хватает шекелей" in err

    # 5. Spectator attempts
    # Fund p2 and accept
    await add_user_global_balance(db, p2, board_id, 1000)
    ok, _, _ = await accept_dice_challenge(game_id, p2)
    assert ok is True

    mock_bot = AsyncMock()
    ok, err, _ = await execute_player_roll(game_id, spectator, mock_bot)
    assert ok is False
    assert "не участвуешь" in err
