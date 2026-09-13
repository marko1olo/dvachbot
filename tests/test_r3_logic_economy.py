# -*- coding: utf-8 -*-
"""
tests/test_r3_logic_economy.py
==============================
Empirical unit & integration test suite covering Milestone 3 fixes:
1. Chain-of-Thought (CoT) & Draft stripping in common/text_utils.py and ai_manager.py.
2. Cyberchad rate-limit rejection sanitization, exact length 20 preservation, and legacy phrase detection.
3. Classic duel escrow lifecycle, refunding on cancel/expiry, and zero-sum balance conservation.
4. Combat moderation bail deduction check, transaction logging, Abu Fund crediting, and safe mock unpacking.
"""

import time
import json
import asyncio
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite

import shared_state
import main
import common.bot_helpers as bh
from common.text_utils import strip_cot_and_drafts, clean_ai_thinking, strip_thinking_tags
from ai_manager import (
    parse_cyberchad_response,
    parse_music_roast_response,
    parse_batch_music_roast_response,
    CYBERCHAD_RATE_LIMIT_REJECTIONS,
    _LEGACY_RATE_LIMIT_REJECTIONS,
    RATE_LIMIT_REJECTION_MARKERS,
)
import handlers.message_router as mr
from common.bot_helpers import accept_duel_logic, decline_duel_logic
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
    get_abu_fund_total,
    record_user_transaction,
)
import combat_moderation_engine as cme
from combat_moderation_engine import (
    create_combat_appeal_session,
    callback_combat_bail,
    reset_combat_moderation_state,
)


@pytest.fixture(autouse=True)
def cleanup_shared_game_states():
    shared_state._active_duels.clear()
    main._duel_cooldowns.clear()
    reset_combat_moderation_state()
    yield
    shared_state._active_duels.clear()
    main._duel_cooldowns.clear()
    reset_combat_moderation_state()


async def pre_seed_achievements(db, user_ids: list[int], board_id: str = "b"):
    """Pre-seed ach_duel_win in Users active_items to prevent achievement bonus money during pure game tests."""
    items_json = json.dumps({"unlocked_achievements": ["ach_duel_win"], "achievements": ["ach_duel_win"]})
    for uid in user_ids:
        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, 0.0, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = ?",
            (uid, board_id, items_json, items_json)
        )
    await db.commit()


# =============================================================================
# SUITE 1: CHAIN-OF-THOUGHT & DRAFT STRIPPING
# =============================================================================

