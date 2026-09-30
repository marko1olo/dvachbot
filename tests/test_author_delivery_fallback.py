import pytest
from unittest.mock import AsyncMock, MagicMock
import shared_state
from post_processor import NewPostProcessor, NewPostContext
from broadcaster import MessageBroadcaster
from aiogram.types import BufferedInputFile

@pytest.mark.asyncio
async def test_author_delivery_fallback_on_direct_failure():
    """Verify that if direct author delivery fails, author is returned to self.recipients."""
    bot = AsyncMock()
    context = NewPostContext(
        bot_instance=bot,
        board_id="b",
        user_id=7716348189,
        content={"type": "text", "text": "test post content"},
        reply_to_post=None,
        is_shadow_muted=False,
        stream="ru"
    )
    processor = NewPostProcessor(context)
    processor.current_post_num = 12345
    processor.recipients = {111, 222}
    processor.final_content = {"type": "text", "text": "test post content"}
    # Simulate author delivery failed (empty results)
    processor.author_results = []
    
    # Run _enqueue_and_notify with mocked enqueue_board_message
    enqueued_items = []
    async def mock_enqueue(board_id, item):
        enqueued_items.append(item)

    import delivery_manager
    orig_enqueue = delivery_manager.enqueue_board_message
    delivery_manager.enqueue_board_message = mock_enqueue
    try:
        await processor._enqueue_and_notify()
    finally:
        delivery_manager.enqueue_board_message = orig_enqueue
        
    assert 7716348189 in processor.recipients, "Author must be added to recipients if direct delivery failed"
    assert len(enqueued_items) == 1
    assert 7716348189 in enqueued_items[0]["recipients"]

@pytest.mark.asyncio
async def test_broadcaster_raw_media_timeout_scaling():
    """Verify that broadcaster scales send_timeout_sec and request_timeout_sec when raw media is present."""
    bot = AsyncMock()
    media_items = [
        {"type": "photo", "media": BufferedInputFile(b"bytes1", filename="file1.jpg")},
        {"type": "photo", "media": BufferedInputFile(b"bytes2", filename="file2.jpg")}
    ]
    cfg = shared_state.BroadcastConfig(
        bot_instance=bot,
        board_id="b",
        recipients={7716348189},
        content={"type": "media_group", "media": media_items, "header": "Test Header"},
        reply_info={},
        verbose=False
    )
    bc = MessageBroadcaster(cfg)
    
    # Check that _send_one_guarded detects raw media and uses >= 120s request timeout
    captured_timeouts = []
    async def mock_send_one(uid, req_timeout):
        captured_timeouts.append(req_timeout)
        mock_msg = MagicMock()
        mock_msg.message_id = 12345
        return [mock_msg]
        
    bc._send_one = mock_send_one
    await bc._send_one_guarded(7716348189, timeout_sec=120.0)
    assert len(captured_timeouts) == 1
    assert captured_timeouts[0] >= 120, f"Expected request_timeout_sec >= 120, got {captured_timeouts[0]}"
