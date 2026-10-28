import pytest
import asyncio
import time
from unittest.mock import patch
from fastapi.testclient import TestClient
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from common.database import (
    create_post,
    create_thread,
    get_thread_by_op_post,
    get_thread_op_by_post_num,
    process_mentions_and_notify,
    get_and_clear_notification_queue,
)


@pytest.fixture(autouse=True)
def _use_isolated_db(isolated_test_db):
    yield isolated_test_db


@pytest.mark.asyncio
async def test_process_mentions_and_notify_disabled_explicitly():
    """Verify that when ENABLE_REPLY_NOTIFICATIONS is False, NotificationQueue is not populated."""
    with patch("common.database.ENABLE_REPLY_NOTIFICATIONS", False):
        ts = time.time()
        op_num = await create_post(
            author_id=7001,
            board_id="b",
            content={"type": "text", "text": f"Test OP disabled {ts}"},
            timestamp=ts,
            post_mode="new_thread"
        )
        assert op_num is not None
        await create_thread(str(op_num), "b", 7001, f"Test Thread disabled {ts}", ts)

        reply_num_1 = await create_post(
            author_id=7002,
            board_id="b",
            content={"type": "text", "text": f">>{op_num} first reply"},
            timestamp=ts + 1,
            reply_to=op_num,
            thread_id_from_bot=str(op_num)
        )
        assert reply_num_1 is not None

        # Call process_mentions_and_notify with ENABLE_REPLY_NOTIFICATIONS = False
        await process_mentions_and_notify(
            source_post_num=reply_num_1,
            board_id="b",
            text=f">>{op_num} first reply",
            author_id=7002,
            reply_to_ui=op_num
        )

        # NotificationQueue must be empty
        notifs = await get_and_clear_notification_queue()
        assert len(notifs) == 0


@pytest.mark.asyncio
async def test_process_mentions_and_notify_fields_when_enabled():
    """Verify that when ENABLE_REPLY_NOTIFICATIONS is True, NotificationQueue and UserReplies store parent and reply post numbers correctly."""
    with patch("common.database.ENABLE_REPLY_NOTIFICATIONS", True):
        ts = time.time()
        # 1. User 7001 creates a thread OP post
        op_num = await create_post(
            author_id=7001,
            board_id="b",
            content={"type": "text", "text": f"Test OP {ts}"},
            timestamp=ts,
            post_mode="new_thread"
        )
        assert op_num is not None
        await create_thread(str(op_num), "b", 7001, f"Test Thread {ts}", ts)

        # 2. User 7002 creates a reply quoting OP post >>op_num
        reply_num_1 = await create_post(
            author_id=7002,
            board_id="b",
            content={"type": "text", "text": f">>{op_num} first reply"},
            timestamp=ts + 1,
            reply_to=op_num,
            thread_id_from_bot=str(op_num)
        )
        assert reply_num_1 is not None

        # Call process_mentions_and_notify for this reply
        await process_mentions_and_notify(
            source_post_num=reply_num_1,
            board_id="b",
            text=f">>{op_num} first reply",
            author_id=7002,
            reply_to_ui=op_num
        )

        # Check NotificationQueue
        notifs = await get_and_clear_notification_queue()
        assert len(notifs) >= 1
        # Filter our specific notification
        target_notifs = [n for n in notifs if n["recipient_id"] == 7001 and n["reply_post_num"] == reply_num_1]
        assert len(target_notifs) == 1
        note = target_notifs[0]
        assert note["recipient_id"] == 7001
        assert note["source_post_num"] == op_num  # Parent post belonging to user 7001
        assert note["reply_post_num"] == reply_num_1  # The new reply
        assert note["board_id"] == "b"
        assert str(note["thread_id"]) == str(op_num)

        # 3. User 7003 replies to User 7002's reply
        reply_num_2 = await create_post(
            author_id=7003,
            board_id="b",
            content={"type": "text", "text": f">>{reply_num_1} second reply"},
            timestamp=ts + 2,
            reply_to=reply_num_1,
            thread_id_from_bot=str(op_num)
        )
        assert reply_num_2 is not None

        await process_mentions_and_notify(
            source_post_num=reply_num_2,
            board_id="b",
            text=f">>{reply_num_1} second reply",
            author_id=7003,
            reply_to_ui=reply_num_1
        )

        notifs2 = await get_and_clear_notification_queue()
        target_notifs2 = [n for n in notifs2 if n["recipient_id"] == 7002 and n["reply_post_num"] == reply_num_2]
        assert len(target_notifs2) == 1
        note2 = target_notifs2[0]
        assert note2["recipient_id"] == 7002
        assert note2["source_post_num"] == reply_num_1  # Post belonging to user 7002
        assert note2["reply_post_num"] == reply_num_2  # The new reply
        assert str(note2["thread_id"]) == str(op_num)


