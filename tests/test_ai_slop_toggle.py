import pytest
import asyncio
import sqlite3
import json
from unittest.mock import AsyncMock, MagicMock, patch

from common.bot_helpers import is_ai_slop_content
from common.database import init_db, update_user_settings_db, load_state_from_db
import shared_state
from shared_state import board_data, BroadcastConfig


def test_is_ai_slop_content_detection():
    # 1. Content dict flags
    assert is_ai_slop_content({'is_ai_roast': True}) is True
    assert is_ai_slop_content({'is_ai_persona': True}) is True
    assert is_ai_slop_content({'is_ai': True}) is True
    assert is_ai_slop_content({'is_ai_slop': True}) is True

    # 2. Text markers
    assert is_ai_slop_content(text="🔥 Вердикт /b/ AI:\nПолный бред") is True
    assert is_ai_slop_content(text="🎵 Трек: Artist — Song\n🔥 Вердикт /b/ музкритика:\nГовно\n💩 Шкала говноедства: 10/10") is True
    assert is_ai_slop_content(text="👽 [ШИЗО-ТАБЛЕТКА]\nСтранный текст") is True
    assert is_ai_slop_content(text="🔥 Разъёб от Киберчеда") is True
    assert is_ai_slop_content({'text': '🤖 [AI-Анон]: Привет Двачу'}) is True

    # 3. Regular posts should NOT be detected as slop
    assert is_ai_slop_content({'type': 'text', 'text': 'Привет, как дела на борде?'}) is False
    assert is_ai_slop_content({'type': 'photo', 'caption': 'Обычное фото котика'}) is False
    assert is_ai_slop_content(text="Просто сообщение без нейросетей") is False
    assert is_ai_slop_content(None, None) is False


@pytest.mark.asyncio
async def test_database_persistence_and_load_state(tmp_path):
    db_file = str(tmp_path / "test_tgach.db")
    
    import common.db_pool
    if common.db_pool._db_connection:
        try:
            await common.db_pool._db_connection.close()
        except Exception:
            pass
        common.db_pool._db_connection = None

    with patch("common.config.DB_NAME", db_file), \
         patch("common.db_pool.DB_NAME", db_file), \
         patch("common.database.DB_NAME", db_file):
        await init_db()

        # Insert test users
        from common.database import add_or_activate_user
        await add_or_activate_user(1001, 'b')
        await add_or_activate_user(1002, 'b')

        # Update user 1001 to disable AI roasts
        await update_user_settings_db(1001, 'b', disable_ai_roasts=1)
        # Update user 1002 with hide_ai_slop alias
        await update_user_settings_db(1002, 'b', hide_ai_slop=0)

        # Load state
        loaded_state = await load_state_from_db(set())
        u1_settings = loaded_state['board_data']['b']['user_settings'][1001]
        u2_settings = loaded_state['board_data']['b']['user_settings'][1002]

        assert u1_settings['disable_ai_roasts'] is True
        assert u1_settings['hide_ai_slop'] is True
        assert u2_settings['disable_ai_roasts'] is False
        assert u2_settings['hide_ai_slop'] is False

        # Toggle user 1001 back to False
        await update_user_settings_db(1001, 'b', disable_ai_roasts=0)
        loaded_state2 = await load_state_from_db(set())
        assert loaded_state2['board_data']['b']['user_settings'][1001]['disable_ai_roasts'] is False

    if common.db_pool._db_connection:
        try:
            await common.db_pool._db_connection.close()
        except Exception:
            pass
        common.db_pool._db_connection = None


