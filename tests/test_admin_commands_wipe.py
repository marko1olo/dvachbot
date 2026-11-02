import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import types
from aiogram.types import InlineKeyboardMarkup

from post_helpers import encode_post_num_zw, extract_post_num_from_message
from common.text_utils import extract_post_num_from_message_text
import main


@pytest.mark.asyncio
async def test_extract_post_num_from_thread_message():
    """Проверяем, что номер поста в треде (№15/500) с ZW-меткой извлекается гарантированно."""
    global_post_num = 998877
    local_post_num = 15
    zw_meta = encode_post_num_zw(global_post_num)
    header_text = f"{zw_meta}Пост №{local_post_num}/500\nПривет анон"

    # 1. extract_post_num_from_message_text
    pnum, local_num = extract_post_num_from_message_text(header_text)
    assert pnum == global_post_num
    assert local_num == local_post_num

    # 2. extract_post_num_from_message
    msg = MagicMock(spec=types.Message)
    msg.text = header_text
    msg.caption = None
    msg.entities = []
    extracted = extract_post_num_from_message(msg)
    assert extracted == global_post_num


@pytest.mark.asyncio
async def test_get_author_and_post_num_by_reply_thread():
    """Тест get_author_id_by_reply и get_post_num_by_reply при реплае на тредовый пост бота."""
    global_post_num = 54321
    target_author_id = 777888
    zw_meta = encode_post_num_zw(global_post_num)

    bot_msg = MagicMock()
    bot_msg.chat = MagicMock()
    bot_msg.chat.id = -1001234567890
    bot_msg.message_id = 42
    bot_msg.from_user = MagicMock()
    bot_msg.from_user.is_bot = True
    bot_msg.forward_from = None
    bot_msg.text = f"{zw_meta}⚡ Донесение №22/500\nТекст сообщения"
    bot_msg.caption = None
    bot_msg.entities = []

    reply_msg = MagicMock()
    reply_msg.reply_to_message = bot_msg

    with patch('main.get_post_by_num', new=AsyncMock(return_value={
        'post_num': global_post_num,
        'author_id': target_author_id,
        'board_id': 'b'
    })):
        extracted_pnum = await main.get_post_num_by_reply(reply_msg)
        assert extracted_pnum == global_post_num

        extracted_author = await main.get_author_id_by_reply(reply_msg)
        assert extracted_author == target_author_id


@pytest.mark.asyncio
async def test_cmd_wipe_reply_with_args():
    """
    Тест cmd_wipe: реплай на пост с аргументом '/wipe all global' или '/wipe 2h'.
    Проверяем, что аргументы не падают в ошибку 'Invalid User ID', а распознаются как длительность и global.
    """
    admin_id = 111222
    target_author_id = 333444
    post_num = 12345

    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = admin_id
    msg.text = "/wipe all global"
    msg.caption = None
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    bot_msg = MagicMock()
    bot_msg.chat = MagicMock()
    bot_msg.chat.id = -10011111111
    bot_msg.message_id = 55
    bot_msg.from_user = MagicMock()
    bot_msg.from_user.is_bot = True
    bot_msg.forward_from = None
    bot_msg.text = f"{encode_post_num_zw(post_num)}Пост №10/500\nТестовый текст"
    bot_msg.caption = None
    bot_msg.entities = []
    msg.reply_to_message = bot_msg

    with patch('main.is_admin', return_value=True), \
         patch('main.get_author_id_by_reply', new=AsyncMock(return_value=target_author_id)), \
         patch('main.get_post_num_by_reply', new=AsyncMock(return_value=post_num)), \
         patch('main.get_post_by_num', new=AsyncMock(return_value={'post_num': post_num, 'author_id': target_author_id, 'board_id': 'b'})):

        await main.cmd_wipe(msg, board_id='b')

        assert msg.answer.called
        call_args = msg.answer.call_args
        sent_text = call_args[0][0]
        reply_markup = call_args[1].get('reply_markup')

        assert "Вайп:" in sent_text
        assert str(target_author_id) in sent_text
        assert "ВСЕХ досках" in sent_text
        assert isinstance(reply_markup, InlineKeyboardMarkup)
        # Проверяем, что есть callback кнопка для вайпа all
        all_callbacks = [btn.callback_data for row in reply_markup.inline_keyboard for btn in row]
        assert any(f"admin_action:wipe:{target_author_id}:all:525600" in cb for cb in all_callbacks)


