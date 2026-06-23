import sys
import unittest
from pathlib import Path
from datetime import datetime, UTC

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# We can import main, but main.py might execute code on import.
# Let's inspect main.py imports or if it can be imported safely.
# Wait, does main.py run the bot on import?
# Usually, main.py defines the bot and runs it inside `if __name__ == '__main__':` or `asyncio.run(...)`.
# Let's verify. Yes, it starts the polling inside `if __name__ == '__main__':`.
import main

class TestBatchReplies(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Backup original messages_storage
        self.original_storage = main.messages_storage.copy()
        main.messages_storage.clear()

    async def asyncTearDown(self):
        # Restore original messages_storage
        main.messages_storage.clear()
        main.messages_storage.update(self.original_storage)

    async def test_get_board_chunk_includes_replies_ru(self):
        # Post 1: regular post
        main.messages_storage[100] = {
            'author_id': 12345,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'content': {
                'type': 'text',
                'text': 'First post text',
                'name': 'Anon1'
            }
        }
        # Post 2: reply using reply_to_post inside content
        main.messages_storage[101] = {
            'author_id': 67890,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'content': {
                'type': 'text',
                'text': 'Reply text',
                'reply_to_post': 100
            }
        }
        # Post 3: reply using reply_to_post_num in outer dict
        main.messages_storage[102] = {
            'author_id': 11111,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'reply_to_post_num': 100,
            'content': {
                'type': 'text',
                'text': 'Another reply',
            }
        }

        chunk = await main.get_board_chunk('b', hours=1)
        
        # Verify formats:
        # Anon1: First post text
        # Анон #7890 (Ответ на #100): Reply text
        # Анон #1111 (Ответ на #100): Another reply
        self.assertIn("Anon1: First post text", chunk)
        self.assertIn("Анон #7890 (Ответ на #100): Reply text", chunk)
        self.assertIn("Анон #1111 (Ответ на #100): Another reply", chunk)

    async def test_get_board_chunk_includes_replies_en(self):
        # Post on English board 'int'
        main.messages_storage[200] = {
            'author_id': 99999,
            'timestamp': datetime.now(UTC),
            'board_id': 'int',
            'content': {
                'type': 'text',
                'text': 'Hello world',
                'name': 'AnonInt'
            }
        }
        main.messages_storage[201] = {
            'author_id': 88888,
            'timestamp': datetime.now(UTC),
            'board_id': 'int',
            'content': {
                'type': 'text',
                'text': 'Reply hello',
                'reply_to_post': 200
            }
        }

        chunk = await main.get_board_chunk('int', hours=1)
        self.assertIn("AnonInt: Hello world", chunk)
        self.assertIn("Anon #8888 (reply to #200): Reply hello", chunk)

if __name__ == '__main__':
    unittest.main()
