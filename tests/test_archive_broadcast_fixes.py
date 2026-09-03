# -*- coding: utf-8 -*-
import asyncio
import json
import time
import pytest
import aiosqlite
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import Bot
from aiogram.types import Message, PhotoSize, FSInputFile
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

import shared_state
from shared_state import storage_lock, messages_storage, post_to_messages, state
import archive_manager
from archive_manager import (
    _forward_post_to_realtime_archive,
    _send_archive_media,
    _send_archive_single_media,
    _send_archive_media_group,
    post_archive_to_channel,
    post_special_num_to_channel,
    _BOT_INACCESSIBLE_CHANNELS,
    _INACCESSIBLE_CHANNELS,
)
import post_processor
from post_processor import post_thread_notification_to_channel, process_new_post
import delivery_manager
from delivery_manager import MessageDeliveryTask


def _make_mock_message(message_id: int = 100, text: str = "test", photo_fid: str | None = None):
    msg = MagicMock(spec=Message)
    msg.message_id = message_id
    msg.text = text
    if photo_fid:
        photo = MagicMock(spec=PhotoSize)
        photo.file_id = photo_fid
        msg.photo = [photo]
        msg.video = None
        msg.document = None
        msg.audio = None
        msg.animation = None
        msg.voice = None
        msg.content_type = "photo"
    else:
        msg.photo = None
        msg.video = None
        msg.document = None
        msg.audio = None
        msg.animation = None
        msg.voice = None
        msg.content_type = "text"
    return msg


def _make_mock_bot(bot_id: int, username: str = "testbot"):
    bot = AsyncMock(spec=Bot)
    bot.id = bot_id
    bot.token = f"token_{bot_id}"
    bot.send_message = AsyncMock(return_value=_make_mock_message(message_id=100 + bot_id))
    bot.send_photo = AsyncMock(return_value=_make_mock_message(message_id=200 + bot_id, photo_fid=f"photo_{bot_id}"))
    bot.send_video = AsyncMock(return_value=_make_mock_message(message_id=300 + bot_id))
    bot.send_document = AsyncMock(return_value=_make_mock_message(message_id=400 + bot_id))
    bot.send_audio = AsyncMock(return_value=_make_mock_message(message_id=500 + bot_id))
    bot.send_animation = AsyncMock(return_value=_make_mock_message(message_id=600 + bot_id))
    bot.send_voice = AsyncMock(return_value=_make_mock_message(message_id=700 + bot_id))
    bot.send_sticker = AsyncMock(return_value=_make_mock_message(message_id=800 + bot_id))
    bot.send_video_note = AsyncMock(return_value=_make_mock_message(message_id=900 + bot_id))
    bot.send_media_group = AsyncMock(return_value=[_make_mock_message(message_id=1000 + bot_id, photo_fid=f"p_{bot_id}")])
    async def _mock_download(file, destination=None, **kwargs):
        if destination and hasattr(destination, 'write'):
            destination.write(b"mock_file_bytes")
        return b"mock_file_bytes"
    bot.download = AsyncMock(side_effect=_mock_download)
    return bot


@pytest.fixture(autouse=True)
def clean_archive_state():
    _BOT_INACCESSIBLE_CHANNELS.clear()
    _INACCESSIBLE_CHANNELS.clear()
    yield
    _BOT_INACCESSIBLE_CHANNELS.clear()
    _INACCESSIBLE_CHANNELS.clear()


# =========================================================================
# 1. Multi-Bot Authorization Fallbacks & Channel Resilience
# =========================================================================