@pytest.mark.asyncio
async def test_cmd_wipe_anon_web_post():
    """
    Тест cmd_wipe: реплай на пост анонима с сайта (author_id = 0).
    Бот не должен показывать help-сообщение или падать.
    Он должен распознать author_id=0 и предложить удалить пост/тред и показать IP.
    """
    admin_id = 111222
    target_author_id = 0
    post_num = 777111

    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = admin_id
    msg.text = "/wipe"
    msg.caption = None
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    bot_msg = MagicMock()
    bot_msg.chat = MagicMock()
    bot_msg.chat.id = -10011111111
    bot_msg.message_id = 66
    bot_msg.from_user = MagicMock()
    bot_msg.from_user.is_bot = True
    bot_msg.forward_from = None
    bot_msg.text = f"{encode_post_num_zw(post_num)}Пост №{post_num}\nАнонимный веб-пост"
    bot_msg.caption = None
    bot_msg.entities = []
    msg.reply_to_message = bot_msg

    with patch('main.is_admin', return_value=True), \
         patch('main.get_author_id_by_reply', new=AsyncMock(return_value=target_author_id)), \
         patch('main.get_post_num_by_reply', new=AsyncMock(return_value=post_num)), \
         patch('main.get_post_by_num', new=AsyncMock(return_value={
             'post_num': post_num,
             'author_id': 0,
             'board_id': 'b',
             'ip': '192.168.1.100',
             'thread_id': '777000'
         })):

        await main.cmd_wipe(msg, board_id='b')

        assert msg.answer.called
        sent_text = msg.answer.call_args[0][0]
        reply_markup = msg.answer.call_args[1].get('reply_markup')

        assert "анонимным пользователем на сайте" in sent_text
        assert "author_id=0" in sent_text
        assert "192.168.1.100" in sent_text
        assert "Вайп по user_id=0 невозможен" in sent_text

        all_callbacks = [btn.callback_data for row in reply_markup.inline_keyboard for btn in row]
        assert any(f"admin_action:del_post:{post_num}:b:0" in cb for cb in all_callbacks)
        assert any("admin_action:del_thread:777000:b:0" in cb for cb in all_callbacks)


@pytest.mark.asyncio
async def test_execute_wipe_global():
    """Тест execute_wipe с board_id='all' (глобальный вайп)."""
    admin_id = 111222
    target_id = 555666
    minutes = 120

    bot_mock = MagicMock()
    msg_mock = MagicMock(spec=types.Message)
    msg_mock.edit_text = AsyncMock()

    with patch('main.update_shadow_mute', new=AsyncMock()) as mock_smute, \
         patch('main.delete_user_posts', new=AsyncMock(return_value=5)) as mock_del, \
         patch('main.log_global_event', new=AsyncMock()) as mock_log:

        await main.execute_wipe(bot_mock, msg_mock, target_id, 'all', admin_id, minutes)

        # Проверяем, что delete_user_posts вызван с effective_board_id='all'
        mock_del.assert_called_once_with(bot_mock, target_id, minutes, 'all')
        # Проверяем, что edit_text показал успешный снос
        assert msg_mock.edit_text.called
        final_text = msg_mock.edit_text.call_args[0][0]
        assert "ВСЕХ досках" in final_text
        assert "5" in final_text