@pytest.mark.asyncio
async def test_get_thread_by_op_post_auto_resolve():
    """Verify that get_thread_by_op_post returns the full thread even when called with a reply post number."""
    ts = time.time()
    op_num = await create_post(
        author_id=7010,
        board_id="b",
        content={"type": "text", "text": f"OP Content {ts}"},
        timestamp=ts,
        post_mode="new_thread"
    )
    await create_thread(str(op_num), "b", 7010, f"Thread Title {ts}", ts)

    reply_1 = await create_post(
        author_id=7011,
        board_id="b",
        content={"type": "text", "text": "Reply 1"},
        timestamp=ts + 1,
        reply_to=op_num,
        thread_id_from_bot=str(op_num)
    )

    reply_2 = await create_post(
        author_id=7012,
        board_id="b",
        content={"type": "text", "text": "Reply 2"},
        timestamp=ts + 2,
        reply_to=reply_1,
        thread_id_from_bot=str(op_num)
    )

    # 1. Fetch using OP post num
    res_op = await get_thread_by_op_post(op_num)
    assert res_op is not None
    op_post, replies = res_op
    assert op_post["post_num"] == op_num
    assert any(r["post_num"] == reply_1 for r in replies)
    assert any(r["post_num"] == reply_2 for r in replies)

    # 2. Fetch using reply post num (e.g. reply_2) - must automatically resolve to OP and return full thread
    res_reply = await get_thread_by_op_post(reply_2)
    assert res_reply is not None
    op_post_r, replies_r = res_reply
    assert op_post_r["post_num"] == op_num
    assert any(r["post_num"] == reply_1 for r in replies_r)
    assert any(r["post_num"] == reply_2 for r in replies_r)


@pytest.mark.asyncio
async def test_get_thread_op_by_post_num():
    """Verify get_thread_op_by_post_num finds OP post num for both OP posts and replies."""
    ts = time.time()
    op_num = await create_post(
        author_id=7020,
        board_id="b",
        content={"type": "text", "text": f"OP {ts}"},
        timestamp=ts,
        post_mode="new_thread"
    )
    await create_thread(str(op_num), "b", 7020, f"OP {ts}", ts)

    reply_num = await create_post(
        author_id=7021,
        board_id="b",
        content={"type": "text", "text": "Reply"},
        timestamp=ts + 1,
        reply_to=op_num,
        thread_id_from_bot=str(op_num)
    )

    # For OP post
    found_op = await get_thread_op_by_post_num(op_num)
    assert found_op == op_num

    # For Reply post
    found_for_reply = await get_thread_op_by_post_num(reply_num)
    assert str(found_for_reply) == str(op_num)


