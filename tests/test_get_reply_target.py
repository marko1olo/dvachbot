import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import types
import economy_extension

class TestGetReplyTarget(unittest.IsolatedAsyncioTestCase):
    async def test_no_reply_to_message(self):
        message = MagicMock(spec=types.Message)
        message.reply_to_message = None
        result = await economy_extension.get_reply_target(message)
        self.assertIsNone(result)

    @patch("aiosqlite.connect")
    async def test_successful_query(self, mock_connect):
        message = MagicMock(spec=types.Message)
        message.reply_to_message = MagicMock()
        message.chat = MagicMock()
        message.chat.id = 123
        message.reply_to_message.message_id = 456

        mock_db = MagicMock()

        # Setup for aiosqlite.connect (matches prompt snippet)
        mock_connect_context = AsyncMock()
        mock_connect_context.__aenter__.return_value = mock_db
        mock_connect.return_value = mock_connect_context

        # Setup for actual codebase (economy_extension.get_pool)
        original_get_pool = getattr(economy_extension, "get_pool", None)
        if original_get_pool:
            economy_extension.get_pool = AsyncMock(return_value=mock_db)

        try:
            mock_cursor = AsyncMock()
            mock_cursor.fetchone.return_value = (789,)

            mock_execute_context = AsyncMock()
            mock_execute_context.__aenter__.return_value = mock_cursor
            mock_db.execute.return_value = mock_execute_context

            result = await economy_extension.get_reply_target(message)

            self.assertEqual(result, 789)
            mock_db.execute.assert_called_once_with(
                "SELECT author_id FROM PostCopies JOIN Posts ON PostCopies.post_num = Posts.post_num WHERE recipient_id = ? AND message_id = ?",
                (123, 456)
            )
        finally:
            if original_get_pool:
                economy_extension.get_pool = original_get_pool

    @patch("aiosqlite.connect")
    async def test_no_row_found(self, mock_connect):
        message = MagicMock(spec=types.Message)
        message.reply_to_message = MagicMock()

        mock_db = MagicMock()
        mock_connect_context = AsyncMock()
        mock_connect_context.__aenter__.return_value = mock_db
        mock_connect.return_value = mock_connect_context

        original_get_pool = getattr(economy_extension, "get_pool", None)
        if original_get_pool:
            economy_extension.get_pool = AsyncMock(return_value=mock_db)

        try:
            mock_cursor = AsyncMock()
            mock_cursor.fetchone.return_value = None

            mock_execute_context = AsyncMock()
            mock_execute_context.__aenter__.return_value = mock_cursor
            mock_db.execute.return_value = mock_execute_context

            result = await economy_extension.get_reply_target(message)

            self.assertIsNone(result)
        finally:
            if original_get_pool:
                economy_extension.get_pool = original_get_pool

    @patch("aiosqlite.connect")
    async def test_exception_handling(self, mock_connect):
        message = MagicMock(spec=types.Message)
        message.reply_to_message = MagicMock()

        mock_connect.side_effect = Exception("DB error")

        original_get_pool = getattr(economy_extension, "get_pool", None)
        if original_get_pool:
            economy_extension.get_pool = AsyncMock(side_effect=Exception("DB error"))

        try:
            result = await economy_extension.get_reply_target(message)
            self.assertIsNone(result)
        finally:
            if original_get_pool:
                economy_extension.get_pool = original_get_pool

if __name__ == "__main__":
    unittest.main()
