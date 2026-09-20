import unittest
from unittest.mock import patch, MagicMock
import runpy

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
        mock_connect.return_value = mock_con
        mock_connect.return_value.__enter__.return_value = mock_con

        run_maintenance()

        mock_exists.assert_called_once_with(DB_NAME)
        mock_connect.assert_called_once_with(DB_NAME, timeout=15.0)

        # Check that both VACUUM and ANALYZE are called
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
        mock_connect.assert_called_once_with(DB_NAME, timeout=15.0)

        # Verify that the critical error message is printed
        mock_print.assert_any_call(f"⛔ КРИТИЧЕСКАЯ ОШИБКА во время обслуживания: {error_msg}")

    @patch('builtins.input', return_value='y')
    @patch('builtins.print')
    def test_main_block_y(self, mock_print, mock_input):
        with patch('maintenance.os.path.exists', return_value=False):
            runpy.run_module('maintenance', run_name='__main__')

    @patch('builtins.input', return_value='n')
    @patch('builtins.print')
    def test_main_block_n(self, mock_print, mock_input):
        runpy.run_module('maintenance', run_name='__main__')
        mock_print.assert_any_call("Операция отменена.")

    @patch('sys.argv', ['maintenance.py', '--yes'])
    @patch('builtins.print')
    @patch('builtins.input')
    def test_main_block_auto_yes(self, mock_input, mock_print):
        with patch('maintenance.os.path.exists', return_value=False):
            runpy.run_module('maintenance', run_name='__main__')
        mock_input.assert_not_called()
        mock_print.assert_any_call(f"Ошибка: Файл базы данных не найден по пути: {DB_NAME}")


    def test_clean_old_postcopies_executes_delete(self):
        from maintenance import clean_old_postcopies
        mock_con = MagicMock()
        mock_cur = MagicMock()
        mock_con.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (500000,)

        clean_old_postcopies(mock_con, retention_days=3)
        mock_cur.execute.assert_any_call("DELETE FROM PostCopies WHERE post_num < ?", (500000,))
        mock_con.commit.assert_called_once()

if __name__ == '__main__':
    unittest.main()

