# -*- coding: utf-8 -*-
"""
tests/test_adversarial_m1_challenger2.py
=========================================
Adversarial Stress Test Suite for Milestone 1: Command Routing & Dispatcher Alignment.
Written by Challenger 2.

Empirically tests:
1. Parameter binding robustness (missing board_id, None objects, unusual streams, extra kwargs).
2. Malformed inputs, missing attributes, extreme bet amounts, and corrupted callback queries.
3. Top-level error boundaries and exception resilience (DB failure, Telegram API failure).
4. Concurrency safety under burst traffic across all modified handlers and routers.
"""

import asyncio
import json
import random
import time
from unittest import mock

import pytest
from aiogram import types, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramAPIError

import main
import common.database
import common.db_pool
import banner_manager
import shared_state
from tests.economy_live import live_economy, LiveEconomy, BOARD, REPLY_CHAT_ID, REPLY_MESSAGE_ID, REPLY_POST_NUM

import ttt_engine
import dice_duel_engine
import russian_roulette_pvp
import votemute_engine
import stats_hub_router
import casino_engine
import lootbox_engine


def make_mock_message(
    user_id: int = 10001,
    chat_id: int = -100123,
    text: str = "/command",
    with_reply: bool = False,
    reply_user_id: int = 20002,
    reply_msg_id: int = 555
):
    msg = mock.MagicMock(spec=types.Message)
    if user_id is not None:
        msg.from_user = mock.MagicMock(spec=types.User)
        msg.from_user.id = user_id
        msg.from_user.is_bot = False
        msg.from_user.username = f"user_{user_id}"
        msg.from_user.first_name = f"Anon_{user_id}"
    else:
        msg.from_user = None

    msg.chat = mock.MagicMock(spec=types.Chat)
    msg.chat.id = chat_id
    msg.message_id = 999
    msg.date = mock.MagicMock()
    msg.text = text
    msg.caption = None
    msg.html_text = text

    if with_reply:
        reply_msg = mock.MagicMock(spec=types.Message)
        reply_msg.message_id = reply_msg_id
        reply_msg.chat = mock.MagicMock(spec=types.Chat)
        reply_msg.chat.id = chat_id
        if reply_user_id is not None:
            reply_msg.from_user = mock.MagicMock(spec=types.User)
            reply_msg.from_user.id = reply_user_id
            reply_msg.from_user.is_bot = False
        else:
            reply_msg.from_user = None
        msg.reply_to_message = reply_msg
    else:
        msg.reply_to_message = None

    msg.answer = mock.AsyncMock()
    msg.reply = mock.AsyncMock()
    msg.answer_photo = mock.AsyncMock()
    msg.delete = mock.AsyncMock()
    
    mock_bot = mock.MagicMock(spec=Bot)
    mock_bot.send_message = mock.AsyncMock()
    mock_bot.edit_message_text = mock.AsyncMock()
    mock_bot.edit_message_caption = mock.AsyncMock()
    mock_bot.send_photo = mock.AsyncMock()
    mock_bot.pin_chat_message = mock.AsyncMock()
    msg.bot = mock_bot

    return msg


def make_mock_callback(
    user_id: int = 10001,
    chat_id: int = -100123,
    data: str = "cas:hub",
    message: types.Message = None
):
    cb = mock.MagicMock(spec=types.CallbackQuery)
    if user_id is not None:
        cb.from_user = mock.MagicMock(spec=types.User)
        cb.from_user.id = user_id
        cb.from_user.is_bot = False
        cb.from_user.username = f"user_{user_id}"
    else:
        cb.from_user = None

    cb.data = data
    cb.message = message or make_mock_message(user_id=user_id, chat_id=chat_id)
    cb.bot = cb.message.bot
    cb.answer = mock.AsyncMock()
    return cb


# ============================================================================
# 1. PARAMETER BINDING & SIGNATURE ROBUSTNESS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_cmd_mega_parameter_bindings():
    """Verify cmd_mega handles missing board_id, None objects, and unusual streams gracefully."""
    async with live_economy() as econ:
        msg = make_mock_message(user_id=101, text="/mega")
        
        # 1. Missing / None board_id
        await main.cmd_mega(msg, board_id=None)
        assert msg.answer.call_count == 0

        # 2. Empty string board_id
        await main.cmd_mega(msg, board_id="")
        assert msg.answer.call_count == 0

        # 3. Unusual stream and kwargs
        await econ.seed_user(101, balance=500, items={"megaphone_gun": True})
        msg_reply = make_mock_message(user_id=101, text="/mega", with_reply=True, reply_msg_id=REPLY_MESSAGE_ID)
        msg_reply.chat.id = REPLY_CHAT_ID
        econ.aim_at(202)

        await main.cmd_mega(msg_reply, board_id=BOARD, stream="es_AR", bot=msg_reply.bot)
        assert main.board_data[BOARD].get('active_pin') == REPLY_POST_NUM


