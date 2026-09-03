import sys
from pathlib import Path
# scripts/ moved here after refactor
_scripts_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from unittest.mock import patch, mock_open

from status_check import get_last_errors

@patch('status_check.os.path.exists')
def test_get_last_errors_file_not_found(mock_exists):
    mock_exists.return_value = False
    result = get_last_errors()
    assert result == ["Log file not found."]

@patch('status_check.os.path.exists')
@patch('builtins.open', new_callable=mock_open, read_data="INFO: All good\nDEBUG: Starting up")
def test_get_last_errors_no_errors(mock_open_file, mock_exists):
    mock_exists.return_value = True
    result = get_last_errors()
    assert result == ["No errors found in recent logs."]

@patch('status_check.os.path.exists')
@patch('builtins.open')
def test_get_last_errors_read_error(mock_open_file, mock_exists):
    mock_exists.return_value = True
    mock_open_file.side_effect = Exception("Permission denied")
    result = get_last_errors()
    assert len(result) == 1
    assert "Could not read log file: Permission denied" in result[0]

@patch('status_check.os.path.exists')
def test_get_last_errors_with_errors(mock_exists):
    mock_exists.return_value = True
    log_data = (
        "[2023-01-01] - INFO Some info\n"
        "[2023-01-01] - ERROR first error\n"
        "[2023-01-02] - CRITICAL critical failure\n"
        "[2023-01-02] - DEBUG debug message\n"
        "[2023-01-03] - Exception occurred during processing\n"
        "[2023-01-04] - ERROR second error\n"
        "[2023-01-04] - ERROR third error\n"
        "[2023-01-05] - ERROR fourth error\n"
        "[2023-01-05] - INFO closing\n"
    )
    with patch('builtins.open', mock_open(read_data=log_data)):
        result = get_last_errors()

    assert len(result) == 5
    # Should be in reverse order
    assert result[0] == "ERROR fourth error"
    assert result[1] == "ERROR third error"
    assert result[2] == "ERROR second error"
    assert result[3] == "Exception occurred during processing"
    assert result[4] == "CRITICAL critical failure"
