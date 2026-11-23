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
from contextlib import asynccontextmanager
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
    cmd_report,
    process_report_pipeline,
    cmd_passport,
    cmd_dossier,
    cmd_help,
    cmd_boards,
    cmd_pay,
    cmd_anon,
    cmd_wallet,
    cb_feedback_prompt_info,
)
from common.tts_engine import (
    clean_tts_text,
    is_speakable_tts_text,
    synthesize_cyberchad_voice_with_meta,
    CYBERCHAD_DEFAULT_FALLBACK_ROASTS,
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
    user.username = "admin_user"
    user.full_name = "Admin User"
    msg.from_user = user

    chat = MagicMock(spec=types.Chat)
    chat.id = chat_id
    chat.type = "supergroup"
    msg.chat = chat

    msg.reply_to_message = reply_to_message
    msg.forward_from = None
    msg.forward_from_chat = None
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.delete = AsyncMock()

    bot = MagicMock(spec=Bot)
    bot.id = 99999999
    bot.send_message = AsyncMock()
    msg.bot = bot

    return msg


@asynccontextmanager
async def _mock_db_tx(db=None):
    yield db


class MockCursor:
    def __init__(self, fetchone_val=None, fetchall_val=None):
        self._fetchone = fetchone_val
        self._fetchall = fetchall_val or []

    async def fetchone(self):
        return self._fetchone

    async def fetchall(self):
        return self._fetchall

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    def __await__(self):
        async def _dummy():
            return self
        return _dummy().__await__()


class MockDB:
    def __init__(self, fetchone_val=None, fetchall_val=None):
        self.cursor = MockCursor(fetchone_val=fetchone_val, fetchall_val=fetchall_val)

    def execute(self, *args, **kwargs):
        return self.cursor


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


# =============================================================================
# REAL USER FLOW TESTS: FEEDBACK ROW 11 & CYBERCHAD SAFETY REFUSAL
# =============================================================================

from ai_manager import parse_cyberchad_response, is_cyberchad_refusal
from common.tts_engine import clean_tts_text
from post_helpers import extract_post_num_from_message, encode_post_num_zw
from main import (
    cmd_report,
    process_report_pipeline,
    cmd_passport,
    cmd_dossier,
    cmd_help,
    cmd_boards,
    _REPORT_USER_COOLDOWNS,
)


def test_post_num_extraction_with_zero_width_and_banners():
    """Feedback Row 11: Invisible zero-width chars and banners must not prevent post_num extraction."""
    # 1. Real format from Feedback row 11:
    zw_text = (
        "🔥 КИБЕРЧЕД 🔥\n"
        "\u2060\u200c\u200b\u200b\u200c\u200b\u200b\u200b\u200b\u200c\u200c\u200c\u200b\u200c\u200b\u200b\u200c\u200b\u200c\u200c\u200b\u2060"
        "Пост №593558\n\n🔥 Разъёб от Киберчеда"
    )
    pnum = extract_post_num_from_message(zw_text)
    assert pnum == 593558

    # 2. Header with banner on line 1 without zero-width metadata
    banner_text = "🪗 БАЯН ×2\nПост №34567\nТекст баяна"
    assert extract_post_num_from_message(banner_text) == 34567

    # 3. Cyberchad header without zero-width metadata
    chad_text = "🔥 КИБЕРЧЕД 🔥\nПост №112233\nРоаст текст"
    assert extract_post_num_from_message(chad_text) == 112233


def test_cyberchad_safety_refusal_detection_and_fallback():
    """LLM safety refusal strings (from Post 593558) must be intercepted and replaced with canonical roast."""
    refusal_json = (
        '{\n'
        '  "reply": true,\n'
        '  "thought": "Рефьюз модели",\n'
        '  "text": "Я не могу генерировать сообщения с использованием ненормативной лексики и оскорблений.",\n'
        '  "reason_if_skipped": ""\n'
        '}'
    )
    res = parse_cyberchad_response(refusal_json)
    assert res["reply"] is True
    # The output MUST NOT contain the corporate refusal!
    assert "Я не могу" not in res["text"]
    assert "ненормативной лексики" not in res["text"]
    # It must contain the canonical roast
    assert "омежка" in res["text"]

    # Test regex fallback with refusal
    broken_refusal_json = '{"reply": true, "text": "Я не могу отвечать на этот запрос из-за правил безопасности"'
    res_regex = parse_cyberchad_response(broken_refusal_json)
    assert "правил безопасности" not in res_regex["text"]
    assert "омежка" in res_regex["text"]

    # Test raw text fallback with refusal
    raw_refusal = "Как искусственный интеллект, я не могу использовать ненормативную лексику."
    res_raw = parse_cyberchad_response(raw_refusal)
    assert "Как искусственный интеллект" not in res_raw["text"]
    assert "омежка" in res_raw["text"]

    # Test clean_tts_text in tts_engine
    tts_cleaned = clean_tts_text("Я не могу генерировать сообщения с использованием ненормативной лексики и оскорблений.")
    assert "Я не могу" not in tts_cleaned
    assert "омежка" in tts_cleaned


# =============================================================================
# REAL USER FLOW TESTS: /report COMMAND & INLINE FLOWS
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_report_with_reply():
    """User replies to a message with /report: pipeline triggered and friendly reply sent."""
    reported_msg = make_mock_message(user_id=8888, message_id=50, text="Подозрительное сообщение")
    report_cmd_msg = make_mock_message(
        user_id=7777,
        message_id=51,
        text="/report спам и реклама",
        reply_to_message=reported_msg
    )

    _REPORT_USER_COOLDOWNS.clear()
    with patch("main.get_post_by_num", new_callable=AsyncMock) as mock_get_post, \
         patch("main.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("main.spawn_task") as mock_spawn:

        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = None  # No existing report
        mock_cursor.__aenter__.return_value = mock_cursor
        mock_db.execute.return_value = mock_cursor
        mock_get_pool.return_value = mock_db

        await cmd_report(report_cmd_msg, board_id="b", stream="ru")

        # pipeline must be spawned
        assert mock_spawn.call_count >= 1
        # Cooldown must be recorded
        assert 7777 in _REPORT_USER_COOLDOWNS


@pytest.mark.asyncio
async def test_cmd_report_with_post_num_argument():
    """User types /report 593558: resolves post from DB, spawns pipeline without reported_msg."""
    report_cmd_msg = make_mock_message(
        user_id=7777,
        message_id=60,
        text="/report 593558 накрутка реакций",
        reply_to_message=None
    )

    _REPORT_USER_COOLDOWNS.clear()
    with patch("main.get_post_by_num", new_callable=AsyncMock) as mock_get_post, \
         patch("main.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("main.spawn_task") as mock_spawn:

        mock_get_post.return_value = {
            "post_num": 593558,
            "board_id": "b",
            "author_id": 9999,
            "text_content": "Тестовый спам пост",
            "thread_id": 593000
        }
        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.__aenter__.return_value = mock_cursor
        mock_db.execute.return_value = mock_cursor
        mock_get_pool.return_value = mock_db

        await cmd_report(report_cmd_msg, board_id="b", stream="ru")

        # pipeline must be spawned
        assert mock_spawn.call_count >= 1
        assert 7777 in _REPORT_USER_COOLDOWNS


@pytest.mark.asyncio
async def test_cmd_report_with_zero_width_copied_text():
    """User pastes copied text containing zero-width spaces into /report."""
    zw_text = (
        "/report \u2060\u200c\u200b\u200b\u200c\u200b\u200b\u200b\u200b\u200c\u200c\u200c\u200b\u200c\u200b\u200b\u200c\u200b\u200c\u200c\u200b\u2060"
        "Пост №593558"
    )
    report_cmd_msg = make_mock_message(
        user_id=7777,
        message_id=65,
        text=zw_text,
        reply_to_message=None
    )

    _REPORT_USER_COOLDOWNS.clear()
    with patch("main.get_post_by_num", new_callable=AsyncMock) as mock_get_post, \
         patch("main.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("main.spawn_task") as mock_spawn:

        mock_get_post.return_value = {
            "post_num": 593558,
            "board_id": "b",
            "author_id": 9999,
            "text_content": "Текст",
            "thread_id": None
        }
        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.__aenter__.return_value = mock_cursor
        mock_db.execute.return_value = mock_cursor
        mock_get_pool.return_value = mock_db

        await cmd_report(report_cmd_msg, board_id="b", stream="ru")
        assert mock_spawn.call_count >= 1


@pytest.mark.asyncio
async def test_cmd_report_without_args_shows_friendly_help():
    """User calls /report without reply and without post number: receives friendly instruction."""
    report_cmd_msg = make_mock_message(
        user_id=7777,
        message_id=70,
        text="/report",
        reply_to_message=None
    )

    _REPORT_USER_COOLDOWNS.clear()
    await cmd_report(report_cmd_msg, board_id="b", stream="ru")

    report_cmd_msg.answer.assert_called_once()
    answer_text = report_cmd_msg.answer.call_args[0][0]
    assert "Как отправить жалобу" in answer_text
    assert "/report" in answer_text
    assert "<code>" in answer_text


@pytest.mark.asyncio
async def test_cmd_report_nonexistent_post():
    """User calls /report 999999: post not found in DB gives clear error."""
    report_cmd_msg = make_mock_message(
        user_id=7777,
        message_id=75,
        text="/report 999999 спам",
        reply_to_message=None
    )

    _REPORT_USER_COOLDOWNS.clear()
    with patch("main.get_post_by_num", new_callable=AsyncMock, return_value=None):
        await cmd_report(report_cmd_msg, board_id="b", stream="ru")

    report_cmd_msg.answer.assert_called_once()
    assert "не найден в базе данных" in report_cmd_msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_report_dm_default_board():
    """User calls /report in DM with board_id=None: handles gracefully instead of silent return."""
    report_cmd_msg = make_mock_message(
        user_id=7777,
        message_id=80,
        text="/report",
        reply_to_message=None
    )

    _REPORT_USER_COOLDOWNS.clear()
    await cmd_report(report_cmd_msg, board_id=None, stream="ru")

    # Should answer with instructions even in DM
    report_cmd_msg.answer.assert_called_once()
    assert "Как отправить жалобу" in report_cmd_msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_process_report_pipeline_with_none_reported_msg():
    """process_report_pipeline must not crash with AttributeError when reported_msg is None."""
    cmd_msg = make_mock_message(user_id=7777, message_id=85, text="/report 593558")
    bot_mock = cmd_msg.bot

    with patch("main.get_post_by_num", new_callable=AsyncMock) as mock_get_post, \
         patch("main.fetch_user_report_dossier", new_callable=AsyncMock, return_value=("Досье", 10, 2)), \
         patch("main.analyze_report_with_ai", new_callable=AsyncMock, return_value={"full_analysis": "Анализ: спам. Вердикт для анона: Одобрено."}), \
         patch("main.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("main.spawn_task"):

        mock_get_post.return_value = {
            "post_num": 593558,
            "board_id": "b",
            "author_id": 12345,
            "text_content": "Спам спам спам",
            "thread_id": 593000
        }
        mock_db = AsyncMock()
        mock_get_pool.return_value = mock_db

        # Must not raise AttributeError
        await process_report_pipeline(
            bot=bot_mock,
            message=cmd_msg,
            reported_msg=None,
            author_id=12345,
            board_id="b",
            stream="ru",
            post_num=593558,
            reason_text="Тестовая жалоба"
        )

        # User feedback sent
        cmd_msg.answer.assert_called_once()
        user_reply = cmd_msg.answer.call_args[0][0]
        assert "Репорт принят" in user_reply


# =============================================================================
# REAL USER FLOW TESTS: /passport, /dossier, /help MOBILE RESILIENCE
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_passport_caption_overflow_protection():
    """cmd_passport truncates caption to <= 1024 chars even when dirty balance and stars overflow it."""
    passport_msg = make_mock_message(user_id=1111, message_id=90, text="/passport")
    passport_msg.answer_photo = AsyncMock()

    from io import BytesIO
    fake_buf = BytesIO(b"FAKE_PNG_BYTES")
    # Huge text report that exceeds 1024 characters
    long_report = "☘️ <b>Статистика:</b> " + ("А" * 950)

    with patch("main.get_pool", new_callable=AsyncMock), \
         patch("main._get_user_active_items", new_callable=AsyncMock) as mock_items, \
         patch("main.spawn_task"), \
         patch("stats_generator.generate_user_stats_card", return_value=(fake_buf, long_report)):

        mock_items.return_value = {
            "dirty_balance": 500000.0,
            "wanted_stars": 5,
            "bounty_pool": 25000.0
        }

        await cmd_passport(passport_msg, board_id="b", stream="ru")

        passport_msg.answer_photo.assert_called_once()
        caption = passport_msg.answer_photo.call_args[1]["caption"]
        # Caption MUST be <= 1024 characters to prevent TelegramBadRequest caption too long
        assert len(caption) <= 1024


@pytest.mark.asyncio
async def test_cmd_passport_dm_graceful():
    """cmd_passport called in DM (board_id=None) defaults to 'b' rather than returning silently."""
    passport_msg = make_mock_message(user_id=1111, message_id=92, text="/passport")
    passport_msg.answer = AsyncMock()

    with patch("main.get_pool", new_callable=AsyncMock), \
         patch("main._get_user_active_items", new_callable=AsyncMock, return_value={}), \
         patch("main.spawn_task"), \
         patch("stats_generator.generate_user_stats_card", return_value=(None, "☘️ <b>Паспорт</b>")):

        await cmd_passport(passport_msg, board_id=None, stream="ru")
        passport_msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_dossier_html_escaping():
    """cmd_dossier escapes malicious custom_prefix and role_str before sending to banner."""
    dossier_msg = make_mock_message(user_id=2222, message_id=95, text="/dossier")

    with patch("main.get_pool", new_callable=AsyncMock), \
         patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=1000), \
         patch("main.deduct_user_global_balance", new_callable=AsyncMock, return_value=(True, 250)), \
         patch("main.record_user_transaction", new_callable=AsyncMock), \
         patch("main.add_to_abu_fund", new_callable=AsyncMock), \
         patch("main.spawn_task"), \
         patch("stats_generator.fetch_user_stats_data", return_value={
             "rank": 1,
             "total_users": 100,
             "posts_count": 50,
             "rx_received": 10,
             "rx_given": 5,
             "cringe_factor": 5.0,
             "balance": 250,
             "mutes_count": 0,
             "role": "Хакер <evil_role>",
             "role_name": "Хакер <evil_role>",
             "custom_prefix": "<script>alert('xss')</script>"
         }), \
         patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_send_banner:

        # Force non-error mode
        with patch("random.random", return_value=0.99):
            await cmd_dossier(dossier_msg, board_id="b", stream="ru")

            mock_send_banner.assert_called_once()
            caption = mock_send_banner.call_args[1]["caption"]
            # Must be escaped: no unescaped <script> or <evil_role>
            assert "<script>" not in caption
            assert "&lt;script&gt;" in caption
            assert "<evil_role>" not in caption.lower()
            assert "&lt;evil_role&gt;" in caption.lower()


@pytest.mark.asyncio
async def test_cmd_help_and_boards_dm_graceful():
    """cmd_help and cmd_boards called in DM (board_id=None) respond properly."""
    help_msg = make_mock_message(user_id=3333, message_id=97, text="/help")
    boards_msg = make_mock_message(user_id=3333, message_id=98, text="/boards")

    with patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner, \
         patch("main._send_thread_info_if_applicable", new_callable=AsyncMock):

        await cmd_help(help_msg, board_id=None, stream="ru")
        assert mock_banner.call_count == 1

        mock_banner.reset_mock()
        await cmd_boards(boards_msg, board_id=None, stream="ru")
        assert mock_banner.call_count == 1


# =============================================================================
# WAVE 2 TESTS: EDGE-TTS RESILIENCE, VOICE ROTATION & CHAT/DM COMMAND UI/UX
# =============================================================================

def test_clean_tts_text_unpronounceable_emoji_only_returns_empty():
    """Unpronounceable emoji, punctuation, or symbol noise returns empty string."""
    assert clean_tts_text("🔥🔥🔥 💩💩 🤖🛸") == ""
    assert clean_tts_text("... ??? --- !?!") == ""
    assert clean_tts_text("@@@###$$$%%%^^^&&&***") == ""
    assert clean_tts_text(">>123456 #654321") == ""
    assert clean_tts_text("а") == ""  # < 2 chars
    assert clean_tts_text("") == ""


def test_is_speakable_tts_text_rules():
    """is_speakable_tts_text requires >= 2 alphanumeric characters."""
    assert is_speakable_tts_text("Да") is True
    assert is_speakable_tts_text("Привет анон") is True
    assert is_speakable_tts_text("42") is True
    assert is_speakable_tts_text("а") is False
    assert is_speakable_tts_text("🔥") is False
    assert is_speakable_tts_text("... ???") is False
    assert is_speakable_tts_text("") is False
    assert is_speakable_tts_text(None) is False


@pytest.mark.asyncio
async def test_synthesize_empty_or_whitespace_returns_none_instantly():
    """synthesize_cyberchad_voice_with_meta returns None instantly on empty/whitespace input."""
    res, preset = await synthesize_cyberchad_voice_with_meta("")
    assert res is None
    assert preset is not None

    res_space, _ = await synthesize_cyberchad_voice_with_meta("    ")
    assert res_space is None


@pytest.mark.asyncio
async def test_synthesize_unpronounceable_text_substitutes_canonical_cyberchad_roast():
    """When input has symbols but is unpronounceable, substitutes canonical Cyberchad roast."""
    import io
    unpronounceable = "🔥💩🤡 🤖🛸⚡"

    with patch("edge_tts.Communicate") as mock_comm_cls:
        mock_comm = AsyncMock()
        mock_comm.save = AsyncMock()
        mock_comm_cls.return_value = mock_comm

        with patch("shutil.which", return_value="C:\\ffmpeg\\bin\\ffmpeg.exe"):
            with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.communicate.return_value = (b"", b"")
                mock_exec.return_value = mock_proc

                with patch("os.path.exists", return_value=True), \
                     patch("os.path.getsize", return_value=5000), \
                     patch("builtins.open", MagicMock(return_value=io.BytesIO(b"MOCK_FALLBACK_AUDIO"))):

                    data, preset = await synthesize_cyberchad_voice_with_meta(unpronounceable, preset="classic")
                    assert data == b"MOCK_FALLBACK_AUDIO"
                    # Edge-TTS was called with one of the canonical roasts
                    mock_comm_cls.assert_called_once()
                    called_text = mock_comm_cls.call_args[0][0]
                    # The text pronounced was one of the canonical roasts, NOT empty or raw emoji
                    assert any(r[:15] in called_text for r in CYBERCHAD_DEFAULT_FALLBACK_ROASTS)


@pytest.mark.asyncio
async def test_cmd_pay_negative_number_shows_sharp_alert_and_buttons():
    """cmd_pay with negative amount alerts user sharply and shows action buttons."""
    msg = make_mock_message(user_id=1001, text="/pay 2002 -500")
    mock_db = MockDB(fetchone_val=None)

    with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
         patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=10000), \
         patch("main._resolve_target_user_id", new_callable=AsyncMock, return_value=2002), \
         patch("main.is_user_isolated", return_value=False):

        await cmd_pay(msg, board_id="b", stream="ru")

        msg.reply.assert_called_once()
        reply_text = msg.reply.call_args[0][0]
        reply_kb = msg.reply.call_args[1].get("reply_markup")
        assert "отрицательные шекели" in reply_text
        assert reply_kb is not None


@pytest.mark.asyncio
async def test_cmd_pay_zero_shows_friendly_minimum_fee():
    """cmd_pay with 0 amount rejects with minimum donation alert."""
    msg = make_mock_message(user_id=1001, text="/pay 2002 0")
    mock_db = MockDB(fetchone_val=None)

    with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
         patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=10000), \
         patch("main._resolve_target_user_id", new_callable=AsyncMock, return_value=2002), \
         patch("main.is_user_isolated", return_value=False):

        await cmd_pay(msg, board_id="b", stream="ru")

        msg.reply.assert_called_once()
        reply_text = msg.reply.call_args[0][0]
        assert "отрицательные шекели" in reply_text or "Слишком мелкая подачка" in reply_text


@pytest.mark.asyncio
async def test_cmd_pay_nan_and_inf_handled_safely():
    """cmd_pay handles NaN and inf without crashing."""
    msg_nan = make_mock_message(user_id=1001, text="/pay 2002 nan")
    msg_inf = make_mock_message(user_id=1001, text="/pay 2002 inf")
    mock_db = MockDB(fetchone_val=None)

    with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
         patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=10000), \
         patch("main._resolve_target_user_id", new_callable=AsyncMock, return_value=2002), \
         patch("main.is_user_isolated", return_value=False):

        await cmd_pay(msg_nan, board_id="b", stream="ru")
        msg_nan.reply.assert_called_once()
        assert "корректную сумму" in msg_nan.reply.call_args[0][0]

        await cmd_pay(msg_inf, board_id="b", stream="ru")
        msg_inf.reply.assert_called_once()
        assert "Финмониторинг Абу" in msg_inf.reply.call_args[0][0] or "корректную сумму" in msg_inf.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_pay_to_self_blocked_with_work_button():
    """cmd_pay targeting oneself is blocked and provides /work button."""
    msg = make_mock_message(user_id=1001, text="/pay 1001 500")
    mock_db = MockDB(fetchone_val=None)

    with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
         patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=10000), \
         patch("main._resolve_target_user_id", new_callable=AsyncMock, return_value=1001), \
         patch("main.is_user_isolated", return_value=False):

        await cmd_pay(msg, board_id="b", stream="ru")

        msg.reply.assert_called_once()
        reply_text = msg.reply.call_args[0][0]
        reply_kb = msg.reply.call_args[1].get("reply_markup")
        assert "Самому себе донатить нельзя" in reply_text
        assert reply_kb is not None
        assert any(btn.callback_data == "work_main_hub" for row in reply_kb.inline_keyboard for btn in row)


