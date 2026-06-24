import unittest
from unittest.mock import MagicMock, patch
from dbchecker import get_table_statistics, Colors

class TestDbChecker(unittest.TestCase):

    @patch('builtins.print')
    def test_get_table_statistics_success(self, mock_print):
        mock_cur = MagicMock()
        # Setup mock to return different counts for different tables
        mock_cur.fetchone.side_effect = [[10], [25]]

        tables = ["Users", "Posts"]
        total_rows = get_table_statistics(mock_cur, tables)

        self.assertEqual(total_rows, 35)

        # Verify execute was called correctly
        self.assertEqual(mock_cur.execute.call_count, 2)
        mock_cur.execute.assert_any_call('SELECT COUNT(*) FROM "Users"')
        mock_cur.execute.assert_any_call('SELECT COUNT(*) FROM "Posts"')

    @patch('builtins.print')
    def test_get_table_statistics_with_exception(self, mock_print):
        mock_cur = MagicMock()

        def side_effect_execute(query):
            if "BadTable" in query:
                raise Exception("DB Error")
            return None

        mock_cur.execute.side_effect = side_effect_execute
        mock_cur.fetchone.side_effect = [[42]] # Only one successful fetchone

        tables = ["GoodTable", "BadTable"]
        total_rows = get_table_statistics(mock_cur, tables)

        self.assertEqual(total_rows, 42)

        # Verify print was called with ERROR for BadTable
        mock_print.assert_any_call(f"{'BadTable':<25} | {'ERROR':<10}")
        mock_print.assert_any_call(f"{'GoodTable':<25} | {42:<10}")

    @patch('builtins.print')
    def test_get_table_statistics_empty(self, mock_print):
        mock_cur = MagicMock()
        tables = []
        total_rows = get_table_statistics(mock_cur, tables)

        self.assertEqual(total_rows, 0)
        mock_cur.execute.assert_not_called()

    @patch('builtins.print')
    def test_get_table_statistics_escape_quotes(self, mock_print):
        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [[5]]

        tables = ['Table"With"Quotes']
        total_rows = get_table_statistics(mock_cur, tables)

        self.assertEqual(total_rows, 5)

        # Expected escaping: Table"With"Quotes -> Table""With""Quotes
        mock_cur.execute.assert_called_once_with('SELECT COUNT(*) FROM "Table""With""Quotes"')

if __name__ == "__main__":
    unittest.main()