@pytest.mark.asyncio
async def test_realtime_archive_bot_fallback_on_forbidden(isolated_test_db):
    """
    Test that when Bot 1 receives 403 Forbidden / Not a member,
    _forward_post_to_realtime_archive does NOT disable the channel globally,
    and successfully falls back to Bot 2.
    """
    db = isolated_test_db
    post_num = 9001
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 123, ?, ?)",
        (post_num, json.dumps({'type': 'text', 'text': 'Hello world'}), time.time())
    )

    bot1 = _make_mock_bot(1)
    bot2 = _make_mock_bot(2)

    # Bot 1 gets 403 Forbidden
    bot1.send_message.side_effect = TelegramForbiddenError(method=MagicMock(), message="Forbidden: bot is not a member")
    # Bot 2 succeeds
    bot2.send_message.return_value = _make_mock_message(message_id=777)

    target_channel = -100111222333
    with patch.object(archive_manager, 'MIRROR_CHANNELS', [target_channel]), \
         patch.object(shared_state, 'MIRROR_CHANNELS', [target_channel]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot1, 'test': bot2}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot1, 'test': bot2}):

        await _forward_post_to_realtime_archive(
            bot_instance=bot1,
            board_id='b',
            post_num=post_num,
            content={'type': 'text', 'text': 'Hello world'},
            is_shadow_muted=False
        )

        # Bot 1 was tried and failed
        assert bot1.send_message.called
        # Bot 2 was tried and succeeded
        assert bot2.send_message.called

        # Bot 1 is recorded as inaccessible for target_channel
        assert (1, target_channel) in _BOT_INACCESSIBLE_CHANNELS
        # But target_channel itself is NOT globally disabled
        assert target_channel not in _INACCESSIBLE_CHANNELS

        # Verify ChannelCopies was written
        async with db.execute("SELECT channel_id, message_id FROM ChannelCopies WHERE post_num = ?", (post_num,)) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == target_channel
            assert row[1] == 777


@pytest.mark.asyncio
async def test_subsequent_post_uses_working_bot_without_retesting_forbidden_bot(isolated_test_db):
    """
    Test that after Bot 1 fails on a channel, subsequent posts skip Bot 1 for that channel
    and immediately succeed via Bot 2.
    """
    db = isolated_test_db
    bot1 = _make_mock_bot(1)
    bot2 = _make_mock_bot(2)
    bot1.send_message.side_effect = TelegramForbiddenError(method=MagicMock(), message="Forbidden")
    bot2.send_message.return_value = _make_mock_message(message_id=888)

    target_channel = -100444555666
    with patch.object(archive_manager, 'MIRROR_CHANNELS', [target_channel]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot1, 'test': bot2}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot1, 'test': bot2}):

        # Post 1: Bot 1 fails, Bot 2 succeeds
        p1 = 9002
        await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 123, '{}', ?)", (p1, time.time()))
        await _forward_post_to_realtime_archive(bot1, 'b', p1, {'type': 'text', 'text': 'Post 1'}, False)
        assert bot1.send_message.call_count == 1
        assert bot2.send_message.call_count == 1

        # Post 2: Bot 1 is skipped directly because (1, target_channel) is in _BOT_INACCESSIBLE_CHANNELS
        p2 = 9003
        await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 123, '{}', ?)", (p2, time.time()))
        await _forward_post_to_realtime_archive(bot1, 'b', p2, {'type': 'text', 'text': 'Post 2'}, False)
        assert bot1.send_message.call_count == 1  # Not called again!
        assert bot2.send_message.call_count == 2  # Bot 2 handled it directly


@pytest.mark.asyncio
async def test_multi_mirror_channels_all_receive_posts(isolated_test_db):
    """
    Test that posts are delivered to ALL configured channels in MIRROR_CHANNELS.
    Even if Bot 1 can access Channel A and Bot 2 can access Channel B.
    """
    db = isolated_test_db
    post_num = 9004
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 123, '{}', ?)", (post_num, time.time()))

    ch_a = -100111
    ch_b = -100222
    ch_c = -100333

    bot1 = _make_mock_bot(1)
    bot2 = _make_mock_bot(2)

    # Bot 1 has access to ch_a only, 403 on ch_b and ch_c
    async def bot1_send(chat_id, *args, **kwargs):
        if chat_id == ch_a:
            return _make_mock_message(101)
        raise TelegramForbiddenError(method=MagicMock(), message="Forbidden: not in channel")
    bot1.send_message.side_effect = bot1_send

    # Bot 2 has access to ch_b and ch_c
    async def bot2_send(chat_id, *args, **kwargs):
        if chat_id in (ch_b, ch_c):
            return _make_mock_message(102)
        raise TelegramForbiddenError(method=MagicMock(), message="Forbidden: not in channel")
    bot2.send_message.side_effect = bot2_send

    with patch.object(archive_manager, 'MIRROR_CHANNELS', [ch_a, ch_b, ch_c]), \
         patch.object(shared_state, 'MIRROR_CHANNELS', [ch_a, ch_b, ch_c]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot1, 'test': bot2}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot1, 'test': bot2}):

        await _forward_post_to_realtime_archive(bot1, 'b', post_num, {'type': 'text', 'text': 'Multi-mirror test'}, False)

        # Verify all 3 channels got copies in the database
        async with db.execute("SELECT channel_id, message_id FROM ChannelCopies WHERE post_num = ?", (post_num,)) as cur:
            rows = await cur.fetchall()
            saved_channels = {r[0]: r[1] for r in rows}
            assert ch_a in saved_channels
            assert ch_b in saved_channels
            assert ch_c in saved_channels


