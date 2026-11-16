# -*- coding: utf-8 -*-
"""
tests/test_admin_and_publisher_fixes.py
Targeted verification tests for:
1. InaccessibleMessage crash resolution in admin_manager.py
2. Dead chat / dummy ID (1, 10, 7001, 7010) purge on TelegramBadRequest (chat not found)
   in periodic_publisher.py
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from aiogram import Bot, types
from aiogram.types import InaccessibleMessage, Message, Chat, User
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import admin_manager
import periodic_publisher
from shared_state import board_data, storage_lock, weekly_active_users
from common.database import get_pool, add_or_activate_user


@pytest.mark.asyncio
async def test_admin_manager_snitch_inaccessible_message(isolated_test_db):
    """
    Verify handle_snitch_callback does not crash with AttributeError
    when callback.message is an InaccessibleMessage without .text or .html_text.
    """
    target_id = 99901
    board_id = "b"
    admin_id = 123456

    # Seed target user
    await add_or_activate_user(target_id, board_id)

    # InaccessibleMessage object in aiogram 3.x
    dummy_chat = Chat(id=admin_id, type="private")
    inaccessible_msg = InaccessibleMessage(chat=dummy_chat, message_id=555, date=0)

    # Verify our assumption: InaccessibleMessage has no .text attribute
    assert not hasattr(inaccessible_msg, "text")
    assert not hasattr(inaccessible_msg, "html_text")
    assert not isinstance(inaccessible_msg, types.Message)

    # Mock callback query with InaccessibleMessage
    callback = MagicMock(spec=types.CallbackQuery)
    callback.data = f"snitch:pardon:{target_id}:{board_id}:100"
    callback.from_user = User(id=admin_id, is_bot=False, first_name="Admin", username="admin_mod")
    callback.message = inaccessible_msg
    callback.bot = AsyncMock(spec=Bot)
    callback.answer = AsyncMock()

    # Admin authorization and safe_callback_answer mock
    with patch("bot_helpers.is_admin", return_value=True), \
         patch("admin_manager.safe_callback_answer", new_callable=AsyncMock) as mock_safe_answer:

        # Should NOT raise AttributeError: 'InaccessibleMessage' object has no attribute 'text'
        await admin_manager.handle_snitch_callback(callback)

        # safe_callback_answer was successfully called with feedback
        mock_safe_answer.assert_called_once()
        args, kwargs = mock_safe_answer.call_args
        assert "оправдан" in args[1] or "Действие выполнено" in args[1]


@pytest.mark.asyncio
async def test_admin_manager_snitch_accessible_message(isolated_test_db):
    """
    Verify handle_snitch_callback correctly updates text when message is a normal types.Message.
    """
    target_id = 99902
    board_id = "b"
    admin_id = 123456

    await add_or_activate_user(target_id, board_id)

    dummy_chat = Chat(id=admin_id, type="private")
    accessible_msg = MagicMock(spec=types.Message)
    accessible_msg.chat = dummy_chat
    accessible_msg.message_id = 556
    accessible_msg.html_text = "<b>Нарушитель замечен!</b>\n<i>Выберите действие одной кнопкой:</i>"
    accessible_msg.text = "Нарушитель замечен!\nВыберите действие одной кнопкой:"
    accessible_msg.edit_text = AsyncMock()

    callback = MagicMock(spec=types.CallbackQuery)
    callback.data = f"snitch:mute:{target_id}:{board_id}:101"
    callback.from_user = User(id=admin_id, is_bot=False, first_name="Admin", username="admin_mod")
    callback.message = accessible_msg
    callback.bot = AsyncMock(spec=Bot)
    callback.answer = AsyncMock()

    with patch("bot_helpers.is_admin", return_value=True), \
         patch("admin_manager.safe_callback_answer", new_callable=AsyncMock) as mock_safe_answer:

        await admin_manager.handle_snitch_callback(callback)

        accessible_msg.edit_text.assert_called_once()
        edited_text = accessible_msg.edit_text.call_args[0][0]
        assert "Решение принято:</b> Подтвердил мут 24ч" in edited_text
        assert "@admin_mod" in edited_text
        mock_safe_answer.assert_called_once()


@pytest.mark.asyncio
async def test_admin_manager_cancel_inaccessible_message(isolated_test_db):
    """
    Verify on_admin_action 'cancel' does not crash if message is InaccessibleMessage.
    """
    dummy_chat = Chat(id=123, type="private")
    inaccessible_msg = InaccessibleMessage(chat=dummy_chat, message_id=557, date=0)

    callback = MagicMock(spec=types.CallbackQuery)
    callback.data = "admin_action:cancel"
    callback.message = inaccessible_msg
    callback.answer = AsyncMock()

    await admin_manager.on_admin_action(callback)
    callback.answer.assert_called_with("Отменено")


@pytest.mark.asyncio
async def test_send_media_group_resilient_error_handling():
    """
    Verify _send_media_group_resilient returns:
    - 'CHAT_NOT_FOUND' on TelegramBadRequest with 'chat not found'
    - 'FORBIDDEN' on TelegramForbiddenError
    - None on generic TelegramBadRequest
    """
    bot = AsyncMock(spec=Bot)

    # 1. Chat not found
    bot.send_media_group.side_effect = TelegramBadRequest(
        method="sendMediaGroup",
        message="Bad Request: chat not found"
    )
    result = await periodic_publisher._send_media_group_resilient(bot, 7001, [], attempts=1)
    assert result == "CHAT_NOT_FOUND"

    # 2. Forbidden (bot blocked)
    bot.send_media_group.side_effect = TelegramForbiddenError(
        method="sendMediaGroup",
        message="Forbidden: bot was blocked by the user"
    )
    result = await periodic_publisher._send_media_group_resilient(bot, 7001, [], attempts=1)
    assert result == "FORBIDDEN"

    # 3. Other generic bad request
    bot.send_media_group.side_effect = TelegramBadRequest(
        method="sendMediaGroup",
        message="Bad Request: message too long"
    )
    result = await periodic_publisher._send_media_group_resilient(bot, 7001, [], attempts=1)
    assert result is None


@pytest.mark.asyncio
async def test_broadcast_purges_dead_chat_and_dummy_ids(isolated_test_db):
    """
    Verify that when sending to dummy IDs (1, 10, 7001, 7010) that return 'chat not found',
    they are immediately purged from board_data['b']['users']['active'],
    weekly_active_users, and the SQLite Users table.
    """
    dummy_ids = [1, 10, 7001, 7010]
    live_id = 88888

    # Populate RAM state
    async with storage_lock:
        board_data['b']['users']['active'] = set(dummy_ids + [live_id])
        weekly_active_users['b'] = set(dummy_ids + [live_id])

    # Populate DB state
    for uid in dummy_ids + [live_id]:
        await add_or_activate_user(uid, 'b')

    # Verify initial DB state
    db = await get_pool()
    async with db.execute("SELECT user_id FROM Users WHERE board_id = 'b'") as cursor:
        rows = await cursor.fetchall()
        user_ids_in_db = {r[0] for r in rows}
    for uid in dummy_ids + [live_id]:
        assert uid in user_ids_in_db

    # Mock bot
    bot = AsyncMock(spec=Bot)

    async def mock_send_media_group(chat_id, media):
        if chat_id in dummy_ids:
            raise TelegramBadRequest(method="sendMediaGroup", message="Bad Request: chat not found")
        # Live user returns dummy sent messages
        msg = MagicMock(spec=types.Message)
        msg.photo = [MagicMock(file_id="photo_123")]
        return [msg]

    bot.send_media_group.side_effect = mock_send_media_group

    uploaded_file_ids = [["file_id_part1", "file_id_part2"]]
    recipients = periodic_publisher._snapshot_active_users(lambda: board_data['b']['users']['active'])
    assert set(recipients) == set(dummy_ids + [live_id])

    with patch("periodic_publisher.BROADCAST_DELAY_BETWEEN_GROUPS", 0), \
         patch("periodic_publisher.BROADCAST_DELAY_BETWEEN_USERS", 0):
        delivered, failed = await periodic_publisher._broadcast_to_users(bot, recipients, uploaded_file_ids)

    assert delivered == 1
    assert failed == 4

    # 1. Verify RAM board_data active set purged
    assert board_data['b']['users']['active'] == {live_id}
    assert weekly_active_users['b'] == {live_id}

    # 2. Verify snapshot no longer contains dummy IDs
    subsequent_recipients = periodic_publisher._snapshot_active_users(lambda: board_data['b']['users']['active'])
    assert subsequent_recipients == [live_id]

    # 3. Verify SQLite DB purged
    async with db.execute("SELECT user_id FROM Users WHERE board_id = 'b'") as cursor:
        rows = await cursor.fetchall()
        remaining_db_uids = {r[0] for r in rows}

    for dummy_id in dummy_ids:
        assert dummy_id not in remaining_db_uids
    assert live_id in remaining_db_uids


@pytest.mark.asyncio
async def test_broadcast_purges_forbidden_user(isolated_test_db):
    """
    Verify that TelegramForbiddenError (user blocked bot) purges user from RAM and DB identically.
    """
    blocked_id = 7002
    live_id = 99999

    async with storage_lock:
        board_data['b']['users']['active'] = {blocked_id, live_id}
        weekly_active_users['b'] = {blocked_id, live_id}

    for uid in [blocked_id, live_id]:
        await add_or_activate_user(uid, 'b')

    bot = AsyncMock(spec=Bot)

    async def mock_send_media_group(chat_id, media):
        if chat_id == blocked_id:
            raise TelegramForbiddenError(method="sendMediaGroup", message="Forbidden: bot was blocked by the user")
        msg = MagicMock(spec=types.Message)
        msg.photo = [MagicMock(file_id="photo_999")]
        return [msg]

    bot.send_media_group.side_effect = mock_send_media_group

    with patch("periodic_publisher.BROADCAST_DELAY_BETWEEN_GROUPS", 0), \
         patch("periodic_publisher.BROADCAST_DELAY_BETWEEN_USERS", 0):
        delivered, failed = await periodic_publisher._broadcast_to_users(
            bot, [blocked_id, live_id], [["file_id_part1"]]
        )

    assert delivered == 1
    assert failed == 1
    assert board_data['b']['users']['active'] == {live_id}
    assert weekly_active_users['b'] == {live_id}

    db = await get_pool()
    async with db.execute("SELECT user_id FROM Users WHERE board_id = 'b'") as cursor:
        rows = await cursor.fetchall()
        remaining = {r[0] for r in rows}
    assert blocked_id not in remaining
    assert live_id in remaining


@pytest.mark.asyncio
async def test_send_stats_to_user_chat_not_found_purges_user(isolated_test_db):
    """
    Verify send_stats_to_user catches chat not found on initial send_message and purges user.
    """
    dead_id = 7010
    async with storage_lock:
        board_data['b']['users']['active'] = {dead_id}

    await add_or_activate_user(dead_id, 'b')

    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramBadRequest(
        method="sendMessage",
        message="Bad Request: chat not found"
    )

    await periodic_publisher.send_stats_to_user(bot, dead_id)

    # User purged from RAM and DB
    assert dead_id not in board_data['b']['users']['active']

    db = await get_pool()
    async with db.execute("SELECT user_id FROM Users WHERE user_id = ? AND board_id = 'b'", (dead_id,)) as cursor:
        assert await cursor.fetchone() is None
