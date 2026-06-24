import unittest
from unittest.mock import patch, MagicMock
import sqlite3
import os

from maintenance import run_maintenance
from common.config import DB_NAME

class TestMaintenance(unittest.TestCase):

    @patch('maintenance.os.path.exists')
    @patch('builtins.print')
    @patch('maintenance.sqlite3.connect')
    def test_run_maintenance_db_not_found(self, mock_connect, mock_print, mock_exists):
        """Test edge case: DB file does not exist."""
        mock_exists.return_value = False

        run_maintenance()

        mock_exists.assert_called_once_with(DB_NAME)
        mock_print.assert_called_once_with(f"Ошибка: Файл базы данных не найден по пути: {DB_NAME}")
        mock_connect.assert_not_called()

    @patch('maintenance.os.path.exists')
    @patch('builtins.print')
    @patch('maintenance.sqlite3.connect')
    def test_run_maintenance_success(self, mock_connect, mock_print, mock_exists):
        """Test happy path: DB file exists, maintenance runs successfully."""
        mock_exists.return_value = True

        mock_con = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_con

        run_maintenance()

        mock_exists.assert_called_once_with(DB_NAME)
        mock_connect.assert_called_once_with(DB_NAME)

        # Check that both VACUUM and ANALYZE are called
        self.assertEqual(mock_con.execute.call_count, 2)
        mock_con.execute.assert_any_call("VACUUM;")
        mock_con.execute.assert_any_call("ANALYZE;")

        # Verify success messages are printed
        mock_print.assert_any_call("✅ VACUUM успешно завершен.")
        mock_print.assert_any_call("✅ ANALYZE успешно завершен.")
        mock_print.assert_any_call("\nОбслуживание базы данных успешно завершено!")

    @patch('maintenance.os.path.exists')
    @patch('builtins.print')
    @patch('maintenance.sqlite3.connect')
    def test_run_maintenance_exception(self, mock_connect, mock_print, mock_exists):
        """Test error condition: An exception is raised during maintenance."""
        mock_exists.return_value = True

        error_msg = "Test Database Error"
        mock_connect.side_effect = Exception(error_msg)

        run_maintenance()

        mock_exists.assert_called_once_with(DB_NAME)
        mock_connect.assert_called_once_with(DB_NAME)

        # Verify that the critical error message is printed
        mock_print.assert_any_call(f"⛔ КРИТИЧЕСКАЯ ОШИБКА во время обслуживания: {error_msg}")

if __name__ == '__main__':
    unittest.main()