# =========================================================================
# 2. Content Type Archiving & Fallback Verification
# =========================================================================

@pytest.mark.asyncio
async def test_archive_photo_post(isolated_test_db):
    """Verify single photo post archiving."""
    db = isolated_test_db
    post_num = 9010
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 123, '{}', ?)", (post_num, time.time()))

    bot = _make_mock_bot(1)
    ch = -100555
    content = {'type': 'photo', 'file_id': 'AgACAgIAAxkBAAI123', 'caption': 'Look at this photo'}

    with patch.object(archive_manager, 'MIRROR_CHANNELS', [ch]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot}):

        await _forward_post_to_realtime_archive(bot, 'b', post_num, content, False)
        assert bot.send_photo.called
        assert (bot.send_photo.call_args[1].get('chat_id') == ch) or (len(bot.send_photo.call_args[0]) > 0 and bot.send_photo.call_args[0][0] == ch)


@pytest.mark.asyncio
async def test_archive_video_and_document(isolated_test_db):
    """Verify video and document post archiving."""
    db = isolated_test_db
    bot = _make_mock_bot(1)
    ch = -100555

    with patch.object(archive_manager, 'MIRROR_CHANNELS', [ch]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot}):

        # Video
        p_vid = 9011
        await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 123, '{}', ?)", (p_vid, time.time()))
        await _forward_post_to_realtime_archive(bot, 'b', p_vid, {'type': 'video', 'file_id': 'BAACAgI123', 'caption': 'Cool video'}, False)
        assert bot.send_video.called

        # Document
        p_doc = 9012
        await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 123, '{}', ?)", (p_doc, time.time()))
        await _forward_post_to_realtime_archive(bot, 'b', p_doc, {'type': 'document', 'file_id': 'BQACAgI456', 'caption': 'Doc file'}, False)
        assert bot.send_document.called


@pytest.mark.asyncio
async def test_archive_media_group(isolated_test_db):
    """Verify media group (album) archiving."""
    db = isolated_test_db
    post_num = 9013
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 123, '{}', ?)", (post_num, time.time()))

    bot = _make_mock_bot(1)
    ch = -100555
    content = {
        'type': 'media_group',
        'media': [
            {'type': 'photo', 'file_id': 'fid_photo_1'},
            {'type': 'photo', 'file_id': 'fid_photo_2'}
        ],
        'caption': 'Album of 2 photos'
    }

    with patch.object(archive_manager, 'MIRROR_CHANNELS', [ch]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot}):

        await _forward_post_to_realtime_archive(bot, 'b', post_num, content, False)
        assert bot.send_media_group.called


@pytest.mark.asyncio
async def test_archive_missing_media_falls_back_to_text(isolated_test_db):
    """
    If a post is marked as photo/media but has no valid file_id or downloadable bytes,
    archive_manager must gracefully fall back to sending a text message so the post is never lost.
    """
    db = isolated_test_db
    post_num = 9014
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 123, '{}', ?)", (post_num, time.time()))

    bot = _make_mock_bot(1)
    ch = -100555
    # Photo type, but file_id is empty/None
    content = {'type': 'photo', 'file_id': None, 'caption': 'Important announcement text'}

    with patch.object(archive_manager, 'MIRROR_CHANNELS', [ch]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot}):

        await _forward_post_to_realtime_archive(bot, 'b', post_num, content, False)
        # Succeeded via text fallback
        assert bot.send_message.called


# =========================================================================
# 3. System Broadcasts (Airdrop, Motivation, Stats, Invites) Archiving
# =========================================================================

