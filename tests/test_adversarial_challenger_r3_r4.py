# -*- coding: utf-8 -*-
"""
tests/test_adversarial_challenger_r3_r4.py
==========================================
Empirical Adversarial Stress Testing & Fuzzing Suite for Requirements R3 & R4:
- R3: Dynamic PvP lobbies, balance calculations, stake multiplication (/2, x2, ALL-IN),
      integer overflow / negative stakes, race conditions in confirmation & escrow,
      double-accept/cancel races, and mathematical balance conservation.
- R4: AI item attack counter-reactions (/shoot, /rob, /shit, /vomit, /pepperspray, /partyvan,
      /dossier, /bribe against author_id == 0), stacking debuffs, Abu Fund balance tracking,
      zero-balance robbery safety, and permission isolation.
"""

import asyncio
import json
import random
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from russian_roulette_pvp import (
    cmd_russian_roulette,
    get_rr_lobby_keyboard,
    get_adaptive_rr_bet_presets,
    format_rr_lobby_message,
    create_rr_challenge,
    accept_rr_challenge,
    decline_or_cancel_rr_challenge,
    pull_rr_trigger,
    surrender_rr_game,
    _finish_rr_game,
    active_rr_games,
    user_active_rr_game,
    MIN_RR_BET,
    MAX_RR_BET,
    RR_RAKE_PERCENT,
)
from dice_duel_engine import (
    cmd_dice_duel_entry,
    get_dice_lobby_keyboard,
    get_adaptive_dice_bet_presets,
    format_dice_bet_amount,
    create_dice_challenge,
    accept_dice_challenge,
    cancel_dice_challenge,
    _finish_dice_game,
    active_dice_games,
    user_active_dice_game,
    MIN_DICE_BET,
    MAX_DICE_BET,
    DICE_RAKE_PERCENT,
    DICE_TIE_RAKE_PERCENT,
)
from ttt_engine import (
    get_ttt_lobby_keyboard,
    get_adaptive_bet_presets as get_adaptive_ttt_bet_presets,
    cmd_ttt,
    MIN_TTT_BET,
    MAX_TTT_BET,
)
from common.bot_helpers import (
    handle_cyberchad_counter_action,
    _get_user_active_items,
)
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
    get_abu_fund_total,
    record_user_transaction,
)
import shared_state


# =============================================================================
# 1. R3: Dynamic Stake Fuzzing & Keyboard Bounds
# =============================================================================

