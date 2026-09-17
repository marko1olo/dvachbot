import unittest
from common import thread_manager
from common.thread_manager import get_thread_info, set_thread_info

class TestThreadManager(unittest.TestCase):
    def setUp(self):
        # Clear the module-level state before each test
        thread_manager._threads_data.clear()

    def test_get_thread_info_empty_fallback(self):
        # Test uninitialized board and non-existent thread
        self.assertEqual(get_thread_info('board_1', '123'), {})

        # Test initialized board but non-existent thread
        set_thread_info('board_2', '1', {'data': 'here'})
        self.assertEqual(get_thread_info('board_2', '123'), {})

        # Check that integer thread_id works since it casts to str
        self.assertEqual(get_thread_info('board_2', 123), {})

if __name__ == '__main__':
    unittest.main()
