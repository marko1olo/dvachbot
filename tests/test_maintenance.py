import pytest
from unittest.mock import patch, MagicMock
from maintenance import run_maintenance

@patch('maintenance.os.path.exists')
@patch('builtins.print')
def test_run_maintenance_db_not_found(mock_print, mock_exists):
    mock_exists.return_value = False
    run_maintenance()
    mock_print.assert_called_once()
    assert "Ошибка: Файл базы данных не найден по пути:" in mock_print.call_args[0][0]

@patch('maintenance.os.path.exists')
@patch('maintenance.sqlite3.connect')
@patch('builtins.print')
def test_run_maintenance_success(mock_print, mock_connect, mock_exists):
    mock_exists.return_value = True

    mock_con = MagicMock()
    # Mocking the context manager for `with sqlite3.connect(...) as con:`
    mock_connect.return_value.__enter__.return_value = mock_con

    run_maintenance()

    assert mock_con.execute.call_count == 2
    mock_con.execute.assert_any_call("VACUUM;")
    mock_con.execute.assert_any_call("ANALYZE;")

    mock_print.assert_any_call("✅ VACUUM успешно завершен.")
    mock_print.assert_any_call("✅ ANALYZE успешно завершен.")
    mock_print.assert_any_call("\nОбслуживание базы данных успешно завершено!")

@patch('maintenance.os.path.exists')
@patch('maintenance.sqlite3.connect')
@patch('builtins.print')
def test_run_maintenance_db_exception(mock_print, mock_connect, mock_exists):
    mock_exists.return_value = True

    # Simulate an exception when connecting or executing
    mock_connect.side_effect = Exception("Test Database Error")

    run_maintenance()

    mock_print.assert_any_call("⛔ КРИТИЧЕСКАЯ ОШИБКА во время обслуживания: Test Database Error")
