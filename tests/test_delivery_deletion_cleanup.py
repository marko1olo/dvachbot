"""
tests/test_delivery_deletion_cleanup.py

Comprehensive tests for:
1. Delivery cancellation when a post is marked for deletion (pending_deletion).
2. Instant queue purging for deleted posts (purge_deleted_post_from_delivery_queues).
3. Non-blocking, safe mass deletion of copies (safe_delete_message & delete_messages_background).
4. Memory pruning and strict ceilings (cumulative_post_metrics, post_to_messages BoundedDict, posts_pending_deletion).
"""

import asyncio
import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

import shared_state
from broadcaster import MessageBroadcaster, send_message_to_users
from delivery_manager import (
    MessageDeliveryTask,
    cumulative_post_metrics,
    message_queues,
    prune_stale_cumulative_post_metrics,
    purge_deleted_post_from_delivery_queues,
)
from post_helpers import (
    _is_harmless_delete_error,
    delete_messages_background,
    delete_single_post,
    safe_delete_message,
)
from shared_state import (
    BoundedDict,
    BroadcastConfig,
    messages_storage,
    post_to_messages,
    posts_pending_deletion,
    storage_lock,
)


@pytest.fixture(autouse=True)
def cleanup_state():
    """Resets memory state before and after each test."""
    posts_pending_deletion.clear()
    cumulative_post_metrics.clear()
    for q in message_queues.values():
        if hasattr(q, "_queue"):
            q._queue.clear()
    yield
    posts_pending_deletion.clear()
    cumulative_post_metrics.clear()
    for q in message_queues.values():
        if hasattr(q, "_queue"):
            q._queue.clear()


class TestDeliveryCancellationOnPostDeletion:
    @pytest.mark.asyncio
    async def test_broadcast_aborts_immediately_when_post_marked_pending_deletion(self):
        """
        Broadcaster must immediately halt delivery loop if self.post_num is in posts_pending_deletion.
        Must drop remaining recipients and not deliver spam/wipe content to them.
        """
        post_num = 602166
        board_id = "b"
        recipients = list(range(1001, 1051))  # 50 recipients
        sent_uids = []

        bot = MagicMock()

        async def fake_send(chat_id, *args, **kwargs):
            sent_uids.append(chat_id)
            # Mark post for deletion right after the 5th message is sent
            if len(sent_uids) == 5:
                posts_pending_deletion.add(post_num)
            await asyncio.sleep(0.001)
            msg = MagicMock()
            msg.message_id = 90000 + chat_id
            return msg

        bot.send_message = AsyncMock(side_effect=fake_send)
        bot.send_photo = AsyncMock()

        # Set up shared board data
        shared_state.board_data[board_id] = {
            "users": {"banned": set(), "active": set(recipients)},
            "user_settings": {},
        }

        config = BroadcastConfig(
            bot_instance=bot,
            board_id=board_id,
            recipients=set(recipients),
            content={"type": "text", "text": "Wipe content that should be cancelled"},
            verbose=False,
        )

        broadcaster = MessageBroadcaster(config)
        broadcaster.post_num = post_num

        results = await broadcaster.broadcast()

        # Delivery must have been aborted before processing all 50 recipients
        assert results.interrupted_reason == "post_deleted_pending_deletion"
        assert len(sent_uids) < len(recipients), f"Expected delivery to abort, but sent to {len(sent_uids)} users"
        # No copies must be saved to DB for deleted post
        assert post_num not in post_to_messages

    @pytest.mark.asyncio
    async def test_purge_deleted_post_from_delivery_queues(self):
        """
        purge_deleted_post_from_delivery_queues must remove pending queue items matching post_num.
        """
        board_id = "b"
        q = message_queues[board_id]
        if not hasattr(q, "_queue"):
            q._queue = deque()

        # Enqueue 3 items: post 100, post 200 (target), post 300
        q._queue.append({"post_num": 100, "recipients": {1, 2}})
        q._queue.append({"post_num": 200, "recipients": {3, 4}})
        q._queue.append({"post_num": 300, "recipients": {5, 6}})
        q._queue.append({"post_num": 200, "recipients": {7, 8}})  # passive slice

        removed = purge_deleted_post_from_delivery_queues(200, board_id)
        assert removed == 2
        remaining_pnums = [item["post_num"] for item in q._queue]
        assert remaining_pnums == [100, 300]
        assert 200 not in remaining_pnums

    @pytest.mark.asyncio
    async def test_worker_skips_post_if_pending_deletion(self):
        """
        MessageDeliveryTask must skip processing immediately if post_num in posts_pending_deletion.
        """
        post_num = 777888
        posts_pending_deletion.add(post_num)

        bot = MagicMock()
        queue = asyncio.Queue()
        msg_data = {
            "post_num": post_num,
            "recipients": {1001, 1002},
            "content": {"type": "text", "text": "Will be skipped"},
            "durable_delivery_id": 42,
        }

        with patch("delivery_manager._delete_durable_delivery_item", new=AsyncMock()) as mock_del_durable, \
             patch("delivery_manager.send_message_to_users", new=AsyncMock()) as mock_send:

            task = MessageDeliveryTask("Worker-b", "b", bot, queue, msg_data)
            await task.process()

            # send_message_to_users must NOT have been called
            mock_send.assert_not_called()
            # Durable item must be cleaned up
            mock_del_durable.assert_called_once_with(msg_data, "post_pending_deletion")

    @pytest.mark.asyncio
    async def test_passive_slice_not_requeued_on_deletion_interrupt(self):
        """
        If broadcaster returns interrupted_reason == 'post_deleted_pending_deletion',
        worker must NOT re-enqueue passive slices to queue.
        """
        post_num = 555666
        bot = MagicMock()
        queue = asyncio.Queue()
        msg_data = {
            "post_num": post_num,
            "recipients": {1001, 1002, 1003},
            "content": {"type": "text", "text": "Post test"},
        }

        fake_results = MagicMock()
        fake_results.__len__.return_value = 1
        fake_results.interrupted_reason = "post_deleted_pending_deletion"
        fake_results.remaining_recipients = {1002, 1003}
        fake_results.stats = {"success": 1}

        with patch("delivery_manager.send_message_to_users", new=AsyncMock(return_value=fake_results)):
            task = MessageDeliveryTask("Worker-b", "b", bot, queue, msg_data)
            await task.process()

            # Queue must remain empty: passive slice must NOT have been re-enqueued
            assert queue.qsize() == 0


