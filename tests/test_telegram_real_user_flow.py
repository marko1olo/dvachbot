# -*- coding: utf-8 -*-
"""
tests/test_telegram_real_user_flow.py — Comprehensive Test Suite for Real User Telegram UI/UX Flows

Covers:
1. HTML/Markdown escaping in /reactions (cmd_reactions):
   - Malicious user IDs and emoji strings (<script>, <evil_tag>, &) escaped properly.
   - Fallback to plain text on TelegramBadRequest ("can't parse entities").
2. Virtual anon formatting in /reactions:
   - System IDs (770100001..770100050) masked as "🕶 Аноним #N" without leaking system IDs.
3. HTML escaping in post_helpers.py (format_header, format_thread_post_header):
   - Malicious author prefixes, debuffs, thread info handling when thread_info is None.
4. Escaping in _format_reactions_block (main.py and broadcaster.py):
   - Neutral/custom reaction strings safely escaped.
5. Debounce for callback_query buttons in CallbackAnswerGuardMiddleware:
   - Rapid double-clicks (<350ms) immediately answered with safe_callback_answer to stop spinner.
   - Handlers are not executed twice.
   - Different users or different callback data execute independently.
   - Subsequent click after threshold passes.
"""

import asyncio
import re
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from post_helpers import format_header, format_thread_post_header
from main import (
    cmd_reactions,
    _format_reactions_block as main_format_reactions_block,
    CallbackAnswerGuardMiddleware,
    _CALLBACK_DEBOUNCE_TRACKER,
)
from broadcaster import _format_reactions_block as broadcaster_format_reactions_block
from common.html_utils import escape_html


# =============================================================================
# FIXTURES & HELPERS
# =============================================================================

def make_mock_message(
    user_id: int = 12345,
    chat_id: int = -1001234567,
    message_id: int = 100,
    text: str = "/reactions",
    reply_to_message: types.Message = None,
    is_admin_user: bool = True
) -> MagicMock:
    """Creates a mock aiogram Message."""
    msg = MagicMock(spec=types.Message)
    msg.message_id = message_id
    msg.text = text

    user = MagicMock(spec=types.User)
    user.id = user_id
    user.is_bot = False
    user.first_name = "Admin"
    msg.from_user = user

    chat = MagicMock(spec=types.Chat)
    chat.id = chat_id
    chat.type = "supergroup"
    msg.chat = chat

    msg.reply_to_message = reply_to_message
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()

    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock()
    msg.bot = bot

    return msg


def make_mock_callback(
    user_id: int = 55555,
    data: str = "menu_btn_1",
    message_id: int = 200
) -> MagicMock:
    """Creates a mock CallbackQuery with tracked answer."""
    cb = MagicMock(spec=types.CallbackQuery)
    cb.id = f"cb_{user_id}_{int(time.time()*1000)}"
    cb.data = data
    cb._answered = False

    user = MagicMock(spec=types.User)
    user.id = user_id
    cb.from_user = user

    msg = MagicMock(spec=types.Message)
    msg.message_id = message_id
    cb.message = msg

    async def mock_answer(*args, **kwargs):
        setattr(cb, "_answered", True)
        return True

    cb.answer = AsyncMock(side_effect=mock_answer)
    return cb


# =============================================================================
# PART 1: /reactions COMMAND & VIRTUAL ANON FORMATTING
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_reactions_virtual_anon_masking():
    """cmd_reactions masks virtual anon IDs (770100001..770100050) as '🕶 Аноним #N'."""
    reply_msg = MagicMock(spec=types.Message)
    reply_msg.message_id = 999
    msg = make_mock_message(reply_to_message=reply_msg)

    post_num = 12345
    # Reactions dictionary with both virtual anons and real users
    mock_post_data = {
        "reactions": {
            "users": {
                770100001: ["❤️", "🔥"],  # Virtual Anon #1
                770100042: ["👍"],        # Virtual Anon #42
                123456789: ["🤡"]         # Real user
            }
        }
    }

    with patch("main.is_admin", return_value=True), \
         patch("main.message_to_post", {(msg.chat.id, 999): post_num}), \
         patch("main.messages_storage", {post_num: mock_post_data}):
        await cmd_reactions(msg, board_id="b", stream="ru")

    assert msg.answer.called
    response_text = msg.answer.call_args[0][0]

    # Virtual anons must be displayed as "🕶 Аноним #1" and "🕶 Аноним #42"
    assert "• 🕶 Аноним #1: ❤️🔥" in response_text
    assert "• 🕶 Аноним #42: 👍" in response_text

    # Real user must be displayed with ID
    assert "• ID <code>123456789</code>: 🤡" in response_text

    # Internal system IDs must NEVER leak in output text
    assert "770100001" not in response_text
    assert "770100042" not in response_text