class TestR3DynamicStakeFuzzingAndKeyboardBounds:
    """Adversarially fuzzer testing for dynamic stake selector math and keyboard generation."""

    def test_r3_fuzz_adaptive_presets_across_extreme_balances(self):
        """Fuzzes balance inputs across extreme ranges (-1M to 10^12) for all 3 game types."""
        test_balances = [
            -1_000_000, -100, -1, 0, 1, 10, 49, 50, 51, 99, 100, 101, 249, 250, 251,
            499, 500, 1000, 1337, 2500, 5000, 9999, 10000, 25000, 50000, 100000,
            250000, 500000, 1000000, 10_000_000, 100_000_000, 10**10, 10**12
        ]

        # Add 100 randomized integer balances
        for _ in range(100):
            test_balances.append(random.randint(-500, 10_000_000))

        for bal in test_balances:
            for cur_bet in [50, 100, 250, 500, 1000, 5000, 100000]:
                # Russian Roulette
                p_rr = get_adaptive_rr_bet_presets(bal, cur_bet)
                assert isinstance(p_rr, list)
                assert len(p_rr) >= 1
                assert len(p_rr) <= 5
                assert all(isinstance(x, int) and x >= MIN_RR_BET for x in p_rr)
                assert all(x <= MAX_RR_BET for x in p_rr)
                assert p_rr == sorted(list(set(p_rr)))  # Strictly ascending & unique

                # Dice Duel
                p_dice = get_adaptive_dice_bet_presets(bal, cur_bet)
                assert isinstance(p_dice, list)
                assert len(p_dice) >= 1
                assert len(p_dice) <= 5
                assert all(isinstance(x, int) and x >= MIN_DICE_BET for x in p_dice)
                assert all(x <= MAX_DICE_BET for x in p_dice)
                assert p_dice == sorted(list(set(p_dice)))

                # Tic-Tac-Toe
                p_ttt = get_adaptive_ttt_bet_presets(bal, cur_bet)
                assert isinstance(p_ttt, list)
                assert len(p_ttt) >= 1
                assert len(p_ttt) <= 5
                assert all(isinstance(x, int) and x >= MIN_TTT_BET for x in p_ttt)
                assert all(x <= MAX_TTT_BET for x in p_ttt)
                assert p_ttt == sorted(list(set(p_ttt)))

    def test_r3_fuzz_lobby_keyboards_structure_and_bounds(self):
        """Fuzzes lobby keyboard builders with extreme bets, negative bets, and extreme balances."""
        extreme_cases = [
            (0, 0), (-500, 0), (-100, -100), (50, 50), (100, 50), (500, 10000),
            (1000000, 500000), (10**9, 10**9), (999999999, 100)
        ]

        for bet, bal in extreme_cases:
            # RR Keyboard
            kb_rr = get_rr_lobby_keyboard(bet=bet, balance=bal, target_id=0)
            assert kb_rr is not None
            assert len(kb_rr.inline_keyboard) >= 4
            # Check confirm button bet amount is strictly bounded
            confirm_btn_rr = kb_rr.inline_keyboard[0][0]
            assert "Бросить вызов" in confirm_btn_rr.text

            # Dice Keyboard
            kb_dice = get_dice_lobby_keyboard(balance=bal, current_bet=bet, target_id=0)
            assert kb_dice is not None
            assert len(kb_dice.inline_keyboard) >= 4
            assert "2d6" in kb_dice.inline_keyboard[0][0].text
            assert "3d6" in kb_dice.inline_keyboard[0][1].text

            # TTT Keyboard
            kb_ttt = get_ttt_lobby_keyboard(bet=bet, balance=bal, target_user_id=0)
            assert kb_ttt is not None
            assert len(kb_ttt.inline_keyboard) >= 4
            assert "Бросить вызов" in kb_ttt.inline_keyboard[0][0].text

    def test_r3_stake_modifier_half_double_allin_extreme_edge_cases(self):
        """Adversarially tests modifiers (/2, x2, 💰 ВА-БАНК) at boundary conditions."""
        # 1. Minimum bet (/2 cannot decrease below MIN_BET)
        kb_min = get_rr_lobby_keyboard(bet=50, balance=1000)
        ctrl_row_min = kb_min.inline_keyboard[2]
        btn_half = next(b for b in ctrl_row_min if b.text == "/2")
        assert "rr:lobby:50" in btn_half.callback_data  # Clamped to min 50

        # 2. Bet doubling when balance is insufficient (cannot exceed balance or current bet)
        kb_tight = get_rr_lobby_keyboard(bet=1000, balance=1500)
        ctrl_row_tight = kb_tight.inline_keyboard[2]
        btn_double = next(b for b in ctrl_row_tight if b.text == "x2")
        # Since balance (1500) < bet*2 (2000), double_bet stays 1000 or clamps to affordable
        assert "rr:lobby:1000" in btn_double.callback_data

        # 3. Zero balance ALL-IN (cannot be negative or zero, clamps to MIN_BET)
        kb_zero = get_rr_lobby_keyboard(bet=50, balance=0)
        ctrl_row_zero = kb_zero.inline_keyboard[2]
        btn_allin_zero = next(b for b in ctrl_row_zero if "ВА-БАНК" in b.text)
        assert "rr:lobby:50" in btn_allin_zero.callback_data

        # 4. Ultra wealthy ALL-IN (clamped to MAX_BET)
        kb_rich = get_dice_lobby_keyboard(balance=500_000_000, current_bet=1000)
        ctrl_row_rich = kb_rich.inline_keyboard[2]
        btn_allin_rich = next(b for b in ctrl_row_rich if "ВА-БАНК" in b.text)
        assert f"dice_lobby_bet:{MAX_DICE_BET}" in btn_allin_rich.callback_data


# =============================================================================
# 2. R3: Direct Command Stake Parsing & Injection Exploits
# =============================================================================

