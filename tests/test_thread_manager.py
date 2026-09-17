import unittest
import asyncio
import os

# Create and set new event loop to avoid Pyrogram/asyncio errors
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from common.thread_manager import get_active_threads, _threads_data, initialize_board_threads

class TestThreadManager(unittest.TestCase):
    def setUp(self):
        # Clear the _threads_data before each test to ensure isolation
        _threads_data.clear()

    def test_get_active_threads_filters_archived(self):
        # Setup mock data for a board
        board_id = "test_board"
        mock_data = {
            "thread_1": {"title": "Active Thread 1", "is_archived": False},
            "thread_2": {"title": "Archived Thread", "is_archived": True},
            "thread_3": {"title": "Active Thread 2"}, # Missing is_archived key implies active
            "thread_4": {"title": "Another Archived", "is_archived": True}
        }

        initialize_board_threads(board_id, mock_data)

        # Call the function
        active_threads = get_active_threads(board_id)

        # Assertions
        self.assertEqual(len(active_threads), 2)
        self.assertIn("thread_1", active_threads)
        self.assertIn("thread_3", active_threads)
        self.assertNotIn("thread_2", active_threads)
        self.assertNotIn("thread_4", active_threads)

    def test_get_active_threads_empty_board(self):
        # Test with a board that has no threads
        board_id = "empty_board"
        initialize_board_threads(board_id, {})

        active_threads = get_active_threads(board_id)
        self.assertEqual(len(active_threads), 0)

    def test_get_active_threads_nonexistent_board(self):
        # Test with a board that hasn't been initialized
        board_id = "nonexistent_board"

        active_threads = get_active_threads(board_id)
        self.assertEqual(len(active_threads), 0)
        self.assertEqual(isinstance(active_threads, dict), True)

if __name__ == '__main__':
    unittest.main()
