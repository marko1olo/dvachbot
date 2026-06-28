import unittest
from unittest.mock import patch

from bot_live_status import _pid_exists


class TestPidExists(unittest.TestCase):

    def test_pid_none(self):
        """Test _pid_exists with None input."""
        self.assertFalse(_pid_exists(None))

    def test_pid_zero(self):
        """Test _pid_exists with zero input (falsy)."""
        self.assertFalse(_pid_exists(0))

    @patch("os.kill")
    def test_kill_success(self, mock_kill):
        """Test _pid_exists when os.kill succeeds."""
        mock_kill.return_value = None
        self.assertTrue(_pid_exists(1234))
        mock_kill.assert_called_once_with(1234, 0)

    @patch("os.kill")
    def test_kill_os_error(self, mock_kill):
        """Test _pid_exists when os.kill raises OSError."""
        # Using a generic OSError which aligns with the exception block in the prompt's snippet
        mock_kill.side_effect = OSError
        self.assertFalse(_pid_exists(1234))
        mock_kill.assert_called_once_with(1234, 0)


if __name__ == "__main__":
    unittest.main()
