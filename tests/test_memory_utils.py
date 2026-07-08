import unittest
from unittest.mock import patch
import gc

from common.memory_utils import log_memory_summary

class TestLogMemorySummary(unittest.IsolatedAsyncioTestCase):

    @patch('common.memory_utils.gc.collect')
    @patch('builtins.print')
    async def test_log_memory_summary_basic(self, mock_print, mock_gc_collect):
        # Setup mock dependencies
        mock_gc_collect.return_value = 42

        messages_storage = {1: {}, 2: {}}
        post_to_messages = {1: [1], 2: [2]}
        message_to_post = {1: 1, 2: 2}
        BOARDS = ['test_board', 'another_board']
        board_data = {
            'test_board': {
                'threads_data': {'t1': {}, 't2': {}},
                'user_state': {'u1': {}},
                'last_user_msgs': {'u1': {}}
            },
            'another_board': {}
        }

        # Ensure the static variable is not set to test the hasattr branch
        if hasattr(log_memory_summary, 'previous_stats'):
            delattr(log_memory_summary, 'previous_stats')

        await log_memory_summary(messages_storage, post_to_messages, message_to_post, BOARDS, board_data)

        # Verify hasattr initialization
        self.assertTrue(hasattr(log_memory_summary, 'previous_stats'))
        self.assertEqual(log_memory_summary.previous_stats, {})

        # Verify gc.collect was called (twice)
        self.assertEqual(mock_gc_collect.call_count, 2)

        # Verify print was called
        mock_print.assert_any_call("GC.collect() завершён, удалено объектов: 42")
        mock_print.assert_any_call("🧹 Очистка памяти завершена.")

    @patch('common.memory_utils.gc.collect')
    @patch('builtins.print')
    async def test_log_memory_summary_subsequent_call(self, mock_print, mock_gc_collect):
        # Setup static variable
        log_memory_summary.previous_stats = {'some_key': 123}

        await log_memory_summary({}, {}, {}, [], {})

        # Verify it wasn't overwritten
        self.assertEqual(log_memory_summary.previous_stats, {'some_key': 123})

if __name__ == '__main__':
    unittest.main()
