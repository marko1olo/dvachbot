# -*- coding: utf-8 -*-
import pytest
import time
from unittest import mock
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers.message_router import (
    CYBERCHAD_DIRECT_TRIGGER_REGEX,
    _is_direct_cyberchad_trigger,
    trigger_cyberchad_with_rate_limit,
    _CYBERCHAD_USER_LAST_DIRECT
)
from ai_manager import (
    CYBERCHAD_NAME_REGEX,
    _LAST_CHAD_POST_TS,
    _BOARD_FIGHT_TRACKER,
    register_post_and_maybe_trigger_cyberchad_intervention
)
from extreme_defense_engine import (
    build_snitch_keyboard,
    send_auto_snitch_alert,
    clear_user_extreme_strikes,
    _EXTREME_STRIKES_CACHE
)
from admin_manager import handle_snitch_callback
from site_tgach.admin_config import ADMIN_IDS
import shared_state
from shared_state import board_data, BOARDS


@pytest.fixture(autouse=True)
def clean_chad_test_state():
    _CYBERCHAD_USER_LAST_DIRECT.clear()
    _LAST_CHAD_POST_TS.clear()
    _EXTREME_STRIKES_CACHE.clear()
    yield
    _CYBERCHAD_USER_LAST_DIRECT.clear()
    _LAST_CHAD_POST_TS.clear()
    _EXTREME_STRIKES_CACHE.clear()


# ==============================================================================
# 1. CYBERCHAD TRIGGER TESTS
# ==============================================================================

def test_cyberchad_trigger_regex_inflections_and_negatives():
    """Проверяет распознавание только Киберчеда и его производных, и строгий отказ на голый 'чед'/'чеду'."""
    positives = [
        "киберчед", "киберчеда", "киберчеду", "киберчедом", "киберчеде", "киберчеди",
        "киберчедик", "киберчедики", "киберчедос",
        "кибер-чед поясни", "кибер дед", "нейрочед ответь", "cyberchad", "cyber chad", "кибер-чедик выходи",
        "спроси у киберчедика", "эй киберчед!"
    ]
    for p in positives:
        assert CYBERCHAD_DIRECT_TRIGGER_REGEX.search(p), f"Regex must match positive: '{p}'"
        assert CYBERCHAD_NAME_REGEX.search(p), f"ai_manager regex must match positive: '{p}'"

    negatives = [
        "чед", "чеда", "чеду", "чедом", "чеде", "чеди",
        "чедик", "чедики", "чедос",
        "чед, ты тут?", "поясни чеду", "спроси у чедика", "эй чед!",
        "chad", "chadd", "chado", "chads",
        "гигачед", "гигачеду", "мегачед",
        "очередь", "в очереди стою", "очередной тред", "человек", "человека", "сыр чеддер", "чеддар"
    ]
    for n in negatives:
        assert not CYBERCHAD_DIRECT_TRIGGER_REGEX.search(n), f"Regex must NOT match negative: '{n}'"
        assert not CYBERCHAD_NAME_REGEX.search(n), f"ai_manager regex must NOT match negative: '{n}'"


@pytest.mark.asyncio
async def test_is_direct_cyberchad_trigger_inflections():
    """Проверяет функцию _is_direct_cyberchad_trigger: только киберчед/производные тригерят, голый 'чед'/'чеду' игнорируются."""
    assert await _is_direct_cyberchad_trigger("чед поясни за жизнь", None) is False
    assert await _is_direct_cyberchad_trigger("поясни чеду", None) is False
    assert await _is_direct_cyberchad_trigger("чедик выходи", None) is False
    assert await _is_direct_cyberchad_trigger("киберчед поясни за жизнь", None) is True
    assert await _is_direct_cyberchad_trigger("киберчедик выходи", None) is True
    assert await _is_direct_cyberchad_trigger("спросим у киберчеда", None) is True
    assert await _is_direct_cyberchad_trigger("ответь киберчеду", None) is True
    assert await _is_direct_cyberchad_trigger("стоял в очереди два часа", None) is False
    assert await _is_direct_cyberchad_trigger("хороший человек", None) is False


@pytest.mark.asyncio
async def test_trigger_cyberchad_passes_is_rate_checked_flag():
    """Проверяет, что router передает is_rate_checked=True при прямом зове."""
    mock_bot = mock.AsyncMock()
    now = 500000.0

    with mock.patch("handlers.message_router.register_post_and_maybe_trigger_cyberchad_intervention", new=mock.AsyncMock()) as mock_intervene, \
         mock.patch("time.time", return_value=now):

        res = await trigger_cyberchad_with_rate_limit(
            bot=mock_bot,
            board_id="b",
            user_id=456,
            text="киберчед поясни",
            post_num=5555,
            reply_to_post=None,
            stream="ru"
        )
        assert res is True
        mock_intervene.assert_called_once_with(
            mock_bot, "b", 456, "киберчед поясни", post_num=5555, reply_to_post=None, stream="ru", is_rate_checked=True
        )


