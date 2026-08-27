import asyncio
import json
import pytest
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import common.db_pool
from common.database import (
    init_db,
    update_user_settings_db,
    load_state_from_db,
    add_spam_word,
    remove_spam_word,
    load_all_spam_words,
)
from common.spam_filter import (
    set_spam_filter_words,
    is_spam_filtered,
    _spam_filter_words,
)
from shared_state import board_data, BroadcastConfig
from broadcaster import MessageBroadcaster
from delivery_manager import edit_post_for_all_recipients
from user_manager import cmd_hide
from admin_manager import cmd_filter


@pytest.fixture(autouse=True)
def reset_globals():
    board_data.clear()
    _spam_filter_words.clear()
    yield
    board_data.clear()
    _spam_filter_words.clear()


@pytest.mark.asyncio
async def test_cmd_hide_add_del_idempotency_and_casing():
    """Тест добавления и удаления слов в /hide с разным регистром и проверкой идепотентности."""
    b_id = "b"
    board_data[b_id] = {
        'user_settings': {},
        'stream': 'ru',
    }
    user_id = 12345

    def make_msg(text):
        m = AsyncMock()
        m.text = text
        m.caption = None
        m.from_user.id = user_id
        m.answer = AsyncMock()
        return m

    with patch("user_manager.spawn_task"):
        # 1. Добавление с разным регистром и пробелами
        await cmd_hide(make_msg("/hide add  СЛОВО  "), b_id, stream='ru')
        assert board_data[b_id]['user_settings'][user_id]['hide'] == {'слово'}

        # 2. Повторное добавление в другом регистре (CamelCase)
        await cmd_hide(make_msg("/hide add СлОвО"), b_id, stream='ru')
        assert board_data[b_id]['user_settings'][user_id]['hide'] == {'слово'}  # Идепотентно, дубликатов нет

        # 3. Добавление в lowercase
        await cmd_hide(make_msg("/hide add слово"), b_id, stream='ru')
        assert board_data[b_id]['user_settings'][user_id]['hide'] == {'слово'}

        # 4. Добавление второго слова в UPPERCASE
        await cmd_hide(make_msg("/hide add КАЛЛ"), b_id, stream='ru')
        assert board_data[b_id]['user_settings'][user_id]['hide'] == {'калл', 'слово'}

        # 5. Проверка команды /hide list
        list_msg = make_msg("/hide list")
        await cmd_hide(list_msg, b_id, stream='ru')
        list_msg.answer.assert_called_once()
        ans_text = list_msg.answer.call_args[0][0]
        assert "<code>калл</code>" in ans_text
        assert "<code>слово</code>" in ans_text

        # 6. Удаление через /hide remove в смешанном регистре
        del_msg1 = make_msg("/hide remove СлОвО")
        await cmd_hide(del_msg1, b_id, stream='ru')
        assert board_data[b_id]['user_settings'][user_id]['hide'] == {'калл'}
        del_msg1.answer.assert_called_once()
        assert "удалено" in del_msg1.answer.call_args[0][0].lower()

        # 7. Удаление через алиас /hide del в UPPERCASE
        del_msg2 = make_msg("/hide del КАЛЛ")
        await cmd_hide(del_msg2, b_id, stream='ru')
        assert board_data[b_id]['user_settings'][user_id]['hide'] == set()
        del_msg2.answer.assert_called_once()
        assert "удалено" in del_msg2.answer.call_args[0][0].lower()

        # 8. Идепотентное удаление несуществующего слова (не падает)
        del_msg3 = make_msg("/hide del НеСуЩеСтВуЮщЕе")
        await cmd_hide(del_msg3, b_id, stream='ru')
        assert board_data[b_id]['user_settings'][user_id]['hide'] == set()
        del_msg3.answer.assert_called_once()
        assert "не найдено" in del_msg3.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_cmd_filter_add_del_idempotency_and_casing():
    """Тест команды администратора /filter add и /filter del/remove на идепотентность и регистронезависимость."""
    b_id = "b"
    board_data[b_id] = {
        'spam_filter_words': set(),
        'stream': 'ru',
    }
    admin_id = 99999

    def make_msg(text):
        m = AsyncMock()
        m.text = text
        m.caption = None
        m.from_user.id = admin_id
        m.answer = AsyncMock()
        m.delete = AsyncMock()
        return m

    with patch("admin_manager.is_admin", return_value=True), \
         patch("admin_manager.add_spam_word", new=AsyncMock(return_value=True)), \
         patch("admin_manager.remove_spam_word", new=AsyncMock(return_value=True)):

        # 1. Добавление стоп-слова в UPPERCASE
        await cmd_filter(make_msg("/filter add СПАМ_ССЫЛКА"), b_id, stream='ru')
        words = board_data[b_id]['spam_filter_words']
        assert words == {'спам_ссылка'}

        # 2. Повторное добавление в CamelCase (идепотентно)
        await cmd_filter(make_msg("/filter add СпАм_СсЫлКа"), b_id, stream='ru')
        assert words == {'спам_ссылка'}

        # 3. Добавление второго слова
        await cmd_filter(make_msg("/filter add РЕКЛАМА"), b_id, stream='ru')
        assert words == {'реклама', 'спам_ссылка'}

        # 4. Проверка /filter list
        list_msg = make_msg("/filter list")
        await cmd_filter(list_msg, b_id, stream='ru')
        list_msg.answer.assert_called_once()
        assert "<code>реклама</code>" in list_msg.answer.call_args[0][0]
        assert "<code>спам_ссылка</code>" in list_msg.answer.call_args[0][0]

        # 5. Удаление через /filter del в нижнем регистре
        del_msg1 = make_msg("/filter del спам_ссылка")
        await cmd_filter(del_msg1, b_id, stream='ru')
        assert words == {'реклама'}

        # 6. Удаление через /filter remove в CAPS
        del_msg2 = make_msg("/filter remove РЕКЛАМА")
        await cmd_filter(del_msg2, b_id, stream='ru')
        assert words == set()


