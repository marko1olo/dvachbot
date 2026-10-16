import unittest
import asyncio
from common.thread_manager import (
    set_thread_info,
    delete_thread_data,
    acquire_thread_lock,
    _threads_data,
    _thread_locks
)

class TestThreadManager(unittest.TestCase):
    def setUp(self):
        # Clear global state for isolated tests
        _threads_data.clear()
        _thread_locks.clear()

    def test_delete_thread_data(self):
        board_id = "b"
        thread_id = "123"

        # Setup: Add thread data and lock
        set_thread_info(board_id, thread_id, {"post_count": 1})
        lock = acquire_thread_lock(board_id, thread_id)

        # Verify it exists
        self.assertIn(thread_id, _threads_data[board_id])
        self.assertIn(thread_id, _thread_locks[board_id])

        # Call function under test
        delete_thread_data(board_id, thread_id)

        # Verify it's removed
        self.assertNotIn(thread_id, _threads_data[board_id])
        self.assertNotIn(thread_id, _thread_locks[board_id])

    def test_delete_thread_data_nonexistent(self):
        board_id = "b"
        thread_id = "999"

        # Verify deleting a non-existent thread doesn't raise errors
        try:
            delete_thread_data(board_id, thread_id)
        except Exception as e:
            self.fail(f"delete_thread_data raised an exception: {e}")