class TestCoTAndDraftStripping:
    """Verifies that LLM meta-reasoning, draft headers, and CoT artifacts are rigorously stripped."""

    def test_strip_cot_removing_pattern(self):
        payload = (
            'Removing "Ой" to avoid sounding overly polite or weak...\n'
            '* Let\'s make it punchy.\n'
            '* *New draft:*\n'
            'Слышь ты, чепуха, иди нахуй.'
        )
        cleaned = strip_cot_and_drafts(payload)
        assert 'Removing' not in cleaned
        assert 'Let\'s' not in cleaned
        assert 'draft' not in cleaned.lower()
        assert cleaned == 'Слышь ты, чепуха, иди нахуй.'

    def test_strip_cot_lets_adjust_and_draft_variants(self):
        payload = (
            '* Draft 1:\n'
            'Let\'s adjust the tone to be more aggressive.\n'
            'Thought: User is whining about code.\n'
            'Поплачь о своей бездарности, мамин программист.'
        )
        cleaned = strip_cot_and_drafts(payload)
        assert 'Draft' not in cleaned
        assert 'adjust' not in cleaned.lower()
        assert 'Thought:' not in cleaned
        assert cleaned == 'Поплачь о своей бездарности, мамин программист.'

    def test_strip_cot_with_xml_tags_and_draft(self):
        payload = (
            '<think>\n'
            'Internal reasoning about user request.\n'
            '</think>\n'
            '* Let\'s change the angle.\n'
            'New draft:\n'
            'Базированный ответ двачера.'
        )
        cleaned = strip_cot_and_drafts(payload)
        assert '<think>' not in cleaned
        assert 'reasoning' not in cleaned.lower()
        assert 'New draft:' not in cleaned
        assert cleaned == 'Базированный ответ двачера.'

    def test_strip_cot_aliases(self):
        payload = 'Removing "test".\n* *New draft:*\nТестовый текст.'
        assert clean_ai_thinking(payload) == 'Тестовый текст.'
        assert strip_thinking_tags(payload) == 'Тестовый текст.'

    def test_parse_cyberchad_response_strips_cot_json(self):
        raw_json = json.dumps({
            "reply": True,
            "thought": "Internal LLM reasoning",
            "text": 'Removing "sorry" from output.\n* Let\'s roast them.\n* *New draft:*\nТы абсолютно безнадежен, омежка.',
            "reason_if_skipped": "",
            "generate_image": False,
            "image_prompt": ""
        })
        res = parse_cyberchad_response(raw_json)
        assert res["reply"] is True
        assert "Removing" not in res["text"]
        assert "New draft" not in res["text"]
        assert res["text"] == "Ты абсолютно безнадежен, омежка."

    def test_parse_cyberchad_response_strips_cot_raw_fallback(self):
        raw_text = (
            'Removing "weakness".\n'
            '* Let\'s make it harder.\n'
            'New draft:\n'
            'Вот твой вердикт, клоун.'
        )
        res = parse_cyberchad_response(raw_text)
        assert res["reply"] is True
        assert "Removing" not in res["text"]
        assert "New draft" not in res["text"]
        assert "Вот твой вердикт, клоун." in res["text"]

    def test_parse_music_roast_response_strips_cot(self):
        raw_roast = (
            '* Let\'s analyze the track.\n'
            'Removing compliments to avoid softness.\n'
            'New draft:\n'
            'ВЕРДИКТ: Унылая попса для сельских дискотек.\n'
            'ОЦЕНКА: 9/10 💩 (Клиническая стадия кала)'
        )
        text, rating = parse_music_roast_response(raw_roast)
        assert "Removing" not in text
        assert "Let's" not in text
        assert "Унылая попса для сельских дискотек." in text
        assert "9/10" in rating

    def test_parse_batch_music_roast_response_strips_cot(self):
        raw_batch = (
            '* Thinking Process:\n'
            '* Let\'s evaluate both tracks.\n'
            'ТРЕК 1: Полный шлак и примитив.\n'
            'ТРЕК 2: Бессмысленный шум.\n'
            'ОБЩИЙ ВЕРДИКТ: Слушатель безнадежен.\n'
            'ИТОГОВАЯ ОЦЕНКА: 10/10 💩 (Тотальный зашквар)'
        )
        reviews, verdict, rating_str, score = parse_batch_music_roast_response(raw_batch, count=2)
        assert len(reviews) == 2
        assert "Thinking Process" not in verdict
        assert "Слушатель безнадежен." in verdict


# =============================================================================
# SUITE 2: CYBERCHAD RATE-LIMIT REJECTION SANITIZATION
# =============================================================================

class TestRateLimitSanitization:
    """Verifies that rate-limit insults are sanitized while maintaining exact len=20 and legacy fallback."""

    def test_rejections_length_preserved(self):
        assert len(CYBERCHAD_RATE_LIMIT_REJECTIONS) == 20
        assert len(mr.CYBERCHAD_RATE_LIMIT_REJECTIONS) == 20

    def test_no_obtekay_or_slysh_in_active_lists(self):
        # Verify in ai_manager
        for i, phrase in enumerate(CYBERCHAD_RATE_LIMIT_REJECTIONS):
            p_lower = phrase.lower()
            assert "обтекай" not in p_lower, f"ai_manager rejection [{i}] contains forbidden word 'обтекай': {phrase}"
            assert "слышь" not in p_lower, f"ai_manager rejection [{i}] contains forbidden word 'слышь': {phrase}"

        # Verify in handlers/message_router
        for i, phrase in enumerate(mr.CYBERCHAD_RATE_LIMIT_REJECTIONS):
            p_lower = phrase.lower()
            assert "обтекай" not in p_lower, f"message_router rejection [{i}] contains forbidden word 'обтекай': {phrase}"
            assert "слышь" not in p_lower, f"message_router rejection [{i}] contains forbidden word 'слышь': {phrase}"

        for i, phrase in enumerate(mr._EXTRA_RATE_LIMIT_REJECTIONS):
            p_lower = phrase.lower()
            assert "обтекай" not in p_lower, f"message_router extra rejection [{i}] contains forbidden word 'обтекай': {phrase}"

    def test_index_3_and_9_content(self):
        # Index 3: "Эй, пулеметчик комнатный, палец с клавиатуры убрал и на таймер посмотрел. Минуту сиди молча и не отсвечивай."
        assert CYBERCHAD_RATE_LIMIT_REJECTIONS[3].startswith("Эй, пулеметчик комнатный")
        assert mr.CYBERCHAD_RATE_LIMIT_REJECTIONS[3].startswith("Эй, пулеметчик комнатный")

        # Index 9: "Хватит мне в личку долбиться, придурок. Минутный кулдаун для особо тупых. Жди молча."
        assert "Жди молча." in CYBERCHAD_RATE_LIMIT_REJECTIONS[9]
        assert "Жди молча." in mr.CYBERCHAD_RATE_LIMIT_REJECTIONS[9]

    def test_legacy_rate_limit_rejections_preserved(self):
        # Legacy list should contain old phrases for backward compatibility / audit
        assert any("обтекай" in s.lower() for s in _LEGACY_RATE_LIMIT_REJECTIONS)
        assert any("обтекай" in s.lower() for s in mr._LEGACY_RATE_LIMIT_REJECTIONS)


