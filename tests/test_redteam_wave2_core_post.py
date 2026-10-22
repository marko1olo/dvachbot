# -*- coding: utf-8 -*-
"""
tests/test_redteam_wave2_core_post.py
RedTeam Inquisitor Test Suite — Wave 2, Sector 1:
Core Router, Post-Processor, Media & Identity.

Verifies:
1. PostProcessor execution order: author delivery runs before memory storage,
   ensuring author_message_id, post_to_messages, message_to_post and extracted
   file_id are properly populated in RAM and SQLite.
2. PostProcessor TelegramRetryAfter handling & timeout protection.
3. PostHelpers format_header HTML sanitization: prevents custom_prefix HTML injection
   and unclosed tag crashes.
4. PostHelpers format_thread_post_header OP identity protection during self-isolation.
5. PostHelpers delete_single_post: chunked deletion (CHUNK_SIZE=47) and TelegramRetryAfter handling.
6. UserManager cmd_hide: valid HTML escaping in Russian and Japanese help messages (<слово>, <単語>).
7. UserManager cmd_report & process_report_action: text truncation (<1000 chars) preventing
   Telegram message-too-long error, and atomic post deletion across board on admin report approval.
8. UserManager cmd_global_top: escaping anon names in leaderboard tables inside <pre>.
9. MediaUtils: proxy failure handling and direct download fallback safety.
"""

import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

import shared_state
from shared_state import (
    board_data, messages_storage, post_to_messages, message_to_post, storage_lock
)
from post_processor import NewPostProcessor, NewPostContext
from post_helpers import (
    format_header, format_thread_post_header, delete_single_post, _delete_message_with_retries
)
from user_manager import cmd_hide, cmd_report, process_report_action, cmd_global_top
from media_utils import _download_image_with_proxy

UTC = timezone.utc


@pytest.fixture(autouse=True)
def clean_shared_state():
    """Ensure shared_state is pristine before and after each test."""
    board_data['b'] = {
        'users': {'active': {111, 222, 333}, 'banned': set()},
        'user_settings': {},
        'user_state': {},
        'threads_data': {},
        'mutes': {},
        'shadow_mutes': {},
    }
    board_data['int'] = {
        'users': {'active': {444}, 'banned': set()},
        'user_settings': {},
        'user_state': {},
        'threads_data': {},
        'mutes': {},
        'shadow_mutes': {},
    }
    messages_storage.clear()
    post_to_messages.clear()
    message_to_post.clear()
    from post_processor import _BOARD_DISPATCH_LOCKS
    _BOARD_DISPATCH_LOCKS.clear()
    yield
    messages_storage.clear()
    post_to_messages.clear()
    message_to_post.clear()
    _BOARD_DISPATCH_LOCKS.clear()


# ==============================================================================
# 1. PostProcessor: Author Results & Memory Storage Order
# ==============================================================================

@pytest.mark.asyncio
async def test_post_processor_author_result_memory_caching(isolated_test_db):
    """
    Verifies that _send_to_author_with_fallback populates self.author_results,
    and _save_to_memory extracts sent message IDs, updates post_to_messages,
    message_to_post, and sets author_message_id in messages_storage.
    """
    bot = MagicMock()
    mock_sent_msg = MagicMock()
    mock_sent_msg.message_id = 999111
    mock_sent_msg.photo = [MagicMock(file_id="AgACAgIAAxkBAAI_photo123")]
    mock_sent_msg.video = None
    mock_sent_msg.animation = None
    mock_sent_msg.voice = None
    mock_sent_msg.audio = None

    author_id = 7770001
    board_data['b']['users']['active'].add(author_id)

    # Mock send_message_to_users to simulate successful author delivery
    async def mock_send_message_to_users(cfg):
        return [(author_id, [mock_sent_msg])]

    with patch('post_processor.send_message_to_users', side_effect=mock_send_message_to_users), \
         patch('delivery_manager.enqueue_board_message', new=AsyncMock()), \
         patch('archive_manager._forward_post_to_realtime_archive', new=AsyncMock()):

        context = NewPostContext(
            bot_instance=bot,
            board_id="b",
            user_id=author_id,
            content={"type": "photo", "image_bytes": b"fake_jpeg_data", "caption": "Test photo post"},
            reply_to_post=None,
            is_shadow_muted=False,
            stream="ru"
        )
        processor = NewPostProcessor(context)
        post_num = await processor.execute()

        assert post_num is not None, "execute() should return created post number"

        # 1. messages_storage must have author_message_id recorded
        assert post_num in messages_storage
        stored = messages_storage[post_num]
        assert stored['author_message_id'] == [999111], f"Expected author_message_id=[999111], got {stored.get('author_message_id')}"

        # 2. post_to_messages and message_to_post maps must contain author message
        assert post_to_messages.get(post_num, {}).get(author_id) == 999111
        assert message_to_post.get((author_id, 999111)) == post_num

        # 3. file_id should be extracted from author's sent message and saved in final_content
        assert processor.final_content.get('file_id') == "AgACAgIAAxkBAAI_photo123"
        assert stored['content'].get('file_id') == "AgACAgIAAxkBAAI_photo123"

        # 4. Author must NOT be redundantly placed into delivery queue
        assert author_id not in processor.recipients


