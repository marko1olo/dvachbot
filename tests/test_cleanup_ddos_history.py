import unittest
from unittest.mock import patch
import time
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Dubsite_tgach.security import cleanup_ddos_history, REQUEST_HISTORY

class TestCleanupDdosHistory(unittest.TestCase):
    def setUp(self):
        REQUEST_HISTORY.clear()

    @patch('Dubsite_tgach.security.time.time')
    def test_cleanup_ddos_history_removes_expired(self, mock_time):
        mock_time.return_value = 1000.0
        # expired: 1000.0 - 601 = 399 < 400 (which is now - 600)
        REQUEST_HISTORY['ip1'] = [1, 399.0]
        # not expired: 1000.0 - 599 = 401 > 400
        REQUEST_HISTORY['ip2'] = [1, 401.0]

        cleanup_ddos_history()

        self.assertNotIn('ip1', REQUEST_HISTORY)
        self.assertIn('ip2', REQUEST_HISTORY)

    @patch('Dubsite_tgach.security.time.time')
    def test_cleanup_ddos_history_empty_history_list(self, mock_time):
        mock_time.return_value = 1000.0
        REQUEST_HISTORY['ip1'] = []
        REQUEST_HISTORY['ip2'] = [1, 1000.0]

        cleanup_ddos_history()

        self.assertNotIn('ip1', REQUEST_HISTORY)
        self.assertIn('ip2', REQUEST_HISTORY)

    @patch('Dubsite_tgach.security.time.time')
    def test_cleanup_ddos_history_empty_dict(self, mock_time):
        mock_time.return_value = 1000.0
        cleanup_ddos_history()
        self.assertEqual(len(REQUEST_HISTORY), 0)

    # Тесты ниже задавали состояние и сразу проверяли результат, НЕ вызвав
    # cleanup_ddos_history() — то есть не проверяли ничего и падали. Возвращён
    # пропущенный вызов; цель @patch выровнена с рабочими тестами выше
    # (Dubsite_tgach.security.time.time вместо глобального time.time, чтобы
    # подмена не влияла на asyncio/logging всего процесса).
    @patch('Dubsite_tgach.security.time.time')
    def test_cleanup_empty_history(self, mock_time):
        mock_time.return_value = 1000
        # Given empty REQUEST_HISTORY -> When cleanup is called -> Then still empty
        cleanup_ddos_history()
        self.assertEqual(len(REQUEST_HISTORY), 0)

    @patch('Dubsite_tgach.security.time.time')
    def test_cleanup_old_history(self, mock_time):
        mock_time.return_value = 1000
        REQUEST_HISTORY['ip1'] = [1, 200]  # Older than now - 600
        REQUEST_HISTORY['ip2'] = [1, 399]  # Older than now - 600
        cleanup_ddos_history()
        self.assertNotIn('ip1', REQUEST_HISTORY)
        self.assertNotIn('ip2', REQUEST_HISTORY)

    @patch('Dubsite_tgach.security.time.time')
    def test_cleanup_recent_history(self, mock_time):
        mock_time.return_value = 1000
        REQUEST_HISTORY['ip1'] = [1, 500]  # More recent than now - 600
        REQUEST_HISTORY['ip2'] = [1, 999]  # More recent than now - 600
        cleanup_ddos_history()
        self.assertEqual(len(REQUEST_HISTORY), 2)
        self.assertIn('ip1', REQUEST_HISTORY)

    @patch('Dubsite_tgach.security.time.time')
    def test_cleanup_mixed_history(self, mock_time):
        mock_time.return_value = 1000
        REQUEST_HISTORY['ip1'] = [1, 200]  # Old
        REQUEST_HISTORY['ip2'] = [1, 800]  # Recent
        REQUEST_HISTORY['ip3'] = []        # Empty history list (edge case)
        cleanup_ddos_history()
        self.assertEqual(len(REQUEST_HISTORY), 1)
        self.assertIn('ip2', REQUEST_HISTORY)
        self.assertNotIn('ip3', REQUEST_HISTORY)
if __name__ == '__main__':
    unittest.main()
