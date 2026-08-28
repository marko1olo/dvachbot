# -*- coding: utf-8 -*-
"""
Unit and integration tests for Bank of Abu direct chat message deposit amount input:
'КОГДА ВЫБИРАЕТСЯ ПОПОЛНЕНИЕ ВКЛАДА ТАМ ЕСЛИ В ЭТОТ МОМЕНТ НАПИСАТЬ ПРОСТО В ЧАТ
СООБЩЕНИЕ С СУММОЙ ТО ЕЕ ВНЕСТИ'
"""

import time
import pytest
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bank_engine import (
    parse_deposit_amount,
    parse_amount_and_tier,
    set_user_pending_deposit,
    get_user_pending_deposit,
    clear_user_pending_deposit,
    PendingBankDepositFilter,
    handle_chat_deposit_amount,
    USER_PENDING_BANK_DEPOSIT,
    BANK_TIERS,
)


class TestBankChatDepositAmountParsing(unittest.TestCase):
    def setUp(self):
        USER_PENDING_BANK_DEPOSIT.clear()

    def test_parse_plain_numbers(self):
        bal = 100000.0
        self.assertEqual(parse_deposit_amount("50000", bal), 50000.0)
        self.assertEqual(parse_deposit_amount("50 000", bal), 50000.0)
        self.assertEqual(parse_deposit_amount("150.50", bal), 150.50)
        self.assertEqual(parse_deposit_amount("150,50", bal), 150.50)
        self.assertEqual(parse_deposit_amount("1000 ₪", bal), 1000.0)
        self.assertEqual(parse_deposit_amount("500 шекелей", bal), 500.0)
        self.assertEqual(parse_deposit_amount("500 руб", bal), 500.0)

    def test_parse_k_and_m_suffixes(self):
        bal = 5000000.0
        self.assertEqual(parse_deposit_amount("25k", bal), 25000.0)
        self.assertEqual(parse_deposit_amount("25к", bal), 25000.0)
        self.assertEqual(parse_deposit_amount("2.5k", bal), 2500.0)
        self.assertEqual(parse_deposit_amount("2,5к", bal), 2500.0)
        self.assertEqual(parse_deposit_amount("1.5m", bal), 1500000.0)
        self.assertEqual(parse_deposit_amount("2м", bal), 2000000.0)

    def test_parse_keywords_and_percentages(self):
        bal = 80000.0
        self.assertEqual(parse_deposit_amount("все", bal), 80000.0)
        self.assertEqual(parse_deposit_amount("всё", bal), 80000.0)
        self.assertEqual(parse_deposit_amount("all", bal), 80000.0)
        self.assertEqual(parse_deposit_amount("макс", bal), 80000.0)
        self.assertEqual(parse_deposit_amount("пол", bal), 40000.0)
        self.assertEqual(parse_deposit_amount("половина", bal), 40000.0)
        self.assertEqual(parse_deposit_amount("half", bal), 40000.0)
        self.assertEqual(parse_deposit_amount("25%", bal), 20000.0)
        self.assertEqual(parse_deposit_amount("50%", bal), 40000.0)
        self.assertEqual(parse_deposit_amount("100%", bal), 80000.0)

    def test_invalid_strings_return_none(self):
        bal = 10000.0
        self.assertIsNone(parse_deposit_amount("привет", bal))
        self.assertIsNone(parse_deposit_amount("как дела", bal))
        self.assertIsNone(parse_deposit_amount("-500", bal))
        self.assertIsNone(parse_deposit_amount("0", bal))
        self.assertIsNone(parse_deposit_amount("", bal))

    def test_parse_amount_and_tier_extraction(self):
        self.assertEqual(parse_amount_and_tier("50000", "sych"), ("50000", "sych"))
        self.assertEqual(parse_amount_and_tier("50000 skuf", "sych"), ("50000", "skuf"))
        self.assertEqual(parse_amount_and_tier("100к скуф", "sych"), ("100к", "skuf"))
        self.assertEqual(parse_amount_and_tier("все в ммм", "sych"), ("все", "mmm_abu"))
        self.assertIsNone(parse_amount_and_tier("обычное сообщение в тред на борде"))
        self.assertIsNone(parse_amount_and_tier("/help"))


