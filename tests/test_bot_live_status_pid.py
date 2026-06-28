import unittest
from unittest.mock import patch, MagicMock
import sys

from bot_live_status import _pid_exists


class TestPidExists(unittest.TestCase):

    def test_pid_none(self):
        """Test _pid_exists with None input."""
        self.assertFalse(_pid_exists(None))

    def test_pid_zero(self):
        """Test _pid_exists with zero input (falsy)."""
        self.assertFalse(_pid_exists(0))

    @patch("sys.platform", "win32")
    def test_windows_openprocess_success(self):
        """Test _pid_exists on Windows when process exists."""
        mock_ctypes = MagicMock()
        mock_open_process = mock_ctypes.windll.kernel32.OpenProcess
        mock_close_handle = mock_ctypes.windll.kernel32.CloseHandle
        mock_open_process.return_value = 123

        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            self.assertTrue(_pid_exists(1234))

        mock_open_process.assert_called_once_with(0x1000, False, 1234)
        mock_close_handle.assert_called_once_with(123)

    @patch("sys.platform", "win32")
    def test_windows_openprocess_fail(self):
        """Test _pid_exists on Windows when process does not exist."""
        mock_ctypes = MagicMock()
        mock_open_process = mock_ctypes.windll.kernel32.OpenProcess
        mock_close_handle = mock_ctypes.windll.kernel32.CloseHandle
        mock_open_process.return_value = 0

        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            self.assertFalse(_pid_exists(1234))

        mock_open_process.assert_called_once_with(0x1000, False, 1234)
        mock_close_handle.assert_not_called()

    @patch("sys.platform", "win32")
    def test_windows_exception(self):
        """Test _pid_exists on Windows when ctypes operations raise an exception."""
        mock_ctypes = MagicMock()
        mock_open_process = mock_ctypes.windll.kernel32.OpenProcess
        mock_open_process.side_effect = Exception("Some exception")

        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            self.assertFalse(_pid_exists(1234))

    @patch("sys.platform", "linux")
    @patch("os.kill")
    def test_posix_kill_success(self, mock_kill):
        """Test _pid_exists on POSIX when os.kill succeeds."""
        mock_kill.return_value = None
        self.assertTrue(_pid_exists(1234))
        mock_kill.assert_called_once_with(1234, 0)

    @patch("sys.platform", "linux")
    @patch("os.kill")
    def test_posix_kill_permission_error(self, mock_kill):
        """Test _pid_exists on POSIX when os.kill raises PermissionError (process exists but owned by other user)."""
        mock_kill.side_effect = PermissionError
        self.assertTrue(_pid_exists(1234))
        mock_kill.assert_called_once_with(1234, 0)

    @patch("sys.platform", "linux")
    @patch("os.kill")
    def test_posix_kill_os_error(self, mock_kill):
        """Test _pid_exists on POSIX when os.kill raises OSError (process does not exist)."""
        mock_kill.side_effect = OSError
        self.assertFalse(_pid_exists(1234))
        mock_kill.assert_called_once_with(1234, 0)


if __name__ == "__main__":
    unittest.main()
