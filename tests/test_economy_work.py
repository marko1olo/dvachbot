import json
import time
from unittest import mock

import pytest

from tests.economy_live import BOARD, live_economy
from economy_extension import cb_work_action

USER_ID = 3001


@pytest.fixture
def mock_callback():
    cb = mock.AsyncMock()
    cb.from_user.id = USER_ID
    cb.answer = mock.AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_cb_work_bottles_success(mock_callback):
    """Сдача бутылок приносит от 10 до 50 шекелей."""
    async with live_economy() as live:
        await live.seed_user(USER_ID, balance=0.0, items={"last_bottles": 0})
        mock_callback.data = "work_bottles"

        with mock.patch("random.randint", return_value=42):
            await cb_work_action(mock_callback, BOARD)

        # Деньги начислены
        assert await live.balance_of(USER_ID) == 42.0
        # Время последней сдачи обновлено
        items = await live.items_of(USER_ID)
        assert items["last_bottles"] > 0
        assert items["last_bottles"] <= int(time.time())
        # Ответ отправлен
        mock_callback.answer.assert_called_once()
        assert "успешно сдал бутылки" in mock_callback.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_work_bottles_cooldown(mock_callback):
    """Сдавать бутылки можно только раз в 24 часа."""
    async with live_economy() as live:
        now = int(time.time())
        last_bottles = now - 3600  # Сдавал час назад
        await live.seed_user(USER_ID, balance=100.0, items={"last_bottles": last_bottles})
        mock_callback.data = "work_bottles"

        await cb_work_action(mock_callback, BOARD)

        # Баланс не изменился
        assert await live.balance_of(USER_ID) == 100.0
        # Время последней сдачи не изменилось
        items = await live.items_of(USER_ID)
        assert items["last_bottles"] == last_bottles
        # Ответ отправлен (с ошибкой)
        mock_callback.answer.assert_called_once()
        assert "Пункты приема закрыты" in mock_callback.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_work_sell_mother_success(mock_callback):
    """Продажа матери приносит 10000 шекелей и вечное клеймо."""
    async with live_economy() as live:
        await live.seed_user(USER_ID, balance=0.0, items={})
        mock_callback.data = "work_sell_mother"

        await cb_work_action(mock_callback, BOARD)

        # Деньги начислены
        assert await live.balance_of(USER_ID) == 10000.0
        # Клеймо установлено
        items = await live.items_of(USER_ID)
        assert items["mother_sold"] is True
        assert (await live.column_of(USER_ID, "custom_prefix")) == "[Продал мать]"
        # Ответ отправлен
        mock_callback.answer.assert_called_once()
        assert "Ты продал мать" in mock_callback.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_work_sell_mother_already_sold(mock_callback):
    """Мать можно продать только один раз."""
    async with live_economy() as live:
        await live.seed_user(USER_ID, balance=0.0, items={"mother_sold": True})
        mock_callback.data = "work_sell_mother"

        await cb_work_action(mock_callback, BOARD)

        # Баланс не изменился
        assert await live.balance_of(USER_ID) == 0.0
        # Ответ отправлен (с ошибкой)
        mock_callback.answer.assert_called_once()
        assert "Ты уже продал мать" in mock_callback.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_work_action_unknown_board(mock_callback):
    """Без board_id ничего не происходит."""
    mock_callback.data = "work_bottles"
    await cb_work_action(mock_callback, None)
    mock_callback.answer.assert_not_called()
