import asyncio
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, r'C:\Users\danat\Desktop\dvachbot')
sys.stdout.reconfigure(encoding='utf-8')

import shared_state
import handlers.message_router as mr

class TestMessageRouterFullSimulation(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.bot = AsyncMock()
        self.bot.id = 123456789
        self.bot.token = "123456:ABCdefGHIjklMNOpqrsTUVwxyz"
        
        self.user = MagicMock()
        self.user.id = 5780136258
        self.user.username = "test_user"
        self.user.first_name = "Test"
        
        self.chat = MagicMock()
        self.chat.id = 5780136258
        self.chat.type = "private"

    def _create_mock_message(self, content_type="text", text="Hello", caption=None):
        msg = AsyncMock()
        msg.content_type = content_type
        msg.text = text
        msg.caption = caption
        msg.html_text = text
        msg.caption_html_text = caption
        msg.from_user = self.user
        msg.chat = self.chat
        msg.message_id = 1001
        msg.reply_to_message = None
        msg.media_group_id = None
        msg.bot = self.bot
        return msg

    async def test_text_message(self):
        msg = self._create_mock_message("text", "Тестовое обычное сообщение")
        print("Testing text message...")
        await mr.handle_message(msg, board_id="b", stream="ru")
        print("SUCCESS: text message processed.")

    async def test_sage_message(self):
        msg = self._create_mock_message("text", "sage сажа сбрасываем бамп")
        print("Testing sage message...")
        await mr.handle_message(msg, board_id="b", stream="ru")
        print("SUCCESS: sage message processed.")

    async def test_photo_message(self):
        msg = self._create_mock_message("photo", None, "Тестовая подпись к фото")
        photo_size = MagicMock()
        photo_size.file_id = "photo_file_id_123"
        photo_size.file_unique_id = "photo_unique_123"
        msg.photo = [photo_size]
        print("Testing photo message...")
        await mr.handle_message(msg, board_id="b", stream="ru")
        print("SUCCESS: photo message processed.")

    async def test_sticker_message(self):
        msg = self._create_mock_message("sticker", None, None)
        msg.sticker = MagicMock()
        msg.sticker.file_id = "sticker_123"
        msg.sticker.file_unique_id = "sticker_uniq_123"
        print("Testing sticker message...")
        await mr.handle_message(msg, board_id="b", stream="ru")
        print("SUCCESS: sticker message processed.")

    async def test_dice_message(self):
        msg = self._create_mock_message("dice", None, None)
        print("Testing dice message...")
        await mr.handle_message(msg, board_id="b", stream="ru")
        print("SUCCESS: dice message processed.")

    async def test_check_spam(self):
        msg = self._create_mock_message("text", "Тест спам проверки")
        res = await mr.check_spam(self.user.id, msg, "b")
        print(f"SUCCESS: check_spam returned {res}")
        self.assertTrue(res)

if __name__ == "__main__":
    unittest.main()
