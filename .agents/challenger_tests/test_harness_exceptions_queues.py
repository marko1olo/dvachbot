import os
import sys
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = r"C:\Users\danat\Desktop\dvachbot"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"

static_dir = os.path.join(PROJECT_ROOT, "Dubsite_tgach", "static")
os.makedirs(static_dir, exist_ok=True)

import shared_state
if not hasattr(shared_state, 'current_deliveries'):
    shared_state.current_deliveries = {}
if not hasattr(shared_state, 'posts_pending_deletion'):
    shared_state.posts_pending_deletion = set()

import broadcaster
from broadcaster import MessageBroadcaster
from shared_state import BroadcastConfig
import delivery_manager
import economy_extension

from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramBadRequest,
    TelegramAPIError
)

class TestBroadcasterExceptions(unittest.IsolatedAsyncioTestCase):
    def _make_mb(self, bot_mock):
        cfg = BroadcastConfig(
            bot_instance=bot_mock,
            board_id="b",
            recipients={12345},
            content={'type': 'text', 'text': 'Hello test message', 'post_num': 100}
        )
        mb = MessageBroadcaster(cfg)
        mb.users_settings = {12345: {'nsfw': False, 'hide': set()}}
        mb.hide_check_text = "hello test message"
        mb.base_head_html = "Header"
        mb.highlight_head_html = "Header"
        mb.common_formatted_body = "Body"
        mb.content_for_common = {'type': 'text', 'text': 'Hello test message', 'post_num': 100}
        mb.reply_to_post_author_id = None
        mb.post_num_for_replies = None
        mb.reply_info = None
        mb.db_replies_map = {}
        mb.b_data = {'users': {'active': {12345}, 'banned': set()}}
        return mb

    async def test_send_one_forbidden_error(self):
        bot = AsyncMock()
        mb = self._make_mb(bot)
        
        err = TelegramForbiddenError(method=MagicMock(), message="Forbidden: bot was blocked by the user")
        bot.send_message.side_effect = err
        
        # _send_one re-raises TelegramForbiddenError to caller (broadcast())
        with self.assertRaises(TelegramForbiddenError):
            await mb._send_one(12345, 10)
        
    async def test_send_one_bad_request(self):
        bot = AsyncMock()
        mb = self._make_mb(bot)
        
        err = TelegramBadRequest(method=MagicMock(), message="Bad Request: message is not modified")
        bot.send_message.side_effect = err
        
        res = await mb._send_one(12345, 10)
        self.assertIsNone(res)
        self.assertEqual(mb.stats['errors'], 1)
        self.assertNotIn(12345, mb.blocked_users)

    async def test_send_one_retry_after(self):
        bot = AsyncMock()
        mb = self._make_mb(bot)
        
        err = TelegramRetryAfter(method=MagicMock(), message="Flood control exceeded: retry after 3", retry_after=3)
        bot.send_message.side_effect = err
        
        with self.assertRaises(TelegramRetryAfter):
            await mb._send_one(12345, 10)

    async def test_send_one_cancelled_error(self):
        bot = AsyncMock()
        mb = self._make_mb(bot)
        
        bot.send_message.side_effect = asyncio.CancelledError()
        
        with self.assertRaises(asyncio.CancelledError):
            await mb._send_one(12345, 10)

class TestQueueIntegrity(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_broadcaster_finally_task_done(self):
        from Dubsite_tgach.main import websocket_broadcaster
        
        queue = asyncio.Queue()
        manager = AsyncMock()
        
        # Put 2 items in queue
        await queue.put({'board_id': 'b', 'post_num': 1})
        await queue.put({'board_id': 'b', 'post_num': 2})
        
        # 1st broadcast succeeds, 2nd raises Exception
        manager.broadcast_post.side_effect = [None, RuntimeError("Simulated broadcast error")]
        
        task = asyncio.create_task(websocket_broadcaster(queue, manager))
        
        # Wait for queue items to be marked done
        await asyncio.wait_for(queue.join(), timeout=5.0)
        
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
            
        self.assertEqual(queue.qsize(), 0)
        
    async def test_message_worker_finally_task_done(self):
        from delivery_manager import message_queues, message_worker
        
        board_id = "test_board_challenger"
        queue = asyncio.Queue()
        message_queues[board_id] = queue
        
        # Add item that will fail processing
        item = {
            'recipients': {999001},
            'content': {'type': 'text', 'text': 'Fail test'},
            'post_num': 777,
            'board_id': board_id,
            '_retry_count': 3 # Exceeded max retries -> will trigger durable save and complete
        }
        await queue.put(item)
        
        bot_mock = AsyncMock()
        
        with patch("delivery_manager._persist_durable_delivery_item", new=AsyncMock()) as mock_persist:
            with patch("delivery_manager.MessageDeliveryTask") as mock_task_cls:
                task_instance = AsyncMock()
                task_instance.process.side_effect = RuntimeError("Delivery processing failed")
                mock_task_cls.return_value = task_instance
                
                worker_task = asyncio.create_task(message_worker("worker_test", board_id, bot_mock))
                
                # Verify queue.join completes because task_done() is in finally block
                await asyncio.wait_for(queue.join(), timeout=5.0)
                
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
                    
                self.assertEqual(queue.qsize(), 0)
                mock_persist.assert_called_once()

class TestEconomyExtensionExceptions(unittest.IsolatedAsyncioTestCase):
    async def test_purge_blocked_user_graceful(self):
        from economy_extension import _purge_blocked_user
        
        # Should complete without error even if main is not imported or board_id is None
        await _purge_blocked_user(12345, None)
        await _purge_blocked_user(12345, "b")

if __name__ == "__main__":
    unittest.main()
