# -*- coding: utf-8 -*-
"""
Adversarial Security Test Suite:
Message Router, Post Processor & Moderation Mute Guards
"""
import re
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, UTC

from handlers.message_router import RE_ARCHIVE_LINK, resolve_archive_or_inline_reply
from post_processor import NewPostProcessor, NewPostContext, _BOARD_DISPATCH_LOCKS


# ===========================================================================
# 1. Message Router: RE_ARCHIVE_LINK and Hex Threads
# ===========================================================================
@pytest.mark.asyncio
async def test_re_archive_link_multiline_and_hex(isolated_test_db):
    db = isolated_test_db
    post_num = 770101
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        (post_num, "b", 1234, '{"type":"text","text":"Target OP Post"}', time.time())
    )
    await db.execute(
        "INSERT INTO Threads (thread_id, thread_num, board_id, op_id, title, created_at, last_updated_at, is_archived, stream) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
        ("a1b2c3d4", post_num, "b", post_num, "Hex Thread", time.time(), time.time(), "ru")
    )
    await db.commit()

    # 1.1 Multiline reply: citation on second line
    text_multiline = f"Здравствуйте!\n>>{post_num}\nОтличный тред."
    pnum, cleaned = await resolve_archive_or_inline_reply(text_multiline)
    assert pnum == post_num
    assert "Здравствуйте!" in cleaned
    assert "Отличный тред." in cleaned

    # 1.2 Hex thread URL with post fragment
    hex_url_with_fragment = f"https://tgach.top/b/res/a1b2c3d4.html#post-{post_num}\nМой ответ"
    pnum2, cleaned2 = await resolve_archive_or_inline_reply(hex_url_with_fragment)
    assert pnum2 == post_num
    assert cleaned2 == "Мой ответ"

    # 1.3 Hex thread URL without fragment (resolves thread OP)
    hex_url_no_fragment = "https://tgach.top/b/res/a1b2c3d4.html\nОтвет в шапку треда"
    pnum3, cleaned3 = await resolve_archive_or_inline_reply(hex_url_no_fragment)
    assert pnum3 == post_num
    assert cleaned3 == "Ответ в шапку треда"

    # 1.4 Tricky fake domain must NOT match
    fake_domain = f"https://faketgach.top/b/res/{post_num}.html"
    pnum4, cleaned4 = await resolve_archive_or_inline_reply(fake_domain)
    assert pnum4 is None
    assert cleaned4 == fake_domain


# ===========================================================================
# 2. Ghost Post Protection: Zero-Width Characters
# ===========================================================================
def test_zero_width_ghost_post_filter():
    re_zw = re.compile(r'[\u200b-\u200d\u2060\ufeff]')

    # Only zero-width characters and whitespace
    ghost_payload = "\u200b\u200c\u200d   \u2060\ufeff\n\t"
    cleaned = re_zw.sub('', ghost_payload).strip()
    assert len(cleaned) == 0, "Ghost payload with zero-width spaces must be reduced to empty string"

    # Legitimate message with accidental zero-width space
    legit_payload = "\u200bПривет, Анон!\u200c"
    cleaned_legit = re_zw.sub('', legit_payload).strip()
    assert cleaned_legit == "Привет, Анон!"


# ===========================================================================
# 3. Combat Commands: Mute Guards (/shoot, /partyvan, /rob)
# ===========================================================================
@pytest.mark.asyncio
async def test_cmd_shoot_mute_guard(isolated_test_db):
    from main import cmd_shoot
    from shared_state import board_data

    user_id = 900101
    board_id = "b"
    board_data.setdefault(board_id, {})

    # 1. Regular muted attacker
    board_data[board_id].setdefault('mutes', {})[user_id] = datetime.now(UTC) + timedelta(minutes=10)

    message = AsyncMock()
    message.from_user.id = user_id
    message.reply_to_message = MagicMock()
    message.reply_to_message.message_id = 555
    message.answer = AsyncMock()

    await cmd_shoot(message, board_id)
    message.answer.assert_called_once()
    assert "В муте стрелять запрещено" in message.answer.call_args[0][0]

    # Clean up regular mute
    board_data[board_id]['mutes'].pop(user_id, None)

    # 2. Shadow muted attacker
    board_data[board_id].setdefault('shadow_mutes', {})[user_id] = datetime.now(UTC) + timedelta(minutes=10)
    message.answer.reset_mock()

    await cmd_shoot(message, board_id)
    # Shadow muted attacker must be silently dropped without answering
    message.answer.assert_not_called()

    board_data[board_id]['shadow_mutes'].pop(user_id, None)