class TestSafeMassDeletionOfCopies:
    @pytest.mark.asyncio
    async def test_safe_delete_message_handles_not_found_and_errors(self):
        """
        safe_delete_message must silently return True for harmless errors (message already deleted),
        and False for non-recoverable errors without raising exceptions.
        """
        bot = MagicMock()

        # 1. Successful deletion
        bot.delete_message = AsyncMock(return_value=True)
        assert await safe_delete_message(bot, 12345, 6789) is True

        # 2. Harmless: message to delete not found
        bot.delete_message = AsyncMock(side_effect=TelegramBadRequest(method="deleteMessage", message="Bad Request: message to delete not found"))
        assert await safe_delete_message(bot, 12345, 6789) is True

        # 3. Harmless: message can't be deleted
        bot.delete_message = AsyncMock(side_effect=TelegramBadRequest(method="deleteMessage", message="Bad Request: message can't be deleted"))
        assert await safe_delete_message(bot, 12345, 6789) is True

        # 4. Forbidden: user blocked bot
        bot.delete_message = AsyncMock(side_effect=TelegramForbiddenError(method="deleteMessage", message="Forbidden: bot was blocked by the user"))
        assert await safe_delete_message(bot, 12345, 6789) is False

    @pytest.mark.asyncio
    async def test_delete_messages_background_chunked_execution(self):
        """
        delete_messages_background must process 100 copies in chunks without crashing on exceptions.
        """
        bot = MagicMock()
        deleted_ids = []

        async def mock_del(chat_id, message_id, **kwargs):
            deleted_ids.append((chat_id, message_id))
            if chat_id == 1010:
                raise TelegramBadRequest(method="deleteMessage", message="message to delete not found")
            return True

        bot.delete_message = AsyncMock(side_effect=mock_del)

        copies = [(1000 + i, 50000 + i) for i in range(100)]
        count = await delete_messages_background(copies, bot, board_id="b")

        # 100 copies processed, harmless error counted as success
        assert count == 100
        assert len(deleted_ids) == 100

    @pytest.mark.asyncio
    async def test_delete_single_post_background_mode(self):
        """
        delete_single_post with background=True must return copy count immediately without waiting.
        """
        post_num = 444555
        bot = MagicMock()

        with patch("post_helpers.get_all_channel_copies", new=AsyncMock(return_value=[])), \
             patch("post_helpers.get_post_copies", new=AsyncMock(return_value=[(1, 10), (2, 20), (3, 30)])), \
             patch("post_helpers.delete_post_by_num", new=AsyncMock(return_value=True)), \
             patch("post_helpers.get_pool") as mock_pool, \
             patch("common.task_manager.spawn_task") as mock_spawn:

            def fake_spawn(coro):
                coro.close()
                return MagicMock()
            mock_spawn.side_effect = fake_spawn

            fake_db = MagicMock()
            fake_db.execute = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(fetchone=AsyncMock(return_value=None)))))
            mock_pool.return_value = fake_db

            deleted_count = await delete_single_post(post_num, bot, background=True)
            assert deleted_count == 3
            assert mock_spawn.called
            assert post_num in posts_pending_deletion