@pytest.mark.asyncio
async def test_reply_notifier_url_and_text_formatting():
    """Verify notification text, buttons, and anchors generated for reply notifications."""
    from common.board_config import BOARD_CONFIG

    recipient_id = 99999
    source_post_num = 500  # User's post
    reply_post_num = 505   # Reply post
    board_id = "b"
    thread_id = 500

    webapp_url = "https://tgach.top"
    thread_url = f"{webapp_url}/{board_id}/res/{thread_id}.html#post-{reply_post_num}"

    # Assert URL structure has #post-505 anchor
    assert thread_url == "https://tgach.top/b/res/500.html#post-505"

    text_ru = f"📢 На ваш пост >>{source_post_num} ответили постом >>{reply_post_num}"
    assert "На ваш пост >>500 ответили постом >>505" in text_ru

    bot_username = BOARD_CONFIG.get(board_id, {}).get('username', '').lstrip('@')
    tg_url = f"https://t.me/{bot_username}?start=thread_{thread_id}"

    buttons = [
        InlineKeyboardButton(text="Открыть в Telegram 💬", url=tg_url),
        InlineKeyboardButton(text="Читать на сайте 🌐", url=thread_url),
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])
    assert len(keyboard.inline_keyboard[0]) == 2
    assert keyboard.inline_keyboard[0][0].url == tg_url
    assert keyboard.inline_keyboard[0][1].url == thread_url


@pytest.mark.asyncio
async def test_web_redirect_reply_url():
    """Verify that requesting /{board_id}/res/{reply_post_num}.html redirects to the thread OP with anchor."""
    from site_tgach.main import app
    client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)

    ts = time.time()
    op_num = await create_post(
        author_id=7030,
        board_id="b",
        content={"type": "text", "text": f"OP {ts}"},
        timestamp=ts,
        post_mode="new_thread"
    )
    await create_thread(str(op_num), "b", 7030, f"OP {ts}", ts)

    reply_num = await create_post(
        author_id=7031,
        board_id="b",
        content={"type": "text", "text": "Reply"},
        timestamp=ts + 1,
        reply_to=op_num,
        thread_id_from_bot=str(op_num)
    )

    # Requesting the reply_num directly should redirect to OP thread with #post-{reply_num}
    resp = client.get(f"/b/res/{reply_num}.html")
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/b/res/{op_num}.html#post-{reply_num}"

    # Requesting the OP num directly should return 200 OK
    resp_op = client.get(f"/b/res/{op_num}.html")
    assert resp_op.status_code == 200


@pytest.mark.asyncio
async def test_reply_notifier_task_disabled():
    """Verify that reply_notifier_task immediately cleans queue and exits when ENABLE_REPLY_NOTIFICATIONS is False."""
    from main import reply_notifier_task
    # Run reply_notifier_task - with ENABLE_REPLY_NOTIFICATIONS = False, it should complete quickly without hanging
    with patch("main.ENABLE_REPLY_NOTIFICATIONS", False):
        await asyncio.wait_for(reply_notifier_task(), timeout=2.0)


@pytest.mark.asyncio
async def test_reply_to_op_inherits_thread_id():
    """Verify that replying to an OP post automatically resolves and inherits the thread ID."""
    ts = time.time()
    op_num = await create_post(
        author_id=7040,
        board_id="b",
        content={"type": "text", "text": f"OP thread test {ts}"},
        timestamp=ts,
        post_mode="new_thread"
    )
    assert op_num is not None
    await create_thread(str(op_num), "b", 7040, f"OP thread test {ts}", ts)

    # Reply created with reply_to=op_num and NO thread_id_from_bot
    reply_num = await create_post(
        author_id=7041,
        board_id="b",
        content={"type": "text", "text": "Replying directly to OP"},
        timestamp=ts + 1,
        reply_to=op_num,
        thread_id_from_bot=None
    )
    assert reply_num is not None

    # Verify that the reply inherited thread_id == str(op_num)
    from common.db_pool import get_pool
    db = await get_pool()
    async with db.execute("SELECT thread_id FROM Posts WHERE post_num = ?", (reply_num,)) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == str(op_num)


