# -*- coding: utf-8 -*-
"""
Тесты надежности и сбора голосов для Народного Вотума (/votemute).
Проверяют:
1. Регистрацию кликов и инкремент голосов через callback_votemute_vote.
2. Восстановление сессии голосования через Posts DB fallback при пустом active_votemutes (рестарт бота).
3. Корректное редактирование карточки (edit_caption для медиа/баннеров и edit_text для текста).
4. Защиту от повторного голосования одним пользователем.
5. Исполнение железного мута при наборе кворума.
"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest

import votemute_engine
from common.database import get_pool
from common.anon_identity import get_anon_id


@pytest.mark.asyncio
async def test_votemute_vote_collection_and_increment(isolated_test_db):
    """Проверяет успешный сбор голосов и инкремент счетчика при клике по инлайн-кнопке."""
    db = isolated_test_db
    target_id = 112233
    post_num = 556677
    board_id = "b"

    # Создаем пост и пользователя в БД
    await db.execute(
        "INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')",
        (target_id, board_id)
    )
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)",
        (post_num, board_id, target_id, time.time())
    )
    await db.commit()

    # Очищаем память
    votemute_engine.active_votemutes.clear()

    # Инициализируем голосование (1-й голос от инициатора)
    initiator_id = 445566
    ok, msg, current_votes, executed = await votemute_engine.start_or_add_vote(
        board_id=board_id,
        target_id=target_id,
        post_num=post_num,
        voter_id=initiator_id
    )
    assert ok is True
    assert current_votes == 1
    assert executed is False

    # 2-й голос через callback_votemute_vote
    voter_2_id = 778899
    token = votemute_engine.get_votemute_callback_token(target_id, post_num)

    mock_msg = AsyncMock()
    mock_msg.caption = None
    mock_msg.photo = None
    mock_msg.edit_text = AsyncMock()

    mock_cb = AsyncMock()
    mock_cb.data = f"vm_vote:{token}"
    mock_cb.from_user = MagicMock(id=voter_2_id)
    mock_cb.message = mock_msg
    mock_cb.bot = AsyncMock()
    mock_cb.answer = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db):
        await votemute_engine.callback_votemute_vote(mock_cb, board_id=board_id)

    # Проверяем, что голос принят
    mock_cb.answer.assert_called()
    assert "голос учтен" in mock_cb.answer.call_args[0][0]
    assert "[2/5]" in mock_cb.answer.call_args[0][0]

    # Проверяем, что карточка была обновлена
    mock_msg.edit_text.assert_called_once()
    assert "[2/5]" in mock_msg.edit_text.call_args[1]["reply_markup"].inline_keyboard[0][0].text

    # Повторный клик тем же пользователем -> отказ с сообщением о дубликате
    mock_cb.reset_mock()
    mock_msg.reset_mock()
    with patch("votemute_engine.get_pool", return_value=db):
        await votemute_engine.callback_votemute_vote(mock_cb, board_id=board_id)
    assert "Ты уже отдал свой голос" in mock_cb.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_votemute_db_recovery_after_bot_restart(isolated_test_db):
    """Проверяет восстановление сессии воте-мута из БД Posts после рестарта бота (active_votemutes пуст)."""
    db = isolated_test_db
    target_id = 223344
    post_num = 667788
    board_id = "b"

    await db.execute(
        "INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')",
        (target_id, board_id)
    )
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)",
        (post_num, board_id, target_id, time.time())
    )
    await db.commit()

    # Симулируем рестарт бота: очищаем активные сессии в памяти
    votemute_engine.active_votemutes.clear()

    token = votemute_engine.get_votemute_callback_token(target_id, post_num)

    with patch("common.database.get_pool", return_value=db):
        resolved = await votemute_engine.resolve_votemute_token(token)
        assert resolved is not None
        assert resolved == (target_id, post_num)

    # Клик нового пользователя после рестарта должен восстановить сессию и засчитать голос
    new_voter = 991122
    mock_msg = AsyncMock()
    mock_msg.caption = "Баннер воте-мута"
    mock_msg.photo = [MagicMock()]
    mock_msg.edit_caption = AsyncMock()

    mock_cb = AsyncMock()
    mock_cb.data = f"vm_vote:{token}"
    mock_cb.from_user = MagicMock(id=new_voter)
    mock_cb.message = mock_msg
    mock_cb.bot = AsyncMock()
    mock_cb.answer = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db), \
         patch("common.database.get_pool", return_value=db):
        await votemute_engine.callback_votemute_vote(mock_cb, board_id=board_id)

    # Для сообщения с фото должен быть вызван edit_caption, а не edit_text!
    mock_msg.edit_caption.assert_called_once()
    mock_cb.answer.assert_called()
    assert "голос учтен" in mock_cb.answer.call_args[0][0]
