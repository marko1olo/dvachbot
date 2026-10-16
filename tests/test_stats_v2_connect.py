import sqlite3
from unittest.mock import patch, MagicMock

from stats_v2 import connect_ro_db

def test_connect_ro_db_success():
    with patch("stats_v2.sqlite3.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        conn = connect_ro_db(db_path="file:test.db?mode=ro", timeout=10.0)

        mock_connect.assert_called_once_with("file:test.db?mode=ro", uri=True, timeout=10.0)
        assert conn.row_factory == sqlite3.Row
        assert mock_conn.execute.call_count == 3
        mock_conn.execute.assert_any_call("PRAGMA journal_mode=WAL;")
        mock_conn.execute.assert_any_call("PRAGMA synchronous=NORMAL;")
        mock_conn.execute.assert_any_call("PRAGMA busy_timeout=15000;")
        assert conn == mock_conn

def test_connect_ro_db_pragma_exception():
    with patch("stats_v2.sqlite3.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("Pragma failed")
        mock_connect.return_value = mock_conn

        conn = connect_ro_db(db_path="file:test.db?mode=ro")

        mock_connect.assert_called_once_with("file:test.db?mode=ro", uri=True, timeout=15.0)
        assert conn.row_factory == sqlite3.Row
        assert mock_conn.execute.call_count == 1
        assert conn == mock_conn