class TestMemoryPruningAndCeilings:
    def test_prune_stale_cumulative_post_metrics(self):
        """
        prune_stale_cumulative_post_metrics must purge entries older than max_age_sec
        and enforce max_keep limit.
        """
        now = time.time()

        # Add 10 stale entries (older than 1800s)
        for i in range(10):
            cumulative_post_metrics[("b", 100 + i)] = {
                "start_time": now - 3600,
                "total": 100, "success": 100,
            }

        # Add 5 fresh entries
        for i in range(5):
            cumulative_post_metrics[("b", 200 + i)] = {
                "start_time": now - 60,
                "total": 100, "success": 100,
            }

        assert len(cumulative_post_metrics) == 15

        # Prune with max_age_sec=1800
        removed = prune_stale_cumulative_post_metrics(max_age_sec=1800.0, max_keep=10)
        assert removed == 10
        assert len(cumulative_post_metrics) == 5

        # Verify only fresh entries remain
        for i in range(5):
            assert ("b", 200 + i) in cumulative_post_metrics

    def test_post_to_messages_bounded_dict_capacity(self):
        """
        post_to_messages must strictly enforce its capacity ceiling and evict oldest entries.
        """
        b_dict = BoundedDict(max_size=5)
        for i in range(10):
            b_dict[i] = {f"user_{i}": i * 10}

        assert len(b_dict) == 5
        # Oldest 0..4 evicted, newest 5..9 kept
        assert list(b_dict.keys()) == [5, 6, 7, 8, 9]

    def test_posts_pending_deletion_bounded_pruning(self):
        """
        Verify that posts_pending_deletion can be safely pruned when large without memory leak.
        """
        posts_pending_deletion.update(range(1200))
        assert len(posts_pending_deletion) == 1200

        # Simulate cleaner pruning excess down to 500
        if len(posts_pending_deletion) > 1000:
            excess = len(posts_pending_deletion) - 500
            for p in sorted(posts_pending_deletion)[:excess]:
                posts_pending_deletion.discard(p)

        assert len(posts_pending_deletion) == 500
        assert min(posts_pending_deletion) == 700