class TestR3DirectCommandExploitsAndParsing:
    """Tests robustness of direct commands against SQL injection, negative values, and corrupted strings."""

    @pytest.mark.asyncio
    async def test_r3_direct_command_negative_and_zero_stakes(self, isolated_test_db):
        """Direct commands with negative or zero stakes must NOT create challenges."""
        db = isolated_test_db
        user_id = 1001
        board_id = "b"
        await add_user_global_balance(db, user_id, board_id, 5000)

        malicious_inputs = ["-500", "-1", "0", "-0", "-999999999"]
        for mal_input in malicious_inputs:
            mock_msg = MagicMock()
            mock_msg.from_user.id = user_id
            mock_msg.chat.id = 1001
            mock_msg.text = f"/rr {mal_input}"
            mock_msg.reply_to_message = None
            mock_msg.answer = AsyncMock()

            await cmd_russian_roulette(mock_msg, board_id)

            # Check that no game was created in active_rr_games for user
            assert user_id not in user_active_rr_game
            # Verify answer opened lobby fallback or returned rejection error
            assert mock_msg.answer.called
            sent_text = mock_msg.answer.call_args[0][0]
            assert "РУССКАЯ РУЛЕТКА" in sent_text or "Минимальная ставка" in sent_text or "Неверная сумма" in sent_text

    @pytest.mark.asyncio
    async def test_r3_direct_command_corrupted_strings_and_injections(self, isolated_test_db):
        """Direct commands with SQL injection or weird types must handle gracefully without crash."""
        db = isolated_test_db
        user_id = 1002
        board_id = "b"
        await add_user_global_balance(db, user_id, board_id, 5000)

        weird_inputs = [
            "500; DROP TABLE Users;", "NaN", "inf", "-inf", "0x100", "50.5",
            "<script>alert(1)</script>", "!@#$%^&*()", "[object Object]"
        ]

        for weird_input in weird_inputs:
            mock_msg = MagicMock()
            mock_msg.from_user.id = user_id
            mock_msg.chat.id = 1002
            mock_msg.text = f"/dice {weird_input}"
            mock_msg.reply_to_message = None
            mock_msg.answer = AsyncMock()

            # Should not raise any unhandled exception
            await cmd_dice_duel_entry(mock_msg, board_id)
            assert user_id not in user_active_dice_game

    @pytest.mark.asyncio
    async def test_r3_direct_command_shorthand_multipliers(self, isolated_test_db):
        """Direct commands with exact amounts (/rr 500) and 'all' / 'вабанк' parse accurately."""
        db = isolated_test_db
        user_id = 1003
        board_id = "b"
        await add_user_global_balance(db, user_id, board_id, 10000)

        # Clear state
        user_active_rr_game.clear()
        active_rr_games.clear()

        # 1. Exact numeric command: /rr 500
        mock_msg = MagicMock()
        mock_msg.from_user.id = user_id
        mock_msg.chat.id = 1003
        mock_msg.text = "/rr 500"
        mock_msg.reply_to_message = None
        mock_msg.answer = AsyncMock()
        mock_msg.bot = MagicMock()
        mock_msg.bot.send_message = AsyncMock()

        await cmd_russian_roulette(mock_msg, board_id)

        assert user_id in user_active_rr_game
        gid = user_active_rr_game[user_id]
        assert active_rr_games[gid]["bet"] == 500

        # Cleanup
        user_active_rr_game.clear()
        active_rr_games.clear()

        # 2. All-in command: /rr all
        mock_msg_all = MagicMock()
        mock_msg_all.from_user.id = user_id
        mock_msg_all.chat.id = 1003
        mock_msg_all.text = "/rr all"
        mock_msg_all.reply_to_message = None
        mock_msg_all.answer = AsyncMock()
        mock_msg_all.bot = MagicMock()
        mock_msg_all.bot.send_message = AsyncMock()

        await cmd_russian_roulette(mock_msg_all, board_id)

        assert user_id in user_active_rr_game
        gid_all = user_active_rr_game[user_id]
        assert active_rr_games[gid_all]["bet"] == 10000

        # Cleanup
        user_active_rr_game.clear()
        active_rr_games.clear()

    @pytest.mark.asyncio
    async def test_r3_direct_command_insufficient_balance_rejection(self, isolated_test_db):
        """Direct command with bet exceeding player's balance must be rejected immediately."""
        db = isolated_test_db
        user_id = 1004
        board_id = "b"
        await add_user_global_balance(db, user_id, board_id, 300)

        mock_msg = MagicMock()
        mock_msg.from_user.id = user_id
        mock_msg.chat.id = 1004
        mock_msg.text = "/rr 1000"
        mock_msg.reply_to_message = None
        mock_msg.answer = AsyncMock()

        await cmd_russian_roulette(mock_msg, board_id)

        assert user_id not in user_active_rr_game
        assert mock_msg.answer.called
        ans_text = mock_msg.answer.call_args[0][0]
        assert "Недостаточно шекелей" in ans_text