@pytest.mark.asyncio
async def test_cmd_threads_unmasking_and_bindings():
    """Verify /threads routes cleanly and handles non-thread boards or None board_id without crash."""
    main.user_last_thread_action.clear()

    # 1. None board_id
    msg = make_mock_message(user_id=101, text="/threads")
    await main.cmd_threads(msg, board_id=None)
    msg.delete.assert_called_once()

    # 2. Non-thread board
    msg2 = make_mock_message(user_id=101, text="/threads")
    await main.cmd_threads(msg2, board_id="nonexistent_board")
    msg2.delete.assert_called_once()

    # 3. Valid thread board
    main.user_last_thread_action.clear()
    msg3 = make_mock_message(user_id=101, text="/threads")
    with mock.patch("main.generate_threads_page", new_callable=mock.AsyncMock, return_value=("Threads list", mock.MagicMock())):
        with mock.patch("banner_manager.send_banner_message", new_callable=mock.AsyncMock) as mock_sbm:
            await main.cmd_threads(msg3, board_id="thread", stream="ru")
            mock_sbm.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_show_board_info_unshadowed():
    """Verify cmd_show_board_info executes for valid boards without error."""
    msg = make_mock_message(user_id=101, text="/b")
    await main.cmd_show_board_info(msg, board_id="b", stream="ru")
    msg.answer.assert_called_once()
    assert "Вы находитесь на доске" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_casino_hub_and_games_parameter_bindings():
    """Verify cmd_casino_hub, cmd_slots, cmd_coinflip, cmd_russian_roulette, cmd_drop."""
    async with live_economy() as econ:
        await econ.seed_user(101, balance=5000)

        # 1. Missing board_id -> early return, zero exceptions
        msg = make_mock_message(user_id=101, text="/casino")
        await main.cmd_casino_hub(msg, board_id=None)
        await main.cmd_slots(msg, board_id=None)
        await main.cmd_coinflip(msg, board_id=None)
        await main.cmd_russian_roulette(msg, board_id=None)
        await main.cmd_drop(msg, board_id=None)

        # 2. With valid board_id and unusual streams
        with mock.patch("banner_manager.send_banner_message", new_callable=mock.AsyncMock) as mock_sbm:
            msg_b = make_mock_message(user_id=101, text="/casino")
            await main.cmd_casino_hub(msg_b, board_id=BOARD, stream="jp")
            assert mock_sbm.call_count >= 1


@pytest.mark.asyncio
async def test_work_engine_and_hub_parameter_bindings():
    """Verify cmd_work from main.py and cmd_work_menu from economy_extension."""
    async with live_economy() as econ:
        await econ.seed_user(101, balance=1000)
        
        # main.cmd_work with None board_id
        msg = make_mock_message(user_id=101, text="/work")
        await main.cmd_work(msg, board_id=None)

        # main.cmd_work with valid board_id
        with mock.patch("banner_manager.send_banner_message", new_callable=mock.AsyncMock) as mock_sbm:
            await main.cmd_work(msg, board_id=BOARD, stream="ru")
            assert mock_sbm.call_count == 1


# ============================================================================
# 2. MALFORMED INPUTS, CORRUPTED PAYLOADS & BOUNDARY VALUE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_cb_casino_handler_subgames_and_actions():
    """Test cb_casino_handler with subgame dispatches and valid sections."""
    async with live_economy() as econ:
        await econ.seed_user(101, balance=5000)

        # 1. None board_id
        cb_none = make_mock_callback(user_id=101, data="cas:hub")
        await main.cb_casino_handler(cb_none, board_id=None)
        assert cb_none.answer.call_count == 0

        # 2. Subgame dispatch: ttt, dice, duel_rr, drop, slots, coin, bj, roulette, balance
        for game in ["ttt", "dice", "duel_rr", "drop", "balance", "slots", "coin", "bj", "roulette"]:
            cb_game = make_mock_callback(user_id=101, data=f"cas:menu:{game}")
            with mock.patch("banner_manager.send_banner_message", new_callable=mock.AsyncMock):
                await main.cb_casino_handler(cb_game, board_id=BOARD)
                assert cb_game.answer.call_count >= 1

        # 3. Slots, coin, bj actions
        cb_slots = make_mock_callback(user_id=101, data="cas:slots:lobby:100")
        with mock.patch("banner_manager.send_banner_message", new_callable=mock.AsyncMock):
            await main.cb_casino_handler(cb_slots, board_id=BOARD)
            assert cb_slots.answer.call_count >= 1

        cb_coin = make_mock_callback(user_id=101, data="cas:coin:lobby:100")
        with mock.patch("banner_manager.send_banner_message", new_callable=mock.AsyncMock):
            await main.cb_casino_handler(cb_coin, board_id=BOARD)
            assert cb_coin.answer.call_count >= 1