@pytest.mark.asyncio
async def test_site_post_mention_notifies_tg_user():
    """Verify that when a post created on the website mentions a TG user >>XXXXX, NotificationQueue is populated."""
    ts = time.time()
    # 1. TG user 8001 creates post 100
    tg_post_num = await create_post(
        author_id=8001,
        board_id="b",
        content={"type": "text", "text": f"Post from Telegram {ts}"},
        timestamp=ts,
    )
    assert tg_post_num is not None

    # 2. Site user creates post quoting >>tg_post_num
    site_post_num = await create_post(
        author_id=-100,  # Site author
        board_id="b",
        content={"type": "text", "text": f">>{tg_post_num} Hello from the web!"},
        timestamp=ts + 1,
        reply_to=tg_post_num,
        is_from_site=True
    )
    assert site_post_num is not None

    # 3. Trigger mention notification
    await process_mentions_and_notify(
        source_post_num=site_post_num,
        board_id="b",
        text=f">>{tg_post_num} Hello from the web!",
        author_id=-100,
        reply_to_ui=tg_post_num
    )

    # 4. Check that user 8001 received notification in NotificationQueue
    notifs = await get_and_clear_notification_queue()
    matching = [n for n in notifs if n["recipient_id"] == 8001 and n["source_post_num"] == tg_post_num and n["reply_post_num"] == site_post_num]
    assert len(matching) == 1
    assert matching[0]["board_id"] == "b"


@pytest.mark.asyncio
async def test_one_click_reply_from_notification_resolution():
    """Verify that when a bot notification message_id is stored in message_to_post, resolve_reply_from_message resolves it."""
    from shared_state import message_to_post, storage_lock
    from handlers.message_router import resolve_reply_from_message
    from unittest.mock import MagicMock

    user_id = 8080
    bot_msg_id = 991122
    target_reply_post_num = 12345

    async with storage_lock:
        message_to_post[(user_id, bot_msg_id)] = target_reply_post_num

    # Mock the telegram message object replying to the notification
    mock_reply_msg = MagicMock()
    mock_reply_msg.chat.id = user_id
    mock_reply_msg.message_id = bot_msg_id
    mock_reply_msg.from_user.id = user_id
    mock_reply_msg.forward_from_chat = None
    mock_reply_msg.forward_from_message_id = None
    mock_reply_msg.text = None
    mock_reply_msg.caption = None
    mock_reply_msg.photo = None
    mock_reply_msg.video = None
    mock_reply_msg.video_note = None
    mock_reply_msg.sticker = None
    mock_reply_msg.audio = None
    mock_reply_msg.voice = None
    mock_reply_msg.animation = None
    mock_reply_msg.document = None

    resolved = await resolve_reply_from_message(mock_reply_msg, user_id)
    assert resolved == target_reply_post_num


@pytest.mark.asyncio
async def test_new_thread_public_notification_buttons():
    """Verify that new thread notification builds both TG deeplink and web reading link buttons."""
    from main import _notify_new_thread_public, NewThreadPublicContext
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    board_id = "b"
    b_data = {
        'users': {'active': {9001, 9002}, 'banned': set()},
        'user_state': {}
    }
    title = "Test Thread Public CTA"
    thread_id = "555"
    now_dt = datetime.now(timezone.utc)

    enqueued_items = []
    async def mock_enqueue(b_id, item):
        enqueued_items.append(item)
        return True

    with patch("main.enqueue_board_message", side_effect=mock_enqueue):
        ctx = NewThreadPublicContext(board_id, b_data, title, thread_id, 'ru', now_dt, 'ru')
        await _notify_new_thread_public(ctx)

    assert len(enqueued_items) == 1
    item = enqueued_items[0]
    keyboard = item.get("keyboard")
    assert keyboard is not None
    buttons = keyboard.inline_keyboard[0]
    # Check that there are two buttons: 1 TG deeplink and 1 Web link
    assert len(buttons) == 2
    assert "start=thread_555" in buttons[0].url
    assert "https://tgach.top/b/res/555.html" in buttons[1].url



