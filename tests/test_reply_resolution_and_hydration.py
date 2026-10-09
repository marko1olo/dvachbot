import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from shared_state import (
    messages_storage,
    post_to_messages,
    message_to_post,
    _trim_post_copy_maps_unlocked,
    BroadcastConfig,
)
from common.config import BOT_POST_CACHE_LIMIT, BOT_COPY_CACHE_POST_LIMIT, BOT_MESSAGE_TO_POST_LIMIT
from common.database import get_post_info_by_copy


class TestReplyResolutionAndHydration(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.orig_storage = messages_storage.copy()
        self.orig_post_to_messages = post_to_messages.copy()
        self.orig_message_to_post = message_to_post.copy()

    def tearDown(self):
        messages_storage.clear()
        messages_storage.update(self.orig_storage)
        post_to_messages.clear()
        post_to_messages.update(self.orig_post_to_messages)
        message_to_post.clear()
        message_to_post.update(self.orig_message_to_post)

    def test_config_limits(self):
        """Verify increased RAM limits for posts and copies."""
        self.assertGreaterEqual(BOT_POST_CACHE_LIMIT, 2000)
        self.assertGreaterEqual(BOT_COPY_CACHE_POST_LIMIT, 1000)
        self.assertGreaterEqual(BOT_MESSAGE_TO_POST_LIMIT, 50000)
        self.assertEqual(message_to_post.max_size, BOT_MESSAGE_TO_POST_LIMIT)

    def test_bounded_dict_capacity_and_decoupled_trim(self):
        """Verify BoundedDict retains mappings when post_to_messages is trimmed."""
        post_to_messages.clear()
        message_to_post.clear()

        # Add 10 posts with copies
        for pnum in range(1, 11):
            post_to_messages[pnum] = {1000 + pnum: 2000 + pnum}
            message_to_post[(1000 + pnum, 2000 + pnum)] = pnum

        self.assertEqual(len(post_to_messages), 10)
        self.assertEqual(len(message_to_post), 10)

        # Trim post_to_messages to keep only 5
        trimmed_posts, _ = _trim_post_copy_maps_unlocked(5)
        self.assertEqual(trimmed_posts, 5)
        self.assertEqual(len(post_to_messages), 5)

        # message_to_post must retain all 10 mappings (decoupled LRU bounded dict)
        self.assertEqual(len(message_to_post), 10)
        for pnum in range(1, 11):
            self.assertEqual(message_to_post.get((1000 + pnum, 2000 + pnum)), pnum)

    async def test_get_post_info_by_copy_postcopies(self):
        """Verify get_post_info_by_copy resolves from PostCopies."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone = AsyncMock(return_value=(540100, 777))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)

        mock_db = MagicMock()
        mock_db.execute.return_value = mock_cursor

        with patch("common.db_pool.get_pool", new_callable=AsyncMock, return_value=mock_db):
            res = await get_post_info_by_copy(12345, 99999)
            self.assertEqual(res, (540100, 777))

    async def test_get_post_info_by_copy_channelcopies_fallback(self):
        """Verify get_post_info_by_copy falls back to ChannelCopies if not in PostCopies."""
        cursor_pc = MagicMock()
        cursor_pc.fetchone = AsyncMock(return_value=None)
        cursor_pc.__aenter__ = AsyncMock(return_value=cursor_pc)
        cursor_pc.__aexit__ = AsyncMock(return_value=None)

        cursor_cc = MagicMock()
        cursor_cc.fetchone = AsyncMock(return_value=(540200, 888))
        cursor_cc.__aenter__ = AsyncMock(return_value=cursor_cc)
        cursor_cc.__aexit__ = AsyncMock(return_value=None)

        mock_db = MagicMock()
        mock_db.execute.side_effect = [cursor_pc, cursor_cc]

        with patch("common.db_pool.get_pool", new_callable=AsyncMock, return_value=mock_db):
            res = await get_post_info_by_copy(-1002827087363, 55555)
            self.assertEqual(res, (540200, 888))

    async def test_broadcaster_reply_coverage_from_db(self):
        """Verify broadcaster dynamically fetches DB copies and hydrates RAM when replying to an evicted post."""
        from broadcaster import MessageBroadcaster

        shared_state.board_data['b'] = {
            'user_settings': {},
            'users': {'active': {111, 222, 333}, 'banned': set()},
        }

        # Target post 530000 was evicted from RAM (not in messages_storage or post_to_messages)
        messages_storage.clear()
        post_to_messages.clear()
        message_to_post.clear()

        db_post_data = {
            'post_num': 530000,
            'author_id': 111,
            'content': {'text': 'Old parent post'},
            'board_id': 'b',
            'thread_id': None,
            'timestamp': 1790000000.0,
            'reply_to_post_num': None
        }
        db_copies_data = [
            (111, 201),  # author copy
            (222, 202),  # recipient 222 copy
            (333, 203),  # recipient 333 copy
        ]

        with patch("broadcaster.get_post_by_num", new_callable=AsyncMock, return_value=db_post_data), \
             patch("broadcaster.get_post_copies", new_callable=AsyncMock, return_value=db_copies_data):

            config = BroadcastConfig(
                bot_instance=AsyncMock(),
                board_id='b',
                recipients={222, 333},
                content={'type': 'text', 'text': 'Reply to old post', 'reply_to_post': 530000},
                reply_info=None
            )

            bc = MessageBroadcaster(config)
            await bc._prepare_content_and_mentions()

            # Verify messages_storage was dynamically hydrated with parent post
            self.assertIn(530000, messages_storage)
            self.assertEqual(messages_storage[530000]['author_id'], 111)

            # Verify db_replies_map was populated from get_post_copies
            self.assertEqual(bc.db_replies_map.get(111), 201)
            self.assertEqual(bc.db_replies_map.get(222), 202)
            self.assertEqual(bc.db_replies_map.get(333), 203)

            # Verify post_to_messages and message_to_post were cached
            self.assertIn(530000, post_to_messages)
            self.assertEqual(post_to_messages[530000].get(222), 202)
            self.assertEqual(message_to_post.get((222, 202)), 530000)


if __name__ == "__main__":
    unittest.main()