@pytest.mark.asyncio
async def test_airdrop_announcement_archived(isolated_test_db):
    """
    Public airdrop announcements have author_id=0, is_system_message=True, archive_allowed=True.
    Verify they are correctly archived.
    """
    db = isolated_test_db
    post_num = 9020
    content = {
        'type': 'text',
        'text': '💸 ПОСОБИЕ ПО БЕЗРАБОТИЦЕ И ШИТПОСТИНГУ АБУСТАНА 💸\nРаздача шекелей завершена!',
        'is_system_message': True,
        'archive_allowed': True
    }
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 0, ?, ?)", (post_num, json.dumps(content), time.time()))

    bot = _make_mock_bot(1)
    ch = -100777

    with patch.object(archive_manager, 'MIRROR_CHANNELS', [ch]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot}):

        await _forward_post_to_realtime_archive(bot, 'b', post_num, content, False)
        assert bot.send_message.called
        # Check ChannelCopies
        async with db.execute("SELECT channel_id FROM ChannelCopies WHERE post_num = ?", (post_num,)) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == ch


@pytest.mark.asyncio
async def test_motivation_and_invite_card_archived(isolated_test_db):
    """
    Motivation messages and graphic invite cards have archive_allowed=True.
    Verify they archive correctly.
    """
    db = isolated_test_db
    post_num = 9021
    content = {
        'type': 'photo',
        'file_id': 'fid_invite_card_123',
        'caption': '💭 Не сиди сычом, позови друзей на Тгач!',
        'is_system_message': True,
        'archive_allowed': True
    }
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 0, ?, ?)", (post_num, json.dumps(content), time.time()))

    bot = _make_mock_bot(1)
    ch = -100777

    with patch.object(archive_manager, 'MIRROR_CHANNELS', [ch]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot}):

        await _forward_post_to_realtime_archive(bot, 'b', post_num, content, False)
        assert bot.send_photo.called


@pytest.mark.asyncio
async def test_archive_skip_overridden_by_archive_allowed(isolated_test_db):
    """
    If content has archive_skip=True, but also archive_allowed=True (e.g. important system post),
    it must NOT be skipped.
    """
    db = isolated_test_db
    post_num = 9022
    content = {
        'type': 'text',
        'text': 'Важный системный анонс',
        'archive_skip': True,
        'archive_allowed': True
    }
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 0, ?, ?)", (post_num, json.dumps(content), time.time()))

    bot = _make_mock_bot(1)
    ch = -100777

    with patch.object(archive_manager, 'MIRROR_CHANNELS', [ch]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot}):

        # Verify delivery manager condition
        should_archive = (content.get('archive_allowed') or not content.get('archive_skip'))
        assert should_archive is True

        await _forward_post_to_realtime_archive(bot, 'b', post_num, content, False)
        assert bot.send_message.called


@pytest.mark.asyncio
async def test_delivery_manager_empty_recipients_still_archives_post(isolated_test_db):
    """
    When delivery_manager processes a post with 0 active recipients (e.g. at night or inactive board),
    it must still spawn _forward_post_to_realtime_archive rather than returning early without archiving.
    """
    db = isolated_test_db
    post_num = 9023
    content = {
        'type': 'text',
        'text': 'Late night announcement',
        'archive_allowed': True
    }
    await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', 0, ?, ?)", (post_num, json.dumps(content), time.time()))

    bot = _make_mock_bot(1)
    ch = -100777

    mock_queue = AsyncMock()
    msg_data = {
        'post_num': post_num,
        'content': content,
        'recipients': set(),  # Empty recipients!
        'board_id': 'b',
        'delivery_phase': 'full'
    }

    with patch.object(archive_manager, 'MIRROR_CHANNELS', [ch]), \
         patch.object(shared_state, 'GLOBAL_BOTS', {'b': bot}), \
         patch.object(archive_manager, 'GLOBAL_BOTS', {'b': bot}), \
         patch.object(shared_state, 'board_data', {'b': {'users': {'active': set(), 'banned': set()}}}):

        processor = MessageDeliveryTask(
            worker_name='worker_b',
            board_id='b',
            bot_instance=bot,
            queue=mock_queue,
            msg_data=msg_data
        )

        with patch('archive_manager._forward_post_to_realtime_archive', new_callable=AsyncMock) as mock_fwd:
            await processor.process()
            # Give spawned task a tick
            await asyncio.sleep(0.05)
            assert mock_fwd.called