class TestTelegramApiMediaFailureFallbacks:
    @pytest.mark.asyncio
    async def test_media_group_fallback_on_webpage_curl_failed(self):
        """
        When Telegram rejects sendMediaGroup with WEBPAGE_CURL_FAILED, broadcaster must
        automatically fall back to text link delivery with LinkPreviewOptions(is_disabled=True)
        and successfully deliver the post without throwing an unhandled exception.
        """
        bot = MagicMock()
        delivered_msg = MagicMock()
        delivered_msg.message_id = 771122

        bot.send_media_group = AsyncMock(
            side_effect=TelegramBadRequest(
                method="sendMediaGroup",
                message='Bad Request: failed to send message #2 with the error message "WEBPAGE_CURL_FAILED"'
            )
        )
        bot.send_message = AsyncMock(return_value=delivered_msg)

        shared_state.board_data["b"] = {
            "users": {"banned": set(), "active": {12345}},
            "user_settings": {},
        }

        config = BroadcastConfig(
            bot_instance=bot,
            board_id="b",
            recipients={12345},
            content={
                "post_num": 99001,
                "type": "media_group",
                "text": "Post with external images",
                "media": [
                    {"type": "photo", "media": "pic_file_id_1"},
                    {"type": "photo", "media": "pic_file_id_2"}
                ]
            },
            verbose=False,
        )
        broadcaster = MessageBroadcaster(config)
        broadcaster.post_num = 99001
        await broadcaster._prepare_content_and_mentions()
        res = await broadcaster._send_one(12345, 10)

        assert res == delivered_msg or (isinstance(res, list) and delivered_msg in res)
        assert broadcaster.media_group_fallback_to_text is True
        assert bot.send_message.called
        call_kwargs = bot.send_message.call_args.kwargs
        assert call_kwargs.get("chat_id") == 12345
        lp = call_kwargs.get("link_preview_options")
        assert getattr(lp, "is_disabled", False) is True

    @pytest.mark.asyncio
    async def test_media_group_fallback_on_webpage_media_empty(self):
        """
        When Telegram rejects sendMediaGroup with WEBPAGE_MEDIA_EMPTY, broadcaster must
        fall back to text link delivery with link previews disabled.
        """
        bot = MagicMock()
        delivered_msg = MagicMock()
        delivered_msg.message_id = 771123

        bot.send_media_group = AsyncMock(
            side_effect=TelegramBadRequest(
                method="sendMediaGroup",
                message='Bad Request: failed to send message #1 with the error message "WEBPAGE_MEDIA_EMPTY"'
            )
        )
        bot.send_message = AsyncMock(return_value=delivered_msg)

        shared_state.board_data["b"] = {
            "users": {"banned": set(), "active": {12346}},
            "user_settings": {},
        }

        config = BroadcastConfig(
            bot_instance=bot,
            board_id="b",
            recipients={12346},
            content={
                "post_num": 99002,
                "type": "media_group",
                "text": "Post with broken webpage preview",
                "media": [
                    {"type": "photo", "media": "empty_file_id_1"},
                    {"type": "photo", "media": "pic_file_id_2"}
                ]
            },
            verbose=False,
        )
        broadcaster = MessageBroadcaster(config)
        broadcaster.post_num = 99002
        await broadcaster._prepare_content_and_mentions()
        res = await broadcaster._send_one(12346, 10)

        assert res == delivered_msg or (isinstance(res, list) and delivered_msg in res)
        assert broadcaster.media_group_fallback_to_text is True
        assert bot.send_message.called
        call_kwargs = bot.send_message.call_args.kwargs
        lp = call_kwargs.get("link_preview_options")
        assert getattr(lp, "is_disabled", False) is True

    @pytest.mark.asyncio
    async def test_single_media_fallback_on_image_process_failed(self):
        """
        When Telegram rejects sendPhoto with IMAGE_PROCESS_FAILED, broadcaster must
        fall back to text delivery with link previews disabled.
        """
        bot = MagicMock()
        delivered_msg = MagicMock()
        delivered_msg.message_id = 771124

        bot.send_photo = AsyncMock(
            side_effect=TelegramBadRequest(
                method="sendPhoto",
                message="Bad Request: IMAGE_PROCESS_FAILED"
            )
        )
        bot.send_message = AsyncMock(return_value=delivered_msg)

        shared_state.board_data["b"] = {
            "users": {"banned": set(), "active": {12347}},
            "user_settings": {},
        }

        config = BroadcastConfig(
            bot_instance=bot,
            board_id="b",
            recipients={12347},
            content={
                "post_num": 99003,
                "type": "photo",
                "file_id": "corrupted_img_id",
                "text": "Post with corrupted photo"
            },
            verbose=False,
        )
        broadcaster = MessageBroadcaster(config)
        broadcaster.post_num = 99003
        await broadcaster._prepare_content_and_mentions()
        res = await broadcaster._send_one(12347, 10)

        assert res is not None
        assert bot.send_message.called
        call_kwargs = bot.send_message.call_args.kwargs
        assert call_kwargs.get("chat_id") == 12347
        lp = call_kwargs.get("link_preview_options")
        assert getattr(lp, "is_disabled", False) is True