# =============================================================================
# SUITE 3: DUEL ESCROW LIFECYCLE & ZERO-SUM BALANCE CONSERVATION
# =============================================================================

class TestDuelEscrowLifecycleAndConservation:
    """Verifies that classic duels escrow stakes up-front, refund on timeout/cancel, and conserve money."""

    @pytest.mark.asyncio
    async def test_duel_create_escrows_funds(self, isolated_test_db):
        db = isolated_test_db
        user_id = 50001
        await add_user_global_balance(db, user_id, "b", 2000.0)

        msg = AsyncMock()
        msg.from_user.id = user_id
        msg.chat.id = 888
        msg.reply_to_message = None
        sent_mock = MagicMock(message_id=999, chat=MagicMock(id=888))
        msg.answer = AsyncMock(return_value=sent_mock)

        await main._handle_duel_create(msg, "b", ["500"])

        # Check balance deducted into escrow immediately
        bal = await get_user_global_balance(db, user_id)
        assert bal == 1500.0

        # Check duel registered with escrowed=True
        duel = shared_state._active_duels.get(user_id)
        assert duel is not None
        assert duel["amount"] == 500
        assert duel.get("escrowed") is True

    @pytest.mark.asyncio
    async def test_duel_create_insufficient_balance_rejected(self, isolated_test_db):
        db = isolated_test_db
        user_id = 50002
        await add_user_global_balance(db, user_id, "b", 100.0)

        msg = AsyncMock()
        msg.from_user.id = user_id
        msg.chat.id = 888
        msg.reply_to_message = None
        msg.answer = AsyncMock()

        await main._handle_duel_create(msg, "b", ["500"])

        # Balance untouched, no duel created
        bal = await get_user_global_balance(db, user_id)
        assert bal == 100.0
        assert user_id not in shared_state._active_duels
        msg.answer.assert_called_once()
        assert "Не хватает шекелей" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_duel_create_replaces_active_duel_with_refund(self, isolated_test_db):
        db = isolated_test_db
        user_id = 50003
        await add_user_global_balance(db, user_id, "b", 3000.0)

        msg = AsyncMock()
        msg.from_user.id = user_id
        msg.chat.id = 888
        msg.reply_to_message = None
        msg.answer = AsyncMock(return_value=MagicMock(message_id=991, chat=MagicMock(id=888)))

        # 1. First duel: 500
        await main._handle_duel_create(msg, "b", ["500"])
        assert await get_user_global_balance(db, user_id) == 2500.0

        # Reset duel cooldown to simulate elapsed cooldown window
        main._duel_cooldowns.pop(user_id, None)

        # 2. Second duel: 1000 replaces first duel -> 500 refunded, 1000 deducted -> 2000 remaining
        msg.answer = AsyncMock(return_value=MagicMock(message_id=992, chat=MagicMock(id=888)))
        await main._handle_duel_create(msg, "b", ["1000"])
        assert await get_user_global_balance(db, user_id) == 2000.0
        assert shared_state._active_duels[user_id]["amount"] == 1000

    @pytest.mark.asyncio
    async def test_duel_decline_refunds_escrowed_funds(self, isolated_test_db):
        db = isolated_test_db
        challenger_id = 50004
        await add_user_global_balance(db, challenger_id, "b", 1000.0)

        # Create active escrowed duel
        shared_state._active_duels[challenger_id] = {
            "amount": 400,
            "target_id": None,
            "ts": time.time(),
            "board_id": "b",
            "msg_id": 100,
            "chat_id": 200,
            "broadcast_msgs": [],
            "escrowed": True,
        }
        # Deduct stake into escrow
        await deduct_user_global_balance(db, challenger_id, "b", 400)
        assert await get_user_global_balance(db, challenger_id) == 600.0

        # Decline duel
        msg = AsyncMock()
        msg.from_user.id = challenger_id
        res = await decline_duel_logic(msg, challenger_id, challenger_id)
        assert res is True
        assert challenger_id not in shared_state._active_duels

        # Funds refunded
        assert await get_user_global_balance(db, challenger_id) == 1000.0

    @pytest.mark.asyncio
    async def test_duel_watchdog_step_refunds_expired_duel(self, isolated_test_db):
        db = isolated_test_db
        challenger_id = 50005
        await add_user_global_balance(db, challenger_id, "b", 500.0)

        # Register expired duel (> 120s ago)
        shared_state._active_duels[challenger_id] = {
            "amount": 300,
            "target_id": None,
            "ts": time.time() - 150,
            "board_id": "b",
            "msg_id": 101,
            "chat_id": 201,
            "broadcast_msgs": [],
            "escrowed": True,
        }
        await deduct_user_global_balance(db, challenger_id, "b", 300)
        assert await get_user_global_balance(db, challenger_id) == 200.0

        mock_bot = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()

        # Run watchdog step
        await main.classic_duel_watchdog_step(mock_bot)

        # Duel expired and popped
        assert challenger_id not in shared_state._active_duels
        # Stake refunded
        assert await get_user_global_balance(db, challenger_id) == 500.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("winner_choice", ["challenger", "acceptor"])
    async def test_accept_duel_exact_mathematical_conservation(self, isolated_test_db, winner_choice):
        db = isolated_test_db
        p1 = 50010
        p2 = 50020
        stake = 1000

        await pre_seed_achievements(db, [p1, p2])
        await add_user_global_balance(db, p1, "b", 50_000)
        await add_user_global_balance(db, p2, "b", 50_000)

        init_p1 = await get_user_global_balance(db, p1)
        init_p2 = await get_user_global_balance(db, p2)
        init_abu = await get_abu_fund_total(db)
        init_total = init_p1 + init_p2 + init_abu

        # Challenger already escrowed stake 1000
        await deduct_user_global_balance(db, p1, "b", stake)
        shared_state._active_duels[p1] = {
            "amount": stake,
            "target_id": None,
            "ts": time.time(),
            "board_id": "b",
            "msg_id": 901,
            "chat_id": 902,
            "broadcast_msgs": [],
            "escrowed": True,
        }

        winner_id = p1 if winner_choice == "challenger" else p2
        msg = AsyncMock()
        msg.from_user.id = p2
        msg.answer = AsyncMock()

        with patch("random.choice", return_value=winner_id):
            await accept_duel_logic(msg, p1, "b")

        assert p1 not in shared_state._active_duels

        final_p1 = await get_user_global_balance(db, p1)
        final_p2 = await get_user_global_balance(db, p2)
        final_abu = await get_abu_fund_total(db)
        final_total = final_p1 + final_p2 + final_abu

        # Absolute zero-sum conservation
        delta_p1 = final_p1 - init_p1
        delta_p2 = final_p2 - init_p2
        delta_abu = final_abu - init_abu

        assert delta_p1 + delta_p2 + delta_abu == 0.0
        assert final_total == init_total

        expected_rake = max(1, int(stake * 0.05))
        assert delta_abu == expected_rake

        if winner_id == p1:
            assert delta_p2 == -stake
            assert delta_p1 == stake - expected_rake
        else:
            assert delta_p1 == -stake
            assert delta_p2 == stake - expected_rake


