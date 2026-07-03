import unittest
from unittest.mock import patch, MagicMock
import sqlite3

class TestStatusCheckDbHealth(unittest.TestCase):
    @patch('status_check.sqlite3')
    @patch('status_check.logger')
    def test_check_db_health_success(self, mock_logger, mock_sqlite):
        from status_check import check_db_health

        mock_conn = MagicMock()
        mock_sqlite.connect.return_value = mock_conn

        result = check_db_health()

        self.assertTrue(result)
        mock_sqlite.connect.assert_called_once_with('test.db')
        mock_conn.execute.assert_called_once_with("SELECT 1")
        mock_conn.close.assert_called_once()
        mock_logger.error.assert_not_called()

    @patch('status_check.sqlite3')
    @patch('status_check.logger')
    def test_check_db_health_error(self, mock_logger, mock_sqlite):
        from status_check import check_db_health

        mock_sqlite.Error = sqlite3.Error
        mock_sqlite.connect.side_effect = sqlite3.Error("Mocked DB error")

        result = check_db_health()

        self.assertFalse(result)
        mock_sqlite.connect.assert_called_once_with('test.db')
        mock_logger.error.assert_called_once_with("Database health check failed: Mocked DB error")

if __name__ == '__main__':
    unittest.main()
