import unittest
from unittest.mock import patch
import sqlite3
import os
import sys

# Add project root to sys.path to allow importing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from maintenance import run_maintenance

class TestMaintenance(unittest.TestCase):

    @patch('maintenance.sqlite3.connect')
    @patch('maintenance.os.path.exists')
    @patch('builtins.print')
    def test_run_maintenance_db_not_found(self, mock_print, mock_exists, mock_connect):
        # Simulate DB file not existing
        mock_exists.return_value = False

        run_maintenance()

        # Verify execution stopped early
        mock_connect.assert_not_called()

        # Verify it printed an error about file missing
        found_err_print = any("Ошибка: Файл базы данных не найден" in call.args[0] for call in mock_print.call_args_list)
        self.assertTrue(found_err_print)

    @patch('maintenance.sqlite3.connect')
    @patch('maintenance.os.path.exists')
    @patch('builtins.print')
    def test_run_maintenance_success(self, mock_print, mock_exists, mock_connect):
        # Simulate DB file existing
        mock_exists.return_value = True

        # Mock connection and its context manager behavior
        mock_con = mock_connect.return_value.__enter__.return_value

        run_maintenance()

        mock_connect.assert_called_once()
        mock_con.execute.assert_any_call("VACUUM;")
        mock_con.execute.assert_any_call("ANALYZE;")
        mock_print.assert_any_call("\nОбслуживание базы данных успешно завершено!")

    @patch('maintenance.sqlite3.connect')
    @patch('maintenance.os.path.exists')
    @patch('builtins.print')
    def test_run_maintenance_sqlite_error(self, mock_print, mock_exists, mock_connect):
        # Simulate DB file existing
        mock_exists.return_value = True

        # Mock connection and its context manager behavior
        mock_con = mock_connect.return_value.__enter__.return_value

        # Simulate an exception during execution of a command
        mock_con.execute.side_effect = sqlite3.Error("Mocked SQLite error")

        run_maintenance()

        # Verify the connection was established
        mock_connect.assert_called_once()

        # Verify execution was attempted
        mock_con.execute.assert_called_once_with("VACUUM;")

        # Verify the exception was caught and handled
        mock_print.assert_any_call("⛔ КРИТИЧЕСКАЯ ОШИБКА во время обслуживания: Mocked SQLite error")

        # Note: Since the test uses the `with` statement, connection closure is handled
        # by the context manager's __exit__ block, and checking __exit__ indicates safe teardown.
        mock_connect.return_value.__exit__.assert_called_once()

if __name__ == '__main__':
    unittest.main()