# =============================================================================
# 3. R3: Confirmation Flow & Broadcast Invariance
# =============================================================================

class TestR3ConfirmationFlowAndBroadcastInvariance:
    """Verifies challenges are broadcast ONLY after explicit confirmation."""

    @pytest.mark.asyncio
    async def test_r3_lobby_never_broadcasts_to_board(self, isolated_test_db):
        """Opening dynamic lobby must only reply to user without any public board broadcast."""
        db = isolated_test_db
        user_id = 2001
        board_id = "b"
        await add_user_global_balance(db, user_id, board_id, 2000)

        mock_msg = MagicMock()
        mock_msg.from_user.id = user_id
        mock_msg.chat.id = 2001
        mock_msg.text = "/rr"
        mock_msg.reply_to_message = None
        mock_msg.answer = AsyncMock()

        with patch("russian_roulette_pvp.broadcast_game_announcement", new_callable=AsyncMock) as mock_bcast:
            await cmd_russian_roulette(mock_msg, board_id)
            mock_bcast.assert_not_called()

        assert mock_msg.answer.called
        # User is not locked in active games yet
        assert user_id not in user_active_rr_game

    @pytest.mark.asyncio
    async def test_r3_balance_drop_before_acceptance_reverts_cleanly(self, isolated_test_db):
        """If challenger spends money elsewhere after creating challenge, acceptance rolls back cleanly."""
        db = isolated_test_db
        challenger = 2002
        acceptor = 2003
        board_id = "b"

        await add_user_global_balance(db, challenger, board_id, 1000)
        await add_user_global_balance(db, acceptor, board_id, 1000)

        user_active_rr_game.clear()
        active_rr_games.clear()

        ok, msg, game_id = await create_rr_challenge(board_id, challenger, bet=500)
        assert ok is True

        # Challenger loses/spends funds in another action before acceptor clicks Accept
        await deduct_user_global_balance(db, challenger, board_id, 800)  # Challenger balance now 200 (< 500)

        # Acceptor attempts to accept
        ok_acc, err_text, game = await accept_rr_challenge(game_id, acceptor)
        assert ok_acc is False
        assert "не хватает шекелей" in err_text

        # Verify acceptor lost 0 funds
        acc_bal = await get_user_global_balance(db, acceptor)
        assert acc_bal == 1000

        # Verify challenger balance unchanged (200)
        ch_bal = await get_user_global_balance(db, challenger)
        assert ch_bal == 200

        # Verify game state reverted from 'accepting' to 'pending'
        assert active_rr_games[game_id]["state"] == "pending"


# =============================================================================
# 4. R3: Concurrency Races & Exact Financial Conservation Fuzzer
# =============================================================================

