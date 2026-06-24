import unittest
from unittest.mock import MagicMock, patch
from dbchecker import check_integrity

class TestCheckIntegrity(unittest.TestCase):
    @patch('builtins.print')
    def test_check_integrity_ok(self, mock_print):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = ["ok"]

        check_integrity(mock_cur)

        mock_cur.execute.assert_called_once_with("PRAGMA integrity_check")
        self.assertTrue(any("✅ Целостность структуры базы данных: OK" in call[0][0] for call in mock_print.call_args_list))

    @patch('builtins.print')
    def test_check_integrity_damaged(self, mock_print):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = ["database disk image is malformed"]

        check_integrity(mock_cur)

        mock_cur.execute.assert_called_once_with("PRAGMA integrity_check")
        self.assertTrue(any("⛔ ОБНАРУЖЕНЫ ПОВРЕЖДЕНИЯ: database disk image is malformed" in call[0][0] for call in mock_print.call_args_list))

    @patch('builtins.print')
    def test_check_integrity_exception(self, mock_print):
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception("test exception")

        check_integrity(mock_cur)

        mock_cur.execute.assert_called_once_with("PRAGMA integrity_check")
        self.assertTrue(any("Ошибка проверки целостности: test exception" in call[0][0] for call in mock_print.call_args_list))

if __name__ == '__main__':
    unittest.main()