@pytest.mark.asyncio
async def test_broadcaster_post_filtering_any_case_combinations():
    """Тест MessageBroadcaster: проверка сокрытия сообщений при любых комбинациях регистра в тексте поста и фильтре."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=101))

    b_id = "test_board_hide"
    uid_filtered = 1001
    uid_normal = 1002

    board_data[b_id] = {
        'users': {'active': {uid_filtered, uid_normal}, 'banned': set()},
        'user_settings': {
            uid_filtered: {'nsfw': False, 'hide': {'калл', 'спам', 'нейросеть'}, 'disable_ai_roasts': False, 'hide_ai_slop': False},
            uid_normal: {'nsfw': False, 'hide': set(), 'disable_ai_roasts': False, 'hide_ai_slop': False},
        },
        'user_state': {},
        'stream': 'ru',
        'subscribers': set(),
    }

    # Вариант 1: Пост содержит слово в верхнем регистре "КАЛЛ"
    content1 = {'type': 'text', 'text': 'Какой-то пост про полный КАЛЛ', 'header': 'Пост #1', 'post_num': 1}
    cfg1 = BroadcastConfig(
        bot_instance=mock_bot,
        board_id=b_id,
        recipients={uid_filtered, uid_normal},
        content=content1,
    )
    broadcaster1 = MessageBroadcaster(cfg1)
    await broadcaster1.broadcast()

    assert mock_bot.send_message.call_count == 2
    calls_map = {
        (call.kwargs.get('chat_id') if 'chat_id' in call.kwargs else (call.args[0] if call.args else None)):
        (call.kwargs.get('text') if 'text' in call.kwargs else (call.args[1] if len(call.args) > 1 else ''))
        for call in mock_bot.send_message.call_args_list
    }
    assert "🛡 Сообщение скрыто" in calls_map[uid_filtered]
    assert "Какой-то пост про полный КАЛЛ" in calls_map[uid_normal]

    mock_bot.send_message.reset_mock()

    # Вариант 2: Пост содержит слово в смешанном регистре "НейРоСеТь" в заголовке
    content2 = {'type': 'text', 'text': 'Обычный текст', 'header': 'Тред: НейРоСеТь захватывает мир', 'post_num': 2}
    cfg2 = BroadcastConfig(
        bot_instance=mock_bot,
        board_id=b_id,
        recipients={uid_filtered, uid_normal},
        content=content2,
    )
    broadcaster2 = MessageBroadcaster(cfg2)
    await broadcaster2.broadcast()

    calls_map2 = {
        (call.kwargs.get('chat_id') if 'chat_id' in call.kwargs else (call.args[0] if call.args else None)):
        (call.kwargs.get('text') if 'text' in call.kwargs else (call.args[1] if len(call.args) > 1 else ''))
        for call in mock_bot.send_message.call_args_list
    }
    assert "🛡 Сообщение скрыто" in calls_map2[uid_filtered]
    assert "Обычный текст" in calls_map2[uid_normal]

    mock_bot.send_message.reset_mock()

    # Вариант 3: Пост с caption фото и словом "сПаМ"
    content3 = {'type': 'photo', 'caption': 'Смотри на этот сПаМ в ленте', 'header': 'Пост #3', 'post_num': 3}
    cfg3 = BroadcastConfig(
        bot_instance=mock_bot,
        board_id=b_id,
        recipients={uid_filtered, uid_normal},
        content=content3,
    )
    broadcaster3 = MessageBroadcaster(cfg3)
    await broadcaster3.broadcast()

    calls_map3 = {
        (call.kwargs.get('chat_id') if 'chat_id' in call.kwargs else (call.args[0] if call.args else None)):
        (call.kwargs.get('text') if 'text' in call.kwargs else (call.args[1] if len(call.args) > 1 else ''))
        for call in mock_bot.send_message.call_args_list
    }
    assert "🛡 Сообщение скрыто" in calls_map3[uid_filtered]


@pytest.mark.asyncio
async def test_delivery_manager_edit_filtering_any_case():
    """Тест edit_post_for_all_recipients: скрытие поста при редактировании при совпадении регистра."""
    mock_bot = AsyncMock()
    mock_bot.edit_message_text = AsyncMock()

    b_id = "test_edit_board"
    uid_filtered = 2001
    uid_clean = 2002

    board_data[b_id] = {
        'user_settings': {
            uid_filtered: {'hide': {'спойлер', 'утечка'}},
            uid_clean: {'hide': set()},
        },
        'stream': 'ru',
    }

    # Имитируем хранилище сообщений
    from shared_state import messages_storage, post_to_messages
    post_num = 9999
    messages_storage[post_num] = {
        'board_id': b_id,
        'author_id': 555,
        'content': {
            'type': 'text',
            'text': 'Новый СПОЙЛЕР к финалу и УтЕчКа сюжета!',
            'header': 'Пост #9999',
            'post_num': post_num
        }
    }
    post_to_messages[post_num] = {
        uid_filtered: 111,
        uid_clean: 222
    }

    try:
        with patch("delivery_manager._format_message_body", new=AsyncMock(return_value="Новый СПОЙЛЕР к финалу и УтЕчКа сюжета!")):
            await edit_post_for_all_recipients(post_num, mock_bot)

        # Проверяем, что _edit_one вызван для каждого получателя
        assert mock_bot.edit_message_text.call_count == 2
        calls = {call.kwargs.get('chat_id') or call.args[1]: call.kwargs.get('text') or call.args[0]
                 for call in mock_bot.edit_message_text.call_args_list}

        assert "🛡 Сообщение скрыто" in calls[uid_filtered]
        assert "СПОЙЛЕР" in calls[uid_clean]
    finally:
        messages_storage.pop(post_num, None)
        post_to_messages.pop(post_num, None)


import aiosqlite

@pytest.mark.asyncio
async def test_database_persistence_and_reloading_normalization(tmp_path):
    """Тест сохранения и загрузки настроек скрытия слов и спам-фильтра в SQLite."""
    test_db_path = str(tmp_path / "test_filter.db")
    
    # Настраиваем подключение к тестовой БД
    conn = await aiosqlite.connect(test_db_path)
    common.db_pool._db_connection = conn
    
    try:
        await init_db(conn)

        user_id = 77777
        board_id = "b"

        # 1. Создаем пользователя в БД
        await conn.execute(
            "INSERT INTO Users (user_id, board_id, status, location, nsfw_spoiler, hidden_words) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, board_id, 'active', 'main', 0, '[]')
        )
        await conn.commit()

        # 2. Обновляем настройки с дубликатами и разным регистром
        dirty_words = ["СЛОВО", "слово", "  СлОвО  ", "КАЛЛ", "калл", "СПАМ"]
        await update_user_settings_db(user_id, board_id, hidden_words=dirty_words)

        # 3. Проверяем сырое содержимое в SQLite
        async with conn.execute("SELECT hidden_words FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            saved_json = row[0]
            saved_list = json.loads(saved_json)
            # Должно быть строго отсортировано, в нижнем регистре и без дубликатов
            assert saved_list == ['калл', 'слово', 'спам']

        # 4. Проверяем load_state_from_db
        state = await load_state_from_db({'b'})
        loaded_hide_set = state['board_data'][board_id]['user_settings'][user_id]['hide']
        assert loaded_hide_set == {'калл', 'слово', 'спам'}

        # 5. Тестируем add_spam_word / remove_spam_word / load_all_spam_words
        await add_spam_word(board_id, "  МАТ_И_СПАМ  ")
        # Повторное добавление (идепотентно)
        await add_spam_word(board_id, "мат_и_спам")
        await add_spam_word(board_id, "Мат_И_Спам")

        loaded_spam = await load_all_spam_words()
        assert loaded_spam[board_id] == {'мат_и_спам'}

        # Удаление в другом регистре
        removed = await remove_spam_word(board_id, "МАТ_И_СПАМ")
        assert removed is True

        loaded_spam_after = await load_all_spam_words()
        assert loaded_spam_after[board_id] == set()

        # Повторное удаление (не падает, возвращает False)
        removed_again = await remove_spam_word(board_id, "мат_и_спам")
        assert removed_again is False

    finally:
        await conn.close()
        common.db_pool._db_connection = None


def test_spam_filter_helper_functions():
    """Тест функций set_spam_filter_words и is_spam_filtered на нормализацию и регистронезависимость."""
    b_id = "test"
    set_spam_filter_words(b_id, {"  ЗАПРЕТНОЕ_СЛОВО  ", "ХАКЕР", "КаЛл"})
    
    assert _spam_filter_words[b_id] == {"запретное_слово", "хакер", "калл"}

    # Проверка фильтрации текста в любом регистре
    assert is_spam_filtered("Тут есть ЗаПреТнОе_СлОвО в тексте", b_id, user_id=123) is True
    assert is_spam_filtered("Полный КАЛЛ", b_id, user_id=123) is True
    assert is_spam_filtered("Чистый пост без запретов", b_id, user_id=123) is False