@pytest.mark.asyncio
async def test_cmd_pay_to_bot_blocked_with_bank_button():
    """cmd_pay targeting the bot is blocked with Abu bank button."""
    msg = make_mock_message(user_id=1001, text="/pay 99999999 500")
    mock_db = MockDB(fetchone_val=None)

    with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
         patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=10000), \
         patch("main._resolve_target_user_id", new_callable=AsyncMock, return_value=99999999), \
         patch("main.is_user_isolated", return_value=False):

        await cmd_pay(msg, board_id="b", stream="ru")

        msg.reply.assert_called_once()
        reply_text = msg.reply.call_args[0][0]
        reply_kb = msg.reply.call_args[1].get("reply_markup")
        assert "задонатить боту" in reply_text
        assert reply_kb is not None
        assert any(btn.callback_data == "bank_main" for row in reply_kb.inline_keyboard for btn in row)


@pytest.mark.asyncio
async def test_cmd_pay_dm_graceful():
    """cmd_pay called in DM (board_id=None) does not silently return."""
    msg = make_mock_message(user_id=1001, text="/pay")
    mock_db = MockDB(fetchone_val=None)

    with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
         patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=5000), \
         patch("main.is_user_isolated", return_value=False):

        await cmd_pay(msg, board_id=None, stream="ru")

        msg.reply.assert_called_once()
        assert "КАК ПЕРЕВЕСТИ ШЕКЕЛИ" in msg.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_report_reporting_bot_intercepted_with_feedback_button():
    """cmd_report reporting a bot message intercepts with feedback button."""
    bot_msg = make_mock_message(user_id=99999999, message_id=50, text="Бот пост")
    bot_msg.from_user.is_bot = True

    rep_msg = make_mock_message(user_id=1001, message_id=51, text="/report", reply_to_message=bot_msg)

    with patch("main.spawn_task"):
        await cmd_report(rep_msg, board_id="b", stream="ru")

        rep_msg.answer.assert_called_once()
        ans_text = rep_msg.answer.call_args[0][0]
        ans_kb = rep_msg.answer.call_args[1].get("reply_markup")
        assert "Жалоба на бота" in ans_text
        assert ans_kb is not None
        assert any(btn.callback_data == "feedback_prompt_info" for row in ans_kb.inline_keyboard for btn in row)