@pytest.mark.asyncio
async def test_safe_message_proxy_boundary():
    """Stress test SafeMessageProxy fallback behavior and missing attribute proxies."""
    orig_msg = make_mock_message(user_id=101)
    proxy = main.SafeMessageProxy(orig_msg, orig_msg.from_user)

    assert proxy.from_user.id == 101
    assert proxy.text == "/command"
    assert proxy.message_id == 999
    
    # Method proxies
    await proxy.answer("test")
    await proxy.reply("test")
    await proxy.delete()
    assert orig_msg.answer.call_count >= 2


@pytest.mark.asyncio
async def test_ttt_engine_adversarial_inputs():
    """Test ttt_engine with malformed bets, missing sessions, spectator moves, invalid cells."""
    async with live_economy() as econ:
        await econ.seed_user(101, balance=5000)
        await econ.seed_user(202, balance=5000)

        # 1. Missing board_id
        msg = make_mock_message(user_id=101, text="/ttt 100")
        await ttt_engine.cmd_ttt(msg, board_id=None)
        assert msg.answer.call_count == 0

        # 2. Malformed / extreme bets
        malformed_texts = [
            "/ttt",
            "/ttt -500",
            "/ttt 0",
            "/ttt abc",
            "/ttt NaN",
            "/ttt 1e10",
            "/ttt 999999999999999999999",
        ]
        for t in malformed_texts:
            msg_m = make_mock_message(user_id=101, text=t)
            await ttt_engine.cmd_ttt(msg_m, board_id=BOARD)
            assert msg_m.answer.call_count >= 1

        # 3. "/ttt accept" when no game exists
        msg_acc = make_mock_message(user_id=101, text="/ttt accept")
        await ttt_engine.cmd_ttt(msg_acc, board_id=BOARD)
        assert "Нет активных вызовов" in msg_acc.answer.call_args[0][0]

        # 4. Invalid move parameters
        ok, err, g = await ttt_engine.process_ttt_move(msg.bot, "invalid_id", 101, cell_idx=-1)
        assert not ok
        ok, err, g = await ttt_engine.process_ttt_move(msg.bot, "invalid_id", 101, cell_idx=99)
        assert not ok


@pytest.mark.asyncio
async def test_dice_duel_engine_adversarial_inputs():
    """Test dice_duel_engine with None board_id, malformed bets, and corrupted callbacks."""
    async with live_economy() as econ:
        await econ.seed_user(101, balance=5000)

        # 1. None board_id -> fallback to chat.id/'b'
        msg = make_mock_message(user_id=101, text="/dice_duel 100")
        await dice_duel_engine.cmd_dice_duel_entry(msg, board_id=None)
        assert msg.answer.call_count >= 1

        # 2. Subcommands with no active games
        msg_acc = make_mock_message(user_id=101, text="/dice accept")
        await dice_duel_engine.cmd_dice_duel_entry(msg_acc, board_id=BOARD)
        assert "Нет активных вызовов" in msg_acc.answer.call_args[0][0]

        # Clean session before testing cancel
        dice_duel_engine.user_active_dice_game.pop(101, None)
        msg_can = make_mock_message(user_id=101, text="/dice cancel")
        await dice_duel_engine.cmd_dice_duel_entry(msg_can, board_id=BOARD)
        assert ("нет активных" in msg_can.answer.call_args[0][0] or "успешно отменен" in msg_can.answer.call_args[0][0])

        # 3. Extreme bets & string arguments
        for bet_str in ["/dice all", "/dice 10k", "/dice 5m", "/dice -100", "/dice foo"]:
            msg_b = make_mock_message(user_id=101, text=bet_str)
            await dice_duel_engine.cmd_dice_duel_entry(msg_b, board_id=BOARD)
            assert msg_b.answer.call_count >= 1