@pytest.mark.asyncio
async def test_cmd_reactions_html_escaping_injection_protection():
    """cmd_reactions safely escapes malicious user IDs and emoji payloads (<script>, <evil>, &)."""
    reply_msg = MagicMock(spec=types.Message)
    reply_msg.message_id = 888
    msg = make_mock_message(reply_to_message=reply_msg)

    post_num = 54321
    evil_user_id = "<script>alert('pwn')</script>"
    evil_emojis = ["<evil_tag>", "&bad;"]

    mock_post_data = {
        "reactions": {
            "users": {
                evil_user_id: evil_emojis
            }
        }
    }

    with patch("main.is_admin", return_value=True), \
         patch("main.message_to_post", {(msg.chat.id, 888): post_num}), \
         patch("main.messages_storage", {post_num: mock_post_data}):
        await cmd_reactions(msg, board_id="b", stream="ru")

    assert msg.answer.called
    response_text = msg.answer.call_args[0][0]

    # Raw unescaped tags MUST NOT be present
    assert "<script>" not in response_text
    assert "<evil_tag>" not in response_text

    # Escaped representations MUST be present
    assert "&lt;script&gt;" in response_text
    assert "&lt;evil_tag&gt;" in response_text
    assert "&amp;bad;" in response_text


@pytest.mark.asyncio
async def test_cmd_reactions_plain_text_fallback_on_parse_error():
    """cmd_reactions falls back to plain text if Telegram rejects HTML parsing."""
    reply_msg = MagicMock(spec=types.Message)
    reply_msg.message_id = 777
    msg = make_mock_message(reply_to_message=reply_msg)

    # First answer raises parse error, second answer succeeds
    call_count = 0
    async def mock_answer_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TelegramBadRequest(method="sendMessage", message="Bad Request: can't parse entities")
        return MagicMock()

    msg.answer = AsyncMock(side_effect=mock_answer_side_effect)

    post_num = 11111
    mock_post_data = {
        "reactions": {
            "users": {
                770100005: ["🔥"]
            }
        }
    }

    with patch("main.is_admin", return_value=True), \
         patch("main.message_to_post", {(msg.chat.id, 777): post_num}), \
         patch("main.messages_storage", {post_num: mock_post_data}):
        await cmd_reactions(msg, board_id="b", stream="ru")

    # Should have attempted HTML, caught parse error, and sent stripped plain text
    assert call_count == 2
    plain_text_call = msg.answer.call_args[0][0]
    # No HTML tags in fallback
    assert "<b>" not in plain_text_call
    assert "🕶 Аноним #5" in plain_text_call


# =============================================================================
# PART 2: post_helpers.py HTML ESCAPING & RESILIENCE
# =============================================================================

@pytest.mark.asyncio
async def test_format_header_escapes_custom_prefix_html():
    """format_header escapes malicious custom prefix tags (<script>, <vip>)."""
    evil_prefix = "<script>alert('pwn')</script> & <VIP>"
    user_id = 99999
    board_id = "b"
    post_num = 1234

    mock_db = MagicMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(None, evil_prefix, int(time.time()) + 3600))
    mock_db.execute.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_db.execute.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("common.db_pool.get_pool", AsyncMock(return_value=mock_db)), \
         patch("shared_state.board_data", {board_id: {}}):
        header = await format_header(board_id, post_num, author_id=user_id)

    # Must NOT contain raw unescaped tags
    assert "<script>" not in header
    assert "<VIP>" not in header
    assert "&lt;script&gt;" in header
    assert "&lt;VIP&gt;" in header
    assert "&amp;" in header


@pytest.mark.asyncio
async def test_format_thread_post_header_handles_none_thread_info():
    """format_thread_post_header safely handles thread_info=None without raising AttributeError."""
    board_id = "b"
    post_num = 1
    author_id = 12345

    with patch("shared_state.board_data", {board_id: {}}), \
         patch("post_helpers._get_author_prefix", AsyncMock(return_value="")):
        # thread_info is explicitly None
        header = await format_thread_post_header(
            board_id=board_id,
            local_post_num=post_num,
            author_id=author_id,
            thread_info=None,
            stream="ru"
        )

    assert "Пост №1/" in header or "1/" in header


@pytest.mark.asyncio
async def test_format_thread_post_header_escapes_op_marker_and_prefix():
    """format_thread_post_header preserves valid op marker and escapes prefix."""
    board_id = "b"
    author_id = 555
    thread_info = {"op_id": 555, "posts": [1, 2]}

    with patch("shared_state.board_data", {board_id: {}}), \
         patch("post_helpers._get_author_prefix", AsyncMock(return_value="&lt;King&gt; ")):
        header = await format_thread_post_header(
            board_id=board_id,
            local_post_num=3,
            author_id=author_id,
            thread_info=thread_info,
            stream="ru"
        )

    assert "(OP)" in header
    assert "&lt;King&gt;" in header


# =============================================================================
# PART 3: _format_reactions_block HTML ESCAPING
# =============================================================================

def test_broadcaster_reactions_block_escapes_custom_reaction_tags():
    """broadcaster._format_reactions_block escapes unexpected HTML entities in neutral reactions."""
    post_data = {
        "reactions": {
            "users": {
                1: ["❤️"],
                2: ["<custom_tag>&bad"]
            }
        }
    }

    block = broadcaster_format_reactions_block(post_data)
    assert block is not None
    assert "<custom_tag>" not in block
    assert "&lt;custom_tag&gt;" in block
    assert "&amp;bad" in block


