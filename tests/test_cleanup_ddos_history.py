import unittest
from unittest.mock import patch
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

if __name__ == '__main__':
    unittest.main()
