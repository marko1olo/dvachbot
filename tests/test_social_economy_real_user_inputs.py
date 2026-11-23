# -*- coding: utf-8 -*-
"""Targeted Red-Team Tests for Social Economy & Transaction UX.

Verifies:
1. Real user input parsing: suffixes 'k', 'к', 'm', 'м', 'кк', 'b', 'б', 'all', 'все', 'всё',
   markdown formatting artifacts ('*100k*', '*50*k'), fractions, NaN/Inf and boundary protection.
2. Shorthand routing regex: /pay5k, /pay100k, /pay1.5m, /pay50к, /payall, /payвсе, /pay100kk, /pay1b.
3. Dual PM notifications on ROB_TINFOIL (victim credited, friendly PM, robber miss explanation).
4. Dual PM notifications on successful /rob with shop advice and self-defense buttons.
5. Strict anonymity law: zero PII / raw Telegram user ID leaks anywhere in public messages or PMs.
"""

import math
import re
import time
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from common.anon_identity import generate_anon_name, get_anon_id
from common.database import calculate_transfer_fee
from main import _parse_pay_amount, cmd_pay, cmd_pay_shorthand, cmd_rob


class MockCursor:
    async def fetchone(self):
        return None

    async def fetchall(self):
        return []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class MockExecContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __await__(self):
        async def _coro():
            return self.cursor
        return _coro().__await__()

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class MockDB:
    def execute(self, *args, **kwargs):
        return MockExecContext(MockCursor())

    async def commit(self):
        pass


class TestRealUserPayParsing:
    """Tests parsing logic for real user commands from chat logs (#601041, #601040, #567151, #540054)."""

    @pytest.mark.parametrize("token,expected", [
        ("100k", 100_000),
        ("50k", 50_000),
        ("5k", 5_000),
        ("50к", 50_000),
        ("2.5k", 2_500),
        ("2,5к", 2_500),
        ("100K", 100_000),
        ("50К", 50_000),
    ])
    def test_k_suffix_variations(self, token, expected):
        amt, err = _parse_pay_amount(token, sender_balance=1_000_000)
        assert err is None
        assert amt == expected

    @pytest.mark.parametrize("token,expected", [
        ("1.5m", 1_500_000),
        ("1,5m", 1_500_000),
        ("2m", 2_000_000),
        ("1.5м", 1_500_000),
        ("1,5м", 1_500_000),
        ("2.5кк", 2_500_000),
        ("2,5кк", 2_500_000),
        ("1kk", 1_000_000),
    ])
    def test_m_and_kk_suffix_variations(self, token, expected):
        amt, err = _parse_pay_amount(token, sender_balance=10_000_000)
        assert err is None
        assert amt == expected

    @pytest.mark.parametrize("token,expected", [
        ("0.005b", 5_000_000),
        ("0,005b", 5_000_000),
        ("0.002б", 2_000_000),
        ("0,002б", 2_000_000),
    ])
    def test_b_suffix_supported(self, token, expected):
        amt, err = _parse_pay_amount(token, sender_balance=10_000_000)
        assert err is None
        assert amt == expected

    def test_b_suffix_too_large(self):
        """1b (1,000,000,000) exceeds maximum transaction limit (10,000,000)."""
        amt, err = _parse_pay_amount("1b", sender_balance=2_000_000_000)
        assert amt is None
        assert err == "too_large"

        amt, err = _parse_pay_amount("100кк", sender_balance=200_000_000)
        assert amt is None
        assert err == "too_large"

    @pytest.mark.parametrize("token", ["all", "все", "всё", "вабанк", "ва-банк", "max", "макс"])
    def test_all_keyword_deducts_fee_correctly(self, token):
        balance = 50_000
        amt, err = _parse_pay_amount(token, sender_balance=balance)
        assert err is None
        assert amt is not None
        fee = calculate_transfer_fee(amt)
        assert amt + fee <= balance
        fee_next = calculate_transfer_fee(amt + 1)
        assert (amt + 1) + fee_next > balance

    def test_all_with_zero_or_negative_balance(self):
        amt, err = _parse_pay_amount("all", sender_balance=0)
        assert amt is None
        assert err == "empty_balance"

        amt, err = _parse_pay_amount("все", sender_balance=-100)
        assert amt is None
        assert err == "empty_balance"

    @pytest.mark.parametrize("token,expected", [
        ("*100k*", 100_000),
        ("*50*k", 50_000),
        ("_1.5m_", 1_500_000),
        ("`5k`", 5_000),
        ("~50к~", 50_000),
    ])
    def test_markdown_formatting_artifacts_cleanup(self, token, expected):
        amt, err = _parse_pay_amount(token, sender_balance=5_000_000)
        assert err is None
        assert amt == expected

    @pytest.mark.parametrize("bad_token,expected_err", [
        ("nan", "invalid_format"),
        ("NaN", "invalid_format"),
        ("inf", "too_large"),
        ("-inf", "too_large"),
        ("-100", "negative_or_zero"),
        ("-5k", "negative_or_zero"),
        ("0", "negative_or_zero"),
        ("0.5", "fractional_less_than_one"),
        ("0,5", "fractional_less_than_one"),
        ("0.0001k", "fractional_less_than_one"),
        ("суммаk", "invalid_format"),
        ("", "invalid_format"),
    ])
    def test_protection_nan_inf_negative_fractions(self, bad_token, expected_err):
        amt, err = _parse_pay_amount(bad_token, sender_balance=100_000)
        assert amt is None
        assert err == expected_err