@pytest.mark.asyncio
async def test_direct_call_bypasses_board_cooldown():
    """Проверяет, что прямой зов Киберчеда по имени не блокируется 25-секундным кулдауном доски."""
    board_id = "b"
    now = 100000.0
    # Доска запостила Чеда 10 секунд назад (кулдаун доски 25с еще не прошел)
    _LAST_CHAD_POST_TS[board_id] = now - 10.0

    mock_bot = mock.AsyncMock()
    with mock.patch("ai_manager.summarize_text_with_hf", new=mock.AsyncMock()) as mock_hf, \
         mock.patch("common.bot_helpers.process_new_post", new=mock.AsyncMock()), \
         mock.patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new=mock.AsyncMock(return_value=(b"voice_data", {}))), \
         mock.patch("time.time", return_value=now), \
         mock.patch("os.environ.get", return_value=""):  # in_test_env = False to trigger cooldown logic

        mock_hf.return_value = '{"reply": true, "text": "Я пришел развалить кабину", "thought": "разнос"}'

        await register_post_and_maybe_trigger_cyberchad_intervention(
            bot=mock_bot,
            board_id=board_id,
            user_id=888,
            text="киберчед выходи",
            post_num=6001,
            reply_to_post=None,
            stream="ru",
            is_rate_checked=True
        )

        # Прямой вызов должен был сработать (effective_board_cd = 5.0с < 10.0с)
        assert mock_hf.called, "Direct call to Cyberchad should NOT be blocked by 25s board cooldown!"


# ==============================================================================
# 2. AUTO-SNITCH TESTS
# ==============================================================================

def test_build_snitch_keyboard():
    """Проверяет структуру и callback_data кнопок Автостукача."""
    kb = build_snitch_keyboard(user_id=12345, board_id="b", post_num=999)
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 2

    row0 = kb.inline_keyboard[0]
    row1 = kb.inline_keyboard[1]
    assert len(row0) == 2
    assert len(row1) == 2

    assert "Сжечь и Забанить" in row0[0].text
    assert row0[0].callback_data == "snitch:ban:12345:b:999"

    assert "Подтвердить мут" in row0[1].text
    assert row0[1].callback_data == "snitch:mute:12345:b:999"

    assert "Запретить медиа" in row1[0].text
    assert row1[0].callback_data == "snitch:media:12345:b:999"

    assert "Размутить" in row1[1].text
    assert row1[1].callback_data == "snitch:pardon:12345:b:999"


@pytest.mark.asyncio
async def test_send_auto_snitch_alert():
    """Проверяет рассылку карточки инцидента Автостукача администраторам."""
    bot_mock = mock.AsyncMock()
    bot_mock.send_message = mock.AsyncMock()

    sent = await send_auto_snitch_alert(
        bot=bot_mock,
        user_id=777888,
        board_id="b",
        post_num=10101,
        reason="Вайп-флуд одинаковыми сообщениями",
        details="Спам текст поста номер 10101"
    )
    assert sent >= 1
    assert bot_mock.send_message.called

    call_args = bot_mock.send_message.call_args[0]
    call_kwargs = bot_mock.send_message.call_args[1]
    assert "АВТОСТУКАЧ: ОБНАРУЖЕН НАРУШИТЕЛЬ" in call_args[1]
    assert "777888" in call_args[1]
    assert "#10101" in call_args[1]
    assert "Вайп-флуд" in call_args[1]
    assert call_kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_handle_snitch_callback_permission_denied():
    """Проверяет отказ в доступе для не-админа при клике по кнопкам Автостукача."""
    cb = mock.AsyncMock(spec=types.CallbackQuery)
    cb.from_user = mock.MagicMock(id=999999999, username="random_user")
    cb.data = "snitch:ban:111222:b:500"
    cb.answer = mock.AsyncMock()

    with mock.patch("admin_manager.is_admin", return_value=False):
        await handle_snitch_callback(cb)

    assert cb.answer.called
    assert "нет прав" in cb.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_snitch_callback_ban_action(isolated_test_db):
    """Проверяет действие 'Сжечь и Забанить': бан в БД/RAM, удаление постов и апдейт карточки."""
    db = isolated_test_db
    admin_id = next(iter(ADMIN_IDS))
    target_id = 111333
    board_id = "b"

    # Инициализация доски в RAM
    b_data = board_data.setdefault(board_id, {})
    b_data.setdefault("users", {"banned": set(), "active": {target_id}})

    cb = mock.AsyncMock(spec=types.CallbackQuery)
    cb.bot = mock.AsyncMock()
    cb.from_user = mock.MagicMock(id=admin_id, username="danata")
    cb.data = f"snitch:ban:{target_id}:{board_id}:777"
    cb.answer = mock.AsyncMock()
    cb.message = mock.AsyncMock()
    cb.message.html_text = "🚨 <b>АВТОСТУКАЧ</b>\nНарушитель: 111333\n<i>Выберите действие одной кнопкой:</i>"
    cb.message.edit_text = mock.AsyncMock()

    with mock.patch("admin_manager.is_admin", return_value=True), \
         mock.patch("post_helpers.delete_user_posts", new=mock.AsyncMock(return_value=5)) as mock_del:

        await handle_snitch_callback(cb)

        assert mock_del.called
        assert target_id in b_data["users"]["banned"]
        assert target_id not in b_data["users"]["active"]

        assert cb.message.edit_text.called
        edited_text = cb.message.edit_text.call_args[0][0]
        assert "Решение принято:" in edited_text
        assert "Сжёг и забанил" in edited_text
        assert "@danata" in edited_text
        assert cb.message.edit_text.call_args[1].get("reply_markup") is None


