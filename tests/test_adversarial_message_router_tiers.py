# -*- coding: utf-8 -*-
"""
tests/test_adversarial_message_router_tiers.py
=============================================
Empirical Adversarial Stress Test Suite for:
1. Database resolution tiers (direct post_num, channel_message_id, PostCopies.message_id, non-existent, conflicts).
2. Message router integration across message types (text, photo, media group, forward quotes).
3. Clean text extraction (multiline, single-link fallback, mixed prefixes/suffixes, query/fragment consumption).
4. Boundary stress, ReDoS safety, and high-concurrency connection resilience.

Written by Challenger 2.
"""

import asyncio
import json
import re
import time
from unittest import mock

import pytest
from aiogram import types, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import common.database
import common.db_pool
from common.text_utils import sanitize_html
from handlers.message_router import (
    RE_ARCHIVE_LINK,
    resolve_archive_or_inline_reply,
    handle_message,
    handle_media_group_init,
)
import shared_state


# ---------------------------------------------------------------------------
# Helper Seed Functions
# ---------------------------------------------------------------------------

async def _seed_post(db, post_num: int, board_id: str = "b", author_id: int = 1001, channel_message_id: int | None = None, text: str = "Seed"):
    content = json.dumps({"type": "text", "text": text})
    now = time.time()
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp, channel_message_id) VALUES (?, ?, ?, ?, ?, ?)",
        (post_num, board_id, author_id, content, now, channel_message_id)
    )


async def _seed_post_copy(db, post_num: int, recipient_id: int = 2002, message_id: int = 70001):
    await db.execute(
        "INSERT INTO PostCopies (post_num, recipient_id, message_id) VALUES (?, ?, ?)",
        (post_num, recipient_id, message_id)
    )


def make_mock_message(
    user_id: int = 10001,
    chat_id: int = -100123,
    content_type: str = "text",
    text: str | None = None,
    caption: str | None = None,
    media_group_id: str | None = None,
    with_reply: bool = False,
    reply_msg_id: int = 555,
    is_bot: bool = False,
):
    msg = mock.MagicMock(spec=types.Message)
    msg.message_id = 9999
    msg.content_type = content_type
    msg.media_group_id = media_group_id
    msg.date = mock.MagicMock()

    user = mock.MagicMock(spec=types.User)
    user.id = user_id
    user.is_bot = is_bot
    user.username = f"user_{user_id}"
    user.first_name = f"Anon_{user_id}"
    msg.from_user = user

    chat = mock.MagicMock(spec=types.Chat)
    chat.id = chat_id
    msg.chat = chat

    msg.text = text
    msg.caption = caption
    msg.html_text = text
    msg.caption_html_text = caption

    if content_type == "photo":
        photo_size = mock.MagicMock(spec=types.PhotoSize)
        photo_size.file_id = "test_photo_file_id_123"
        photo_size.file_unique_id = "test_photo_uid_123"
        msg.photo = [photo_size]
    elif content_type in ["video", "animation", "document", "audio", "voice"]:
        media_obj = mock.MagicMock()
        media_obj.file_id = f"test_{content_type}_file_id_123"
        media_obj.file_unique_id = f"test_{content_type}_uid_123"
        setattr(msg, content_type, media_obj)

    if with_reply:
        reply_msg = mock.MagicMock(spec=types.Message)
        reply_msg.message_id = reply_msg_id
        reply_msg.chat = chat
        reply_msg.from_user = mock.MagicMock(spec=types.User)
        reply_msg.from_user.id = 88888
        reply_msg.from_user.is_bot = False
        reply_msg.text = None
        reply_msg.caption = None
        msg.reply_to_message = reply_msg
    else:
        msg.reply_to_message = None

    msg.delete = mock.AsyncMock()
    msg.answer = mock.AsyncMock()

    mock_bot = mock.MagicMock(spec=Bot)
    mock_bot.id = 999999999
    mock_bot.send_message = mock.AsyncMock()
    msg.bot = mock_bot

    return msg


# ===========================================================================
# 1. DATABASE RESOLUTION TIERS (Adversarial Probes)
# ===========================================================================