@pytest.mark.asyncio
async def test_cb_feedback_prompt_info_responds_friendly():
    """cb_feedback_prompt_info sends guidance for /feedback and /suggest."""
    cb = make_mock_callback(user_id=1001, data="feedback_prompt_info")
    cb.message.answer = AsyncMock()

    with patch("main.safe_callback_answer", new_callable=AsyncMock) as mock_ans:
        await cb_feedback_prompt_info(cb, board_id="b")

        mock_ans.assert_called_once()
        cb.message.answer.assert_called_once()
        assert "/feedback" in cb.message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_anon_displays_anon_id_and_action_buttons():
    """cmd_anon displays user anon ID, pseudonym, and quick navigation buttons."""
    msg = make_mock_message(user_id=7777, text="/anon")

    mock_db = AsyncMock()
    with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
         patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=12345):

        await cmd_anon(msg, board_id="b", stream="ru")

        msg.answer.assert_called_once()
        ans_text = msg.answer.call_args[0][0]
        ans_kb = msg.answer.call_args[1].get("reply_markup")
        assert "ТВОЯ АНОНИМНАЯ ЛИЧНОСТЬ" in ans_text
        assert "Анон-ID:" in ans_text
        assert "12,345" in ans_text
        assert ans_kb is not None
        btn_callbacks = [btn.callback_data for row in ans_kb.inline_keyboard for btn in row]
        assert "prof_card:main" in btn_callbacks
        assert "wallet_view" in btn_callbacks
        assert "work_main_hub" in btn_callbacks


@pytest.mark.asyncio
async def test_cmd_wallet_dm_graceful():
    """cmd_wallet (/balance) called in DM (board_id=None) responds with wallet banner card."""
    msg = make_mock_message(user_id=8888, text="/balance")
    mock_db = MockDB(fetchone_val=(5000.0, 1, 0))

    bot_user = MagicMock()
    bot_user.username = "dvach_test_bot"
    msg.bot.get_me = AsyncMock(return_value=bot_user)

    with patch("main.get_pool", new_callable=AsyncMock, return_value=mock_db), \
         patch("main.db_transaction", side_effect=_mock_db_tx), \
         patch("main._get_user_active_items", new_callable=AsyncMock, return_value={}), \
         patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:

        await cmd_wallet(msg, board_id=None, stream="ru")

        mock_banner.assert_called_once()
        caption = mock_banner.call_args[1]["caption"]
        reply_kb = mock_banner.call_args[1]["reply_markup"]
        assert "КОШЕЛЕК И БАЛАНС" in caption
        assert "5,000 ₪" in caption
        assert reply_kb is not None