@pytest.mark.asyncio
async def test_handle_snitch_callback_pardon_action(isolated_test_db):
    """Проверяет действие 'Оправдать и размутить': снятие мутов, разбан, очистка страйков."""
    db = isolated_test_db
    admin_id = next(iter(ADMIN_IDS))
    target_id = 222444
    board_id = "b"

    b_data = board_data.setdefault(board_id, {})
    b_data.setdefault("users", {"banned": {target_id}, "active": set()})
    b_data.setdefault("user_settings", {})[target_id] = {"shadow_media": True}
    b_data.setdefault("mutes", {})[target_id] = time.time() + 3600

    # Запишем пользователя в БД с мутом и запретом медиа
    await db.execute(
        "INSERT INTO Users (user_id, board_id, status, cursed_until, shadow_ban_media) VALUES (?, ?, 'banned', ?, 1)",
        (target_id, board_id, int(time.time() + 3600))
    )
    await db.commit()

    # Добавим страйк в кэш
    _EXTREME_STRIKES_CACHE[target_id] = [{"post_num": 1, "category": "COPRO"}]

    cb = mock.AsyncMock(spec=types.CallbackQuery)
    cb.bot = mock.AsyncMock()
    cb.from_user = mock.MagicMock(id=admin_id, username="admin_boss")
    cb.data = f"snitch:pardon:{target_id}:{board_id}:888"
    cb.answer = mock.AsyncMock()
    cb.message = mock.AsyncMock()
    cb.message.html_text = "🚨 <b>АВТОСТУКАЧ</b>\nНарушитель: 222444\n<i>Выберите действие одной кнопкой:</i>"
    cb.message.edit_text = mock.AsyncMock()

    with mock.patch("admin_manager.is_admin", return_value=True), \
         mock.patch("common.database.remove_global_mute", new=mock.AsyncMock()) as mock_remove_gm, \
         mock.patch("common.database.update_shadow_mute", new=mock.AsyncMock()) as mock_unmute, \
         mock.patch("common.database.add_or_activate_user", new=mock.AsyncMock()) as mock_activate, \
         mock.patch("extreme_defense_engine.get_pool", return_value=db), \
         mock.patch("admin_manager.get_pool", return_value=db):

        await handle_snitch_callback(cb)

        # Мут снят и проверен вызов remove_global_mute
        assert mock_remove_gm.called
        assert mock_unmute.called
        assert mock_activate.called
        assert target_id in b_data["users"]["active"]
        assert target_id not in b_data["users"]["banned"]
        assert target_id not in b_data["mutes"]
        assert b_data["user_settings"][target_id]["shadow_media"] is False
        assert target_id not in _EXTREME_STRIKES_CACHE

        # Проверяем сброс cursed_until и shadow_ban_media в БД
        async with db.execute("SELECT cursed_until, shadow_ban_media FROM Users WHERE user_id = ?", (target_id,)) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 0
            assert row[1] == 0

        assert cb.message.edit_text.called
        edited_text = cb.message.edit_text.call_args[0][0]
        assert "Оправдал и размутил" in edited_text
        assert "@admin_boss" in edited_text