class TestPayShorthandRouting:
    """Verifies shorthand routing regex matches concatenated forms like /pay5k, /pay100k."""

    @pytest.mark.parametrize("text,expected_amt,expected_rest", [
        ("/pay5k", "5k", None),
        ("/pay100k", "100k", None),
        ("/pay1.5m", "1.5m", None),
        ("/pay1,5m", "1,5m", None),
        ("/pay50к", "50к", None),
        ("/payall", "all", None),
        ("/payвсе", "все", None),
        ("/payвсё", "всё", None),
        ("/pay100kk", "100kk", None),
        ("/pay1b", "1b", None),
        ("/pay5k [Локада6]", "5k", "[Локада6]"),
        ("/pay100k @anon_user", "100k", "@anon_user"),
        ("/pay5k@dvachbot", "5k", None),
        ("/pay1.5m@dvachbot [Шолтер5]", "1.5m", "[Шолтер5]"),
    ])
    def test_regex_matching(self, text, expected_amt, expected_rest):
        pattern = r"^/(?:pay|give|tip|перевод|скинуть|донат|задонатить|перевести|поделиться|пей)(\d+(?:[.,]\d+)?(?:k|к|kk|кк|m|м|b|б)?|all|всё|все)(?:@\w+)?(?:\s+(.*))?$"
        m = re.match(pattern, text.strip(), re.IGNORECASE)
        assert m is not None, f"Pattern failed to match: {text}"
        assert m.group(1).lower() == expected_amt.lower()
        assert (m.group(2) if m.group(2) else None) == expected_rest

    @pytest.mark.asyncio
    async def test_cmd_pay_shorthand_execution(self):
        """Verifies cmd_pay_shorthand parses /pay5k and invokes cmd_pay with raw_command_text."""
        mock_msg = MagicMock()
        mock_msg.text = "/pay5k [Локада6]"

        with patch("main.cmd_pay", new=AsyncMock(return_value="OK")) as mock_cmd:
            res = await cmd_pay_shorthand(mock_msg, board_id="b")
            assert res == "OK"
            mock_cmd.assert_called_once()
            call_kwargs = mock_cmd.call_args[1]
            assert call_kwargs["raw_command_text"] == "/pay 5k [Локада6]"


