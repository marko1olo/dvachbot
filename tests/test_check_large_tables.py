import unittest
from unittest.mock import patch, MagicMock
import sqlite3
import check_large_tables

class TestCheckLargeTables(unittest.TestCase):
    @patch('check_large_tables.sqlite3.connect')
    def test_sql_injection_prevention(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # First execute gets tables
        # Let's inject a malicious table name with newline
        malicious_table = "users\nDROP TABLE users"
        mock_cursor.__iter__.return_value = [(malicious_table,), ("valid_table",)]

        # We need to simulate fetchall for query_indexes
        mock_cursor.fetchall.side_effect = [
            [], # for query_indexes
            [], # for UNION ALL
        ]

        check_large_tables.check_indexes()

        # The malicious table should be filtered out from valid_tables
        # Let's verify valid_tables filtering by looking at the json_each call
        # It should only contain valid_table
        import json
        expected_json = json.dumps(["valid_table"])

        # Verify the query_indexes call
        mock_cursor.execute.assert_any_call(
            "SELECT j.value, p.seq, p.name, p.[unique], p.origin, p.partial "
            "FROM json_each(?) j CROSS JOIN pragma_index_list(j.value) p",
            (expected_json,)
        )

        # We can also verify that UNION ALL query doesn't include the malicious table
        mock_cursor.execute.assert_any_call(
            "SELECT 'valid_table', COUNT(*) FROM \"valid_table\""
        )