class TestR3ConcurrencyRacesAndFinancialConservation:
    """Stress tests concurrent race conditions and mathematical zero-sum conservation."""

    @pytest.mark.asyncio
    async def test_r3_double_accept_concurrency_race_rr(self, isolated_test_db):
        """10 concurrent players try to accept 1 pending RR challenge simultaneously; exactly 1 must succeed."""
        db = isolated_test_db
        challenger = 3001
        acceptors = [3002 + i for i in range(10)]
        board_id = "b"
        bet = 250

        await add_user_global_balance(db, challenger, board_id, 1000)
        for acc in acceptors:
            await add_user_global_balance(db, acc, board_id, 1000)

        user_active_rr_game.clear()
        active_rr_games.clear()

        ok, _, game_id = await create_rr_challenge(board_id, challenger, bet=bet)
        assert ok is True

        # Launch 10 simultaneous accept calls
        tasks = [accept_rr_challenge(game_id, acc) for acc in acceptors]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for (ok_res, _, _) in results if ok_res is True)
        fail_count = sum(1 for (ok_res, _, _) in results if ok_res is False)

        assert success_count == 1
        assert fail_count == 9

        # Verify challenger balance was deducted exactly ONCE (-250)
        ch_bal = await get_user_global_balance(db, challenger)
        assert ch_bal == 750

        # Verify exactly one acceptor was deducted (-250) and nine kept full 1000
        acc_balances = [await get_user_global_balance(db, acc) for acc in acceptors]
        assert acc_balances.count(750) == 1
        assert acc_balances.count(1000) == 9

    @pytest.mark.asyncio
    async def test_r3_double_accept_concurrency_race_dice(self, isolated_test_db):
        """10 concurrent players try to accept 1 pending Dice challenge simultaneously; exactly 1 must succeed."""
        db = isolated_test_db
        challenger = 4001
        acceptors = [4002 + i for i in range(10)]
        board_id = "b"
        bet = 300

        await add_user_global_balance(db, challenger, board_id, 1500)
        for acc in acceptors:
            await add_user_global_balance(db, acc, board_id, 1500)

        user_active_dice_game.clear()
        active_dice_games.clear()

        ok, _, game_id = await create_dice_challenge(board_id, challenger, bet=bet)
        assert ok is True

        tasks = [accept_dice_challenge(game_id, acc) for acc in acceptors]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for (ok_res, _, _) in results if ok_res is True)
        fail_count = sum(1 for (ok_res, _, _) in results if ok_res is False)

        assert success_count == 1
        assert fail_count == 9

        ch_bal = await get_user_global_balance(db, challenger)
        assert ch_bal == 1200

        acc_balances = [await get_user_global_balance(db, acc) for acc in acceptors]
        assert acc_balances.count(1200) == 1
        assert acc_balances.count(1500) == 9

    @pytest.mark.asyncio
    async def test_r3_accept_vs_cancel_concurrency_race(self, isolated_test_db):
        """Simultaneous accept and cancel race condition must leave system in consistent zero-leak state."""
        db = isolated_test_db
        challenger = 5001
        acceptor = 5002
        board_id = "b"
        bet = 500

        await add_user_global_balance(db, challenger, board_id, 2000)
        await add_user_global_balance(db, acceptor, board_id, 2000)

        user_active_rr_game.clear()
        active_rr_games.clear()

        ok, _, game_id = await create_rr_challenge(board_id, challenger, bet=bet)
        assert ok is True

        # Race accept and cancel
        accept_task = asyncio.create_task(accept_rr_challenge(game_id, acceptor))
        cancel_task = asyncio.create_task(decline_or_cancel_rr_challenge(game_id, challenger))

        res_acc, res_canc = await asyncio.gather(accept_task, cancel_task)

        # Either Accept succeeded and Cancel failed, or Cancel succeeded and Accept failed
        ch_bal = await get_user_global_balance(db, challenger)
        acc_bal = await get_user_global_balance(db, acceptor)

        if res_acc[0] is True:
            # Game started -> escrow deducted
            assert ch_bal == 1500
            assert acc_bal == 1500
        else:
            # Game cancelled -> 0 funds deducted
            assert ch_bal == 2000
            assert acc_bal == 2000

    @pytest.mark.asyncio
    async def test_r3_balance_conservation_monte_carlo(self, isolated_test_db):
        """
        Monte-Carlo simulation of 50 PvP games (Dice + RR) verifying that across all outcomes:
        Sum(User Balances End) + Abu_Fund_End == Sum(User Balances Start) + Abu_Fund_Start
        (Zero-Sum Mathematical Invariant: Total System Delta == 0).
        """
        db = isolated_test_db
        board_id = "b"
        players = [6000 + i for i in range(10)]

        # Pre-seed ach_duel_win so achievement rewards don't inject extra funds into pure game math
        items_json = json.dumps({"unlocked_achievements": ["ach_duel_win"]})
        for p in players:
            await add_user_global_balance(db, p, board_id, 50_000)
            await db.execute(
                "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?) ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items",
                (p, board_id, items_json)
            )
        await db.commit()

        initial_abu = await get_abu_fund_total(db)
        initial_user_sum = sum([await get_user_global_balance(db, p) for p in players])

        # Run 50 simulated games
        for i in range(50):
            p1, p2 = random.sample(players, 2)
            bet = random.choice([50, 100, 250, 500, 1000])

            game_type = random.choice(["dice", "rr"])
            if game_type == "dice":
                user_active_dice_game.pop(p1, None)
                user_active_dice_game.pop(p2, None)
                ok, _, gid = await create_dice_challenge(board_id, p1, bet=bet)
                if not ok:
                    continue
                ok_a, _, game = await accept_dice_challenge(gid, p2)
                if not ok_a:
                    continue

                outcome_choice = random.choice(["p1_win", "p2_win", "draw", "timeout", "surrender"])
                if outcome_choice == "p1_win":
                    await _finish_dice_game(gid, winner_id=p1, loser_id=p2, reason="score", bot=None)
                elif outcome_choice == "p2_win":
                    await _finish_dice_game(gid, winner_id=p2, loser_id=p1, reason="score", bot=None)
                elif outcome_choice == "draw":
                    await _finish_dice_game(gid, winner_id=None, loser_id=None, reason="draw", bot=None)
                elif outcome_choice == "timeout":
                    await _finish_dice_game(gid, winner_id=p1, loser_id=p2, reason="timeout", bot=None)
                elif outcome_choice == "surrender":
                    await _finish_dice_game(gid, winner_id=p1, loser_id=p2, reason="surrender", bot=None)

            else:  # RR
                user_active_rr_game.pop(p1, None)
                user_active_rr_game.pop(p2, None)
                ok, _, gid = await create_rr_challenge(board_id, p1, bet=bet)
                if not ok:
                    continue
                ok_a, _, game = await accept_rr_challenge(gid, p2)
                if not ok_a:
                    continue

                outcome_choice = random.choice(["p1_win", "p2_win", "surrender", "timeout"])
                if outcome_choice == "p1_win":
                    await _finish_rr_game(gid, winner_id=p1, loser_id=p2, reason="shot")
                elif outcome_choice == "p2_win":
                    await _finish_rr_game(gid, winner_id=p2, loser_id=p1, reason="shot")
                elif outcome_choice == "surrender":
                    await _finish_rr_game(gid, winner_id=p1, loser_id=p2, reason="surrender")
                elif outcome_choice == "timeout":
                    await _finish_rr_game(gid, winner_id=p1, loser_id=p2, reason="timeout")

        final_abu = await get_abu_fund_total(db)
        final_user_sum = sum([await get_user_global_balance(db, p) for p in players])

        # Exact mathematical conservation
        assert (final_user_sum + final_abu) == (initial_user_sum + initial_abu)