@pytest.mark.asyncio
async def test_db_resolution_tier_1_direct_post_num(isolated_test_db):
    """Tier 1: Direct post_num lookup in Posts."""
    db = isolated_test_db
    await _seed_post(db, post_num=601001, channel_message_id=None)

    # Resolve via tgchan_archive URL
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/601001\nDirect post_num tier 1")
    assert pnum == 601001
    assert cleaned == "Direct post_num tier 1"

    # Resolve via direct board URL
    pnum2, cleaned2 = await resolve_archive_or_inline_reply("https://tgach.top/b/res/601001.html#601001")
    assert pnum2 == 601001
    assert cleaned2 == ">>601001"

    # Resolve via citation
    pnum3, cleaned3 = await resolve_archive_or_inline_reply(">>601001")
    assert pnum3 == 601001
    assert cleaned3 == ">>601001"


@pytest.mark.asyncio
async def test_db_resolution_tier_2_channel_message_id(isolated_test_db):
    """Tier 2: Lookup by Posts.channel_message_id when direct post_num does not match."""
    db = isolated_test_db
    # Post with post_num=602001, published to archive channel with channel_message_id=90001
    await _seed_post(db, post_num=602001, channel_message_id=90001)

    # Link referencing the channel_message_id 90001
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/90001\nArchive channel link")
    assert pnum == 602001
    assert cleaned == "Archive channel link"

    # With query parameter
    pnum2, cleaned2 = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/90001?single")
    assert pnum2 == 602001
    assert cleaned2 == ">>602001"


@pytest.mark.asyncio
async def test_db_resolution_tier_3_postcopies_message_id(isolated_test_db):
    """Tier 3: Lookup by PostCopies.message_id when neither post_num nor channel_message_id match."""
    db = isolated_test_db
    # Post with post_num=603001, copied to user with message_id=80001
    await _seed_post(db, post_num=603001, channel_message_id=None)
    await _seed_post_copy(db, post_num=603001, recipient_id=3003, message_id=80001)

    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/c/1234567890/80001\nPost copy link")
    assert pnum == 603001
    assert cleaned == "Post copy link"


@pytest.mark.asyncio
async def test_db_resolution_tier_priority_and_precedence(isolated_test_db):
    """
    Verify precedence order:
    Tier 1 (direct post_num) > Tier 2 (channel_message_id) > Tier 3 (PostCopies).
    """
    db = isolated_test_db

    # Post 1: post_num=70001, channel_message_id=70002
    await _seed_post(db, post_num=70001, channel_message_id=70002)
    # Post 2: post_num=70002, channel_message_id=None
    await _seed_post(db, post_num=70002, channel_message_id=None)

    # When querying 70002, Tier 1 check for post_num=70002 must match Post 2 (post_num 70002),
    # NOT Post 1 (which has channel_message_id=70002).
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/70002\nPrecedence test")
    assert pnum == 70002
    assert cleaned == "Precedence test"

    # Post 3: post_num=70003, channel_message_id=70005
    await _seed_post(db, post_num=70003, channel_message_id=70005)
    # Post 4: post_num=70004, copy with message_id=70005
    await _seed_post(db, post_num=70004, channel_message_id=None)
    await _seed_post_copy(db, post_num=70004, recipient_id=3003, message_id=70005)

    # When querying 70005 (neither post_num 70005 exists), Tier 2 (channel_message_id=70005 -> 70003)
    # takes precedence over Tier 3 (PostCopies message_id=70005 -> 70004).
    pnum2, cleaned2 = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/70005\nPrecedence tier 2 vs 3")
    assert pnum2 == 70003
    assert cleaned2 == "Precedence tier 2 vs 3"


@pytest.mark.asyncio
async def test_db_resolution_non_existent_and_corrupt_ids(isolated_test_db):
    """Probes non-existent post IDs, boundary values, and DB error handling."""
    db = isolated_test_db

    # Non-existent ID
    raw_text = "https://t.me/tgchan_archive/99999999\nNon-existent post"
    pnum, cleaned = await resolve_archive_or_inline_reply(raw_text)
    assert pnum is None
    assert cleaned == raw_text

    # Extremely large 64-bit integer
    large_text = "https://t.me/tgchan_archive/9223372036854775800\nLarge ID"
    pnum, cleaned = await resolve_archive_or_inline_reply(large_text)
    assert pnum is None
    assert cleaned == large_text

    # Negative or non-numeric strings
    neg_text = ">>-500\nNegative"
    pnum, cleaned = await resolve_archive_or_inline_reply(neg_text)
    assert pnum is None
    assert cleaned == neg_text

    # DB exception simulation: ensure function catches and safely returns (None, text)
    with mock.patch("handlers.message_router.get_post_by_num", side_effect=Exception("Simulated SQLite Error")):
        pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/12345\nDB error")
        assert pnum is None
        assert cleaned == "https://t.me/tgchan_archive/12345\nDB error"


