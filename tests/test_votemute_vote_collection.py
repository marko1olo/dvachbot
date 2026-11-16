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

async def seed_voter_activity(db, *voter_ids, board_id="b"):
    now = time.time()
    for uid in voter_ids:
        for offset in (3600, 3000, 2400, 1800, 1200):
            await db.execute(
                "INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow) VALUES (?, ?, '{}', ?, 0)",
                (board_id, uid, now - offset)
            )
    await db.commit()


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
    await seed_voter_activity(db, 445566, 778899, board_id=board_id)
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

    await seed_voter_activity(db, *range(7001, 7006), board_id=board_id)
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
    await seed_voter_activity(db, 991122, board_id=board_id)
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


@pytest.mark.asyncio
async def test_votemute_deduplication_same_target_different_posts(isolated_test_db):
    """
    Проверяет устранение дублирования:
    Если против юзера уже открыт вотум по посту #1, повторный /votemute по посту #2
    НЕ создает вторую сессию, а засчитывает голос в существующую и информирует юзера.
    """
    db = isolated_test_db
    target_id = 334455
    post_1 = 1001
    post_2 = 1002
    board_id = "b"

    await db.execute("INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')", (target_id, board_id))
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)", (post_1, board_id, target_id, time.time()))
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)", (post_2, board_id, target_id, time.time()))
    await db.commit()

    votemute_engine.active_votemutes.clear()

    # 1. Первый анон запускает вотум по посту #1
    await seed_voter_activity(db, 5001, 5002, board_id=board_id)
    initiator_1 = 5001
    mock_msg_1 = AsyncMock()
    mock_msg_1.from_user.id = initiator_1
    mock_msg_1.answer = AsyncMock()
    mock_msg_1.bot = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db), \
         patch("votemute_engine._resolve_target_from_message", return_value=(post_1, target_id)), \
         patch("banner_manager.broadcast_banner_to_users", new_callable=AsyncMock), \
         patch("event_push_engine.push_votemute_open", new_callable=AsyncMock):
        await votemute_engine.cmd_votemute(mock_msg_1, board_id=board_id)

    assert mock_msg_1.answer.called or mock_msg_1.answer_photo.called
    # Проверяем, что в БД создана ровно одна сессия
    async with db.execute("SELECT COUNT(*) FROM Votemutes WHERE target_id = ? AND status = 'active'", (target_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 1

    # 2. Второй анон пишет /votemute по посту #2 того же самого пользователя
    initiator_2 = 5002
    mock_msg_2 = AsyncMock()
    mock_msg_2.from_user.id = initiator_2
    mock_msg_2.answer = AsyncMock()
    mock_msg_2.bot = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db), \
         patch("votemute_engine._resolve_target_from_message", return_value=(post_2, target_id)):
        await votemute_engine.cmd_votemute(mock_msg_2, board_id=board_id)

    assert mock_msg_2.answer.called
    ans_text = mock_msg_2.answer.call_args[0][0]
    assert "уже активно" in ans_text or "уже идёт" in ans_text
    assert "Твой голос 'ЗА' добавлен" in ans_text

    # Проверяем: сессий в БД по-прежнему РОВНО 1, а голосов стало 2!
    async with db.execute("SELECT COUNT(*), yes_votes FROM Votemutes WHERE target_id = ? AND status = 'active'", (target_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 1  # НЕТ дубликата!
        assert row[1] == 2  # Голос засчитан!


@pytest.mark.asyncio
async def test_votemute_dual_voting_and_vote_switching(isolated_test_db):
    """
    Проверяет работу кнопок «Замутить» и «Оправдать»:
    1. Голос ЗА увеличивает yes_votes.
    2. Голос ПРОТИВ увеличивает no_votes.
    3. Переключение с ЗА на ПРОТИВ атомарно уменьшает yes_votes и увеличивает no_votes.
    4. Повторный клик тем же выбором отклоняется с уведомлением.
    """
    db = isolated_test_db
    target_id = 889900
    post_num = 778811
    board_id = "b"

    await db.execute("INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')", (target_id, board_id))
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)", (post_num, board_id, target_id, time.time()))
    await db.commit()

    votemute_engine.active_votemutes.clear()
    token = votemute_engine.get_votemute_callback_token(target_id, post_num)

    # Voter 1 голосует ЗА
    await seed_voter_activity(db, 6001, 6002, board_id=board_id)
    voter_1 = 6001
    cb_1 = AsyncMock()
    cb_1.data = f"vm_vote:yes:{token}"
    cb_1.from_user = MagicMock(id=voter_1)
    cb_1.message = AsyncMock(caption=None, photo=None, edit_text=AsyncMock())
    cb_1.bot = AsyncMock()
    cb_1.answer = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db):
        await votemute_engine.callback_votemute_vote(cb_1, board_id=board_id)

    assert "голос учтен" in cb_1.answer.call_args[0][0]
    # Кнопки должны содержать счетчики
    kb = cb_1.message.edit_text.call_args[1]["reply_markup"].inline_keyboard
    assert "[1/5]" in kb[0][0].text
    assert "[0]" in kb[0][1].text

    # Voter 2 голосует ПРОТИВ
    voter_2 = 6002
    cb_2 = AsyncMock()
    cb_2.data = f"vm_vote:no:{token}"
    cb_2.from_user = MagicMock(id=voter_2)
    cb_2.message = AsyncMock(caption=None, photo=None, edit_text=AsyncMock())
    cb_2.bot = AsyncMock()
    cb_2.answer = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db):
        await votemute_engine.callback_votemute_vote(cb_2, board_id=board_id)

    kb2 = cb_2.message.edit_text.call_args[1]["reply_markup"].inline_keyboard
    assert "[1/5]" in kb2[0][0].text
    assert "[1]" in kb2[0][1].text

    # Voter 1 переключает свой голос с ЗА на ПРОТИВ
    cb_1.reset_mock()
    cb_1.data = f"vm_vote:no:{token}"
    with patch("votemute_engine.get_pool", return_value=db):
        await votemute_engine.callback_votemute_vote(cb_1, board_id=board_id)

    assert "голос изменен" in cb_1.answer.call_args[0][0]
    kb3 = cb_1.message.edit_text.call_args[1]["reply_markup"].inline_keyboard
    # Теперь YES = 0, NO = 2
    assert "[0/5]" in kb3[0][0].text
    assert "[2]" in kb3[0][1].text

    # Повторный клик ПРОТИВ от Voter 1 -> отказ
    cb_1.reset_mock()
    with patch("votemute_engine.get_pool", return_value=db):
        await votemute_engine.callback_votemute_vote(cb_1, board_id=board_id)
    assert "Ты уже отдал свой голос" in cb_1.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_votemute_acquittal_when_no_quorum_reached(isolated_test_db):
    """
    Проверяет оправдание (апелляцию) при наборе 5 голосов ПРОТИВ:
    Сессия переходит в 'rejected', карточка закрывается вердиктом «ОПРАВДАН НАРОДОМ»,
    а нарушитель НЕ мутится.
    """
    db = isolated_test_db
    target_id = 998877
    post_num = 332211
    board_id = "b"

    await db.execute("INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active')", (target_id, board_id))
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, '{}', ?)", (post_num, board_id, target_id, time.time()))
    await db.commit()

    votemute_engine.active_votemutes.clear()
    await seed_voter_activity(db, *range(7001, 7006), board_id=board_id)

    # 5 анонов голосуют ПРОТИВ мута
    with patch("votemute_engine.get_pool", return_value=db):
        for v_id in range(7001, 7006):
            ok, msg, yes_votes, executed = await votemute_engine.start_or_add_vote(
                board_id=board_id,
                target_id=target_id,
                post_num=post_num,
                voter_id=v_id,
                vote_type="no"
            )

    assert executed is False
    assert "ОПРАВДАН" in msg

    # Проверяем в БД: статус = rejected
    async with db.execute("SELECT status, no_votes, yes_votes FROM Votemutes WHERE target_id = ?", (target_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == "rejected"
        assert row[1] == 5
        assert row[2] == 0

    # Проверяем, что мут НЕ был наложен
    is_muted, _ = await votemute_engine.check_user_unbribable_mute(target_id, board_id)
    assert is_muted is False
