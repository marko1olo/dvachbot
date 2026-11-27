# -*- coding: utf-8 -*-
"""
tests/test_reaction_and_casino_fixes.py
Verifies:
1. Reaction notification delivery:
   - Immediate dispatch helper send_author_reaction_notification.
   - Fallback when reply_to_message_id fails with TelegramBadRequest.
   - Fallback to other bots in global_bot_pool when primary bot is blocked or chat not found.
2. execute_delayed_edit notification fallback resilience.
3. Casino cooldown UX:
   - When callback query trips cooldown, answers callback with alert and never destroys game UI.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter


@pytest.mark.asyncio
async def test_send_author_reaction_notification_success():
    from handlers.message_router import send_author_reaction_notification

    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())

    ok = await send_author_reaction_notification(
        author_id=12345,
        notify_text="🔥 Анон двачует пост #100",
        reply_to_message_id=999,
        bot_instance=bot
    )

    assert ok is True
    bot.send_message.assert_called_once_with(
        12345,
        "🔥 Анон двачует пост #100",
        reply_to_message_id=999,
        parse_mode="HTML"
    )


@pytest.mark.asyncio
async def test_send_author_reaction_notification_reply_fallback():
    from handlers.message_router import send_author_reaction_notification

    bot = MagicMock()
    # First call with reply_to fails with TelegramBadRequest; second call without reply_to succeeds
    bot.send_message = AsyncMock(side_effect=[
        TelegramBadRequest(method="send_message", message="Bad Request: reply message not found"),
        MagicMock()
    ])

    ok = await send_author_reaction_notification(
        author_id=12345,
        notify_text="🔥 Анон двачует пост #100",
        reply_to_message_id=999,
        bot_instance=bot
    )

    assert ok is True
    assert bot.send_message.call_count == 2
    # Verify second call was without reply_to_message_id
    bot.send_message.assert_called_with(
        12345,
        "🔥 Анон двачует пост #100",
        parse_mode="HTML"
    )


@pytest.mark.asyncio
async def test_send_author_reaction_notification_bot_pool_fallback():
    from handlers.message_router import send_author_reaction_notification

    bot1 = MagicMock()
    # bot1 is blocked or has no chat
    bot1.send_message = AsyncMock(side_effect=TelegramForbiddenError(method="send_message", message="Forbidden: bot was blocked by the user"))

    bot2 = MagicMock()
    bot2.send_message = AsyncMock(return_value=MagicMock())

    mock_pool = MagicMock()
    mock_pool.get_main_bot.return_value = bot2
    mock_pool.all_bots = [bot1, bot2]

    with patch("common.bot_pool.global_bot_pool", mock_pool):
        ok = await send_author_reaction_notification(
            author_id=12345,
            notify_text="🔥 Анон двачует пост #100",
            reply_to_message_id=None,
            bot_instance=bot1
        )

        assert ok is True
        bot2.send_message.assert_called_once_with(
            12345,
            "🔥 Анон двачует пост #100",
            parse_mode="HTML"
        )


@pytest.mark.asyncio
async def test_execute_delayed_edit_fallback_without_reply():
    from delivery_manager import execute_delayed_edit

    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[
        TelegramBadRequest(method="send_message", message="Bad Request: message to be replied not found"),
        MagicMock()
    ])

    with patch("delivery_manager.edit_post_for_all_recipients", new_callable=AsyncMock) as mock_edit:
        await execute_delayed_edit(
            post_num=500,
            bot_instance=bot,
            author_id=777,
            notify_text="👍 Твой пост одобрен!",
            reply_to_message_id=123,
            delay=0.01
        )

        assert bot.send_message.call_count == 2
        mock_edit.assert_called_once_with(500, bot)


@pytest.mark.asyncio
async def test_slots_spin_cooldown_toast_preserves_ui():
    import casino_engine
    import main

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    bot = MagicMock()

    user_id = 999999

    with patch("casino_engine.check_casino_cooldown", return_value=(False, 1.5)), \
         patch("main.safe_edit_message", new_callable=AsyncMock) as mock_edit, \
         patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:

        await main._run_slots_spin(
            bot=bot,
            chat_id=123,
            user_id=user_id,
            board_id="b",
            bet=100,
            message_to_edit=callback.message,
            callback=callback
        )

        # Must answer callback with alert toast
        callback.answer.assert_called_once()
        args, kwargs = callback.answer.call_args
        assert "Барабан еще остывает" in args[0]
        assert kwargs.get("show_alert") is True

        # Must NEVER overwrite the message or post a dead banner!
        mock_edit.assert_not_called()
        mock_banner.assert_not_called()
