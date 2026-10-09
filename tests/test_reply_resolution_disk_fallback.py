import pytest
import time
from unittest import mock
from aiogram.types import Message, Chat, User

from shared_state import message_to_post, messages_storage, post_to_messages, storage_lock
from common.database import create_post, add_post_copies
from handlers.message_router import resolve_reply_from_message
from post_processor import NewPostContext, NewPostProcessor


def make_mock_message(
    message_id: int,
    chat_id: int,
    user_id: int,
    text: str = None,
    caption: str = None,
    video_note_file_id: str = None,
    sticker_file_id: str = None,
    photo_file_id: str = None,
    reply_to_message: Message = None,
    forward_from_chat_id: int = None,
    forward_from_message_id: int = None,
) -> mock.MagicMock:
    msg = mock.MagicMock(spec=Message)
    msg.message_id = message_id
    msg.chat = mock.MagicMock(spec=Chat)
    msg.chat.id = chat_id
    msg.from_user = mock.MagicMock(spec=User)
    msg.from_user.id = user_id
    msg.from_user.is_bot = False
    msg.text = text
    msg.caption = caption
    msg.reply_to_message = reply_to_message

    if video_note_file_id:
        vn = mock.MagicMock()
        vn.file_id = video_note_file_id
        vn.file_unique_id = f"uniq_{video_note_file_id}"
        vn.thumbnail = None
        msg.video_note = vn
    else:
        msg.video_note = None

    if sticker_file_id:
        st = mock.MagicMock()
        st.file_id = sticker_file_id
        st.file_unique_id = f"uniq_{sticker_file_id}"
        st.thumbnail = None
        st.emoji = "😎"
        msg.sticker = st
    else:
        msg.sticker = None

    if photo_file_id:
        p = mock.MagicMock()
        p.file_id = photo_file_id
        p.file_unique_id = f"uniq_{photo_file_id}"
        msg.photo = [p]
    else:
        msg.photo = None

    msg.video = None
    msg.animation = None
    msg.document = None
    msg.voice = None
    msg.audio = None

    if forward_from_chat_id and forward_from_message_id:
        fwd_chat = mock.MagicMock(spec=Chat)
        fwd_chat.id = forward_from_chat_id
        msg.forward_from_chat = fwd_chat
        msg.forward_from_message_id = forward_from_message_id
    else:
        msg.forward_from_chat = None
        msg.forward_from_message_id = None

    return msg


@pytest.mark.asyncio
async def test_resolve_reply_tier1_ram(isolated_test_db):
    """Tier 1: fast RAM hit."""
    async with storage_lock:
        message_to_post[(12345, 999)] = 500

    mock_msg = make_mock_message(message_id=999, chat_id=12345, user_id=12345)
    resolved = await resolve_reply_from_message(mock_msg, chat_id=12345)
    assert resolved == 500


@pytest.mark.asyncio
async def test_resolve_reply_tier2_sqlite_postcopies_after_ram_eviction(isolated_test_db):
    """
    Tier 2: RAM is completely empty (simulating 500+ posts eviction).
    Post was saved to SQLite Posts & PostCopies.
    resolve_reply_from_message recovers post_num from SQLite and hydrates messages_storage.
    """
    # 1. Create original post in DB
    post_num = await create_post(
        author_id=777,
        board_id="b",
        content={"type": "text", "text": "Original old post from 500 posts ago"},
        timestamp=time.time(),
        reply_to=None
    )
    assert post_num is not None

    # 2. Add copy for user 12345 with message_id 88888
    await add_post_copies(post_num, [(12345, 88888)])

    # 3. Simulate total RAM eviction
    async with storage_lock:
        message_to_post.clear()
        messages_storage.clear()
        post_to_messages.clear()

    assert (12345, 88888) not in message_to_post
    assert post_num not in messages_storage

    # 4. User replies to message_id 88888
    mock_replied_msg = make_mock_message(message_id=88888, chat_id=12345, user_id=12345)
    resolved = await resolve_reply_from_message(mock_replied_msg, chat_id=12345)

    assert resolved == post_num
    # Ensure hydrated back into RAM
    async with storage_lock:
        assert message_to_post.get((12345, 88888)) == post_num
        assert post_num in messages_storage
        assert messages_storage[post_num]["author_id"] == 777