@pytest.mark.asyncio
async def test_broadcaster_filtering():
    from broadcaster import MessageBroadcaster
    
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=123))

    b_id = 'test_board_ai'
    board_data[b_id] = {
        'users': {'active': {101, 102, 103}, 'banned': set()},
        'user_settings': {
            101: {'nsfw': False, 'hide': set(), 'disable_ai_roasts': False, 'hide_ai_slop': False},
            102: {'nsfw': False, 'hide': set(), 'disable_ai_roasts': True, 'hide_ai_slop': True},  # Opted out
            103: {'nsfw': False, 'hide': set(), 'disable_ai_roasts': False, 'hide_ai_slop': False},
        },
        'user_state': {},
        'stream': 'ru',
        'subscribers': set(),
        'post_counter': 100
    }

    # 1. Broadcaster for normal post -> should go to 101, 102, 103
    normal_content = {'type': 'text', 'text': 'Обычный анонимный пост', 'post_num': 101}
    cfg_normal = BroadcastConfig(
        bot_instance=mock_bot,
        board_id=b_id,
        recipients={101, 102, 103},
        content=normal_content,
        keyboard=None
    )
    broadcaster_normal = MessageBroadcaster(cfg_normal)
    assert broadcaster_normal.is_ai_content is False
    res_normal = await broadcaster_normal.broadcast()
    assert mock_bot.send_message.call_count == 3

    mock_bot.send_message.reset_mock()

    # 2. Broadcaster for AI roast post -> should ONLY go to 101 and 103, skipping 102
    ai_content = {
        'type': 'text',
        'text': '🔥 Вердикт /b/ AI: Ваша голосовуха — полная чушь',
        'is_ai_roast': True,
        'post_num': 102
    }
    cfg_ai = BroadcastConfig(
        bot_instance=mock_bot,
        board_id=b_id,
        recipients={101, 102, 103},
        content=ai_content,
        keyboard=None
    )
    broadcaster_ai = MessageBroadcaster(cfg_ai)
    assert broadcaster_ai.is_ai_content is True
    res_ai = await broadcaster_ai.broadcast()
    
    called_uids = {call.kwargs.get('chat_id') or (call.args[0] if call.args else None) for call in mock_bot.send_message.call_args_list}
    assert 102 not in called_uids
    assert 101 in called_uids
    assert 103 in called_uids


    # 3. Broadcaster for Cyberchad Voice Roast -> should ONLY go to 101 and 103 via send_voice, skipping 102
    mock_bot.send_voice = AsyncMock(return_value=MagicMock(message_id=124))
    voice_content = {
        'type': 'voice',
        'voice_bytes': b"MOCK_CYBERCHAD_VOICE_BYTES",
        'caption': '🔥 Разъёб от Киберчеда',
        'is_ai_roast': True,
        'is_ai': True,
        'post_num': 103
    }
    cfg_voice = BroadcastConfig(
        bot_instance=mock_bot,
        board_id=b_id,
        recipients={101, 102, 103},
        content=voice_content,
        keyboard=None
    )
    broadcaster_voice = MessageBroadcaster(cfg_voice)
    assert broadcaster_voice.is_ai_content is True
    res_voice = await broadcaster_voice.broadcast()

    called_voice_uids = {call.kwargs.get('chat_id') or (call.args[0] if call.args else None) for call in mock_bot.send_voice.call_args_list}
    assert 102 not in called_voice_uids
    assert 101 in called_voice_uids
    assert 103 in called_voice_uids


@pytest.mark.asyncio
async def test_delivery_manager_recipient_resolution():
    from delivery_manager import MessageDeliveryTask
    
    b_id = 'test_deliv_ai'
    board_data[b_id] = {
        'users': {'active': {201, 202}, 'banned': set()},
        'user_settings': {
            201: {'nsfw': False, 'hide': set(), 'disable_ai_roasts': False, 'hide_ai_slop': False},
            202: {'nsfw': False, 'hide': set(), 'disable_ai_roasts': True, 'hide_ai_slop': True}, # Opted out
        },
        'user_state': {201: {'location': 'main'}, 202: {'location': 'main'}},
        'stream': 'ru',
        'post_counter': 200
    }

    # AI Roast Task (Text)
    ai_task = MessageDeliveryTask(
        worker_name='w1',
        board_id=b_id,
        bot_instance=AsyncMock(),
        queue=MagicMock(),
        msg_data={'post_num': 101, 'content': {'type': 'text', 'text': '🔥 Вердикт /b/ AI', 'is_ai_roast': True}}
    )
    ai_task.content = ai_task.msg_data['content']
    ai_task.thread_id = None
    ai_task.initial_recipients = {201, 202}
    resolved_recipients = ai_task._resolve_active_recipients()
    assert 202 not in resolved_recipients
    assert 201 in resolved_recipients

    # AI Roast Task (Voice from RAM)
    voice_ai_task = MessageDeliveryTask(
        worker_name='w1_voice',
        board_id=b_id,
        bot_instance=AsyncMock(),
        queue=MagicMock(),
        msg_data={'post_num': 102, 'content': {
            'type': 'voice',
            'voice_bytes': b"MOCK_OGG",
            'caption': '🔥 Разъёб от Киберчеда',
            'is_ai_roast': True,
            'is_ai': True
        }}
    )
    voice_ai_task.content = voice_ai_task.msg_data['content']
    voice_ai_task.thread_id = None
    voice_ai_task.initial_recipients = {201, 202}
    resolved_voice_recipients = voice_ai_task._resolve_active_recipients()
    assert 202 not in resolved_voice_recipients
    assert 201 in resolved_voice_recipients

    # Normal Task
    normal_task = MessageDeliveryTask(
        worker_name='w2',
        board_id=b_id,
        bot_instance=AsyncMock(),
        queue=MagicMock(),
        msg_data={'post_num': 103, 'content': {'type': 'text', 'text': 'Обычный текст'}}
    )
    normal_task.content = normal_task.msg_data['content']
    normal_task.thread_id = None
    normal_task.initial_recipients = {201, 202}
    resolved_normal = normal_task._resolve_active_recipients()
    assert 201 in resolved_normal
    assert 202 in resolved_normal


