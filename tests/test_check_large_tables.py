import unittest
import sqlite3
from unittest.mock import patch
import os
from check_large_tables import check_indexes

class TestCheckLargeTables(unittest.TestCase):
    def setUp(self):
        # Create an in-memory dummy database
        self.conn = sqlite3.connect(':memory:')
        self.cursor = self.conn.cursor()

        # Create table with < 10000 rows
        self.cursor.execute("CREATE TABLE small_table (id INT)")
        self.cursor.execute("CREATE INDEX idx_small ON small_table(id)")
        self.cursor.executemany("INSERT INTO small_table VALUES (?)", [(i,) for i in range(10)])

        # Create table with > 10000 rows
        self.cursor.execute("CREATE TABLE large_table (id INT, val TEXT)")
        self.cursor.execute("CREATE INDEX idx_large_id ON large_table(id)")
        self.cursor.execute("CREATE INDEX idx_large_val ON large_table(val)")
        self.cursor.executemany("INSERT INTO large_table VALUES (?, ?)", [(i, str(i)) for i in range(10005)])

        # Create a table with invalid name characters
        self.cursor.execute("CREATE TABLE \"invalid-name\" (id INT)")

        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    @patch('builtins.print')
    @patch('check_large_tables.sqlite3.connect')
    def test_check_indexes_output(self, mock_connect, mock_print):
        mock_connect.return_value = self.conn
        check_indexes()

        # Should only print info for large_table
        mock_print.assert_any_call("Table large_table: 10005 rows")
        mock_print.assert_any_call("  Index: idx_large_id -> Columns: ['id']")
        mock_print.assert_any_call("  Index: idx_large_val -> Columns: ['val']")

        # Ensure it didn't print for small_table or invalid-name
        for call_args in mock_print.call_args_list:
            arg = call_args[0][0]
            self.assertNotIn("small_table", arg)
            self.assertNotIn("invalid-name", arg)

if __name__ == '__main__':
    unittest.main()