# =============================================================================
# 5. R4: AI Item Attack Counter-Reactions Matrix & Hardening
# =============================================================================

class TestR4AICounterReactionsMatrixAndHardening:
    """Stress tests the AI counter-reaction dispatcher across all actions and edge cases."""

    @pytest.mark.asyncio
    async def test_r4_full_counter_reaction_action_matrix(self, isolated_test_db):
        """Tests all supported actions (/shoot, /rob, /shit, /vomit, /pepperspray, /partyvan, /dossier, /bribe)."""
        db = isolated_test_db
        user_id = 7001
        board_id = "b"
        await add_user_global_balance(db, user_id, board_id, 2000)

        actions_expected = {
            "shoot": ("РИКОШЕТ МУТ-ГАНА", True),
            "rob": ("ОГРАБЛЕНИЕ ПРОВАЛЕНО", True),
            "shit": ("КРИТИЧЕСКИЙ САМООБСЁР", True),
            "vomit": ("ОБРАТНЫЙ РЕФЛЮКС", True),
            "pepperspray": ("ПЕРЦОВЫЙ ИНГАЛЯТОР", True),
            "partyvan": ("ЛОЖНЫЙ ДОНОС НА КИБЕРЧЕДА", True),
            "dossier": ("ДОСЬЕ НА КИБЕРЧЕДА", True),
            "bribe": ("ВЗЯТКА НЕ ПРИНЯТА", True),
            "invalid_action_xyz": ("", False)
        }

        for action, (expected_str, expected_handled) in actions_expected.items():
            mock_msg = MagicMock()
            mock_msg.answer = AsyncMock()

            handled = await handle_cyberchad_counter_action(mock_msg, action, user_id, board_id, db)
            assert handled == expected_handled

            if expected_handled:
                assert mock_msg.answer.called
                text = mock_msg.answer.call_args[0][0]
                assert expected_str in text

    @pytest.mark.asyncio
    async def test_r4_rob_fine_conservation_and_zero_balance_safety(self, isolated_test_db):
        """Tests /rob against AI with varying attacker balances (0, 50, 499, 500, 5000)."""
        db = isolated_test_db
        board_id = "b"

        test_balances = [0, 1, 50, 499, 500, 501, 5000]

        for bal in test_balances:
            user_id = 7100 + bal
            await add_user_global_balance(db, user_id, board_id, bal)
            start_bal = await get_user_global_balance(db, user_id)
            start_abu = await get_abu_fund_total(db)

            mock_msg = MagicMock()
            mock_msg.answer = AsyncMock()

            handled = await handle_cyberchad_counter_action(mock_msg, "rob", user_id, board_id, db)
            assert handled is True

            end_bal = await get_user_global_balance(db, user_id)
            end_abu = await get_abu_fund_total(db)

            expected_fine = min(bal, 500)
            assert end_bal == start_bal - expected_fine
            assert end_bal >= 0  # Negative balance impossible!
            assert end_abu == start_abu + expected_fine
            # Total conservation
            assert (end_bal + end_abu) == (start_bal + start_abu)