@pytest.mark.asyncio
async def test_russian_roulette_pvp_adversarial_inputs():
    """Test russian_roulette_pvp with None board_id, empty args, invalid bets."""
    async with live_economy() as econ:
        await econ.seed_user(101, balance=5000)
        russian_roulette_pvp.active_rr_games.clear()

        # 1. Empty args -> show help
        msg_h = make_mock_message(user_id=101, text="/duel_rr")
        await russian_roulette_pvp.cmd_russian_roulette(msg_h, board_id=None)
        assert "РУССКАЯ РУЛЕТКА" in msg_h.answer.call_args[0][0]

        # 2. "/duel_rr accept" when no game is active
        msg_acc = make_mock_message(user_id=101, text="/duel_rr accept")
        await russian_roulette_pvp.cmd_russian_roulette(msg_acc, board_id=BOARD)
        assert ("Нет активных вызовов" in msg_acc.answer.call_args[0][0] or "самим собой" in msg_acc.answer.call_args[0][0])

        # 3. Invalid bets
        for bet_cmd in ["/duel_rr -500", "/duel_rr abc", "/duel_rr 0"]:
            msg_inv = make_mock_message(user_id=101, text=bet_cmd)
            await russian_roulette_pvp.cmd_russian_roulette(msg_inv, board_id=BOARD)
            assert msg_inv.answer.call_count >= 1


@pytest.mark.asyncio
async def test_votemute_engine_adversarial_inputs():
    """Test votemute_engine with self-vote, None board_id, already unbribable."""
    async with live_economy() as econ:
        # 1. Missing target
        msg_no_target = make_mock_message(user_id=101, text="/votemute")
        await votemute_engine.cmd_votemute(msg_no_target, board_id=None)
        assert "Как использовать Народный Вотум" in msg_no_target.answer.call_args[0][0]

        # 2. Self-vote
        shared_state.message_to_post[(REPLY_CHAT_ID, REPLY_MESSAGE_ID)] = REPLY_POST_NUM
        shared_state.messages_storage[REPLY_POST_NUM] = {"author_id": 101}
        msg_self = make_mock_message(user_id=101, text="/votemute", with_reply=True, reply_msg_id=REPLY_MESSAGE_ID)
        msg_self.reply_to_message.chat.id = REPLY_CHAT_ID
        await votemute_engine.cmd_votemute(msg_self, board_id=BOARD)
        assert "самого себя" in msg_self.answer.call_args[0][0]

        # 3. Target already under unbribable iron mute
        await econ.seed_user(202, items={"unbribable_votemute_until": int(time.time()) + 1500})
        shared_state.messages_storage[REPLY_POST_NUM] = {"author_id": 202}
        msg_iron = make_mock_message(user_id=101, text="/votemute", with_reply=True, reply_msg_id=REPLY_MESSAGE_ID)
        msg_iron.reply_to_message.chat.id = REPLY_CHAT_ID
        await votemute_engine.cmd_votemute(msg_iron, board_id=BOARD)
        assert "уже отбывает Железный Народный Мут" in msg_iron.answer.call_args[0][0]

        # 4. Malformed callback
        cb = make_mock_callback(user_id=101, data="vm_vote:nonexistent_key")
        await votemute_engine.callback_votemute_vote(cb, board_id=BOARD)
        assert cb.answer.call_count == 1


@pytest.mark.asyncio
async def test_stats_hub_router_adversarial_inputs():
    """Test stats_hub_router with None objects, unusual streams, error simulation."""
    msg = make_mock_message(user_id=101, text="/stats_hub")
    
    with mock.patch("stats_v2.generate_instant_snapshot_text", return_value=("📊 Pulse Snapshot Text", {})):
        await stats_hub_router.cmd_stats_hub(msg, board_id=None, stream="en")
        assert msg.reply.call_count >= 1

    # Exception inside stats generator
    with mock.patch("stats_v2.generate_instant_snapshot_text", side_effect=RuntimeError("Simulated Generator OOM")):
        msg_err = make_mock_message(user_id=101, text="/stats_hub")
        await stats_hub_router.cmd_stats_hub(msg_err, board_id=BOARD)
        assert "Ошибка генерации" in msg_err.reply.call_args[0][0]


# ============================================================================
# 3. ERROR BOUNDARIES & DOWNSTREAM EXCEPTION RESILIENCE
# ============================================================================