# ===========================================================================
# 2. MESSAGE ROUTING INTEGRATION & MEDIA HANDLING
# ===========================================================================

@pytest.mark.asyncio
async def test_message_router_single_text_post_integration(isolated_test_db):
    """Verifies handle_message correctly extracts archive reply from text message."""
    db = isolated_test_db
    await _seed_post(db, post_num=604001, text="Target text post")

    msg = make_mock_message(
        user_id=12345,
        content_type="text",
        text="https://t.me/tgchan_archive/604001?single\nТекстовый ответ на пост",
    )

    with mock.patch("handlers.message_router.process_new_post", new_callable=mock.AsyncMock) as mock_pnp, \
         mock.patch("handlers.message_router.check_spam", new_callable=mock.AsyncMock, return_value=True):
        
        shared_state.board_data.setdefault("b", {
            "users": {"active": set(), "banned": set()},
            "mutes": {},
            "single_photo_counter": {12345: 0},
            "last_activity": {},
            "user_settings": {},
        })

        await handle_message(msg, board_id="b")

        assert mock_pnp.called
        call_params = mock_pnp.call_args[0][0]
        assert call_params.reply_to_post == 604001
        assert "tgchan_archive" not in call_params.content.get("text", "")
        assert "?single" not in call_params.content.get("text", "")
        assert "Текстовый ответ на пост" in call_params.content.get("text", "")


@pytest.mark.asyncio
async def test_message_router_photo_caption_integration(isolated_test_db):
    """Verifies handle_message correctly extracts archive reply from photo caption."""
    db = isolated_test_db
    await _seed_post(db, post_num=604002, text="Target photo post")

    msg = make_mock_message(
        user_id=12345,
        content_type="photo",
        text=None,
        caption="https://tgach.top/b/res/604002.html#post-604002\nПодпись к прикрепленному фото",
    )

    with mock.patch("handlers.message_router.process_new_post", new_callable=mock.AsyncMock) as mock_pnp, \
         mock.patch("handlers.message_router.check_spam", new_callable=mock.AsyncMock, return_value=True):

        shared_state.board_data.setdefault("b", {
            "users": {"active": set(), "banned": set()},
            "mutes": {},
            "single_photo_counter": {12345: 0},
            "last_activity": {},
            "user_settings": {},
        })

        await handle_message(msg, board_id="b")

        assert mock_pnp.called
        call_params = mock_pnp.call_args[0][0]
        assert call_params.reply_to_post == 604002
        assert call_params.content.get("type") == "photo"
        assert "tgach.top" not in call_params.content.get("caption", "")
        assert "Подпись к прикрепленному фото" in call_params.content.get("caption", "")


@pytest.mark.asyncio
async def test_message_router_media_group_integration(isolated_test_db):
    """Verifies handle_media_group_init extracts archive reply from album caption."""
    db = isolated_test_db
    await _seed_post(db, post_num=604003, text="Target album post")

    mg_id = "1357924680"
    msg = make_mock_message(
        user_id=12345,
        content_type="photo",
        media_group_id=mg_id,
        text=None,
        caption="https://t.me/tgchan_archive/604003?comment=100\nАльбомная подпись",
    )

    shared_state.board_data.setdefault("b", {
        "users": {"active": set(), "banned": set()},
        "mutes": {},
        "single_photo_counter": {12345: 0},
        "last_activity": {},
        "user_settings": {},
    })

    with mock.patch("handlers.message_router.check_spam", new_callable=mock.AsyncMock, return_value=True), \
         mock.patch("handlers.message_router.complete_media_group_after_delay", new_callable=mock.AsyncMock):

        await handle_media_group_init(msg, board_id="b")

        mg_key = shared_state._media_group_state_key(msg.chat.id, mg_id)
        group = shared_state.current_media_groups.get(mg_key)
        assert group is not None
        assert group.get("reply_to_post") == 604003
        assert "tgchan_archive" not in group.get("caption", "")
        assert "?comment=100" not in group.get("caption", "")
        assert "Альбомная подпись" in group.get("caption", "")