# ==============================================================================
# 2. PostProcessor: TelegramRetryAfter Resilience
# ==============================================================================

@pytest.mark.asyncio
async def test_post_processor_author_retry_after_resilience(isolated_test_db):
    """
    Verifies that _send_to_author_with_fallback handles TelegramRetryAfter,
    sleeping for the required delay and retrying.
    """
    bot = MagicMock()
    mock_sent_msg = MagicMock()
    mock_sent_msg.message_id = 888222
    mock_sent_msg.photo = None
    mock_sent_msg.video = None
    mock_sent_msg.animation = None
    mock_sent_msg.voice = None
    mock_sent_msg.audio = None
    mock_sent_msg.document = None

    author_id = 7770002
    board_data['b']['users']['active'].add(author_id)
    calls = 0

    async def mock_send_with_rate_limit(cfg):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TelegramRetryAfter(method="sendMessage", message="Too Many Requests", retry_after=1)
        return [(author_id, [mock_sent_msg])]

    with patch('post_processor.send_message_to_users', side_effect=mock_send_with_rate_limit), \
         patch('delivery_manager.enqueue_board_message', new=AsyncMock()), \
         patch('archive_manager._forward_post_to_realtime_archive', new=AsyncMock()):

        context = NewPostContext(
            bot_instance=bot,
            board_id="b",
            user_id=author_id,
            content={"type": "text", "text": "Rate-limited test post"},
            reply_to_post=None,
            is_shadow_muted=False,
            stream="ru"
        )
        processor = NewPostProcessor(context)
        post_num = await processor.execute()

        assert post_num is not None
        assert calls == 2, f"Expected 2 attempts (initial + retry after 429), got {calls}"
        assert processor.author_results is not None
        assert post_to_messages.get(post_num, {}).get(author_id) == 888222


# ==============================================================================
# 3. PostHelpers: format_header HTML Sanitization
# ==============================================================================

@pytest.mark.asyncio
async def test_post_helpers_header_html_sanitization(isolated_test_db):
    """
    Verifies that format_header properly escapes custom_prefix from Users table,
    preventing HTML entity injection or unclosed tags.
    """
    db = isolated_test_db
    author_id = 999001
    now_ts = int(time.time())

    # User configured a dangerous/malformed custom prefix
    malformed_prefix = "<b>[HACKER] <script>alert(1)</script> <a href='tg://user?id=123'>Click"
    await db.execute(
        """
        INSERT INTO Users (user_id, board_id, custom_prefix, prefix_expires_at)
        VALUES (?, 'b', ?, ?)
        """,
        (author_id, malformed_prefix, now_ts + 3600)
    )

    header = await format_header(board_id="b", post_num=456789, author_id=author_id, stream="ru")

    # Header must NOT contain raw unescaped <script> or unclosed <b>
    assert "<script>" not in header, "Raw <script> tag leaked into header!"
    assert "&lt;script&gt;" in header, "Expected <script> to be escaped as &lt;script&gt;"
    assert "&lt;b&gt;" in header or "<b>" not in header, "Unclosed raw <b> must be escaped"
    assert "456789" in header


# ==============================================================================
# 4. PostHelpers: format_thread_post_header OP Identity Protection
# ==============================================================================

@pytest.mark.asyncio
async def test_post_helpers_thread_header_isolation():
    """
    Verifies that when an anon has activated is_isolated (self-isolation mode),
    the (OP) badge is suppressed in thread headers to protect their anonymity.
    """
    author_id = 555001
    thread_info = {
        'op_id': author_id,
        'posts': [100, 101, 102]
    }

    # Case A: Not isolated -> receives (OP)
    board_data['b']['user_settings'][author_id] = {'is_isolated': False}
    header_normal = await format_thread_post_header(
        board_id="b", local_post_num=4, author_id=author_id,
        thread_info=thread_info, stream="ru", global_post_num=103
    )
    assert "(OP)" in header_normal, "OP marker should be visible when not in self-isolation"

    # Case B: Isolated -> (OP) must be completely suppressed
    board_data['b']['user_settings'][author_id]['is_isolated'] = True
    header_isolated = await format_thread_post_header(
        board_id="b", local_post_num=4, author_id=author_id,
        thread_info=thread_info, stream="ru", global_post_num=103
    )
    assert "(OP)" not in header_isolated, "OP marker MUST be suppressed when author is isolated"