# =========================================================================
# 4. Thread HTML Archiving & Happy Posts Bot Fallback
# =========================================================================

@pytest.mark.asyncio
async def test_post_archive_to_channel_fallback():
    """
    When the primary ARCHIVE_POSTING_BOT_ID fails (403 forbidden),
    post_archive_to_channel falls back to other available bots.
    """
    bot1 = _make_mock_bot(1)
    bot2 = _make_mock_bot(2)

    bot1.send_document.side_effect = TelegramForbiddenError(method=MagicMock(), message="Forbidden")
    bot2.send_document.return_value = _make_mock_message(999)

    bots = {'test': bot1, 'b': bot2}
    thread_info = {'title': 'Тестовый тред'}

    import tempfile, os
    with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as f:
        f.write(b"<html>archive</html>")
        tmp_path = f.name

    try:
        with patch.object(shared_state, 'ARCHIVE_CHANNEL_ID', -100999), \
             patch.object(archive_manager, 'ARCHIVE_CHANNEL_ID', -100999), \
             patch.object(shared_state, 'ARCHIVE_POSTING_BOT_ID', 'test'):

            await post_archive_to_channel(bots, tmp_path, 'b', thread_info)

            assert bot1.send_document.called
            assert bot2.send_document.called
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@pytest.mark.asyncio
async def test_post_special_num_to_channel_fallback(isolated_test_db):
    """
    When the primary bot fails (403 forbidden) on a Get / Quad post,
    post_special_num_to_channel falls back to other available bots.
    """
    db = isolated_test_db
    bot1 = _make_mock_bot(1)
    bot2 = _make_mock_bot(2)

    bot1.send_message.side_effect = TelegramForbiddenError(method=MagicMock(), message="Forbidden")
    bot2.send_message.return_value = _make_mock_message(100500)

    bots = {'b': bot1, 'test': bot2}
    content = {'type': 'text', 'text': 'Квадрипл чек!'}

    with patch.object(shared_state, 'ARCHIVE_CHANNEL_ID', -100999), \
         patch.object(archive_manager, 'ARCHIVE_CHANNEL_ID', -100999), \
         patch.object(shared_state, 'GLOBAL_BOTS', bots), \
         patch.object(archive_manager, 'GLOBAL_BOTS', bots):

        await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (555555, 'b', 12345, '{}', ?)", (time.time(),))
        await post_special_num_to_channel(
            bots=bots,
            board_id='b',
            post_num=555555,
            level=6,  # Sextuple
            content=content,
            author_id=12345
        )

        assert bot1.send_message.called
        assert bot2.send_message.called

        # Verified in ChannelCopies
        async with db.execute("SELECT message_id FROM ChannelCopies WHERE post_num = 555555") as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 100500


@pytest.mark.asyncio
async def test_post_thread_notification_to_channel_fallback():
    """
    When posting a thread milestone/notification, bot fallback ensures delivery.
    """
    bot1 = _make_mock_bot(1)
    bot2 = _make_mock_bot(2)

    bot1.send_message.side_effect = TelegramForbiddenError(method=MagicMock(), message="Forbidden")
    bot2.send_message.return_value = _make_mock_message(333)

    bots = {'test': bot1, 'b': bot2}
    thread_info = {'title': 'Бурлящий тред', 'posts': list(range(150))}

    with patch.object(shared_state, 'ARCHIVE_CHANNEL_ID', -100999), \
         patch.object(post_processor, 'ARCHIVE_CHANNEL_ID', -100999), \
         patch.object(shared_state, 'GLOBAL_BOTS', bots), \
         patch.object(post_processor, 'GLOBAL_BOTS', bots):

        await post_thread_notification_to_channel(
            bots=bots,
            board_id='b',
            thread_id='100',
            thread_info=thread_info,
            event_type='milestone',
            details={'posts': 150}
        )

        assert bot1.send_message.called
        assert bot2.send_message.called


# =========================================================================
# 5. R3 & R4 System Broadcast & Money Drop State Machine Tests
# =========================================================================