@pytest.mark.asyncio
async def test_message_router_external_link_negative_preservation(isolated_test_db):
    """Verifies external Telegram URLs are NOT intercepted and remain untouched."""
    db = isolated_test_db
    # Seed post 604004 to ensure it is not matched by an external link containing 604004
    await _seed_post(db, post_num=604004, text="Seeded post")

    external_texts = [
        "https://t.me/durov/604004\nИнтересный канал Дурова",
        "https://t.me/telegram/123?single\nОфициальный канал",
        "https://t.me/random_group/456\nСторонний чат",
        "https://t.me/tgchan_archive_fake/604004\nФейковый канал архива",
    ]

    for ext_text in external_texts:
        msg = make_mock_message(
            user_id=12345,
            content_type="text",
            text=ext_text,
        )

        with mock.patch("handlers.message_router.process_new_post", new_callable=mock.AsyncMock) as mock_pnp, \
             mock.patch("handlers.message_router.check_spam", new_callable=mock.AsyncMock, return_value=True):

            shared_state.board_data.setdefault("b", {
                "users": {"active": set(), "banned": set()},
                "mutes": {},
                "single_photo_counter": {12345: 0},
                "last_activity": {},
                "user_settings": {},
            })

            await handle_message(msg, board_id="b")

            assert mock_pnp.called
            call_params = mock_pnp.call_args[0][0]
            assert call_params.reply_to_post is None
            assert call_params.content.get("text") == ext_text


@pytest.mark.asyncio
async def test_message_router_telegram_native_reply_precedence(isolated_test_db):
    """
    If message is a native Telegram reply to a known post, the native reply takes precedence
    over any archive URL inside the message text (lines 867: if not reply_to_post and text_for_corpus).
    """
    db = isolated_test_db
    # Native replied post
    await _seed_post(db, post_num=604005, text="Native reply post")
    # Inline link post
    await _seed_post(db, post_num=604006, text="Inline link post")

    msg = make_mock_message(
        user_id=12345,
        content_type="text",
        text="https://t.me/tgchan_archive/604006\nТекст сообщения",
        with_reply=True,
        reply_msg_id=7777,
    )

    # Set native lookup in memory
    async with shared_state.storage_lock:
        shared_state.message_to_post[(msg.chat.id, 7777)] = 604005

    with mock.patch("handlers.message_router.process_new_post", new_callable=mock.AsyncMock) as mock_pnp, \
         mock.patch("handlers.message_router.check_spam", new_callable=mock.AsyncMock, return_value=True):

        shared_state.board_data.setdefault("b", {
            "users": {"active": set(), "banned": set()},
            "mutes": {},
            "single_photo_counter": {12345: 0},
            "last_activity": {},
            "user_settings": {},
        })

        await handle_message(msg, board_id="b")

        assert mock_pnp.called
        call_params = mock_pnp.call_args[0][0]
        # Native reply takes precedence
        assert call_params.reply_to_post == 604005


# ===========================================================================
# 3. CLEAN TEXT EXTRACTION & BOUNDARY EDGE CASES
# ===========================================================================

@pytest.mark.asyncio
async def test_clean_text_multiline_and_mixed_positions(isolated_test_db):
    """Tests multiline messages with archive links in various positions."""
    db = isolated_test_db
    await _seed_post(db, post_num=605001, text="Post for multiline")

    test_cases = [
        # Link at start
        (
            "https://t.me/tgchan_archive/605001?single\nСтрока 1\nСтрока 2\nСтрока 3",
            "Строка 1\nСтрока 2\nСтрока 3"
        ),
        # Link with leading spaces and CRLF
        (
            "   https://t.me/tgchan_archive/605001\r\nВторая строка\r\nТретья строка",
            "Вторая строка\r\nТретья строка"
        ),
        # Single link with trailing whitespace -> fallback
        (
            "https://t.me/tgchan_archive/605001?single   \n\n",
            ">>605001"
        ),
        # Anchored board URL with query and fragment
        (
            "https://tgach.top/b/res/605001.html?comment=42#post-605001\nОтвет по ссылке треда",
            "Ответ по ссылке треда"
        ),
        # Explicit citation with russian text
        (
            ">>605001\nСогласен с аноном выше!",
            "Согласен с аноном выше!"
        ),
    ]

    for raw_input, expected_cleaned in test_cases:
        pnum, cleaned = await resolve_archive_or_inline_reply(raw_input)
        assert pnum == 605001
        assert cleaned == expected_cleaned


