import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest
from unittest.mock import patch, MagicMock
from maintenance import run_maintenance
from common.config import DB_NAME

class TestMaintenance(unittest.TestCase):
    @patch('maintenance.os.path.exists')
    @patch('builtins.print')
    def test_run_maintenance_db_not_found(self, mock_print, mock_exists):
        mock_exists.return_value = False

        run_maintenance()

        mock_exists.assert_called_once_with(DB_NAME)
        mock_print.assert_called_once_with(f"Ошибка: Файл базы данных не найден по пути: {DB_NAME}")

    @patch('maintenance.sqlite3.connect')
    @patch('maintenance.os.path.exists')
    @patch('builtins.print')
    def test_run_maintenance_success(self, mock_print, mock_exists, mock_connect):
        mock_exists.return_value = True

        # Setup the context manager mock
        mock_con = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_con

        run_maintenance()

        mock_exists.assert_called_once_with(DB_NAME)
        mock_connect.assert_called_once_with(DB_NAME)

        # Check that execute was called with VACUUM and ANALYZE
        mock_con.execute.assert_any_call("VACUUM;")
        mock_con.execute.assert_any_call("ANALYZE;")
        self.assertEqual(mock_con.execute.call_count, 2)

        # Check successful prints
        mock_print.assert_any_call(f"Подключение к базе данных: {DB_NAME}")
        mock_print.assert_any_call("\nОбслуживание базы данных успешно завершено!")

    @patch('maintenance.sqlite3.connect')
    @patch('maintenance.os.path.exists')
    @patch('builtins.print')
    def test_run_maintenance_exception(self, mock_print, mock_exists, mock_connect):
        mock_exists.return_value = True

        error_msg = "Test DB Error"
        mock_connect.side_effect = Exception(error_msg)

        run_maintenance()

        mock_exists.assert_called_once_with(DB_NAME)
        mock_connect.assert_called_once_with(DB_NAME)

        mock_print.assert_any_call(f"⛔ КРИТИЧЕСКАЯ ОШИБКА во время обслуживания: {error_msg}")

if __name__ == '__main__':
    unittest.main()