@pytest.mark.asyncio
async def test_pvp_and_system_announcements_have_archive_allowed():
    """Verify that dice duels and russian roulette announcements have is_system_message and archive_allowed."""
    import dice_duel_engine
    import russian_roulette_pvp
    mock_bot = _make_mock_bot(1)

    with patch('post_processor.process_new_post', new_callable=AsyncMock) as mock_post:
        await dice_duel_engine.broadcast_dice_announcement(mock_bot, 'b', "🎲 Duel finished!")
        assert mock_post.called
        params = mock_post.call_args[0][0]
        assert params.content.get('is_system_message') is True
        assert params.content.get('archive_allowed') is True

    with patch('post_processor.process_new_post', new_callable=AsyncMock) as mock_post:
        await russian_roulette_pvp.broadcast_game_announcement(mock_bot, 'b', "💀 Russian Roulette finished!")
        assert mock_post.called
        params = mock_post.call_args[0][0]
        assert params.content.get('is_system_message') is True
        assert params.content.get('archive_allowed') is True


@pytest.mark.asyncio
async def test_money_drop_mid_broadcast_stops_sending():
    """Verify that _broadcast_money_drop immediately stops sending when drop is claimed mid-broadcast."""
    import main
    import drop_engine

    mock_bot = _make_mock_bot(1)
    drop_id = "test_mid_claim"
    rec = drop_engine.DropRecord(
        drop_id=drop_id,
        donor_id=111,
        donor_name="Donor",
        board_id="b",
        amount=500,
        created_at=time.time(),
        expires_at=time.time() + 600,
        status="active"
    )
    drop_engine.active_drops[drop_id] = rec

    # Simulate 5 active users
    users = [10, 20, 30, 40, 50]
    with patch.object(main, 'board_data', {'b': {'users': {'active': users, 'banned': set()}}}):
        call_count = 0

        async def send_msg_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                # Mid-broadcast claim occurs!
                rec.status = "claimed"
                rec.claimed_by = 20
            return _make_mock_message(message_id=100 + call_count)

        mock_bot.send_message.side_effect = send_msg_side_effect
        mock_bot.send_photo.side_effect = send_msg_side_effect

        await main._broadcast_money_drop(
            bot=mock_bot,
            board_id="b",
            drop_id=drop_id,
            exclude_chat_id=111,
            photo_payload=None,
            caption="Money drop!",
            kb=MagicMock()
        )

        # After user 2, rec.status became "claimed", so loop stopped before users 30, 40, 50!
        assert call_count == 2
        assert len(drop_engine.get_drop_messages(drop_id)) == 2


@pytest.mark.asyncio
async def test_money_drop_retry_after_resilience():
    """Verify that _broadcast_money_drop and _update_all_drop_messages handle TelegramRetryAfter gracefully."""
    import main
    import drop_engine
    from aiogram.exceptions import TelegramRetryAfter

    mock_bot = _make_mock_bot(1)
    drop_id = "test_retry_after"
    rec = drop_engine.DropRecord(
        drop_id=drop_id,
        donor_id=111,
        donor_name="Donor",
        board_id="b",
        amount=500,
        created_at=time.time(),
        expires_at=time.time() + 600,
        status="active"
    )
    drop_engine.active_drops[drop_id] = rec

    # 1. Test broadcast with retry_after
    retry_err = TelegramRetryAfter(method=MagicMock(), message="Flood control", retry_after=0.01)
    mock_bot.send_message.side_effect = [retry_err, _make_mock_message(message_id=999)]

    with patch.object(main, 'board_data', {'b': {'users': {'active': [222], 'banned': set()}}}):
        await main._broadcast_money_drop(
            bot=mock_bot,
            board_id="b",
            drop_id=drop_id,
            exclude_chat_id=111,
            photo_payload=None,
            caption="Money drop!",
            kb=MagicMock()
        )
        assert mock_bot.send_message.call_count == 2
        assert (222, 999) in drop_engine.get_drop_messages(drop_id)

    # 2. Test update with retry_after
    mock_bot.edit_message_caption.side_effect = [retry_err, _make_mock_message(message_id=999)]
    await main._update_all_drop_messages(mock_bot, drop_id, "New text")
    assert mock_bot.edit_message_caption.call_count == 2

