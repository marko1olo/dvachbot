import unittest
from unittest.mock import patch, AsyncMock
import asyncio
import json
import aiosqlite

from common.database import toggle_post_censorship

class TestTogglePostCensorship(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(':memory:', isolation_level=None)
        await self.db.execute("CREATE TABLE Posts (post_num INTEGER, content TEXT)")

        self.dummy_lock = asyncio.Lock()

        self.patcher_get_pool = patch('common.db_pool.get_pool', return_value=self.db)
        self.patcher_db_lock = patch('common.db_pool.db_lock', self.dummy_lock)

        self.mock_get_pool = self.patcher_get_pool.start()
        self.patcher_db_lock.start()

    async def asyncTearDown(self):
        await self.db.close()
        self.patcher_get_pool.stop()
        self.patcher_db_lock.stop()

    async def test_toggle_non_existent_post(self):
        result = await toggle_post_censorship(1)
        self.assertFalse(result)

    async def test_toggle_existing_post_no_censored_flag(self):
        initial_content = {"text": "hello", "type": "text"}
        await self.db.execute("INSERT INTO Posts (post_num, content) VALUES (?, ?)", (2, json.dumps(initial_content)))

        result = await toggle_post_censorship(2)
        self.assertTrue(result)

        async with self.db.execute("SELECT content FROM Posts WHERE post_num = 2") as cursor:
            row = await cursor.fetchone()

        updated_content = json.loads(row[0])
        self.assertTrue(updated_content.get('is_censored'))

    async def test_toggle_existing_post_already_censored(self):
        initial_content = {"text": "hello", "type": "text", "is_censored": True}
        await self.db.execute("INSERT INTO Posts (post_num, content) VALUES (?, ?)", (3, json.dumps(initial_content)))

        result = await toggle_post_censorship(3)
        self.assertFalse(result)

        async with self.db.execute("SELECT content FROM Posts WHERE post_num = 3") as cursor:
            row = await cursor.fetchone()

        updated_content = json.loads(row[0])
        self.assertFalse(updated_content.get('is_censored'))

    async def test_toggle_existing_post_invalid_json(self):
        await self.db.execute("INSERT INTO Posts (post_num, content) VALUES (?, ?)", (4, "invalid json"))

        result = await toggle_post_censorship(4)
        self.assertTrue(result)

        async with self.db.execute("SELECT content FROM Posts WHERE post_num = 4") as cursor:
            row = await cursor.fetchone()

        updated_content = json.loads(row[0])
        self.assertTrue(updated_content.get('is_censored'))
        self.assertEqual(updated_content.get('text'), "")

    async def test_retry_on_locked_db(self):
        # We need to simulate a locked database on update
        initial_content = {"text": "hello", "type": "text"}
        await self.db.execute("INSERT INTO Posts (post_num, content) VALUES (?, ?)", (5, json.dumps(initial_content)))

        # We need a mock for db.execute that fails a couple of times with "database is locked"
        # and then succeeds on the 3rd try. Since db is returned by get_pool, we can patch its execute method.
        original_execute = self.db.execute
        call_count = 0



        def mock_execute(query, *args, **kwargs):
            nonlocal call_count
            if query.startswith("UPDATE Posts"):
                call_count += 1
                if call_count <= 2:
                    import sqlite3
                    async def async_raise():
                        raise sqlite3.OperationalError("database is locked")
                    return async_raise()
            return original_execute(query, *args, **kwargs)


        with patch.object(self.db, 'execute', side_effect=mock_execute):
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                result = await toggle_post_censorship(5)

                self.assertTrue(result)
                self.assertEqual(call_count, 3)
                self.assertEqual(mock_sleep.call_count, 2)

    async def test_break_on_other_error(self):
        initial_content = {"text": "hello", "type": "text"}
        await self.db.execute("INSERT INTO Posts (post_num, content) VALUES (?, ?)", (6, json.dumps(initial_content)))

        original_execute = self.db.execute



        def mock_execute(query, *args, **kwargs):
            if query.startswith("UPDATE Posts"):
                async def async_raise():
                    raise ValueError("Unexpected error")
                return async_raise()
            return original_execute(query, *args, **kwargs)

        with patch.object(self.db, 'execute', side_effect=mock_execute):
            result = await toggle_post_censorship(6)
            self.assertFalse(result)
