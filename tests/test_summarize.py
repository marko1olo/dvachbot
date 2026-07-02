import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys

# Mock modules to avoid heavy imports or missing dependencies
sys.modules["openai"] = MagicMock()
sys.modules["common.token_pool"] = MagicMock()
sys.modules["httpx"] = MagicMock()

from summarize import _load_google_keys

class TestSummarize(unittest.TestCase):
    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, clear=True)
    def test_load_google_keys_from_envgoogle(self, mock_open_func, mock_exists):
        """Test loading from .envgoogle file."""
        mock_exists.return_value = True
        mock_open_func.return_value = mock_open(read_data="GOOGLE_API_KEYS=key1, key2 ,key3\nOTHER_KEY=val").return_value

        keys = _load_google_keys()
        self.assertEqual(keys, ["key1", "key2", "key3"])
        mock_exists.assert_called_once_with(".envgoogle")
        mock_open_func.assert_called_once_with(".envgoogle", "r", encoding="utf-8")

    @patch("os.path.exists")
    @patch.dict(os.environ, {"GOOGLE_API_KEYS": "envkey1, envkey2  , envkey3"}, clear=True)
    def test_load_google_keys_from_env_fallback(self, mock_exists):
        """Test fallback to os.environ when .envgoogle doesn't exist."""
        mock_exists.return_value = False

        keys = _load_google_keys()
        self.assertEqual(keys, ["envkey1", "envkey2", "envkey3"])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, {"GOOGLE_API_KEYS": "envkey1, envkey2"}, clear=True)
    def test_load_google_keys_invalid_envgoogle(self, mock_open_func, mock_exists):
        """Test fallback to os.environ when .envgoogle is invalid/doesn't contain key."""
        mock_exists.return_value = True
        mock_open_func.return_value = mock_open(read_data="INVALID_FORMAT").return_value

        keys = _load_google_keys()
        self.assertEqual(keys, ["envkey1", "envkey2"])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("summarize.logger.warning")
    @patch.dict(os.environ, {"GOOGLE_API_KEYS": "envkey1, envkey2"}, clear=True)
    def test_load_google_keys_exception_envgoogle(self, mock_logger, mock_open_func, mock_exists):
        """Test fallback to os.environ when reading .envgoogle raises an exception."""
        mock_exists.return_value = True
        mock_open_func.side_effect = PermissionError("Permission denied")

        keys = _load_google_keys()
        self.assertEqual(keys, ["envkey1", "envkey2"])
        mock_logger.assert_called_once()
        self.assertIn("Error loading .envgoogle", mock_logger.call_args[0][0])

    @patch("os.path.exists")
    @patch.dict(os.environ, clear=True)
    def test_load_google_keys_empty(self, mock_exists):
        """Test when no keys are found anywhere."""
        mock_exists.return_value = False

        keys = _load_google_keys()
        self.assertEqual(keys, [])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch.dict(os.environ, clear=True)
    def test_load_google_keys_empty_elements(self, mock_open_func, mock_exists):
        """Test empty elements are ignored when splitting."""
        mock_exists.return_value = True
        mock_open_func.return_value = mock_open(read_data="GOOGLE_API_KEYS=key1,,key2\n").return_value

        keys = _load_google_keys()
        self.assertEqual(keys, ["key1", "key2"])

if __name__ == "__main__":
    unittest.main()
