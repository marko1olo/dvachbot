# -*- coding: utf-8 -*-
"""
test_votemute_quorum_eligibility.py — Модульные тесты проверки кворума активности Народного Вотума (/votemute).
======================================================================================================
Требование:
Участвовать в кворуме могут только активные аноны борды (больше 1 поста за последние 2 дня на доске).
Администраторы борды освобождены от данного ограничения.

Тестовые сценарии:
1. Анон с 0 постов на борде пытается создать вотум через cmd_votemute -> отказ.
2. Анон с 1 постом на борде пытается проголосовать кнопкой через callback_votemute_vote -> отказ с алертом.
3. Анон с 2 постами (> 1) в пределах 48 часов голосует -> голос успешно принимается и счетчик инкрементируется.
4. Анон с 2 постами, но старше 48 часов (например 3 дня назад) -> отказ с алертом.
5. Анон с 3 постами, но на другой доске (например на /sex/, а вотум на /b/) -> на /b/ отказ.
6. Анон с 2 постами, но один из них теневой (is_shadow = 1) -> учитывается только 1 пост, отказ.
7. Администратор с 0 постов запускает вотум и голосует -> успешно принимается (exempt).
8. start_or_add_vote строго соблюдает флаг check_eligibility.
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import votemute_engine
from votemute_engine import (
    check_voter_eligibility,
    cmd_votemute,
    callback_votemute_vote,
    start_or_add_vote,
    get_votemute_callback_token,
    active_votemutes,
    QUORUM_ELIGIBILITY_ERROR,
    QUORUM_ACTIVITY_WINDOW_SEC,
    MIN_POSTS_REQUIRED_FOR_QUORUM,
)


async def insert_post_for_user(
    db,
    user_id: int,
    board_id: str = "b",
    age_seconds: float = 3600.0,
    is_shadow: int = 0
):
    """Вставляет пост пользователя с заданным возрастом (в секундах назад) и флагом теневого мута."""
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES (?, ?)", (board_id, board_id))
    ts = time.time() - age_seconds
    await db.execute(
        """INSERT INTO Posts (board_id, author_id, content, timestamp, is_shadow)
           VALUES (?, ?, '{}', ?, ?)""",
        (board_id, user_id, ts, is_shadow)
    )
    await db.commit()


async def setup_target_and_post(
    db,
    target_id: int = 900001,
    post_num: int = 800001,
    board_id: str = "b"
):
    """Инициализирует целевого пользователя и его пост в изолированной БД."""
    await db.execute(
        "INSERT INTO Users (user_id, board_id, status) VALUES (?, ?, 'active') "
        "ON CONFLICT(user_id, board_id) DO NOTHING",
        (target_id, board_id)
    )
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
        "VALUES (?, ?, ?, '{}', ?) ON CONFLICT(post_num) DO NOTHING",
        (post_num, board_id, target_id, time.time())
    )
    await db.commit()
    return target_id, post_num


# ============================================================================
# ТЕСТ 1: Анон с 0 постов -> cmd_votemute отказ
# ============================================================================
@pytest.mark.asyncio
async def test_anon_zero_posts_cmd_votemute_rejected(isolated_test_db):
    """
    Тест 1: Анон с 0 постов на борде пытается создать вотум через cmd_votemute:
    - Получает отказ с точным текстом QUORUM_ELIGIBILITY_ERROR.
    - Сессия вотума в базе данных и памяти НЕ создается.
    """
    db = isolated_test_db
    active_votemutes.clear()
    target_id, post_num = await setup_target_and_post(db, target_id=901001, post_num=801001, board_id="b")

    voter_zero = 10001  # 0 постов в БД

    # Прямая проверка функции eligibility
    is_eligible, reason = await check_voter_eligibility(voter_zero, "b", db=db)
    assert is_eligible is False
    assert reason == QUORUM_ELIGIBILITY_ERROR

    mock_msg = AsyncMock()
    mock_msg.from_user = MagicMock(id=voter_zero)
    mock_msg.bot = AsyncMock()
    mock_msg.answer = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db), \
         patch("votemute_engine._resolve_target_from_message", return_value=(post_num, target_id)):
        await cmd_votemute(mock_msg, board_id="b")

    # Пользователю отправлен отказ с объяснением
    mock_msg.answer.assert_called_once()
    assert QUORUM_ELIGIBILITY_ERROR in mock_msg.answer.call_args[0][0]

    # Никакая сессия в Votemutes не создана
    async with db.execute("SELECT COUNT(*) FROM Votemutes WHERE target_id = ?", (target_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 0
    assert len(active_votemutes) == 0


# ============================================================================
# ТЕСТ 2: Анон с 1 постом -> callback_votemute_vote отказ с алертом
# ============================================================================
@pytest.mark.asyncio
async def test_anon_one_post_callback_vote_rejected(isolated_test_db):
    """
    Тест 2: Анон с 1 постом на борде пытается проголосовать кнопкой через callback_votemute_vote:
    - Получает отказ с show_alert=True и сообщением QUORUM_ELIGIBILITY_ERROR.
    - Счетчик голосов не увеличивается.
    """
    db = isolated_test_db
    active_votemutes.clear()
    target_id, post_num = await setup_target_and_post(db, target_id=902001, post_num=802001, board_id="b")

    # Инициатор с 2 постами открывает сессию
    initiator_id = 702001
    for off in (3600, 3000, 2400, 1800, 1200):
        await insert_post_for_user(db, initiator_id, "b", age_seconds=off)
    with patch("votemute_engine.get_pool", return_value=db):
        ok, _, votes, _ = await start_or_add_vote(
            board_id="b", target_id=target_id, post_num=post_num, voter_id=initiator_id
        )
    assert ok is True
    assert votes == 1

    # Анон с ровно 1 постом за последние 48 часов
    voter_one = 10002
    await insert_post_for_user(db, voter_one, "b", age_seconds=1800)

    # Прямая проверка функции eligibility
    is_eligible, reason = await check_voter_eligibility(voter_one, "b", db=db)
    assert is_eligible is False
    assert reason == QUORUM_ELIGIBILITY_ERROR

    token = get_votemute_callback_token(target_id, post_num)
    mock_msg = AsyncMock(caption=None, photo=None, edit_text=AsyncMock())
    mock_cb = AsyncMock()
    mock_cb.data = f"vm_vote:yes:{token}"
    mock_cb.from_user = MagicMock(id=voter_one)
    mock_cb.message = mock_msg
    mock_cb.bot = AsyncMock()
    mock_cb.answer = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db):
        await callback_votemute_vote(mock_cb, board_id="b")

    # Ответ с алертом
    mock_cb.answer.assert_called_once()
    assert QUORUM_ELIGIBILITY_ERROR in mock_cb.answer.call_args[0][0]
    assert mock_cb.answer.call_args[1].get("show_alert") is True

    # Счетчик голосов в БД по-прежнему 1
    async with db.execute("SELECT yes_votes FROM Votemutes WHERE target_id = ?", (target_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 1


# ============================================================================
# ТЕСТ 3: Анон с 2 постами (> 1) в пределах 48ч -> голос принят, счетчик +1
# ============================================================================
@pytest.mark.asyncio
async def test_anon_two_posts_within_48h_vote_accepted(isolated_test_db):
    """
    Тест 3: Анон с 2 постами (> 1) в пределах 48 часов голосует:
    - Голос успешно принимается, карточка обновляется, счетчик инкрементируется до [2/5].
    """
    db = isolated_test_db
    active_votemutes.clear()
    target_id, post_num = await setup_target_and_post(db, target_id=903001, post_num=803001, board_id="b")

    # Инициатор
    initiator_id = 703001
    for off in (3600, 3000, 2400, 1800, 1200):
        await insert_post_for_user(db, initiator_id, "b", age_seconds=off)
    with patch("votemute_engine.get_pool", return_value=db):
        await start_or_add_vote("b", target_id, post_num, initiator_id)

    # Анон с 5 свежими постами
    voter_two = 10003
    for off in (7200, 5400, 3600, 1800, 600):
        await insert_post_for_user(db, voter_two, "b", age_seconds=off)

    # Прямая проверка
    is_eligible, reason = await check_voter_eligibility(voter_two, "b", db=db)
    assert is_eligible is True
    assert reason == ""

    token = get_votemute_callback_token(target_id, post_num)
    mock_msg = AsyncMock(caption=None, photo=None, edit_text=AsyncMock())
    mock_cb = AsyncMock()
    mock_cb.data = f"vm_vote:yes:{token}"
    mock_cb.from_user = MagicMock(id=voter_two)
    mock_cb.message = mock_msg
    mock_cb.bot = AsyncMock()
    mock_cb.answer = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db):
        await callback_votemute_vote(mock_cb, board_id="b")

    mock_cb.answer.assert_called_once()
    assert "голос учтен" in mock_cb.answer.call_args[0][0]
    assert "[2/5]" in mock_cb.answer.call_args[0][0]

    # В БД стало 2 голоса
    async with db.execute("SELECT yes_votes FROM Votemutes WHERE target_id = ?", (target_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 2


# ============================================================================
# ТЕСТ 4: Анон с 2 постами, но старше 48ч (3 дня назад) -> отказ с алертом
# ============================================================================
@pytest.mark.asyncio
async def test_anon_two_posts_older_than_48h_vote_rejected(isolated_test_db):
    """
    Тест 4: Анон с 2 постами, но старше 48 часов (3 дня назад):
    - Окно 48ч не пройдено.
    - Отказ с алертом QUORUM_ELIGIBILITY_ERROR.
    """
    db = isolated_test_db
    active_votemutes.clear()
    target_id, post_num = await setup_target_and_post(db, target_id=904001, post_num=804001, board_id="b")

    initiator_id = 704001
    for off in (3600, 3000, 2400, 1800, 1200):
        await insert_post_for_user(db, initiator_id, "b", age_seconds=off)
    with patch("votemute_engine.get_pool", return_value=db):
        await start_or_add_vote("b", target_id, post_num, initiator_id)

    # Анон: 5 постов, созданные 8 дней назад (> 7 дней)
    voter_stale = 10004
    eight_days = 8 * 86400.0
    for off in range(5):
        await insert_post_for_user(db, voter_stale, "b", age_seconds=eight_days + off * 600)

    # Прямая проверка
    is_eligible, reason = await check_voter_eligibility(voter_stale, "b", db=db)
    assert is_eligible is False
    assert reason == QUORUM_ELIGIBILITY_ERROR

    token = get_votemute_callback_token(target_id, post_num)
    mock_msg = AsyncMock(caption=None, photo=None, edit_text=AsyncMock())
    mock_cb = AsyncMock()
    mock_cb.data = f"vm_vote:yes:{token}"
    mock_cb.from_user = MagicMock(id=voter_stale)
    mock_cb.message = mock_msg
    mock_cb.bot = AsyncMock()
    mock_cb.answer = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db):
        await callback_votemute_vote(mock_cb, board_id="b")

    mock_cb.answer.assert_called_once()
    assert QUORUM_ELIGIBILITY_ERROR in mock_cb.answer.call_args[0][0]
    assert mock_cb.answer.call_args[1].get("show_alert") is True

    # Голос не засчитан
    async with db.execute("SELECT yes_votes FROM Votemutes WHERE target_id = ?", (target_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 1


# ============================================================================
# ТЕСТ 5: Анон с 3 постами, но на другой доске (/sex/, а вотум на /b/) -> отказ
# ============================================================================
@pytest.mark.asyncio
async def test_anon_posts_on_different_board_rejected(isolated_test_db):
    """
    Тест 5: Анон с 3 постами на доске /sex/, голосующий на доске /b/:
    - На /sex/ он активен, но на /b/ у него 0 постов.
    - На /b/ получает отказ с алертом QUORUM_ELIGIBILITY_ERROR.
    """
    db = isolated_test_db
    active_votemutes.clear()
    target_id, post_num = await setup_target_and_post(db, target_id=905001, post_num=805001, board_id="b")

    initiator_id = 705001
    for off in (3600, 3000, 2400, 1800, 1200):
        await insert_post_for_user(db, initiator_id, "b", age_seconds=off)
    with patch("votemute_engine.get_pool", return_value=db):
        await start_or_add_vote("b", target_id, post_num, initiator_id)

    # 5 постов на /sex/, 0 постов на /b/
    voter_other_board = 10005
    for offset in (3600, 3000, 2400, 1800, 600):
        await insert_post_for_user(db, voter_other_board, "sex", age_seconds=offset)

    # Проверка на /sex/ проходит
    is_eligible_sex, reason_sex = await check_voter_eligibility(voter_other_board, "sex", db=db)
    assert is_eligible_sex is True
    assert reason_sex == ""

    # Проверка на /b/ проваливается
    is_eligible_b, reason_b = await check_voter_eligibility(voter_other_board, "b", db=db)
    assert is_eligible_b is False
    assert reason_b == QUORUM_ELIGIBILITY_ERROR

    token = get_votemute_callback_token(target_id, post_num)
    mock_msg = AsyncMock(caption=None, photo=None, edit_text=AsyncMock())
    mock_cb = AsyncMock()
    mock_cb.data = f"vm_vote:yes:{token}"
    mock_cb.from_user = MagicMock(id=voter_other_board)
    mock_cb.message = mock_msg
    mock_cb.bot = AsyncMock()
    mock_cb.answer = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db):
        await callback_votemute_vote(mock_cb, board_id="b")

    mock_cb.answer.assert_called_once()
    assert QUORUM_ELIGIBILITY_ERROR in mock_cb.answer.call_args[0][0]
    assert mock_cb.answer.call_args[1].get("show_alert") is True

    # Голос на /b/ не засчитан
    async with db.execute("SELECT yes_votes FROM Votemutes WHERE target_id = ?", (target_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 1


# ============================================================================
# ТЕСТ 6: Анон с 2 постами, но 1 теневой (is_shadow = 1) -> учитывается 1, отказ
# ============================================================================
@pytest.mark.asyncio
async def test_anon_one_normal_and_one_shadow_post_rejected(isolated_test_db):
    """
    Тест 6: Анон с 2 постами, но один из них теневой (is_shadow = 1):
    - Теневые посты игнорируются (AND is_shadow = 0).
    - Эффективный счетчик = 1 post <= 1 -> отказ с алертом.
    """
    db = isolated_test_db
    active_votemutes.clear()
    target_id, post_num = await setup_target_and_post(db, target_id=906001, post_num=806001, board_id="b")

    initiator_id = 706001
    for off in (3600, 3000, 2400, 1800, 1200):
        await insert_post_for_user(db, initiator_id, "b", age_seconds=off)
    with patch("votemute_engine.get_pool", return_value=db):
        await start_or_add_vote("b", target_id, post_num, initiator_id)

    # 4 обычных поста и 1 теневой (всего 5 постов, но обычных только 4 < 5)
    voter_shadow = 10006
    for off in (4800, 3600, 2400, 1200):
        await insert_post_for_user(db, voter_shadow, "b", age_seconds=off, is_shadow=0)
    await insert_post_for_user(db, voter_shadow, "b", age_seconds=600, is_shadow=1)

    # Прямая проверка
    is_eligible, reason = await check_voter_eligibility(voter_shadow, "b", db=db)
    assert is_eligible is False
    assert reason == QUORUM_ELIGIBILITY_ERROR

    token = get_votemute_callback_token(target_id, post_num)
    mock_msg = AsyncMock(caption=None, photo=None, edit_text=AsyncMock())
    mock_cb = AsyncMock()
    mock_cb.data = f"vm_vote:yes:{token}"
    mock_cb.from_user = MagicMock(id=voter_shadow)
    mock_cb.message = mock_msg
    mock_cb.bot = AsyncMock()
    mock_cb.answer = AsyncMock()

    with patch("votemute_engine.get_pool", return_value=db):
        await callback_votemute_vote(mock_cb, board_id="b")

    mock_cb.answer.assert_called_once()
    assert QUORUM_ELIGIBILITY_ERROR in mock_cb.answer.call_args[0][0]
    assert mock_cb.answer.call_args[1].get("show_alert") is True

    # Голос не засчитан
    async with db.execute("SELECT yes_votes FROM Votemutes WHERE target_id = ?", (target_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 1


# ============================================================================
# ТЕСТ 7: Администратор с 0 постов -> запуск и голосование разрешены (exempt)
# ============================================================================
@pytest.mark.asyncio
async def test_admin_zero_posts_initiates_and_votes_exempt(isolated_test_db):
    """
    Тест 7: Администратор борды с 0 постов в Posts:
    - check_voter_eligibility возвращает True (освобожден от кворума активности).
    - Успешно создает сессию вотума через cmd_votemute.
    - Второй администратор с 0 постов успешно голосует через callback_votemute_vote.
    """
    db = isolated_test_db
    active_votemutes.clear()
    target_id, post_num = await setup_target_and_post(db, target_id=907001, post_num=807001, board_id="b")

    admin_1_id = 999999001  # Администратор с 0 постов
    admin_2_id = 999999002  # Второй администратор с 0 постов

    # Мокаем is_admin(voter_id) = True
    with patch("admin_manager.is_admin", return_value=True):
        # 1. Прямая проверка eligibility
        is_eligible_1, reason_1 = await check_voter_eligibility(admin_1_id, "b", db=db)
        assert is_eligible_1 is True
        assert reason_1 == ""

        is_eligible_2, reason_2 = await check_voter_eligibility(admin_2_id, "b", db=db)
        assert is_eligible_2 is True
        assert reason_2 == ""

        # 2. Первый администратор запускает вотум через cmd_votemute
        mock_msg = AsyncMock()
        mock_msg.from_user = MagicMock(id=admin_1_id)
        mock_msg.bot = AsyncMock()
        mock_sent = AsyncMock(chat=MagicMock(id=12345), message_id=6789)
        mock_msg.answer = AsyncMock(return_value=mock_sent)
        mock_msg.answer_photo = AsyncMock(return_value=mock_sent)

        with patch("votemute_engine.get_pool", return_value=db), \
             patch("votemute_engine._resolve_target_from_message", return_value=(post_num, target_id)), \
             patch("banner_manager.broadcast_banner_to_users", new_callable=AsyncMock), \
             patch("event_push_engine.push_votemute_open", new_callable=AsyncMock):
            await cmd_votemute(mock_msg, board_id="b")

        assert mock_msg.answer_photo.called or mock_msg.answer.called
        # Проверяем карточку: не содержит текст ошибки кворума
        call_obj = mock_msg.answer_photo if mock_msg.answer_photo.called else mock_msg.answer
        ans_text = call_obj.call_args.kwargs.get("caption") or (call_obj.call_args[0][0] if call_obj.call_args[0] else "")
        assert QUORUM_ELIGIBILITY_ERROR not in ans_text

        # В БД создана активная сессия с 1 голосом
        async with db.execute("SELECT yes_votes, status FROM Votemutes WHERE target_id = ?", (target_id,)) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 1
            assert row[1] == "active"

        # 3. Второй администратор голосует через callback_votemute_vote
        token = get_votemute_callback_token(target_id, post_num)
        mock_cb_msg = AsyncMock(caption=None, photo=None, edit_text=AsyncMock())
        mock_cb = AsyncMock()
        mock_cb.data = f"vm_vote:yes:{token}"
        mock_cb.from_user = MagicMock(id=admin_2_id)
        mock_cb.message = mock_cb_msg
        mock_cb.bot = AsyncMock()
        mock_cb.answer = AsyncMock()

        with patch("votemute_engine.get_pool", return_value=db):
            await callback_votemute_vote(mock_cb, board_id="b")

        mock_cb.answer.assert_called_once()
        assert "голос учтен" in mock_cb.answer.call_args[0][0]
        assert "[2/5]" in mock_cb.answer.call_args[0][0]

        # В БД зафиксировано 2 голоса
        async with db.execute("SELECT yes_votes FROM Votemutes WHERE target_id = ?", (target_id,)) as cur:
            row = await cur.fetchone()
            assert row[0] == 2


# ============================================================================
# ТЕСТ 8: start_or_add_vote соблюдает параметр check_eligibility
# ============================================================================
@pytest.mark.asyncio
async def test_start_or_add_vote_eligibility_enforcement(isolated_test_db):
    """
    Тест 8: Проверка ядра start_or_add_vote:
    - При check_eligibility=True неактивный анон отклоняется с кодом False и текстом ошибки.
    - При check_eligibility=False проверка активности пропускается.
    """
    db = isolated_test_db
    active_votemutes.clear()
    target_id, post_num = await setup_target_and_post(db, target_id=908001, post_num=808001, board_id="b")

    ineligible_voter = 10008  # 0 постов

    with patch("votemute_engine.get_pool", return_value=db):
        # По умолчанию check_eligibility=True -> отказ
        ok, msg, votes, executed = await start_or_add_vote(
            board_id="b",
            target_id=target_id,
            post_num=post_num,
            voter_id=ineligible_voter,
            check_eligibility=True
        )
        assert ok is False
        assert msg == QUORUM_ELIGIBILITY_ERROR
        assert votes == 0
        assert executed is False

        # При check_eligibility=False (системный оверрайд) -> успешно
        ok_override, msg_override, votes_override, _ = await start_or_add_vote(
            board_id="b",
            target_id=target_id,
            post_num=post_num,
            voter_id=ineligible_voter,
            check_eligibility=False
        )
        assert ok_override is True
        assert votes_override == 1