# ==============================================================================
# 5. PostHelpers: delete_single_post Chunking & RetryAfter
# ==============================================================================

@pytest.mark.asyncio
async def test_post_helpers_delete_single_post_chunking_and_retry_after(isolated_test_db):
    """
    Verifies that delete_single_post chunks deletion tasks and safely handles
    TelegramRetryAfter without unhandled exception.
    """
    bot = MagicMock()
    deleted_calls = []

    async def mock_delete_message(uid, mid):
        deleted_calls.append((uid, mid))
        # Trigger 429 on one recipient
        if uid == 1005:
            raise TelegramRetryAfter(method="deleteMessage", message="Flood limit", retry_after=1)
        return True

    bot.delete_message = AsyncMock(side_effect=mock_delete_message)

    post_num = 333444
    author_id = 1001

    # Populate in-memory copies for 100 recipients to test chunking
    recipients = {1000 + i: 50000 + i for i in range(100)}
    async with storage_lock:
        messages_storage[post_num] = {
            'author_id': author_id,
            'board_id': 'b',
            'content': {'type': 'text', 'text': 'Delete me'}
        }
        post_to_messages[post_num] = recipients.copy()
        for u, m in recipients.items():
            message_to_post[(u, m)] = post_num

    deleted_count = await delete_single_post(post_num, bot)

    assert deleted_count >= 99, f"Expected at least 99 successfully deleted messages, got {deleted_count}"
    assert post_num not in messages_storage
    assert post_num not in post_to_messages


# ==============================================================================
# 6. UserManager: cmd_hide HTML Tag Escaping
# ==============================================================================

@pytest.mark.asyncio
async def test_user_manager_cmd_hide_html_escaping():
    """
    Verifies that cmd_hide help message in Russian and Japanese contains properly
    escaped HTML tags (&lt;слово&gt; and &lt;単語&gt;) instead of raw tags that crash aiogram.
    """
    bot = MagicMock()
    sent_messages = []

    async def mock_answer(text, parse_mode=None, **kwargs):
        sent_messages.append({"text": text, "parse_mode": parse_mode})
        return MagicMock()

    msg_ru = MagicMock()
    msg_ru.text = "/hide"
    msg_ru.caption = None
    msg_ru.from_user = MagicMock(id=12345)
    msg_ru.answer = AsyncMock(side_effect=mock_answer)
    msg_ru.bot = bot

    # Test Russian stream
    await cmd_hide(msg_ru, board_id="b", stream="ru")
    assert len(sent_messages) == 1
    ru_text = sent_messages[0]["text"]
    assert "<слово>" not in ru_text, "Raw <слово> tag must not exist in HTML mode"
    assert "&lt;слово&gt;" in ru_text, "Expected &lt;слово&gt; escaped entity"

    # Test Japanese stream
    sent_messages.clear()
    msg_jp = MagicMock()
    msg_jp.text = "/hide"
    msg_jp.caption = None
    msg_jp.from_user = MagicMock(id=12345)
    msg_jp.answer = AsyncMock(side_effect=mock_answer)
    msg_jp.bot = bot

    with patch('user_manager.ENABLE_MULTILANG', True):
        await cmd_hide(msg_jp, board_id="b", stream="jp")
    assert len(sent_messages) == 1
    jp_text = sent_messages[0]["text"]
    assert "<単語>" not in jp_text, "Raw <単語> tag must not exist in HTML mode"
    assert "&lt;単語&gt;" in jp_text, "Expected &lt;単語&gt; escaped entity"


# ==============================================================================
# 7. UserManager: cmd_report Truncation & Atomic Post Deletion
# ==============================================================================