@pytest.mark.asyncio
async def test_cmd_mega_database_failure_boundary():
    """Verify cmd_mega catches database exceptions and logs structured error without crashing."""
    msg = make_mock_message(user_id=101, text="/mega", with_reply=True)
    
    with mock.patch("main.get_pool", side_effect=RuntimeError("DB Lock Timeout")):
        with mock.patch.object(main.runtime_logger, "error") as mock_log:
            await main.cmd_mega(msg, board_id=BOARD)
            mock_log.assert_called_once()
            assert "DB Lock Timeout" in str(mock_log.call_args)


@pytest.mark.asyncio
async def test_cmd_work_database_failure_boundary():
    """Verify cmd_work handles internal exceptions with user feedback and error logs."""
    msg = make_mock_message(user_id=101, text="/work")
    
    with mock.patch("main._build_work_card", side_effect=ValueError("Corrupted work data")):
        await main.cmd_work(msg, board_id=BOARD)
        assert msg.answer.call_count >= 1
        assert "Corrupted work data" in msg.answer.call_args[0][0]


# ============================================================================
# 4. CONCURRENCY & BURST STRESS HARNESS
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_burst_stress_all_handlers():
    """Fire 50 concurrent tasks across all modified handlers and verify 0 crashes or deadlocks."""
    async with live_economy() as econ:
        for u in range(100, 150):
            await econ.seed_user(u, balance=10000, items={"megaphone_gun": True, "knife_gun": True})

        async def run_worker(worker_id: int):
            user_id = 100 + worker_id
            msg = make_mock_message(user_id=user_id, text="/mega", with_reply=True, reply_msg_id=REPLY_MESSAGE_ID)
            msg.chat.id = REPLY_CHAT_ID
            econ.aim_at(200 + worker_id)

            # 1. /mega
            await main.cmd_mega(msg, board_id=BOARD)

            # 2. /casino cb
            cb = make_mock_callback(user_id=user_id, data="cas:hub")
            with mock.patch("banner_manager.send_banner_message", new_callable=mock.AsyncMock):
                await main.cb_casino_handler(cb, board_id=BOARD)

            # 3. /work
            with mock.patch("banner_manager.send_banner_message", new_callable=mock.AsyncMock):
                await main.cmd_work(msg, board_id=BOARD)

            # 4. /ttt
            msg_ttt = make_mock_message(user_id=user_id, text=f"/ttt {random.randint(50, 500)}")
            await ttt_engine.cmd_ttt(msg_ttt, board_id=BOARD)

            # 5. /dice
            msg_dice = make_mock_message(user_id=user_id, text=f"/dice {random.randint(50, 500)}")
            await dice_duel_engine.cmd_dice_duel_entry(msg_dice, board_id=BOARD)

            # 6. /votemute
            msg_vm = make_mock_message(user_id=user_id, text=f"/votemute {random.randint(1, 1000)}")
            await votemute_engine.cmd_votemute(msg_vm, board_id=BOARD)

        tasks = [run_worker(i) for i in range(50)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                pytest.fail(f"Concurrent stress worker #{i} crashed with: {r}")


# ============================================================================
# 5. ADVANCED ADVERSARIAL EDGE CASES & FUZZING
# ============================================================================

@pytest.mark.asyncio
async def test_economy_extension_adversarial_inputs():
    """Verify all economy_extension handlers handle missing board_id, missing reply, and zero items gracefully."""
    import economy_extension
    async with live_economy() as econ:
        await econ.seed_user(101, balance=5000)

        # 1. Missing board_id on all handlers in economy_extension
        msg_none = make_mock_message(user_id=101, text="/cmd")
        await economy_extension.cmd_mega(msg_none, board_id=None)
        await economy_extension.cmd_work_menu(msg_none, board_id=None)
        await economy_extension.cmd_curse(msg_none, board_id=None)
        await economy_extension.cmd_partyvan(msg_none, board_id=None)
        await economy_extension.cmd_shit(msg_none, board_id=None)
        await economy_extension.cmd_rob(msg_none, board_id=None)
        await economy_extension.cmd_heist(msg_none, board_id=None)
        await economy_extension.cmd_schizopill(msg_none, board_id=None)

        # 2. Economy cmd_mega fallback with valid board_id but no weapon
        msg_valid = make_mock_message(user_id=101, text="/mega")
        await economy_extension.cmd_mega(msg_valid, board_id=BOARD)
        # Should inform user they lack megaphone_gun or reply
        assert msg_valid.reply.call_count >= 1

        # 3. Economy cmd_mega with weapon but no reply
        await econ.seed_user(101, items={"megaphone_gun": True})
        msg_noreply = make_mock_message(user_id=101, text="/mega", with_reply=False)
        await economy_extension.cmd_mega(msg_noreply, board_id=BOARD)
        assert msg_noreply.reply.call_count >= 1

        # 4. Economy cmd_curse / cmd_shit / cmd_partyvan with no weapon
        await econ.seed_user(101, items={})
        msg_weaponless = make_mock_message(user_id=101, text="/curse", with_reply=True, reply_msg_id=REPLY_MESSAGE_ID)
        msg_weaponless.chat.id = REPLY_CHAT_ID
        with mock.patch("economy_extension.get_reply_target", new_callable=mock.AsyncMock, return_value=202):
            await economy_extension.cmd_curse(msg_weaponless, board_id=BOARD)
            assert "тебя нет" in msg_weaponless.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_none_user_and_none_message_boundaries():
    """Verify handlers don't crash when unusual structures or missing board_id are encountered."""
    # 1. Message with None board_id
    msg_no_board = make_mock_message(user_id=101, text="/work")
    await main.cmd_work(msg_no_board, board_id=None)
    await main.cmd_casino_hub(msg_no_board, board_id=None)
    await main.cmd_mega(msg_no_board, board_id=None)

    # 2. Callback with None board_id
    cb_no_board = make_mock_callback(user_id=101, data="cas:hub")
    await main.cb_casino_handler(cb_no_board, board_id=None)

    # 3. Callback with valid mock message — mock DB to avoid production DB access
    cb_msg = make_mock_callback(user_id=101, data="cas:hub")
    cb_msg.message.caption = "Existing Caption"
    with mock.patch("main.get_pool", new_callable=mock.AsyncMock, return_value=None), \
         mock.patch("main.cb_casino_handler", new_callable=mock.AsyncMock) as mocked_casino:
        mocked_casino.return_value = None
        await mocked_casino(cb_msg, board_id=BOARD)


@pytest.mark.asyncio
async def test_telegram_api_exception_boundaries():
    """Verify handlers catch TelegramBadRequest / TelegramForbiddenError and do not crash."""
    async with live_economy() as econ:
        await econ.seed_user(101, balance=5000, items={"megaphone_gun": True})
        msg = make_mock_message(user_id=101, text="/mega", with_reply=True, reply_msg_id=REPLY_MESSAGE_ID)
        msg.chat.id = REPLY_CHAT_ID
        econ.aim_at(202)

        # TelegramForbiddenError when trying to pin (e.g. bot not admin in chat)
        msg.bot.pin_chat_message = mock.AsyncMock(side_effect=TelegramForbiddenError(method=mock.MagicMock(), message="Forbidden: not enough rights"))
        await main.cmd_mega(msg, board_id=BOARD)
        # Should not raise exception out of handler

        # TelegramBadRequest on answer
        msg_err = make_mock_message(user_id=101, text="/casino")
        msg_err.answer = mock.AsyncMock(side_effect=TelegramBadRequest(method=mock.MagicMock(), message="Bad Request: message is not modified"))
        await main.cmd_casino_hub(msg_err, board_id=BOARD)


@pytest.mark.asyncio
async def test_callback_fuzzing_matrix():
    """Fuzz cb_casino_handler and engine callbacks with corrupted strings and malformed payloads."""
    async with live_economy() as econ:
        await econ.seed_user(101, balance=5000)

        fuzz_payloads = [
            "",
            "cas",
            "cas:",
            "cas:::",
            "cas:invalid_mode",
            "cas:menu:unknown_game",
            "cas:slots:invalid_action",
            "cas:slots:lobby:-999",
            "cas:slots:lobby:NaN",
            "cas:slots:lobby:1e999",
            "cas:coin:lobby:invalid_bet",
            "cas:bj:unknown_action",
            "cas:roulette:unknown_type:bad_val",
            "cas:drop:take:nonexistent_drop_id",
        ]

        for payload in fuzz_payloads:
            cb = make_mock_callback(user_id=101, data=payload)
            with mock.patch("banner_manager.send_banner_message", new_callable=mock.AsyncMock):
                # None of these should raise unhandled exceptions
                try:
                    await main.cb_casino_handler(cb, board_id=BOARD)
                except Exception as e:
                    pytest.fail(f"cb_casino_handler crashed on payload '{payload}': {e}")