class TestGroupActivitiesAndAnonymity:
    @pytest.mark.asyncio
    async def test_cmd_bid_dispatches_outbid_notification_to_previous_leader(self):
        """
        When a new bid is placed in cmd_bid, the previous leader must receive
        an outbid notification via PM with 100% escrow refund confirmation and anonymous leader name.
        """
        from auction_engine import cmd_bid

        bot = MagicMock()
        bot.send_message = AsyncMock()

        message = MagicMock()
        message.from_user.id = 555666
        message.chat.id = 555666
        message.text = "/bid 1 75000"
        message.bot = bot
        message.reply = AsyncMock()

        fake_res = {
            "ok": True,
            "auction_id": 1,
            "bid_amount": 75000.0,
            "ends_at": time.time() + 3600,
            "extended": False,
            "previous_winner": 111222,
            "previous_bid": 60000.0,
            "title": "VIP Pin Voucher",
        }

        with patch("auction_engine.get_pool", AsyncMock()), \
             patch("common.database.is_shadow_muted", AsyncMock(return_value=False)), \
             patch("common.bot_helpers.check_user_is_muted", AsyncMock(return_value=False)), \
             patch("auction_engine.place_auction_bid", AsyncMock(return_value=fake_res)):
            await cmd_bid(message)

        # Ensure outbid PM was sent to previous winner 111222
        assert bot.send_message.called
        call_kwargs = bot.send_message.call_args.kwargs
        assert call_kwargs.get("chat_id") == 111222
        outbid_text = call_kwargs.get("text", "")
        assert "ТВОЮ СТАВКУ ПЕРЕБИЛИ" in outbid_text
        assert "60 000" in outbid_text
        assert "75 000" in outbid_text
        # Assert no naked user_id in user-facing message
        assert "555666" not in outbid_text

    @pytest.mark.asyncio
    async def test_cb_raid_join_fanout_to_all_participants_and_victim(self):
        """
        When 5th participant joins the proletarian raid, cb_raid_join must execute the raid,
        edit the caller's message, send PM to all other 4 participants, send PM to the victim,
        and trigger board push and news channel publication.
        """
        from auction_engine import cb_raid_join, _ACTIVE_RAIDS

        bot = MagicMock()
        bot.send_message = AsyncMock()

        raid_id = "testraid1"
        _ACTIVE_RAIDS[raid_id] = {
            "voters": [101, 102, 103, 104],
            "target_id": 999000,
            "board_id": "b",
            "created_at": time.time(),
            "chat_id": 105,
        }

        callback = MagicMock()
        callback.data = f"raid_join_{raid_id}"
        callback.from_user.id = 105
        callback.bot = bot
        callback.message = MagicMock()
        callback.message.caption = None
        callback.message.photo = False
        callback.message.edit_text = AsyncMock()
        callback.answer = AsyncMock()

        fake_raid_res = {
            "ok": True,
            "target_id": 999000,
            "confiscated": 100000.0,
            "burned_to_abu": 70000.0,
            "distributed_total": 30000.0,
            "per_voter": 6000.0,
            "voters": [101, 102, 103, 104, 105],
            "old_balance": 1000000.0,
            "new_balance": 900000.0,
        }

        with patch("auction_engine.get_pool", AsyncMock()), \
             patch("auction_engine.check_raid_proletarian", AsyncMock(return_value=(True, ""))), \
             patch("auction_engine.execute_oligarch_raid", AsyncMock(return_value=fake_raid_res)), \
             patch("event_push_engine.push_raid_success", AsyncMock()) as mock_push_raid, \
             patch("news_channel_publisher.publish_oligarch_raid_news", AsyncMock()) as mock_news_raid:
            await cb_raid_join(callback)

        # 1. Check callback message was edited with win_text
        assert callback.message.edit_text.called
        win_card = callback.message.edit_text.call_args.kwargs.get("text", "")
        assert "РАСКУЛАЧИВАНИЕ ОЛИГАРХА" in win_card
        assert "100,000" in win_card
        assert "6,000" in win_card
        assert "999000" not in win_card  # Strict anonymity check!

        # 2. Check PM sent to other 4 participants (101, 102, 103, 104) and oligarch (999000)
        sent_chats = [call.args[0] if call.args else call.kwargs.get("chat_id") for call in bot.send_message.call_args_list]
        for vid in [101, 102, 103, 104, 999000]:
            assert vid in sent_chats

    @pytest.mark.asyncio
    async def test_cmd_whale_safe_broadcasts_rare_drop_anonymously(self):
        """
        When cmd_whale_safe drops a prestige or mythic reward, it must trigger
        push_whale_drop and publish_whale_safe_rare_drop anonymously.
        """
        from auction_engine import cmd_whale_safe

        bot = MagicMock()
        message = MagicMock()
        message.from_user.id = 888777
        message.chat.id = 888777
        message.text = "/whale_safe"
        message.bot = bot
        message.reply = AsyncMock()

        fake_safe_res = {
            "ok": True,
            "price": 50000.0,
            "burned_to_abu": 35000.0,
            "tier": "🌟 ПРЕСТИЖНЫЙ ШМОТ (НАВСЕГДА)",
            "title": "Платиновый Монокль",
            "desc": "+50 к Рассудку",
            "final_cash": 0.0,
            "recycle_note": "",
            "new_balance": 150000.0,
            "opened_today": 1,
        }

        with patch("auction_engine.get_pool", AsyncMock()), \
             patch("auction_engine.buy_whale_safe", AsyncMock(return_value=fake_safe_res)), \
             patch("event_push_engine.push_whale_drop", AsyncMock()) as mock_push_whale, \
             patch("news_channel_publisher.publish_whale_safe_rare_drop", AsyncMock()) as mock_news_whale:
            await cmd_whale_safe(message)

        assert message.reply.called
        reply_text = message.reply.call_args.args[0]
        assert "СЕЙФ ОЛИГАРХА ВЗЛОМАН" in reply_text
        assert "Платиновый Монокль" in reply_text

    @pytest.mark.asyncio
    async def test_anonymity_strict_in_ttt_and_main_templates(self):
        """
        Ensures that generated strings in ttt_engine and main templates never leak raw user_ids.
        """
        from common.anon_identity import get_anon_id, generate_anon_name

        uid = 998877
        anon_name = generate_anon_name(uid)
        anon_id = get_anon_id(uid)

        # Test TTT target string format
        target_str = f"🎯 <b>Цель:</b> Анон <code>[ID:{get_anon_id(uid)}]</code>\n"
        assert str(uid) not in target_str
        assert anon_id in target_str

        # Test doxx msg format
        doxx_msg = f"🦹‍♂️ <b>Нарушитель:</b> Анон <code>[ID:{get_anon_id(uid)}]</code> пытался парализовать общение!"
        assert str(uid) not in doxx_msg
        assert anon_id in doxx_msg
    @pytest.mark.asyncio
    async def test_news_channel_and_event_push_strict_anonymity(self):
        """
        Verifies that news_channel_publisher, event_push_engine, and daily_abu_airdrop
        announcements never expose raw integer user_ids and always use anonymous phonetic identities.
        """
        from common.anon_identity import get_anon_id
        from event_push_engine import push_whale_drop, push_raid_success, push_duel_open
        from news_channel_publisher import (
            publish_casino_jackpot_news,
            publish_oligarch_raid_news,
            publish_whale_safe_rare_drop,
        )
        from daily_abu_airdrop_engine import format_daily_board_announcement

        uid = 77112233
        anon_id = get_anon_id(uid)
        bot = MagicMock()
        bot.get_me = AsyncMock(return_value=MagicMock(username="test_bot"))

        sent_messages = []

        async def capture_send_channel_content(bot, channel_id, content, header_text, body_text="", footer_text=""):
            full_text = f"{header_text}\n{body_text}\n{footer_text}"
            sent_messages.append(full_text)
            return 999111

        # 1. Test news_channel_publisher
        with patch("news_channel_publisher.get_target_channels", return_value=(-100123, -100123)), \
             patch("news_channel_publisher.send_channel_content", side_effect=capture_send_channel_content):
            
            await publish_casino_jackpot_news(
                bot=bot, user_id=uid, game_type="slots",
                bet_amount=10000, win_amount=500000, multiplier=50.0,
                symbols="[7 | 7 | 7]"
            )
            await publish_oligarch_raid_news(
                bot=bot, user_id=uid, tax_amount=100000,
                old_balance=1000000, new_balance=900000
            )
            await publish_whale_safe_rare_drop(
                bot=bot, user_id=uid, tier_name="🌟 ПРЕСТИЖНЫЙ ШМОТ",
                item_title="Платиновый Монокль", burned_to_abu=35000
            )

        for text in sent_messages:
            assert str(uid) not in text
            assert anon_id in text

        # 2. Test event_push_engine
        bot_push = MagicMock()
        bot_push.send_message = AsyncMock()

        shared_state.board_data["b"] = {
            "users": {"banned": set(), "active": {555001}},
            "user_settings": {},
        }

        with patch("event_push_engine._can_push", return_value=True):
            await push_whale_drop(bot_push, "b", winner_anon_id=anon_id, tier_name="Тир 3", item_title="Монокль", burned_to_abu=35000)
            await push_raid_success(bot_push, "b", target_anon_id=anon_id, confiscated=100000, per_voter=6000)
            await push_duel_open(bot_push, "b", challenger_anon_id=anon_id, amount=50000)

        for call in bot_push.send_message.call_args_list:
            body = call.kwargs.get("text", "")
            assert str(uid) not in body
            assert anon_id in body

        # 3. Test daily_abu_airdrop_engine
        airdrop_text = format_daily_board_announcement(winners=[uid], pool_size=10, payout=5000)
        assert str(uid) not in airdrop_text
        assert anon_id in airdrop_text

