import unittest
from unittest.mock import MagicMock
from check_indexes import print_indexes


class TestCheckIndexes(unittest.TestCase):
    def test_print_indexes_no_injection(self):
        # Create a mock cursor
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("0", "my_index_name", "0", "c", "0")]

        # This shouldn't throw any syntax errors even with malicious quotes
        # because it uses PRAGMA table-valued function correctly or replaces
        # the quotes appropriately.
        malicious_table = 'Posts"; DROP TABLE Posts; --'
        print_indexes(mock_cur, malicious_table)

        # We verify that it used parameterization
        mock_cur.execute.assert_any_call(
            "SELECT * FROM pragma_index_list(?)", (malicious_table,))
        mock_cur.execute.assert_any_call(
            "SELECT * FROM pragma_index_info(?)", ("my_index_name",))


if __name__ == '__main__':
    unittest.main()