class TestRobTinfoilAndDualNotifications:
    """Verifies dual PM notifications and balance crediting for ROB_TINFOIL and successful /rob."""

    @pytest.mark.asyncio
    async def test_rob_tinfoil_dual_pm_and_balance_transfer(self):
        """When Tin Foil Hat triggers:
        1. Robber drops money which is credited to victim's balance.
        2. Victim receives friendly PM with anonymized robber hash and dropped amount.
        3. Robber receives PM explaining the mishap.
        4. Zero raw Telegram user IDs leaked.
        """
        robber_id = 7547199874
        victim_id = 9063021869

        mock_msg = MagicMock()
        mock_msg.from_user.id = robber_id
        mock_msg.reply_to_message = MagicMock()
        mock_msg.reply_to_message.from_user.id = victim_id
        mock_msg.answer = AsyncMock()
        mock_msg.answer_photo = AsyncMock()
        mock_msg.bot.send_message = AsyncMock()

        current_time = int(time.time())
        robber_items = {"knife_gun": True}
        victim_items = {"tinfoil_hat": current_time + 7200, "tinfoil_until": current_time + 7200}
        mock_db = MockDB()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_tx_ctx(db):
            yield

        async def mock_get_bal(db, uid):
            return 3000.0 if uid == robber_id else 1000.0

        with patch("main.get_pool", new=AsyncMock(return_value=mock_db)), \
             patch("main.db_transaction", mock_tx_ctx), \
             patch("common.bot_helpers.check_user_is_muted", new=AsyncMock(return_value=False)), \
             patch("common.database.is_shadow_muted", new=AsyncMock(return_value=False)), \
             patch("main.get_combat_cooldown_remaining", return_value=0), \
             patch("main.get_author_id_by_reply", new=AsyncMock(return_value=victim_id)), \
             patch("main.check_isolation_combat_guard", new=AsyncMock(return_value=False)), \
             patch("main.is_admin", return_value=False), \
             patch("main._get_user_active_items", new=AsyncMock(side_effect=[robber_items, victim_items])), \
             patch("main.handle_attack_abuse_check", new=AsyncMock(return_value=False)), \
             patch("main.check_target_grief_protection", new=AsyncMock(return_value=False)), \
             patch("main.get_user_posts_count", new=AsyncMock(return_value=50)), \
             patch("main.get_victim_rob_cooldown_remaining", return_value=0), \
             patch("main.get_user_global_balance", new=AsyncMock(side_effect=mock_get_bal)), \
             patch("main.deduct_user_global_balance", new=AsyncMock(return_value=(True, 2400.0))) as mock_deduct, \
             patch("main.add_user_global_balance", new=AsyncMock(return_value=True)) as mock_add, \
             patch("main.add_user_transaction", new=AsyncMock()), \
             patch("main.log_global_event", new=AsyncMock()):

            with patch("random.uniform", return_value=0.2):
                await cmd_rob(mock_msg, board_id="b")

        # 1. Money credited to victim (20% of 3000 = 600)
        mock_deduct.assert_called_once_with(mock_db, robber_id, "b", 600)
        mock_add.assert_called_once_with(mock_db, victim_id, "b", 600)

        # 2. Dual PM calls
        assert mock_msg.bot.send_message.call_count == 2
        pm_calls = mock_msg.bot.send_message.call_args_list

        victim_pm = next(c for c in pm_calls if c[0][0] == victim_id)
        robber_pm = next(c for c in pm_calls if c[0][0] == robber_id)

        victim_text = victim_pm[0][1]
        robber_text = robber_pm[0][1]

        # Friendly victim notification check
        assert "🛡" in victim_text
        assert "Шапочка из фольги защитила тебя" in victim_text
        assert "Неудачливый грабитель обронил" in victim_text
        assert "которые перешли в твой карман" in victim_text
        assert "600 ₪" in victim_text

        # Robber PM check
        assert "ОСЕЧКА ПРИ ОГРАБЛЕНИИ" in robber_text
        assert "Шапочка из фольги" in robber_text
        assert "600 ₪" in robber_text

        # Strict Anonymity & PII check
        robber_hash = get_anon_id(robber_id)
        victim_hash = get_anon_id(victim_id)
        assert robber_hash in victim_text
        assert victim_hash in robber_text

        assert str(robber_id) not in victim_text
        assert str(victim_id) not in robber_text
        assert str(robber_id) not in robber_text
        assert str(victim_id) not in victim_text

    @pytest.mark.asyncio
    async def test_successful_rob_dual_notifications_and_shop_advice(self):
        """When robbery succeeds:
        1. Victim gets guaranteed PM with stolen amount and /shop self-defense advice.
        2. Inline buttons for /shop and defense items are provided.
        3. No raw Telegram IDs leaked.
        """
        robber_id = 888111222
        victim_id = 999333444

        mock_msg = MagicMock()
        mock_msg.from_user.id = robber_id
        mock_msg.reply_to_message = MagicMock()
        mock_msg.reply_to_message.from_user.id = victim_id
        mock_msg.answer = AsyncMock()
        mock_msg.answer_photo = AsyncMock()
        mock_msg.bot.send_message = AsyncMock()

        robber_items = {"knife_gun": True}
        victim_items = {}
        mock_db = MockDB()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_tx_ctx(db):
            yield

        async def mock_get_bal(db, uid):
            return 5000.0

        with patch("main.get_pool", new=AsyncMock(return_value=mock_db)), \
             patch("main.db_transaction", mock_tx_ctx), \
             patch("common.bot_helpers.check_user_is_muted", new=AsyncMock(return_value=False)), \
             patch("common.database.is_shadow_muted", new=AsyncMock(return_value=False)), \
             patch("main.get_combat_cooldown_remaining", return_value=0), \
             patch("main.get_author_id_by_reply", new=AsyncMock(return_value=victim_id)), \
             patch("main.check_isolation_combat_guard", new=AsyncMock(return_value=False)), \
             patch("main.is_admin", return_value=False), \
             patch("main._get_user_active_items", new=AsyncMock(side_effect=[robber_items, victim_items])), \
             patch("main.handle_attack_abuse_check", new=AsyncMock(return_value=False)), \
             patch("main.check_target_grief_protection", new=AsyncMock(return_value=False)), \
             patch("main.get_user_posts_count", new=AsyncMock(return_value=50)), \
             patch("main.get_victim_rob_cooldown_remaining", return_value=0), \
             patch("main.get_user_global_balance", new=AsyncMock(side_effect=mock_get_bal)), \
             patch("main.deduct_user_global_balance", new=AsyncMock(return_value=(True, 4000.0))), \
             patch("main.add_user_global_balance", new=AsyncMock(return_value=True)), \
             patch("main.add_user_transaction", new=AsyncMock()), \
             patch("main.log_global_event", new=AsyncMock()):

            with patch("random.uniform", return_value=0.2):
                await cmd_rob(mock_msg, board_id="b")

        mock_msg.bot.send_message.assert_called_once()
        call_args = mock_msg.bot.send_message.call_args
        target_sent_to = call_args[0][0]
        text_sent = call_args[0][1]
        kb_sent = call_args[1]["reply_markup"]

        assert target_sent_to == victim_id
        assert "ТЕБЯ ОГРАБИЛ АНОН" in text_sent
        assert "украл у тебя" in text_sent
        assert "/shop" in text_sent
        assert "Совет по самообороне" in text_sent

        # Check buttons
        button_texts = [btn.text for row in kb_sent.inline_keyboard for btn in row]
        assert any("Шапочку из фольги" in bt for bt in button_texts)
        assert any("Заточку для мести" in bt for bt in button_texts)
        assert any("/shop" in bt for bt in button_texts)

        # Zero PII
        assert str(robber_id) not in text_sent
        assert str(victim_id) not in text_sent
        assert get_anon_id(robber_id) in text_sent


