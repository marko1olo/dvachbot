import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json

import bot_live_status

class TestBotLiveStatus(unittest.TestCase):
    def setUp(self):
        pass

    @patch('bot_live_status._read_json')
    def test_health_success(self, mock_read_json):
        mock_read_json.return_value = {"status": "good"}
        status, data = bot_live_status._health()

        self.assertEqual(status, "ok")
        self.assertEqual(data, {"status": "good"})
        mock_read_json.assert_called_once_with(bot_live_status.LIVE_DATA_DIR / "metrics_db.json")
    @patch('bot_live_status._read_json')
    def test_health_exception(self, mock_read_json):
        mock_read_json.side_effect = Exception("File not found")
        status, data = bot_live_status._health()

        self.assertEqual(status, "error")
        self.assertEqual(data, "File not found")
        mock_read_json.assert_called_once_with(bot_live_status.LIVE_DATA_DIR / "metrics_db.json")
    def test_read_json_valid(self):
        mock_path = MagicMock(spec=Path)
        mock_path.read_text.return_value = '{"key": "value"}'
        result = bot_live_status._read_json(mock_path)
        self.assertEqual(result, {"key": "value"})

    def test_read_json_invalid(self):
        mock_path = MagicMock(spec=Path)
        mock_path.read_text.return_value = 'invalid json'
        result = bot_live_status._read_json(mock_path)
        self.assertEqual(result, {})

    def test_read_json_exception(self):
        mock_path = MagicMock(spec=Path)
        mock_path.read_text.side_effect = Exception("Read error")
        result = bot_live_status._read_json(mock_path)
        self.assertEqual(result, {})

    def test_read_json_not_dict(self):
        mock_path = MagicMock(spec=Path)
        mock_path.read_text.return_value = '"string"'
        result = bot_live_status._read_json(mock_path)
        self.assertEqual(result, {})

    def test_pid_exists_none(self):
        self.assertFalse(bot_live_status._pid_exists(None))

    def test_pid_exists_zero_or_negative(self):
        self.assertFalse(bot_live_status._pid_exists(0))
        self.assertFalse(bot_live_status._pid_exists(-1))

    @patch('sys.platform', 'linux')
    @patch('os.kill')
    def test_pid_exists_linux_success(self, mock_kill):
        self.assertTrue(bot_live_status._pid_exists(1234))
        mock_kill.assert_called_once_with(1234, 0)

    @patch('sys.platform', 'linux')
    @patch('os.kill')
    def test_pid_exists_linux_permission_error(self, mock_kill):
        mock_kill.side_effect = PermissionError()
        self.assertTrue(bot_live_status._pid_exists(1234))

    @patch('sys.platform', 'linux')
    @patch('os.kill')
    def test_pid_exists_linux_os_error(self, mock_kill):
        mock_kill.side_effect = OSError()
        self.assertFalse(bot_live_status._pid_exists(1234))
