import unittest
from unittest.mock import patch, MagicMock
from check_large_tables import check_indexes, get_table_count

class TestCheckLargeTables(unittest.TestCase):
    def test_get_table_count(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [42]
        count = get_table_count(mock_cursor, "valid", {"valid"})
        self.assertEqual(count, 42)
        mock_cursor.execute.assert_called_once_with('SELECT COUNT(*) FROM "valid"')

    def test_get_table_count_invalid(self):
        mock_cursor = MagicMock()
        with self.assertRaises(ValueError):
            get_table_count(mock_cursor, "invalid", {"valid"})

    @patch('check_large_tables.sqlite3.connect')
    @patch('builtins.print')
    def test_check_indexes(self, mock_print, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        def fetchall_side_effect():
            # first fetchall is for tables, second is for indexes
            call_count = mock_cursor.fetchall.call_count
            if call_count == 1:
                return [("table1",)]
            elif call_count == 2:
                return []
            return []

        mock_cursor.fetchall.side_effect = fetchall_side_effect
        mock_cursor.fetchone.return_value = [15000]

        check_indexes()

        mock_connect.assert_called_once_with('dvach_bot.db')
        mock_print.assert_called_once_with('Table table1: 15000 rows')

if __name__ == '__main__':
    unittest.main()