@pytest.mark.asyncio
async def test_cmd_ban_anon_web_post():
    """Тест cmd_ban: реплай на пост анонима с сайта (author_id = 0)."""
    admin_id = 111222
    target_author_id = 0
    post_num = 888222

    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = admin_id
    msg.text = "/ban"
    msg.caption = None
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    bot_msg = MagicMock()
    bot_msg.chat = MagicMock()
    bot_msg.chat.id = -10011111111
    bot_msg.message_id = 77
    bot_msg.from_user = MagicMock()
    bot_msg.from_user.is_bot = True
    bot_msg.forward_from = None
    bot_msg.text = f"{encode_post_num_zw(post_num)}Пост №{post_num}\nТекст"
    bot_msg.caption = None
    bot_msg.entities = []
    msg.reply_to_message = bot_msg

    with patch('main.is_admin', return_value=True), \
         patch('main.get_author_id_by_reply', new=AsyncMock(return_value=target_author_id)), \
         patch('main.get_post_num_by_reply', new=AsyncMock(return_value=post_num)), \
         patch('main.get_post_by_num', new=AsyncMock(return_value={
             'post_num': post_num,
             'author_id': 0,
             'board_id': 'b',
             'ip': '203.0.113.42',
             'thread_id': '888000'
         })):

        await main.cmd_ban(msg, board_id='b')

        assert msg.answer.called
        sent_text = msg.answer.call_args[0][0]
        reply_markup = msg.answer.call_args[1].get('reply_markup')

        assert "анонимным пользователем на сайте" in sent_text
        assert "author_id=0" in sent_text
        assert "203.0.113.42" in sent_text
        assert "Бан по user_id=0 невозможен" in sent_text

        all_callbacks = [btn.callback_data for row in reply_markup.inline_keyboard for btn in row]
        assert any(f"admin_action:del_post:{post_num}:b:0" in cb for cb in all_callbacks)
        assert any("admin_action:del_thread:888000:b:0" in cb for cb in all_callbacks)


@pytest.mark.asyncio
async def test_on_admin_action_del_post_and_thread():
    """Тест on_admin_action для кнопок del_post и del_thread."""
    admin_id = 111222
    post_num = 123456
    thread_id = "123000"

    # 1. del_post
    cb_post = MagicMock(spec=types.CallbackQuery)
    cb_post.from_user = MagicMock()
    cb_post.from_user.id = admin_id
    cb_post.data = f"admin_action:del_post:{post_num}:b:0"
    cb_post.answer = AsyncMock()
    cb_post.message = MagicMock()
    cb_post.message.edit_text = AsyncMock()
    cb_post.bot = MagicMock()

    with patch('main.is_admin', return_value=True), \
         patch('main.delete_single_post', new=AsyncMock(return_value=3)) as mock_del_single, \
         patch('main.log_global_event', new=AsyncMock()):

        await main.on_admin_action(cb_post)

        mock_del_single.assert_called_once_with(post_num, cb_post.bot)
        assert cb_post.message.edit_text.called
        assert f"#{post_num}" in cb_post.message.edit_text.call_args[0][0]

    # 2. del_thread
    cb_thread = MagicMock(spec=types.CallbackQuery)
    cb_thread.from_user = MagicMock()
    cb_thread.from_user.id = admin_id
    cb_thread.data = f"admin_action:del_thread:{thread_id}:b:0"
    cb_thread.answer = AsyncMock()
    cb_thread.message = MagicMock()
    cb_thread.message.edit_text = AsyncMock()
    cb_thread.bot = MagicMock()

    with patch('main.is_admin', return_value=True), \
         patch('common.database.archive_thread_in_db', new=AsyncMock()) as mock_arch, \
         patch('main.delete_thread_atomic', new=AsyncMock()) as mock_del_th, \
         patch('main.log_global_event', new=AsyncMock()):

        await main.on_admin_action(cb_thread)

        assert mock_del_th.called
        assert cb_thread.message.edit_text.called
        assert f"#{thread_id}" in cb_thread.message.edit_text.call_args[0][0]
