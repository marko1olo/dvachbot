# -*- coding: utf-8 -*-
"""
Тесты для:
1. Повышения порога канала «Лучшее» до 4 реакций и скрытия хэша/ID автора в футере.
2. Режима «Самоизоляция» (инкогнито, заморозка капитала, иммунитет от грабежей, порчи, досье и налогов).
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import shared_state
from common.database import update_user_settings_db, get_pool
from main import is_user_isolated, check_isolation_combat_guard, get_personal_menu_keyboard
from post_helpers import _get_author_name, format_header
import whale_economy_engine


@pytest.mark.asyncio
async def test_best_channel_likes_threshold_and_anon_footer():
    """Проверяет порог 4 лайка и полное скрытие хэша автора в канале «Лучшее»."""
    assert shared_state.LIKES_THRESHOLD == 4

    from news_channel_publisher import publish_to_best_channel

    mock_bot = AsyncMock()
    mock_bot.get_me = AsyncMock(return_value=MagicMock(username="dvach_test_bot"))
    mock_send = AsyncMock(return_value=MagicMock(message_id=99999))
    mock_bot.send_message = mock_send

    post_data = {
        'author_id': 778899,
        'content': {'text': 'Годный двач-контент', 'type': 'text'}
    }

    with patch('news_channel_publisher.get_target_channels', return_value=(-100111, -100222)), \
         patch('news_channel_publisher.add_channel_copy', new_callable=AsyncMock), \
         patch('news_channel_publisher.update_post_content', new_callable=AsyncMock), \
         patch('news_channel_publisher.send_channel_content', new_callable=AsyncMock) as mock_send_content:
        mock_send_content.return_value = 88888

        res = await publish_to_best_channel(mock_bot, 'b', 123456, post_data, likes_count=4)
        assert res is True
        assert post_data.get('forwarded_to_best') is True

        # Проверяем переданный footer_text в send_channel_content
        _, kwargs = mock_send_content.call_args
        footer_text = kwargs.get('footer_text', '')
        assert "ID:" not in footer_text
        assert "Автор" not in footer_text
        assert "Открыть пост в боте" in footer_text


@pytest.mark.asyncio
async def test_isolation_database_persistence(isolated_test_db):
    """Проверяет сохранение и считывание флага is_isolated в БД."""
    db = await get_pool()
    user_id = 999111
    board_id = "b"

    # Создаем пользователя
    await db.execute(
        "INSERT INTO Users (user_id, board_id, status, is_isolated) VALUES (?, ?, 'active', 0)",
        (user_id, board_id)
    )
    await db.commit()

    # Включаем изоляцию через update_user_settings_db
    await update_user_settings_db(user_id, board_id, is_isolated=1)

    async with db.execute("SELECT is_isolated FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        assert row is not None
        assert row[0] == 1

    # Выключаем изоляцию
    await update_user_settings_db(user_id, board_id, is_isolated=0)
    async with db.execute("SELECT is_isolated FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        assert row[0] == 0


@pytest.mark.asyncio
async def test_isolation_combat_guard():
    """Проверяет блокировку боевых команд для изолированного инициатора и цели."""
    board_id = "b"
    b_data = shared_state.board_data[board_id]

    user_attacker = 888101
    user_target = 888102
    user_neutral = 888103

    try:
        # По умолчанию никто не изолирован
        b_data['user_settings'][user_attacker] = {'is_isolated': False}
        b_data['user_settings'][user_target] = {'is_isolated': False}
        b_data['user_settings'][user_neutral] = {'is_isolated': False}

        mock_msg = AsyncMock()

        # 1. Обычная атака -> разрешена (возвращает False)
        blocked = await check_isolation_combat_guard(mock_msg, user_attacker, user_target, board_id)
        assert blocked is False

        # 2. Атакующий в изоляции -> заблокирована (возвращает True)
        b_data['user_settings'][user_attacker]['is_isolated'] = True
        blocked_att = await check_isolation_combat_guard(mock_msg, user_attacker, user_neutral, board_id)
        assert blocked_att is True
        mock_msg.answer.assert_called()
        assert "Вы находитесь в режиме самоизоляции" in mock_msg.answer.call_args[0][0]

        # 3. Цель в изоляции -> заблокирована (возвращает True)
        b_data['user_settings'][user_attacker]['is_isolated'] = False
        b_data['user_settings'][user_target]['is_isolated'] = True
        mock_msg.reset_mock()
        blocked_tgt = await check_isolation_combat_guard(mock_msg, user_attacker, user_target, board_id)
        assert blocked_tgt is True
        mock_msg.answer.assert_called()
        assert "Цель находится в режиме самоизоляции" in mock_msg.answer.call_args[0][0]
    finally:
        b_data['user_settings'].pop(user_attacker, None)
        b_data['user_settings'].pop(user_target, None)
        b_data['user_settings'].pop(user_neutral, None)
        b_data['user_settings'].pop(1001, None)
        b_data['user_settings'].pop(1002, None)


@pytest.mark.asyncio
async def test_author_anonymity_in_isolation():
    """Проверяет, что при режиме самоизоляции имя автора в цитатах — чисто 'Анон', а префиксы подавлены."""
    board_id = "b"
    author_id = 555666
    b_data = shared_state.board_data[board_id]
    b_data['user_settings'][author_id] = {'is_isolated': True}

    post = {'author_id': author_id}
    content = {'text': 'Привет двач'}

    # 1. _get_author_name возвращает чистый 'Анон' без [хэша]
    name_ru = _get_author_name(post, content, board_id, lang='ru')
    assert name_ru == "Анон"
    assert "[" not in name_ru

    name_en = _get_author_name(post, content, board_id, lang='en')
    assert name_en == "Anon"

    # 2. format_header возвращает чистый заголовок без кастомных префиксов
    header = await format_header(board_id, 12345, author_id=author_id)
    assert "Пост №12345" in header


@pytest.mark.asyncio
async def test_wealth_tax_bypasses_isolated_users(isolated_test_db):
    """Проверяет, что налог на богатство не трогает изолированных пользователей (резервация капитала)."""
    db = await get_pool()
    user_id = 444555
    board_id = "b"

    # Создаем богатого пользователя в самоизоляции с 500,000 ₪
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, status, is_isolated) VALUES (?, ?, ?, 'active', 1)",
        (user_id, board_id, 500000.0)
    )
    await db.commit()

    # Запускаем сбор налога
    res = await whale_economy_engine.process_daily_wealth_tax(db)

    # Баланс изолированного пользователя должен остаться нетронутым: ровно 500,000 ₪
    async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        assert row[0] == 500000.0


@pytest.mark.asyncio
async def test_proletarian_raid_blocks_isolated_target(isolated_test_db):
    """Проверяет, что рейд ОБЭП (/raid_oligarch) не может раскулачить изолированного пользователя."""
    db = await get_pool()
    target_id = 333222
    board_id = "b"

    # Цель-олигарх в изоляции
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, status, posts_count, is_isolated) VALUES (?, ?, ?, 'active', 100, 1)",
        (target_id, board_id, 1000000.0)
    )

    # 5 квалифицированных рабочих (баланс < 5000, постов >= 25, is_isolated = 0)
    voters = [20001, 20002, 20003, 20004, 20005]
    for v in voters:
        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, status, posts_count, is_isolated) VALUES (?, ?, 100.0, 'active', 50, 0)",
            (v, board_id)
        )
    await db.commit()

    res = await whale_economy_engine.execute_oligarch_raid(db, voters, target_id=target_id, board_id=board_id)
    assert res["ok"] is False
    assert "режиме самоизоляции" in res["error"]


@pytest.mark.asyncio
async def test_personal_settings_menu_isolation_toggle():
    """Проверяет отображение кнопки и текста самоизоляции в меню личных настроек."""
    board_id = "b"
    user_id = 777333
    b_data = shared_state.board_data[board_id]
    try:
        b_data['user_settings'][user_id] = {'nsfw': False, 'hide': set(), 'disable_ai_roasts': False, 'hide_ai_slop': False, 'is_isolated': False}

        # 1. Изоляция выключена
        text_off, kb_off = get_personal_menu_keyboard(board_id, user_id, stream='ru')
        assert "Режим самоизоляции:" in text_off
        assert "❌ ВЫКЛ" in text_off

        btn_iso_off = next(b for row in kb_off.inline_keyboard for b in row if b.callback_data == "pers_isolation_toggle")
        assert "❌ ВЫКЛ" in btn_iso_off.text

        # 2. Изоляция включена
        b_data['user_settings'][user_id]['is_isolated'] = True
        text_on, kb_on = get_personal_menu_keyboard(board_id, user_id, stream='ru')
        assert "✅ ВКЛ" in text_on

        btn_iso_on = next(b for row in kb_on.inline_keyboard for b in row if b.callback_data == "pers_isolation_toggle")
        assert "✅ ВКЛ" in btn_iso_on.text
    finally:
        b_data['user_settings'].pop(user_id, None)


@pytest.mark.asyncio
async def test_cmd_isolation_handler(isolated_test_db):
    """Проверяет команду /isolation on и /isolation off."""
    from user_manager import cmd_isolation

    board_id = "b"
    user_id = 888111
    b_data = shared_state.board_data[board_id]
    try:
        b_data['user_settings'][user_id] = {'is_isolated': False}

        mock_msg = AsyncMock()
        mock_msg.from_user = MagicMock(id=user_id)
        mock_msg.text = "/isolation on"
        mock_msg.caption = None

        await cmd_isolation(mock_msg, board_id=board_id)
        assert b_data['user_settings'][user_id]['is_isolated'] is True
        assert "Режим самоизоляции включен" in mock_msg.answer.call_args[0][0]

        mock_msg.reset_mock()
        # Сбрасываем кулдаун для тестирования выключения в рамках теста
        b_data['user_settings'][user_id]['isolation_last_toggle'] = 0.0
        mock_msg.text = "/isolation off"
        await cmd_isolation(mock_msg, board_id=board_id)
        assert b_data['user_settings'][user_id]['is_isolated'] is False
        assert "Режим самоизоляции выключен" in mock_msg.answer.call_args[0][0]
    finally:
        b_data['user_settings'].pop(user_id, None)


@pytest.mark.asyncio
async def test_cmd_pay_isolation_protection(isolated_test_db):
    """Проверяет блокировку переводов шекелей в /pay при самоизоляции."""
    from main import cmd_pay

    db = await get_pool()
    board_id = "b"
    sender_id = 999333
    target_id = 999444

    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, status) VALUES (?, ?, 1000.0, 'active')",
        (sender_id, board_id)
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance, status) VALUES (?, ?, 1000.0, 'active')",
        (target_id, board_id)
    )
    await db.commit()

    b_data = shared_state.board_data[board_id]

    try:
        # 1. Отправитель в изоляции
        b_data['user_settings'][sender_id] = {'is_isolated': True}
        b_data['user_settings'][target_id] = {'is_isolated': False}

        mock_msg = AsyncMock()
        mock_msg.from_user = MagicMock(id=sender_id)
        mock_msg.text = f"/pay {target_id} 100"
        mock_msg.caption = None
        mock_msg.reply_to_message = None

        await cmd_pay(mock_msg, board_id=board_id)
        assert "Вы находитесь в режиме самоизоляции" in mock_msg.answer.call_args[0][0]

        # 2. Получатель в изоляции
        b_data['user_settings'][sender_id]['is_isolated'] = False
        b_data['user_settings'][target_id]['is_isolated'] = True

        mock_msg.reset_mock()
        await cmd_pay(mock_msg, board_id=board_id)
        assert "Получатель находится в режиме самоизоляции" in mock_msg.reply.call_args[0][0]
    finally:
        b_data['user_settings'].pop(sender_id, None)
        b_data['user_settings'].pop(target_id, None)


@pytest.mark.asyncio
async def test_isolation_24h_cooldown(isolated_test_db):
    """Проверяет кулдаун 24 часа на переключение режима самоизоляции."""
    import time
    from user_manager import cmd_isolation

    board_id = "b"
    user_id = 998877
    b_data = shared_state.board_data[board_id]

    try:
        b_data['user_settings'][user_id] = {
            'is_isolated': False,
            'isolation_last_toggle': 0.0
        }

        # 1. Первое переключение: успешно включается
        msg = AsyncMock()
        msg.from_user = MagicMock(id=user_id)
        msg.text = "/isolation on"
        msg.caption = None
        await cmd_isolation(msg, board_id=board_id)

        assert b_data['user_settings'][user_id]['is_isolated'] is True
        assert b_data['user_settings'][user_id]['isolation_last_toggle'] > 0
        assert "включен" in msg.answer.call_args[0][0]

        # 2. Попытка выключить через 5 минут (кулдаун 24 часа не прошел)
        msg.reset_mock()
        msg.text = "/isolation off"
        await cmd_isolation(msg, board_id=board_id)

        # Статус не должен измениться!
        assert b_data['user_settings'][user_id]['is_isolated'] is True
        assert "не чаще одного раза в 24 часа" in msg.answer.call_args[0][0]

        # 3. Перемотка времени на 24 часа вперед
        b_data['user_settings'][user_id]['isolation_last_toggle'] = time.time() - 86500.0
        msg.reset_mock()
        msg.text = "/isolation off"
        await cmd_isolation(msg, board_id=board_id)

        # Теперь успешно выключился
        assert b_data['user_settings'][user_id]['is_isolated'] is False
        assert "выключен" in msg.answer.call_args[0][0]
    finally:
        b_data['user_settings'].pop(user_id, None)


