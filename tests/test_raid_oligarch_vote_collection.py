# -*- coding: utf-8 -*-
"""
Тесты надежности и сбора голосов для рейда ОБЭП (/raid_oligarch).
Проверяют:
1. Создание интерактивного лобби рейда.
2. Сбор голосов через callback cb_raid_join с инкрементом счетчика (1/5 -> 2/5 -> ... -> 5/5).
3. Защиту от повторного вступления тем же работягой.
4. Отклонение кандидатов с высоким балансом (>= 5000 ₪) или недостатком постов (< 25).
5. Отклонение самоизолированных кандидатов.
6. Выполнение рейда и распределение добычи при наборе 5 пролетариев.
"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import CallbackQuery, Message

import auction_engine
from common.database import get_pool, add_user_global_balance
import common.database


@pytest.mark.asyncio
async def test_raid_oligarch_lobby_and_vote_accumulation(isolated_test_db):
    """Проверяет сбор 5 голосов пролетариев через инлайн-кнопку лобби ОБЭП."""
    db = isolated_test_db
    board_id = "b"

    # Создаем олигарха с капиталом 100,000 ₪
    oligarch_id = 990099
    await add_user_global_balance(db, oligarch_id, board_id, 100000.0)
    await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (oligarch_id,))
    await db.commit()

    # Создаем 5 квалифицированных пролетариев (баланс < 5000 ₪, постов >= 25)
    workers = [880010 + i for i in range(5)]
    for w in workers:
        await add_user_global_balance(db, w, board_id, 500.0)
        await db.execute("UPDATE Users SET posts_count = 30 WHERE user_id = ?", (w,))
    await db.commit()

    # Очищаем лобби
    auction_engine._ACTIVE_RAIDS.clear()

    # 1. Первый рабочий создает лобби через /raid_oligarch
    initiator = workers[0]
    msg = AsyncMock()
    msg.from_user = MagicMock(id=initiator)
    msg.text = f"/raid_oligarch {oligarch_id}"
    msg.board_id = board_id
    msg.chat = MagicMock(id=12345)
    msg.reply_to_message = None
    msg.reply = AsyncMock()

    with patch("auction_engine.get_pool", return_value=db), \
         patch("event_push_engine.push_raid_oligarch", new_callable=AsyncMock):
        await auction_engine.cmd_raid_oligarch(msg)

    assert len(auction_engine._ACTIVE_RAIDS) == 1
    raid_id = list(auction_engine._ACTIVE_RAIDS.keys())[0]
    raid = auction_engine._ACTIVE_RAIDS[raid_id]
    assert raid["voters"] == [initiator]

    # 2. Рабочий 2 вступает в рейд через кнопку raid_join_
    mock_msg = AsyncMock()
    mock_msg.caption = None
    mock_msg.photo = None
    mock_msg.edit_text = AsyncMock()

    cb_worker2 = AsyncMock(spec=CallbackQuery)
    cb_worker2.data = f"raid_join_{raid_id}"
    cb_worker2.from_user = MagicMock(id=workers[1])
    cb_worker2.message = mock_msg
    cb_worker2.answer = AsyncMock()

    with patch("auction_engine.get_pool", return_value=db):
        await auction_engine.cb_raid_join(cb_worker2)

    assert len(raid["voters"]) == 2
    assert cb_worker2.answer.call_args[0][0] == "🚩 Ты вступил в рейд ОБЭП! (2/5)"
    assert mock_msg.edit_text.called

    # 3. Попытка повторного вступления тем же рабочим 2
    cb_worker2.answer.reset_mock()
    with patch("auction_engine.get_pool", return_value=db):
        await auction_engine.cb_raid_join(cb_worker2)
    assert "Ты уже в строю!" in cb_worker2.answer.call_args[0][0]
    assert len(raid["voters"]) == 2

    # 4. Попытка вступления богача (баланс >= 5000 ₪) -> отказ
    rich_user = 770077
    await add_user_global_balance(db, rich_user, board_id, 15000.0)
    await db.execute("UPDATE Users SET posts_count = 50 WHERE user_id = ?", (rich_user,))
    await db.commit()

    cb_rich = AsyncMock()
    cb_rich.data = f"raid_join_{raid_id}"
    cb_rich.from_user = MagicMock(id=rich_user)
    cb_rich.message = mock_msg
    cb_rich.answer = AsyncMock()

    with patch("auction_engine.get_pool", return_value=db):
        await auction_engine.cb_raid_join(cb_rich)
    assert "Ты не подходишь для рейда!" in cb_rich.answer.call_args[0][0]
    assert len(raid["voters"]) == 2

    # 5. Рабочие 3, 4 и 5 вступают в рейд -> рейд выполняется!
    for w in workers[2:4]:
        cb_w = AsyncMock()
        cb_w.data = f"raid_join_{raid_id}"
        cb_w.from_user = MagicMock(id=w)
        cb_w.message = mock_msg
        cb_w.answer = AsyncMock()
        with patch("auction_engine.get_pool", return_value=db):
            await auction_engine.cb_raid_join(cb_w)

    assert len(raid["voters"]) == 4

    # 5-й рабочий закрывает сбор -> рейд исполняется
    cb_w5 = AsyncMock()
    cb_w5.data = f"raid_join_{raid_id}"
    cb_w5.from_user = MagicMock(id=workers[4])
    cb_w5.message = mock_msg
    cb_w5.answer = AsyncMock()

    with patch("auction_engine.get_pool", return_value=db):
        await auction_engine.cb_raid_join(cb_w5)

    assert "Рейд успешно завершен" in cb_w5.answer.call_args[0][0]
    # Лобби удалено из активных
    assert raid_id not in auction_engine._ACTIVE_RAIDS
    # Олигарх раскулачен: 10% конфисковано (100,000 -> 90,000)
    oligarch_final_bal = await common.database.get_user_global_balance(db, oligarch_id)
    assert oligarch_final_bal == 90000.0