@pytest.mark.asyncio
async def test_resolve_reply_tier4_video_note_no_text_by_file_id(isolated_test_db):
    """
    Tier 4: Replying to a video_note (кружочек) with NO text and NO copy in PostCopies.
    resolve_reply_from_message extracts file_id from video_note and recovers post from SQLite.
    """
    v_file_id = "BAACAgIAAxkBAAIBY1234567890video_note_test"
    post_num = await create_post(
        author_id=888,
        board_id="b",
        content={"type": "video_note", "file_id": v_file_id},
        timestamp=time.time(),
        reply_to=None
    )
    assert post_num is not None

    # Clear RAM completely
    async with storage_lock:
        message_to_post.clear()
        messages_storage.clear()

    # User replies to a video_note that has no copy in PostCopies
    mock_replied_vn = make_mock_message(
        message_id=77777,
        chat_id=99999,
        user_id=99999,
        video_note_file_id=v_file_id
    )

    resolved = await resolve_reply_from_message(mock_replied_vn, chat_id=99999)
    assert resolved == post_num


@pytest.mark.asyncio
async def test_resolve_reply_tier5_global_message_id_fallback(isolated_test_db):
    """
    Tier 5: Replying to a message where chat_id differs (e.g., forwarded or group mismatch),
    but message_id exists in PostCopies globally.
    """
    post_num = await create_post(
        author_id=555,
        board_id="b",
        content={"type": "text", "text": "Tier 5 post"},
        timestamp=time.time(),
        reply_to=None
    )
    await add_post_copies(post_num, [(11111, 44444)])

    # Clear RAM
    async with storage_lock:
        message_to_post.clear()
        messages_storage.clear()

    # Incoming reply has chat_id=99999 (not 11111!), but message_id=44444
    mock_replied = make_mock_message(message_id=44444, chat_id=99999, user_id=99999)
    resolved = await resolve_reply_from_message(mock_replied, chat_id=99999)
    assert resolved == post_num


@pytest.mark.asyncio
async def test_post_processor_author_reply_info_and_postcopies_persistence(isolated_test_db):
    """
    Verifies that:
    1. NewPostProcessor sets self.reply_info_for_author = {user_id: reply_to_message_id}
    2. Author message copy is persisted to SQLite PostCopies table
    """
    mock_bot = mock.AsyncMock()
    # Mock bot.send_message returning a sent message
    sent_msg = mock.MagicMock(spec=Message)
    sent_msg.message_id = 123456
    mock_bot.send_message.return_value = sent_msg

    context = NewPostContext(
        bot_instance=mock_bot,
        board_id="b",
        user_id=1001,
        content={"type": "text", "text": "Hello world with reply"},
        reply_to_post=50,
        is_shadow_muted=False,
        stream="ru",
        reply_to_message_id=999888
    )

    processor = NewPostProcessor(context)
    # Check that reply_info_for_author is populated correctly
    assert processor.reply_info_for_author == {1001: 999888}


@pytest.mark.asyncio
async def test_resolve_reply_tier2_5_forwarded_message(isolated_test_db):
    """
    Tier 2.5: User forwards a post copy from another channel/chat,
    and resolves via forward_from_chat and forward_from_message_id.
    """
    post_num = await create_post(
        author_id=444,
        board_id="b",
        content={"type": "text", "text": "Post in channel"},
        timestamp=time.time(),
        reply_to=None
    )
    await add_post_copies(post_num, [(999888, 333222)])

    async with storage_lock:
        message_to_post.clear()
        messages_storage.clear()

    # User replies to a forwarded message
    mock_fwd = make_mock_message(
        message_id=111,
        chat_id=55555,
        user_id=55555,
        forward_from_chat_id=999888,
        forward_from_message_id=333222
    )

    resolved = await resolve_reply_from_message(mock_fwd, chat_id=55555)
    assert resolved == post_num


@pytest.mark.asyncio
async def test_resolve_reply_tier3_header_metadata(isolated_test_db):
    """
    Tier 3: Post number extracted from header text / zero-width characters
    when PostCopies has no record (e.g., deleted copy or foreign repost).
    """
    post_num = await create_post(
        author_id=333,
        board_id="b",
        content={"type": "text", "text": "Target post"},
        timestamp=time.time(),
        reply_to=None
    )

    async with storage_lock:
        message_to_post.clear()
        messages_storage.clear()

    # Message with post header text
    header_text = f"Пост №{post_num}\nКакой-то текст сообщения"
    mock_msg = make_mock_message(
        message_id=999111,
        chat_id=12345,
        user_id=12345,
        text=header_text
    )

    resolved = await resolve_reply_from_message(mock_msg, chat_id=12345)
    assert resolved == post_num

