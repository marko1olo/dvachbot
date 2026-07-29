import unittest
import asyncio
import os
from unittest.mock import patch, AsyncMock, MagicMock

from common.database import delete_post_by_num, _THREAD_CACHE, _VIDEO_CACHE, _IMAGE_CACHE

class TestDatabase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ["DB_NAME"] = ":memory:"
        _THREAD_CACHE.clear()
        _VIDEO_CACHE.clear()
        _IMAGE_CACHE.clear()

        _THREAD_CACHE['board1'].append('10')
        _THREAD_CACHE['board2'].append('20')
        _VIDEO_CACHE['board1'].append((10, "vid1"))
        _VIDEO_CACHE['board1'].append((20, "vid2"))
        _IMAGE_CACHE['board2'].append((20, "img1"))
        _IMAGE_CACHE['board2'].append((30, "img2"))

    @patch('common.db_pool.get_pool')
    async def test_delete_post_by_num_thread(self, mock_get_pool):
        # We need an AsyncContextManager for db.execute, and await db.execute for DELETE

        class MockDB:
            def __init__(self):
                self.calls = []

            def execute(self, query, params=None):
                self.calls.append((query, params))
                # For SELECT 1 FROM Threads, we need to return a cursor as an async context manager
                class AsyncContextManagerMock:
                    async def __aenter__(self):
                        cursor = AsyncMock()
                        # If query is select, return (1,) to simulate thread
                        if "SELECT 1 FROM Threads" in query:
                            cursor.fetchone.return_value = (1,)
                        else:
                            cursor.fetchone.return_value = None
                        return cursor
                    async def __aexit__(self, exc_type, exc_val, exc_tb):
                        pass

                    def __await__(self):
                        # Some executes are awaited directly (like DELETE and COMMIT)
                        async def dummy():
                            return None
                        return dummy().__await__()
                return AsyncContextManagerMock()

        mock_db = MockDB()
        mock_get_pool.return_value = mock_db

        res = await delete_post_by_num(20)
        self.assertTrue(res)

        self.assertNotIn('20', _THREAD_CACHE['board2'])
        self.assertNotIn((20, "vid2"), _VIDEO_CACHE['board1'])
        self.assertNotIn((20, "img1"), _IMAGE_CACHE['board2'])

if __name__ == '__main__':
    unittest.main()