# =============================================================================
# SUITE 4: COMBAT MODERATION BAIL DEDUCTION CHECK
# =============================================================================

class TestCombatModerationBailDeduction:
    """Verifies safe deduction unpacking, transaction recording, and aborting unmute on failure."""

    @pytest.mark.asyncio
    async def test_bail_payment_success(self, isolated_test_db):
        db = isolated_test_db
        attacker = 60001
        target = 60002
        payer = 60003

        await add_user_global_balance(db, payer, "b", 2000.0)
        sess_id = create_combat_appeal_session("b", attacker, target, "partyvan", 7200)

        cb = MagicMock()
        cb.from_user.id = payer
        cb.data = f"cbail:{sess_id}"
        cb.answer = AsyncMock()
        cb.message.edit_text = AsyncMock()

        with patch("main.get_current_item_price", return_value=600.0), \
             patch("main.remove_regular_mute", new_callable=AsyncMock) as mock_unmute:
            await callback_combat_bail(cb)

            # Target unmuted
            mock_unmute.assert_called_once_with(target, "b")
            cb.message.edit_text.assert_called_once()
            assert "ВЫКУП ИЗ-ПОД АРЕСТА" in cb.message.edit_text.call_args[0][0]

            # Balance deducted from payer
            final_payer_bal = await get_user_global_balance(db, payer)
            assert final_payer_bal == 1400.0

            # Abu Fund received bail
            abu_total = await get_abu_fund_total(db)
            assert abu_total >= 600

    @pytest.mark.asyncio
    async def test_bail_payment_insufficient_initial_balance(self, isolated_test_db):
        db = isolated_test_db
        attacker = 60011
        target = 60012
        payer = 60013

        await add_user_global_balance(db, payer, "b", 200.0)  # less than 600
        sess_id = create_combat_appeal_session("b", attacker, target, "partyvan", 7200)

        cb = MagicMock()
        cb.from_user.id = payer
        cb.data = f"cbail:{sess_id}"
        cb.answer = AsyncMock()

        with patch("main.get_current_item_price", return_value=600.0), \
             patch("main.remove_regular_mute", new_callable=AsyncMock) as mock_unmute, \
             patch("main.deduct_user_global_balance", new_callable=AsyncMock) as mock_deduct:
            await callback_combat_bail(cb)

            mock_deduct.assert_not_called()
            mock_unmute.assert_not_called()
            cb.answer.assert_called_once()
            assert "Недостаточно шекелей" in cb.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_bail_payment_deduction_failure_aborts_unmute(self, isolated_test_db):
        db = isolated_test_db
        attacker = 60021
        target = 60022
        payer = 60023

        await add_user_global_balance(db, payer, "b", 1000.0)
        sess_id = create_combat_appeal_session("b", attacker, target, "partyvan", 7200)

        cb = MagicMock()
        cb.from_user.id = payer
        cb.data = f"cbail:{sess_id}"
        cb.answer = AsyncMock()
        cb.message.edit_text = AsyncMock()

        # Deduct returns failure tuple (False, balance)
        with patch("main.get_current_item_price", return_value=600.0), \
             patch("main.deduct_user_global_balance", new_callable=AsyncMock, return_value=(False, 0.0)), \
             patch("main.remove_regular_mute", new_callable=AsyncMock) as mock_unmute:
            await callback_combat_bail(cb)

            # Unmute must NOT be called when deduction fails
            mock_unmute.assert_not_called()
            cb.answer.assert_called_once()
            assert "Недостаточно шекелей" in cb.answer.call_args[0][0]
            cb.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_bail_payment_safe_async_mock_unpacking(self, isolated_test_db):
        """Ensures bare AsyncMock from unit tests does not raise ValueError: not enough values to unpack."""
        db = isolated_test_db
        attacker = 60031
        target = 60032
        payer = 60033

        await add_user_global_balance(db, payer, "b", 1000.0)
        sess_id = create_combat_appeal_session("b", attacker, target, "partyvan", 7200)

        cb = MagicMock()
        cb.from_user.id = payer
        cb.data = f"cbail:{sess_id}"
        cb.answer = AsyncMock()
        cb.message.edit_text = AsyncMock()

        # Standard AsyncMock without explicit return_value returns another AsyncMock instance
        bare_mock_deduct = AsyncMock()

        with patch("main.get_current_item_price", return_value=600.0), \
             patch("main.deduct_user_global_balance", bare_mock_deduct), \
             patch("main.remove_regular_mute", new_callable=AsyncMock) as mock_unmute:
            # Must not throw ValueError
            await callback_combat_bail(cb)
            mock_unmute.assert_called_once_with(target, "b")