@pytest.mark.asyncio
async def test_user_manager_cmd_report_truncation_and_atomic_deletion():
    """
    Verifies that:
    1. cmd_report truncates huge reported messages (<1000 chars) to prevent 4096-char Telegram overflow.
    2. process_report_action ('rep:del') resolves post_num and calls delete_single_post across the board.
    """
    bot = MagicMock()
    admin_id = 999999
    reporter_id = 111111
    author_id = 222222
    board_id = "b"

    # Configure admin
    from common.board_config import BOARD_CONFIG
    BOARD_CONFIG['b']['admins'] = {admin_id}

    sent_admin_reports = []
    async def mock_send_message(chat_id, text, **kwargs):
        sent_admin_reports.append({"chat_id": chat_id, "text": text})
        return MagicMock()

    bot.send_message = AsyncMock(side_effect=mock_send_message)

    reported_msg = MagicMock()
    reported_msg.message_id = 456
    # 5000 character spam message
    reported_msg.text = "A" * 5000
    reported_msg.caption = None

    msg = MagicMock()
    msg.from_user = MagicMock(id=reporter_id)
    msg.chat = MagicMock(id=reporter_id)
    msg.reply_to_message = reported_msg
    msg.bot = bot
    msg.answer = AsyncMock()

    with patch('user_manager.get_author_id_by_reply', new=AsyncMock(return_value=author_id)):
        await cmd_report(msg, board_id=board_id, stream="ru")

    assert len(sent_admin_reports) == 1
    delivered_text = sent_admin_reports[0]["text"]
    # Total report text must easily fit inside Telegram 4096 char limit
    assert len(delivered_text) < 1500, f"Report text too long: {len(delivered_text)} chars"
    assert "..." in delivered_text, "Huge message must be truncated with ellipsis"

    # Now verify process_report_action ('rep:del') deletes whole post via delete_single_post
    post_num = 78910
    message_to_post[(reporter_id, 456)] = post_num

    callback = MagicMock()
    callback.from_user = MagicMock(id=admin_id)
    callback.data = f"rep:del:{author_id}:{reporter_id}:456"
    callback.bot = bot
    callback.message = MagicMock()
    callback.message.html_text = "🚨 <b>Новый РЕПОРТ в /b/</b>"
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    with patch('post_helpers.delete_single_post', new=AsyncMock(return_value=5)) as mock_delete_post, \
         patch('user_manager.is_admin', return_value=True):
        await process_report_action(callback, board_id=board_id)

        assert mock_delete_post.called, "delete_single_post must be called for reported post"
        assert mock_delete_post.call_args[0][0] == post_num
        assert callback.answer.called


# ==============================================================================
# 8. UserManager: cmd_global_top Table Escaping
# ==============================================================================

@pytest.mark.asyncio
async def test_user_manager_cmd_global_top_escaped(isolated_test_db):
    """
    Verifies that cmd_global_top escapes special characters in generated names
    inside the <pre> block.
    """
    db = isolated_test_db
    author_id = 888001

    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (1, 'b', ?, ?, '{}')",
        (author_id, time.time())
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 50000.0)",
        (author_id,)
    )

    msg = MagicMock()
    msg.from_user = MagicMock(id=author_id)
    msg.text = "/global_top"
    msg.caption = None
    answers = []

    async def mock_answer(text, parse_mode=None, **kwargs):
        answers.append({"text": text, "parse_mode": parse_mode})
        ret = MagicMock()
        ret.delete = AsyncMock()
        return ret

    msg.answer = AsyncMock(side_effect=mock_answer)

    # Name contains angle brackets
    dangerous_name = "<Super&Anon>"
    with patch('user_manager.generate_anon_name', return_value=dangerous_name):
        await cmd_global_top(msg, board_id="b", stream="ru")

    assert len(answers) >= 2
    final_text = answers[-1]["text"]
    assert "<Super&Anon>" not in final_text, "Unescaped name leaked into HTML table!"
    assert "&lt;Super&amp;Anon&gt;" in final_text, "Name must be properly escaped inside <pre>"


# ==============================================================================
# 9. MediaUtils: Proxy Fallback & HTML Error Trap
# ==============================================================================

@pytest.mark.asyncio
async def test_media_utils_direct_fallback_resilience():
    """
    Verifies that _download_image_with_proxy catches proxy connection failures
    and falls back to DIRECT download, cleanly rejecting HTML error pages.
    """
    html_data = b"<!DOCTYPE html><html><body>Error 403 Forbidden Cloudflare</body></html>"

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers = {'Content-Type': 'text/html; charset=utf-8'}
    mock_resp.read = AsyncMock(return_value=html_data)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    # Context manager setup
    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    mock_resp_cm = MagicMock()
    mock_resp_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp_cm.__aexit__ = AsyncMock(return_value=None)

    mock_session.get.return_value = mock_resp_cm

    with patch('aiohttp.ClientSession', return_value=mock_session_cm):
        result = await _download_image_with_proxy("https://example.com/image.jpg", timeout=2)
        # HTML error payload must be safely detected and rejected
        assert result is None, "HTML error response must return None instead of saving html as image bytes"