def test_main_reactions_block_escapes_custom_reaction_tags():
    """main._format_reactions_block escapes unexpected HTML entities."""
    post_data = {
        "reactions": {
            "users": {
                1: ["🔥"],
                2: ["<img_onerror>"]
            }
        }
    }

    block = main_format_reactions_block(post_data)
    assert block is not None
    assert "<img_onerror>" not in block
    assert "&lt;img_onerror&gt;" in block


# =============================================================================
# PART 4: CALLBACK QUERY DEBOUNCE (RAPID DOUBLE-CLICK PROTECTION)
# =============================================================================

@pytest.mark.asyncio
async def test_callback_debounce_first_click_executes_handler():
    """First callback click passes debounce and executes the inner handler."""
    mw = CallbackAnswerGuardMiddleware()
    cb = make_mock_callback(user_id=1001, data="pagination_page_2")

    handler_mock = AsyncMock(return_value="success_result")

    # Clear tracker for test isolation
    _CALLBACK_DEBOUNCE_TRACKER.clear()

    res = await mw(handler_mock, cb, {})

    assert res == "success_result"
    assert handler_mock.call_count == 1
    assert cb._answered is True


@pytest.mark.asyncio
async def test_callback_debounce_rapid_double_click_blocked_and_answered():
    """Rapid double-click on the same button (<350ms) is debounced immediately to stop spinner."""
    mw = CallbackAnswerGuardMiddleware()
    user_id = 2002
    button_data = "vote_reaction_heart"

    cb1 = make_mock_callback(user_id=user_id, data=button_data)
    cb2 = make_mock_callback(user_id=user_id, data=button_data)

    handler_mock = AsyncMock(return_value="done")
    _CALLBACK_DEBOUNCE_TRACKER.clear()

    # 1. First click
    res1 = await mw(handler_mock, cb1, {})
    assert res1 == "done"
    assert handler_mock.call_count == 1

    # 2. Rapid second click within 50ms
    res2 = await mw(handler_mock, cb2, {})
    # Second click was debounced: handler NOT called again!
    assert res2 is None
    assert handler_mock.call_count == 1

    # BUT cb2 was answered immediately to stop spinner in Telegram client!
    assert cb2.answer.called
    toast_text = cb2.answer.call_args[0][0]
    assert "Подожди" in toast_text or "обрабатывается" in toast_text


@pytest.mark.asyncio
async def test_callback_debounce_different_buttons_not_blocked():
    """Clicking different buttons sequentially by the same user is NOT blocked."""
    mw = CallbackAnswerGuardMiddleware()
    user_id = 3003

    cb1 = make_mock_callback(user_id=user_id, data="shop_tab_weapons")
    cb2 = make_mock_callback(user_id=user_id, data="shop_tab_clothes")

    handler_mock = AsyncMock(return_value="page_loaded")
    _CALLBACK_DEBOUNCE_TRACKER.clear()

    res1 = await mw(handler_mock, cb1, {})
    res2 = await mw(handler_mock, cb2, {})

    # Both buttons are executed because data keys are distinct
    assert res1 == "page_loaded"
    assert res2 == "page_loaded"
    assert handler_mock.call_count == 2


@pytest.mark.asyncio
async def test_callback_debounce_different_users_not_blocked():
    """Clicking the same button by two different users is NOT blocked."""
    mw = CallbackAnswerGuardMiddleware()
    button_data = "duel_accept_999"

    cb_user1 = make_mock_callback(user_id=4001, data=button_data)
    cb_user2 = make_mock_callback(user_id=4002, data=button_data)

    handler_mock = AsyncMock(return_value="duel_started")
    _CALLBACK_DEBOUNCE_TRACKER.clear()

    res1 = await mw(handler_mock, cb_user1, {})
    res2 = await mw(handler_mock, cb_user2, {})

    assert res1 == "duel_started"
    assert res2 == "duel_started"
    assert handler_mock.call_count == 2


@pytest.mark.asyncio
async def test_callback_debounce_subsequent_click_after_threshold_passes():
    """Clicking the same button after cooldown threshold (>350ms) passes normally."""
    mw = CallbackAnswerGuardMiddleware()
    user_id = 5005
    button_data = "refresh_stats"

    cb1 = make_mock_callback(user_id=user_id, data=button_data)
    cb2 = make_mock_callback(user_id=user_id, data=button_data)

    handler_mock = AsyncMock(return_value="refreshed")
    _CALLBACK_DEBOUNCE_TRACKER.clear()

    # 1. First click
    await mw(handler_mock, cb1, {})
    assert handler_mock.call_count == 1

    # 2. Wait 400ms (> 350ms threshold)
    await asyncio.sleep(0.40)

    # 3. Second click after threshold
    res2 = await mw(handler_mock, cb2, {})
    assert res2 == "refreshed"
    assert handler_mock.call_count == 2
