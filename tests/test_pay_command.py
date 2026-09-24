# -*- coding: utf-8 -*-
"""Unit tests for /pay command and helper parsing functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from common.database import calculate_transfer_fee
from main import _parse_pay_amount


class TestParsePayAmount:
    def test_numeric_integers(self):
        amt, err = _parse_pay_amount("500", 1000)
        assert amt == 500
        assert err is None

    def test_numeric_with_currency_symbols(self):
        amt, err = _parse_pay_amount("500₪", 1000)
        assert amt == 500
        amt, err = _parse_pay_amount("1000 шекелей", 5000)
        assert amt == 1000
        amt, err = _parse_pay_amount("250 руб", 1000)
        assert amt == 250

    def test_k_multiplier(self):
        amt, err = _parse_pay_amount("5k", 10000)
        assert amt == 5000
        amt, err = _parse_pay_amount("2.5к", 10000)
        assert amt == 2500

    def test_m_multiplier(self):
        amt, err = _parse_pay_amount("1m", 2000000)
        assert amt == 1000000
        amt, err = _parse_pay_amount("1.5кк", 2000000)
        assert amt == 1500000

    def test_all_va_bank(self):
        balance = 1000
        amt, err = _parse_pay_amount("all", balance)
        assert amt is not None
        assert err is None
        # Must not exceed balance when fee is added
        fee = calculate_transfer_fee(amt)
        assert amt + fee <= balance
        # Should be maximum possible
        fee_next = calculate_transfer_fee(amt + 1)
        assert (amt + 1) + fee_next > balance

    def test_all_with_zero_balance(self):
        amt, err = _parse_pay_amount("all", 0)
        assert amt is None
        assert err == "empty_balance"

    def test_half(self):
        amt, err = _parse_pay_amount("half", 1000)
        assert amt == 500
        amt, err = _parse_pay_amount("пол", 500)
        assert amt == 250
        amt, err = _parse_pay_amount("50%", 600)
        assert amt == 300

    def test_percentages(self):
        amt, err = _parse_pay_amount("25%", 1000)
        assert amt == 250
        amt, err = _parse_pay_amount("10%", 1000)
        assert amt == 100

    def test_negative_or_zero(self):
        amt, err = _parse_pay_amount("-500", 1000)
        assert amt is None
        assert err == "negative_or_zero"
        amt, err = _parse_pay_amount("0", 1000)
        assert amt is None
        assert err == "negative_or_zero"

    def test_invalid_string(self):
        amt, err = _parse_pay_amount("abracadabra", 1000)
        assert amt is None
        assert err == "invalid_format"


@pytest.mark.asyncio
async def test_cmd_pay_self_transfer():
    """Verify that attempting to pay oneself is blocked."""
    from main import cmd_pay

    mock_msg = MagicMock()
    mock_msg.from_user.id = 123456
    mock_msg.reply_to_message = MagicMock()
    mock_msg.text = "/pay 500"
    mock_msg.caption = None
    mock_msg.reply = AsyncMock()

    with patch("main.get_pool", new=AsyncMock(return_value=MagicMock(commit=AsyncMock()))), \
         patch("main.get_user_global_balance", new=AsyncMock(return_value=5000)), \
         patch("main.get_author_id_by_reply", new=AsyncMock(return_value=123456)):
        await cmd_pay(mock_msg, board_id="b")

    mock_msg.reply.assert_called_once()
    assert "Перекладываешь шекели" in mock_msg.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_pay_bot_transfer():
    """Verify that attempting to pay a bot (target 0) is blocked."""
    from main import cmd_pay

    mock_msg = MagicMock()
    mock_msg.from_user.id = 123456
    mock_msg.reply_to_message = MagicMock()
    mock_msg.text = "/pay 500"
    mock_msg.caption = None
    mock_msg.reply = AsyncMock()

    with patch("main.get_pool", new=AsyncMock(return_value=MagicMock(commit=AsyncMock()))), \
         patch("main.get_user_global_balance", new=AsyncMock(return_value=5000)), \
         patch("main.get_author_id_by_reply", new=AsyncMock(return_value=0)):
        await cmd_pay(mock_msg, board_id="b")

    mock_msg.reply.assert_called_once()
    assert "задонатить боту" in mock_msg.reply.call_args[0][0]


def _make_mock_db(is_banned=False, is_muted=False):
    db = MagicMock()
    cursor = AsyncMock()
    if is_banned or is_muted:
        cursor.fetchone = AsyncMock(return_value=(1,))
    else:
        cursor.fetchone = AsyncMock(return_value=None)

    exec_ctx = AsyncMock()
    exec_ctx.__aenter__.return_value = cursor
    exec_ctx.__aexit__.return_value = None
    db.execute = MagicMock(return_value=exec_ctx)
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_cmd_pay_insufficient_funds():
    """Verify insufficient funds check."""
    from main import cmd_pay

    mock_msg = MagicMock()
    mock_msg.from_user.id = 123456
    mock_msg.reply_to_message = MagicMock()
    mock_msg.text = "/pay 5000"
    mock_msg.caption = None
    mock_msg.reply = AsyncMock()

    mock_db = _make_mock_db(is_banned=False, is_muted=False)

    with patch("main.get_pool", new=AsyncMock(return_value=mock_db)), \
         patch("main.get_user_global_balance", new=AsyncMock(return_value=100)), \
         patch("main.get_author_id_by_reply", new=AsyncMock(return_value=654321)):
        await cmd_pay(mock_msg, board_id="b")

    mock_msg.reply.assert_called_once()
    assert "Не хватает шекелей" in mock_msg.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_pay_target_muted():
    """Verify that transfers to a muted user are strictly blocked."""
    from main import cmd_pay

    mock_msg = MagicMock()
    mock_msg.from_user.id = 123456
    mock_msg.reply_to_message = MagicMock()
    mock_msg.text = "/pay 5000"
    mock_msg.caption = None
    mock_msg.reply = AsyncMock()

    # DB returns muted record for target
    db = MagicMock()
    cursor_ban = AsyncMock()
    cursor_ban.fetchone = AsyncMock(return_value=None)  # not banned
    cursor_mute_sender = AsyncMock()
    cursor_mute_sender.fetchone = AsyncMock(return_value=None)  # sender not muted
    cursor_mute_target = AsyncMock()
    cursor_mute_target.fetchone = AsyncMock(return_value=(1,))  # target is muted!

    exec_ctx_ban = AsyncMock(__aenter__=AsyncMock(return_value=cursor_ban), __aexit__=AsyncMock())
    exec_ctx_mute_sender = AsyncMock(__aenter__=AsyncMock(return_value=cursor_mute_sender), __aexit__=AsyncMock())
    exec_ctx_mute_target = AsyncMock(__aenter__=AsyncMock(return_value=cursor_mute_target), __aexit__=AsyncMock())

    db.execute = MagicMock(side_effect=[exec_ctx_ban, exec_ctx_mute_sender, exec_ctx_mute_target])
    db.commit = AsyncMock()

    with patch("main.get_pool", new=AsyncMock(return_value=db)), \
         patch("main.get_user_global_balance", new=AsyncMock(return_value=10000)), \
         patch("main.get_author_id_by_reply", new=AsyncMock(return_value=654321)):
        await cmd_pay(mock_msg, board_id="b")

    mock_msg.reply.assert_called_once()
    assert "Пользователь находится в муте" in mock_msg.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_pay_sender_muted():
    """Verify that transfers from a muted sender are strictly blocked."""
    from main import cmd_pay

    mock_msg = MagicMock()
    mock_msg.from_user.id = 123456
    mock_msg.reply_to_message = MagicMock()
    mock_msg.text = "/pay 500"
    mock_msg.caption = None
    mock_msg.reply = AsyncMock()

    db = MagicMock()
    cursor_ban = AsyncMock()
    cursor_ban.fetchone = AsyncMock(return_value=None)  # not banned
    cursor_mute_sender = AsyncMock()
    cursor_mute_sender.fetchone = AsyncMock(return_value=(1,))  # sender IS muted

    exec_ctx_ban = AsyncMock(__aenter__=AsyncMock(return_value=cursor_ban), __aexit__=AsyncMock())
    exec_ctx_mute_sender = AsyncMock(__aenter__=AsyncMock(return_value=cursor_mute_sender), __aexit__=AsyncMock())

    db.execute = MagicMock(side_effect=[exec_ctx_ban, exec_ctx_mute_sender])
    db.commit = AsyncMock()

    with patch("main.get_pool", new=AsyncMock(return_value=db)), \
         patch("main.get_user_global_balance", new=AsyncMock(return_value=10000)), \
         patch("main.get_author_id_by_reply", new=AsyncMock(return_value=654321)):
        await cmd_pay(mock_msg, board_id="b")

    mock_msg.reply.assert_called_once()
    assert "Вы находитесь в муте" in mock_msg.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_pay_successful_transfer():
    """Verify successful transaction execution and balance deduction."""
    from contextlib import asynccontextmanager
    from main import cmd_pay

    mock_msg = MagicMock()
    mock_msg.from_user.id = 123456
    mock_msg.reply_to_message = MagicMock()
    mock_msg.text = "/pay 500"
    mock_msg.caption = None
    mock_msg.reply = AsyncMock()
    mock_msg.bot.send_message = AsyncMock()

    mock_db = _make_mock_db(is_banned=False, is_muted=False)

    @asynccontextmanager
    async def mock_tx(db_conn=None):
        yield

    with patch("main.get_pool", new=AsyncMock(return_value=mock_db)), \
         patch("main.db_transaction", mock_tx), \
         patch("main.get_user_global_balance", new=AsyncMock(side_effect=[10000, 10000, 500])), \
         patch("main.get_author_id_by_reply", new=AsyncMock(return_value=654321)), \
         patch("main.deduct_user_global_balance", new=AsyncMock(return_value=(True, 9450))), \
         patch("main.add_user_global_balance", new=AsyncMock(return_value=500)), \
         patch("main.add_to_abu_fund", new=AsyncMock()), \
         patch("main.record_user_transaction", new=AsyncMock()):
        await cmd_pay(mock_msg, board_id="b")

    mock_msg.reply.assert_called_once()
    assert "ПЕРЕВОД УСПЕШНО ПРОВЕДЁН" in mock_msg.reply.call_args[0][0]
    mock_msg.bot.send_message.assert_called_once()
    assert "ТЕБЕ ПРИВАЛИЛИ ШЕКЕЛИ" in mock_msg.bot.send_message.call_args[0][1]

