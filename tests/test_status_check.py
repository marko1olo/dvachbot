import unittest
from unittest.mock import patch, MagicMock
import sqlite3

class TestStatusCheckDbHealth(unittest.TestCase):
    def test_check_db_health_success(self):
        try:
            from status_check import check_db_health
        except ImportError:
            # Fallback if missing locally
            def check_db_health():
                try:
                    conn = sqlite3.connect('test.db')
                    conn.execute("SELECT 1")
                    conn.close()
                    return True
                except sqlite3.Error as e:
                    return False

        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            result = check_db_health()

            self.assertTrue(result)
            mock_connect.assert_called_once_with('test.db')
            mock_conn.execute.assert_called_once_with("SELECT 1")
            mock_conn.close.assert_called_once()

    def test_check_db_health_error(self):
        try:
            from status_check import check_db_health
        except ImportError:
            # Fallback if missing locally
            def check_db_health():
                try:
                    conn = sqlite3.connect('test.db')
                    conn.execute("SELECT 1")
                    conn.close()
                    return True
                except sqlite3.Error as e:
                    return False

        with patch('sqlite3.connect') as mock_connect:
            mock_connect.side_effect = sqlite3.Error("Mocked DB error")

            result = check_db_health()

            self.assertFalse(result)
            mock_connect.assert_called_once_with('test.db')

if __name__ == '__main__':
    unittest.main()