@pytest.mark.asyncio
async def test_cmd_partyvan_mute_guard(isolated_test_db):
    from main import cmd_partyvan
    from shared_state import board_data

    user_id = 900202
    board_id = "b"
    board_data.setdefault(board_id, {})

    # 1. Regular muted attacker
    board_data[board_id].setdefault('mutes', {})[user_id] = datetime.now(UTC) + timedelta(minutes=10)

    message = AsyncMock()
    message.from_user.id = user_id
    message.reply_to_message = MagicMock()
    message.reply_to_message.message_id = 555
    message.answer = AsyncMock()

    await cmd_partyvan(message, board_id)
    message.answer.assert_called_once()
    assert "В муте вызывать пативэн запрещено" in message.answer.call_args[0][0]

    board_data[board_id]['mutes'].pop(user_id, None)

    # 2. Shadow muted attacker
    board_data[board_id].setdefault('shadow_mutes', {})[user_id] = datetime.now(UTC) + timedelta(minutes=10)
    message.answer.reset_mock()

    await cmd_partyvan(message, board_id)
    message.answer.assert_not_called()

    board_data[board_id]['shadow_mutes'].pop(user_id, None)


@pytest.mark.asyncio
async def test_cmd_create_mute_guard(isolated_test_db):
    from main import cmd_create_fsm_entry, cb_create_thread_confirm
    from shared_state import board_data

    user_id = 900303
    board_id = "thread"
    board_data.setdefault(board_id, {})

    # 1. Regular muted user entering /create
    board_data[board_id].setdefault('mutes', {})[user_id] = datetime.now(UTC) + timedelta(minutes=10)

    message = AsyncMock()
    message.from_user.id = user_id
    message.text = "/create New Test Thread"
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    state = AsyncMock()

    await cmd_create_fsm_entry(message, state, board_id)
    message.answer.assert_called_once()
    assert "Вы замучены и не можете создавать треды" in message.answer.call_args[0][0]
    state.set_state.assert_not_called()

    # 2. Shadow muted user entering /create
    board_data[board_id]['mutes'].pop(user_id, None)
    board_data[board_id].setdefault('shadow_mutes', {})[user_id] = datetime.now(UTC) + timedelta(minutes=10)
    message.answer.reset_mock()

    await cmd_create_fsm_entry(message, state, board_id)
    message.answer.assert_not_called()
    state.set_state.assert_not_called()

    # 3. Confirming thread creation while muted
    callback = AsyncMock()
    callback.from_user.id = user_id
    callback.answer = AsyncMock()
    callback.message = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.message.delete = AsyncMock()

    await cb_create_thread_confirm(callback, state, board_id)
    state.clear.assert_called_once()

    board_data[board_id]['shadow_mutes'].pop(user_id, None)


# ===========================================================================
# 4. Post Processor: Referenced Thread ID on Retry
# ===========================================================================
@pytest.mark.asyncio
async def test_post_processor_db_retry_preserves_referenced_thread(isolated_test_db):
    bot = AsyncMock()
    ctx = NewPostContext(
        bot_instance=bot,
        board_id="b",
        user_id=777888,
        content={"type": "text", "text": "Retry preserving thread test"},
        reply_to_post=None,
        is_shadow_muted=False,
        stream="ru"
    )
    processor = NewPostProcessor(ctx)
    processor.referenced_thread_id = "target_thread_123"

    call_params = []
    real_create_post = None

    async def mock_create_post(**kwargs):
        call_params.append(kwargs)
        if len(call_params) == 1:
            return None  # First attempt fails to trigger retry loop
        return 999111  # Second attempt succeeds

    with patch("post_processor.create_post", side_effect=mock_create_post), \
         patch("asyncio.sleep", return_value=None):
        now_dt = datetime.now(UTC)
        success = await processor._create_post_record(now_dt)

    assert success is True
    assert len(call_params) == 2
    # First attempt preserved referenced_thread_id
    assert call_params[0]["thread_id_from_bot"] == "target_thread_123"
    # Second retry attempt MUST also preserve referenced_thread_id
    assert call_params[1]["thread_id_from_bot"] == "target_thread_123"


# ===========================================================================
# 5. Post Processor: Author Dispatch Outside Board Lock
# ===========================================================================
@pytest.mark.asyncio
async def test_author_dispatch_executed_outside_board_lock():
    bot = AsyncMock()
    ctx = NewPostContext(
        bot_instance=bot,
        board_id="b",
        user_id=555666,
        content={"type": "text", "text": "Dispatch lock benchmark"},
        reply_to_post=None,
        is_shadow_muted=False,
        stream="ru"
    )
    processor = NewPostProcessor(ctx)

    lock_was_held_during_author_send = None
    board_lock = _BOARD_DISPATCH_LOCKS["b"]

    async def mock_send_author():
        nonlocal lock_was_held_during_author_send
        lock_was_held_during_author_send = board_lock.locked()

    with patch.object(processor, "_determine_recipients_and_thread", return_value=True), \
         patch.object(processor, "_apply_content_transformations", return_value=None), \
         patch.object(processor, "_create_post_record", return_value=True), \
         patch.object(processor, "_format_and_update_headers", return_value=None), \
         patch.object(processor, "_save_to_memory", return_value=None), \
         patch.object(processor, "_send_to_author_with_fallback", side_effect=mock_send_author), \
         patch.object(processor, "_process_author_results", return_value=None), \
         patch.object(processor, "_enqueue_and_notify", return_value=None):
        processor.current_post_num = 888222
        res = await processor.execute()

    assert res == 888222
    assert lock_was_held_during_author_send is False, (
        "Telegram _send_to_author_with_fallback MUST be executed outside board_dispatch_lock!"
    )