class TestFormattingAndZeroPII:
    """Verifies thousand separators and zero PII leaks across payment transactions."""

    @pytest.mark.asyncio
    async def test_pay_thousand_separator_formatting(self):
        """Verify successful /pay outputs beautiful thousand separators like 100,000 ₪."""
        from contextlib import asynccontextmanager

        mock_msg = MagicMock()
        mock_msg.from_user.id = 111222333
        mock_msg.reply_to_message = MagicMock()
        mock_msg.text = "/pay 100k"
        mock_msg.caption = None
        mock_msg.reply = AsyncMock()
        mock_msg.bot.send_message = AsyncMock()

        mock_db = MockDB()

        @asynccontextmanager
        async def mock_tx(db_conn=None):
            yield

        with patch("main.get_pool", new=AsyncMock(return_value=mock_db)), \
             patch("main.db_transaction", mock_tx), \
             patch("main.get_user_global_balance", new=AsyncMock(side_effect=[500_000, 500_000, 100_000])), \
             patch("main.get_author_id_by_reply", new=AsyncMock(return_value=444555666)), \
             patch("main.deduct_user_global_balance", new=AsyncMock(return_value=(True, 395_000))), \
             patch("main.add_user_global_balance", new=AsyncMock(return_value=100_000)), \
             patch("main.add_to_abu_fund", new=AsyncMock()), \
             patch("main.record_user_transaction", new=AsyncMock()):

            await cmd_pay(mock_msg, board_id="b")

        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]
        assert "+100,000 ₪" in reply_text
        assert "111222333" not in reply_text
        assert "444555666" not in reply_text

        mock_msg.bot.send_message.assert_called_once()
        pm_text = mock_msg.bot.send_message.call_args[0][1]
        assert "+100,000 ₪" in pm_text
        assert "111222333" not in pm_text
        assert "444555666" not in pm_text
