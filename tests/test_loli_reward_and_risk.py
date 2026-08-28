# -*- coding: utf-8 -*-
"""
Unit and integration tests for /loli hourly risk-reward system:
- 1-2 pics: +15 ₪ (risk 0%)
- 3-5 pics: +50 ₪ (risk 15%, fine 30 ₪)
- 6-8 pics: +120 ₪ (risk 30%, fine 100 ₪)
- 9-10 pics: +250 ₪ JACKPOT (risk 50%, fine 200 ₪)
- Cooldown: max 1 reward per hour (3600 seconds)
"""

import time
import pytest
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from main import (
    _process_loli_reward_and_risk,
    USER_LOLI_REWARD_COOLDOWN,
    LOLI_REWARD_COOLDOWN_SEC,
)


class TestLoliRewardAndRisk(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        USER_LOLI_REWARD_COOLDOWN.clear()
        self.user_id = 77712345
        self.board_id = "b"

    @patch("main.get_pool", new_callable=AsyncMock)
    @patch("main.add_user_global_balance", new_callable=AsyncMock)
    @patch("main.record_user_transaction", new_callable=AsyncMock)
    async def test_low_count_zero_risk_reward(self, mock_record, mock_add_bal, mock_pool):
        mock_add_bal.return_value = 115.0
        msg = MagicMock()
        msg.answer = AsyncMock()

        await _process_loli_reward_and_risk(msg, self.board_id, self.user_id, pic_count=1)

        # Reward 15 awarded
        mock_add_bal.assert_called_once_with(mock_pool.return_value, self.user_id, self.board_id, 15.0)
        mock_record.assert_called_once()
        self.assertEqual(mock_record.call_args[0][2], 15.0)
        self.assertEqual(mock_record.call_args[0][3], "admin")

        # Confirmation message
        msg.answer.assert_called_once()
        sent_text = msg.answer.call_args[0][0]
        self.assertIn("15", sent_text)

        # Cooldown recorded
        self.assertIn(self.user_id, USER_LOLI_REWARD_COOLDOWN)

    @patch("main.get_pool", new_callable=AsyncMock)
    @patch("main.add_user_global_balance", new_callable=AsyncMock)
    async def test_hourly_cooldown_enforced(self, mock_add_bal, mock_pool):
        # Set recent cooldown
        USER_LOLI_REWARD_COOLDOWN[self.user_id] = time.time() - 300.0  # 5 min ago

        msg = MagicMock()
        msg.answer = AsyncMock()

        await _process_loli_reward_and_risk(msg, self.board_id, self.user_id, pic_count=5)

        # Must NOT award or answer anything during cooldown
        mock_add_bal.assert_not_called()
        msg.answer.assert_not_called()

    @patch("random.random", return_value=0.8)  # Safe outcome (> 0.50)
    @patch("main.get_pool", new_callable=AsyncMock)
    @patch("main.add_user_global_balance", new_callable=AsyncMock)
    @patch("main.record_user_transaction", new_callable=AsyncMock)
    async def test_jackpot_10_pics_success(self, mock_record, mock_add_bal, mock_pool, mock_rand):
        mock_add_bal.return_value = 1250.0
        msg = MagicMock()
        msg.answer = AsyncMock()

        await _process_loli_reward_and_risk(msg, self.board_id, self.user_id, pic_count=10)

        # 250 shekels jackpot
        mock_add_bal.assert_called_once_with(mock_pool.return_value, self.user_id, self.board_id, 250.0)
        msg.answer.assert_called_once()
        self.assertIn("ДЖЕКПОТ", msg.answer.call_args[0][0])
        self.assertIn("250", msg.answer.call_args[0][0])

    @patch("random.random", return_value=0.2)  # Busted outcome (< 0.50)
    @patch("main.get_pool", new_callable=AsyncMock)
    @patch("main._get_user_active_items", new_callable=AsyncMock, return_value={})
    @patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=500.0)
    @patch("main.deduct_user_global_balance", new_callable=AsyncMock)
    @patch("main.add_to_abu_fund", new_callable=AsyncMock)
    @patch("main.record_user_transaction", new_callable=AsyncMock)
    async def test_jackpot_10_pics_partyvan_busted(self, mock_record, mock_abu_fund, mock_deduct, mock_bal, mock_items, mock_pool, mock_rand):
        mock_deduct.return_value = (True, 50.0)
        msg = MagicMock()
        msg.answer = AsyncMock()

        await _process_loli_reward_and_risk(msg, self.board_id, self.user_id, pic_count=10)

        # Fine 200 shekels deducted
        mock_deduct.assert_called_once_with(mock_pool.return_value, self.user_id, self.board_id, 200.0)
        mock_abu_fund.assert_called_once()
        mock_record.assert_called_once()
        self.assertEqual(mock_record.call_args[0][2], -200.0)
        self.assertEqual(mock_record.call_args[0][3], "police")

        msg.answer.assert_called_once()
        self.assertIn("ПАТИВАН", msg.answer.call_args[0][0])
        self.assertIn("200", msg.answer.call_args[0][0])

    @patch("random.random", return_value=0.05)  # Busted outcome (< 0.15)
    @patch("main.get_pool", new_callable=AsyncMock)
    @patch("main._get_user_active_items", new_callable=AsyncMock, return_value={})
    @patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=300.0)
    @patch("main.deduct_user_global_balance", new_callable=AsyncMock)
    @patch("main.add_to_abu_fund", new_callable=AsyncMock)
    @patch("main.record_user_transaction", new_callable=AsyncMock)
    async def test_medium_5_pics_busted(self, mock_record, mock_abu_fund, mock_deduct, mock_bal, mock_items, mock_pool, mock_rand):
        mock_deduct.return_value = (True, 70.0)
        msg = MagicMock()
        msg.answer = AsyncMock()

        await _process_loli_reward_and_risk(msg, self.board_id, self.user_id, pic_count=5)

        # Fine 30 shekels
        mock_deduct.assert_called_once_with(mock_pool.return_value, self.user_id, self.board_id, 30.0)
        msg.answer.assert_called_once()
        self.assertIn("ТОВАРИЩ МАЙОР", msg.answer.call_args[0][0])
        self.assertIn("30", msg.answer.call_args[0][0])
