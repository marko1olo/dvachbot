import unittest
from unittest.mock import patch
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from summarize import _load_google_keys

class TestLoadGoogleKeys(unittest.TestCase):
    @patch("os.path.exists")
    @patch("builtins.open")
    def test_load_google_keys_file_not_found(self, mock_open_func, mock_exists):
        # Simulate that os.path.exists returns True to enter the file reading block
        mock_exists.return_value = True

        # Raise FileNotFoundError
        mock_open_func.side_effect = FileNotFoundError()

        # Clear env to trigger fallback [] return
        with patch.dict(os.environ, clear=True):
            keys = _load_google_keys()
            self.assertEqual(keys, [])

    @patch("os.path.exists")
    @patch("builtins.open")
    def test_load_google_keys_permission_error(self, mock_open_func, mock_exists):
        # Simulate that os.path.exists returns True to enter the file reading block
        mock_exists.return_value = True

        # Raise PermissionError
        mock_open_func.side_effect = PermissionError()

        # Clear env to trigger fallback [] return
        with patch.dict(os.environ, clear=True):
            keys = _load_google_keys()
            self.assertEqual(keys, [])

if __name__ == '__main__':
    unittest.main()