def test_personal_menu_keyboard_rendering():
    from main import get_personal_menu_keyboard

    b_id = 'test_menu_ai'
    board_data[b_id] = {
        'user_settings': {
            301: {'nsfw': False, 'hide': set(), 'disable_ai_roasts': False, 'hide_ai_slop': False},
            302: {'nsfw': False, 'hide': set(), 'disable_ai_roasts': True, 'hide_ai_slop': True},
        }
    }

    # User with enabled AI
    text1, kb1 = get_personal_menu_keyboard(b_id, 301, stream='ru')
    assert "AI-разъёбы / Нейрослоп:</b> 👁 Включены" in text1
    ai_btn1 = next(btn for row in kb1.inline_keyboard for btn in row if btn.callback_data == "pers_ai_toggle")
    assert "🚫 Скрыть AI-разъёбы: ❌ НЕТ" in ai_btn1.text

    # User with hidden AI
    text2, kb2 = get_personal_menu_keyboard(b_id, 302, stream='ru')
    assert "AI-разъёбы / Нейрослоп:</b> 🚫 Скрыты" in text2
    ai_btn2 = next(btn for row in kb2.inline_keyboard for btn in row if btn.callback_data == "pers_ai_toggle")
    assert "🚫 Скрыть AI-разъёбы: ✅ ДА" in ai_btn2.text

    # English stream with multilang enabled
    with patch("main.ENABLE_MULTILANG", True):
        text_en, kb_en = get_personal_menu_keyboard(b_id, 302, stream='en')
        assert "AI Roasts / Neuro-Slop:</b> 🚫 Hidden" in text_en
        ai_btn_en = next(btn for row in kb_en.inline_keyboard for btn in row if btn.callback_data == "pers_ai_toggle")
        assert "🚫 Hidden" in ai_btn_en.text


@pytest.mark.asyncio
async def test_cmd_toggle_ai_slop():
    from main import cmd_toggle_ai_slop

    b_id = 'test_cmd_ai'
    board_data[b_id] = {
        'users': {'active': {401}, 'banned': set()},
        'user_settings': {
            401: {'nsfw': False, 'hide': set(), 'disable_ai_roasts': False, 'hide_ai_slop': False}
        }
    }

    msg_mock = AsyncMock()
    msg_mock.from_user.id = 401
    msg_mock.text = "/slop hide"
    msg_mock.caption = None
    msg_mock.answer = AsyncMock()

    with patch("main.spawn_task") as mock_spawn:
        await cmd_toggle_ai_slop(msg_mock, b_id, stream='ru')
        assert board_data[b_id]['user_settings'][401]['disable_ai_roasts'] is True
        assert board_data[b_id]['user_settings'][401]['hide_ai_slop'] is True
        assert "скрыты" in msg_mock.answer.call_args[0][0]

        # Toggle back to show
        msg_mock.text = "/slop show"
        await cmd_toggle_ai_slop(msg_mock, b_id, stream='ru')
        assert board_data[b_id]['user_settings'][401]['disable_ai_roasts'] is False
        assert board_data[b_id]['user_settings'][401]['hide_ai_slop'] is False
        assert "включены" in msg_mock.answer.call_args[0][0]