class TestBankChatDepositStateAndFilter(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        USER_PENDING_BANK_DEPOSIT.clear()
        self.user_id = 99887766

    def test_pending_state_lifecycle(self):
        # Initial: no state
        self.assertIsNone(get_user_pending_deposit(self.user_id))

        # Set state
        set_user_pending_deposit(self.user_id, "skuf", chat_id=12345, board_id="b")
        pending = get_user_pending_deposit(self.user_id)
        self.assertIsNotNone(pending)
        self.assertEqual(pending["tier_id"], "skuf")

        # Clear state
        clear_user_pending_deposit(self.user_id)
        self.assertIsNone(get_user_pending_deposit(self.user_id))

    def test_pending_state_ttl_expiration(self):
        set_user_pending_deposit(self.user_id, "mmm_abu")
        # Artificially expire TTL
        USER_PENDING_BANK_DEPOSIT[self.user_id]["expires_at"] = time.time() - 10.0
        self.assertIsNone(get_user_pending_deposit(self.user_id))

    async def test_filter_rejects_when_no_pending_state(self):
        msg = MagicMock()
        msg.text = "50000"
        msg.from_user.id = self.user_id
        filt = PendingBankDepositFilter()
        res = await filt(msg)
        self.assertFalse(res)

    async def test_filter_rejects_commands_and_chatter(self):
        set_user_pending_deposit(self.user_id, "sych")
        filt = PendingBankDepositFilter()

        # Command
        msg_cmd = MagicMock()
        msg_cmd.text = "/help"
        msg_cmd.from_user.id = self.user_id
        self.assertFalse(await filt(msg_cmd))

        # Regular chatter
        msg_chat = MagicMock()
        msg_chat.text = "Привет аноны, как дела?"
        msg_chat.from_user.id = self.user_id
        self.assertFalse(await filt(msg_chat))

    async def test_filter_accepts_valid_amount_when_pending(self):
        set_user_pending_deposit(self.user_id, "skuf")
        filt = PendingBankDepositFilter()

        msg = MagicMock()
        msg.text = "75000"
        msg.from_user.id = self.user_id

        res = await filt(msg)
        self.assertIsInstance(res, dict)
        self.assertEqual(res["amount_str"], "75000")
        self.assertEqual(res["detected_tier"], "skuf")


class TestBankChatDepositExecution(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        USER_PENDING_BANK_DEPOSIT.clear()
        self.user_id = 99887766
        set_user_pending_deposit(self.user_id, "sych", board_id="b")

    @patch("bank_engine.create_bank_deposit", new_callable=AsyncMock)
    @patch("bank_engine.get_user_global_balance", new_callable=AsyncMock)
    @patch("bank_engine.get_pool", new_callable=AsyncMock)
    async def test_handle_chat_deposit_success(self, mock_pool, mock_get_bal, mock_create):
        mock_get_bal.return_value = 100000.0
        mock_create.return_value = (
            True,
            {"id": 1, "tier_id": "sych", "principal": 50000.0},
            None
        )

        msg = MagicMock()
        msg.text = "50000"
        msg.from_user.id = self.user_id
        msg.answer = AsyncMock()

        pending = get_user_pending_deposit(self.user_id)
        await handle_chat_deposit_amount(
            message=msg,
            pending_deposit=pending,
            amount_str="50000",
            detected_tier="sych",
            board_id="b"
        )

        # Deposit created with correct amount
        mock_create.assert_called_once()
        args = mock_create.call_args[0]
        self.assertEqual(args[1], self.user_id)
        self.assertEqual(args[3], "sych")
        self.assertEqual(args[4], 50000.0)

        # Pending state cleared
        self.assertIsNone(get_user_pending_deposit(self.user_id))

        # Confirmation message answered
        msg.answer.assert_called_once()
        self.assertIn("ВКЛАД УСПЕШНО ОФОРМЛЕН", msg.answer.call_args[0][0])
        self.assertIn("50,000.00", msg.answer.call_args[0][0])

    @patch("bank_engine.get_user_global_balance", new_callable=AsyncMock)
    @patch("bank_engine.get_pool", new_callable=AsyncMock)
    async def test_handle_chat_deposit_insufficient_funds(self, mock_pool, mock_get_bal):
        mock_get_bal.return_value = 1000.0

        msg = MagicMock()
        msg.text = "50000"
        msg.from_user.id = self.user_id
        msg.answer = AsyncMock()

        pending = get_user_pending_deposit(self.user_id)
        await handle_chat_deposit_amount(
            message=msg,
            pending_deposit=pending,
            amount_str="50000",
            detected_tier="sych",
            board_id="b"
        )

        msg.answer.assert_called_once()
        self.assertIn("Недостаточно средств", msg.answer.call_args[0][0])
        # Pending state preserved so user can re-try
        self.assertIsNotNone(get_user_pending_deposit(self.user_id))