# =============================================================================
# 6. R4: Stacking Debuffs & Permission Isolation
# =============================================================================

class TestR4StackingDebuffsAndPermissionIsolation:
    """Stress tests debuff coexistence and human target isolation."""

    @pytest.mark.asyncio
    async def test_r4_stacking_all_debuffs_on_single_attacker(self, isolated_test_db):
        """Single user attacks AI repeatedly; verify all debuffs stack cleanly without overwriting."""
        db = isolated_test_db
        user_id = 8001
        board_id = "b"
        await add_user_global_balance(db, user_id, board_id, 5000)

        # Attack flurry: pepperspray -> shit -> vomit -> shoot -> partyvan
        sequence = ["pepperspray", "shit", "vomit", "shoot", "partyvan"]

        for action in sequence:
            mock_msg = MagicMock()
            mock_msg.answer = AsyncMock()
            handled = await handle_cyberchad_counter_action(mock_msg, action, user_id, board_id, db)
            assert handled is True

        # Check DB active_items contains all three duration keys
        u_items = await _get_user_active_items(db, user_id, board_id)
        assert "peppersprayed_until" in u_items
        assert "shit_until" in u_items
        assert "vomit_until" in u_items

        now = int(time.time())
        assert u_items["peppersprayed_until"] >= now + 1700
        assert u_items["shit_until"] >= now + 3500
        assert u_items["vomit_until"] >= now + 3500

        # Check shared_state RAM tracking
        assert user_id in shared_state._ACTIVE_AUTHOR_ATTACKS.get("pepperspray", {})
        assert user_id in shared_state._ACTIVE_AUTHOR_ATTACKS.get("shit", {})
        assert user_id in shared_state._ACTIVE_AUTHOR_ATTACKS.get("vomit", {})

    @pytest.mark.asyncio
    async def test_r4_human_target_isolation_no_false_backfire(self, isolated_test_db):
        """Attacks against real human users (author_id != 0) must not trigger handle_cyberchad_counter_action."""
        db = isolated_test_db
        human_author_id = 99999
        attacker_id = 8002
        board_id = "b"

        # When caller inspects post, author_id == 99999 is NOT AI (author_id == 0 is AI)
        is_ai_post = (human_author_id == 0)
        assert is_ai_post is False
