import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import shared_state
from shared_state import (
    post_to_messages, message_to_post, storage_lock, current_deliveries,
    current_media_groups, sent_media_groups, message_queues,
    enqueue_board_message, remove_blocked_user_copies, BroadcastConfig
)
from delivery_manager import (
    _queue_item_can_be_durable, _persist_durable_delivery_item,
    MessageDeliveryTask, complete_media_group_after_delay,
    process_complete_media_group, edit_post_for_all_recipients
)
from aiogram.exceptions import TelegramForbiddenError


@pytest.mark.asyncio
async def test_queue_item_can_be_durable_fresh_posts():
    """Verify fresh posts with None or 'full' delivery_phase are allowed to be durable."""
    with patch('shared_state.DURABLE_DELIVERY_QUEUE_ENABLED', True):
        # Fresh post without delivery_phase key
        item_fresh_none = {
            "post_num": 1001,
            "content": {"type": "text", "text": "Fresh post test"},
            "recipients": [10, 20, 30],
        }
        assert _queue_item_can_be_durable(item_fresh_none) is True

        # Fresh post with delivery_phase="full"
        item_fresh_full = {
            "post_num": 1002,
            "content": {"type": "text", "text": "Full phase post"},
            "delivery_phase": "full",
            "recipients": [10, 20],
        }
        assert _queue_item_can_be_durable(item_fresh_full) is True

        # Passive post remains valid
        item_passive = {
            "post_num": 1003,
            "content": {"type": "text", "text": "Passive phase post"},
            "delivery_phase": "passive",
            "recipients": [10],
        }
        assert _queue_item_can_be_durable(item_passive) is True

        # Invalid phase is rejected
        item_invalid = {
            "post_num": 1004,
            "content": {"type": "text", "text": "Invalid phase post"},
            "delivery_phase": "unknown_phase_xyz",
            "recipients": [10],
        }
        assert _queue_item_can_be_durable(item_invalid) is False


@pytest.mark.asyncio
async def test_enqueue_board_message_persists_durable_item():
    """Verify enqueue_board_message saves durable item to SQLite before putting into queue."""
    board_id = "test_durable_board"
    shared_state.message_queues[board_id] = asyncio.Queue()

    item = {
        "post_num": 2001,
        "content": {"type": "text", "text": "Persist on enqueue test"},
        "recipients": [100, 200],
    }

    mock_upsert = AsyncMock(return_value=999)
    with patch('delivery_manager.upsert_delivery_queue_item', mock_upsert), \
         patch('shared_state.DURABLE_DELIVERY_QUEUE_ENABLED', True):
        res = await enqueue_board_message(board_id, item)
        assert res is True
        assert mock_upsert.called
        enqueued_item = await shared_state.message_queues[board_id].get()
        assert enqueued_item.get("durable_delivery_id") == 999


@pytest.mark.asyncio
async def test_current_deliveries_leak_prevention():
    """Verify current_deliveries entry is cleaned up in finally block even if send fails."""
    board_id = "test_leak_board"
    bot_mock = MagicMock()
    q = asyncio.Queue()
    current_deliveries.clear()

    msg_data = {
        "post_num": 3001,
        "content": {"type": "text", "text": "Test leak prevention"},
        "recipients": {101, 102},
        "delivery_phase": "full",
        "board_id": board_id,
    }

    task = MessageDeliveryTask("Worker-test", board_id, bot_mock, q, msg_data)

    # Simulate an error during send_message_to_users
    with patch('delivery_manager.send_message_to_users', AsyncMock(side_effect=RuntimeError("Simulated send crash"))):
        with pytest.raises(RuntimeError):
            await task.process()

    # current_deliveries must be cleared in finally block, no ghost!
    assert board_id not in current_deliveries


@pytest.mark.asyncio
async def test_remove_blocked_user_copies_cleans_ram_and_db():
    """Verify remove_blocked_user_copies clears post_to_messages, message_to_post, and DB."""
    blocked_uid = 555666
    post_num = 4001
    msg_id = 998877

    async with storage_lock:
        post_to_messages[post_num] = {blocked_uid: msg_id, 777: 112233}
        message_to_post[(blocked_uid, msg_id)] = post_num
        message_to_post[(777, 112233)] = post_num

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    with patch('common.db_pool.get_pool', AsyncMock(return_value=mock_db)):
        await remove_blocked_user_copies(blocked_uid)

    async with storage_lock:
        assert blocked_uid not in post_to_messages[post_num]
        assert (blocked_uid, msg_id) not in message_to_post
        # Other user remains intact
        assert 777 in post_to_messages[post_num]
        assert (777, 112233) in message_to_post

    assert mock_db.execute.called
    sql_call = mock_db.execute.call_args[0][0]
    assert "DELETE FROM PostCopies WHERE recipient_id IN" in sql_call


@pytest.mark.asyncio
async def test_media_group_split_race_and_processing_status():
    """Verify complete_media_group_after_delay holds 'processing' status and pops only after sent."""
    mg_key = "chat123:mg999"
    current_media_groups[mg_key] = {
        "status": "collecting",
        "raw_messages": [],
        "media": [{"type": "photo", "file_id": "photo_fid_1"}]
    }

    bot_mock = MagicMock()

    # Track that sent_media_groups contains mg_key before current_media_groups is popped
    order_check = []

    async def mock_process(key, group, bot):
        order_check.append("processed")
        sent_media_groups.append(key)
        assert current_media_groups.get(key, {}).get("status") == "processing"

    with patch('delivery_manager.process_complete_media_group', side_effect=mock_process):
        # Trigger with zero delay
        msg_obj = MagicMock()
        msg_obj.message_id = 1
        msg_obj.caption = "Test album"
        msg_obj.content_type = "photo"
        photo_sz = MagicMock()
        photo_sz.file_id = "photo_fid_1"
        photo_sz.file_unique_id = "uniq_1"
        msg_obj.photo = [photo_sz]
        msg_obj.video = None
        msg_obj.document = None
        msg_obj.audio = None

        current_media_groups[mg_key]["raw_messages"] = [msg_obj]

        await complete_media_group_after_delay(mg_key, bot_mock, delay=0.0)

        assert "processed" in order_check
        assert mg_key in sent_media_groups
        assert mg_key not in current_media_groups


@pytest.mark.asyncio
async def test_chunked_media_group_inherits_reply_to_post():
    """Verify that when a media group has >10 items, subsequent chunks inherit reply_to_post."""
    mg_key = "chat123:mg_chunked"
    items = [{"type": "photo", "file_id": f"fid_{i}"} for i in range(25)]
    group = {
        "author_id": 100,
        "board_id": "b",
        "media": items,
        "caption": "Large album with 25 photos",
        "reply_to_post": 77777,
        "stream": "ru",
    }

    captured_params = []

    async def mock_new_post(params):
        captured_params.append(params)
        return 88000 + len(captured_params)

    with patch('delivery_manager.process_new_post', side_effect=mock_new_post), \
         patch('delivery_manager.board_data', {'b': {'users': {'banned': set()}, 'user_settings': {}, 'shadow_mutes': {}}}), \
         patch('delivery_manager.is_admin', return_value=True):
        await process_complete_media_group(mg_key, group, MagicMock())

    # 25 photos should split into 3 chunks: [10, 10, 5]
    # Plus 1 separate text caption post = 4 posts total
    assert len(captured_params) >= 3
    # Check media chunks (first 3)
    for idx, param in enumerate(captured_params[:3]):
        assert param.reply_to_post == 77777, f"Chunk {idx} lost reply_to_post!"