@pytest.mark.asyncio
async def test_clean_text_html_entities_and_unicode(isolated_test_db):
    """Tests clean text handling of HTML entities, Cyrillic, and emojis."""
    db = isolated_test_db
    await _seed_post(db, post_num=605002, text="Post for unicode")

    input_text = "https://t.me/tgchan_archive/605002?single\n🦀 <b>Тест &lt;HTML&gt;</b> 🌟"
    pnum, cleaned = await resolve_archive_or_inline_reply(input_text)
    assert pnum == 605002
    assert cleaned == "🦀 <b>Тест &lt;HTML&gt;</b> 🌟"

    sanitized = sanitize_html(cleaned)
    assert "<b>Тест &lt;HTML&gt;</b>" in sanitized


# ===========================================================================
# 4. STRESS, CONCURRENCY & REDOS RESILIENCE
# ===========================================================================

@pytest.mark.asyncio
async def test_regex_redos_safety():
    """
    Stress-test RE_ARCHIVE_LINK against catastrophic backtracking patterns:
    - 50,000 character strings
    - Nested slashes, queries, fragments
    - Repetitive matching prefixes
    """
    # 1. 50,000 characters of leading whitespace and garbage
    evil_string_1 = " " * 10000 + "https://t.me/tgchan_archive/" + "9" * 1000 + "?" + "a=" * 5000
    start = time.perf_counter()
    match = RE_ARCHIVE_LINK.search(evil_string_1)
    duration = time.perf_counter() - start
    assert duration < 0.1, f"Regex evaluation too slow: {duration:.4f}s"

    # 2. Pathological query parameters
    evil_string_2 = "https://t.me/tgchan_archive/12345?" + "&".join([f"k{i}=v{i}" for i in range(2000)])
    start = time.perf_counter()
    match2 = RE_ARCHIVE_LINK.search(evil_string_2)
    duration2 = time.perf_counter() - start
    assert duration2 < 0.1, f"Regex query parsing too slow: {duration2:.4f}s"
    assert match2 is not None


@pytest.mark.asyncio
async def test_concurrent_resolution_burst_safety(isolated_test_db):
    """
    Execute 200 concurrent resolution requests probing all 3 tiers + non-existent IDs.
    Verifies DB connection pool integrity and absence of deadlocks / connection leaks.
    """
    db = isolated_test_db

    # Seed 20 test posts
    for i in range(1, 21):
        pnum = 606000 + i
        ch_id = 906000 + i if i % 2 == 0 else None
        await _seed_post(db, post_num=pnum, channel_message_id=ch_id)
        if i % 3 == 0:
            await _seed_post_copy(db, post_num=pnum, recipient_id=4004, message_id=806000 + i)

    async def worker(idx: int):
        target_i = (idx % 20) + 1
        tier_mode = idx % 4

        if tier_mode == 0:
            # Tier 1: direct
            target_pnum = 606000 + target_i
            url = f"https://t.me/tgchan_archive/{target_pnum}?single\nWorker {idx}"
            pnum, cleaned = await resolve_archive_or_inline_reply(url)
            assert pnum == target_pnum
            assert cleaned == f"Worker {idx}"
        elif tier_mode == 1 and target_i % 2 == 0:
            # Tier 2: channel_message_id
            ch_id = 906000 + target_i
            url = f"https://t.me/tgchan_archive/{ch_id}?single\nWorker {idx}"
            pnum, cleaned = await resolve_archive_or_inline_reply(url)
            assert pnum == 606000 + target_i
            assert cleaned == f"Worker {idx}"
        elif tier_mode == 2 and target_i % 3 == 0:
            # Tier 3: PostCopies
            copy_msg_id = 806000 + target_i
            url = f"https://t.me/c/1234567890/{copy_msg_id}\nWorker {idx}"
            pnum, cleaned = await resolve_archive_or_inline_reply(url)
            assert pnum == 606000 + target_i
            assert cleaned == f"Worker {idx}"
        else:
            # Non-existent
            url = f"https://t.me/tgchan_archive/9999999{idx}\nWorker {idx}"
            pnum, cleaned = await resolve_archive_or_inline_reply(url)
            assert pnum is None
            assert cleaned == url

    # Launch 200 concurrent tasks
    tasks = [worker(i) for i in range(200)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 0, f"Encountered {len(errors)} errors during concurrent resolution: {errors[:3]}"
