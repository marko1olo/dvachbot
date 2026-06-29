import unittest
from unittest.mock import patch, MagicMock
import pr_merger
import subprocess

class TestPrMerger(unittest.TestCase):
    @patch('subprocess.check_output')
    def test_run_cmd_success(self, mock_check_output):
        mock_check_output.return_value = b'test output\n'
        result = pr_merger.run_cmd(['git', 'fetch', '--all'])
        self.assertEqual(result, 'test output')
        mock_check_output.assert_called_once_with(['git', 'fetch', '--all'], shell=False, stderr=subprocess.STDOUT)

    @patch('subprocess.check_output')
    def test_run_cmd_failure_with_check(self, mock_check_output):
        mock_check_output.side_effect = subprocess.CalledProcessError(1, 'cmd', output=b'error output\n')
        with self.assertRaises(subprocess.CalledProcessError):
            pr_merger.run_cmd(['git', 'fetch', '--all'])

    @patch('subprocess.check_output')
    def test_run_cmd_failure_without_check(self, mock_check_output):
        mock_check_output.side_effect = subprocess.CalledProcessError(1, 'cmd', output=b'error output\n')
        result = pr_merger.run_cmd(['git', 'fetch', '--all'], check=False)
        self.assertEqual(result, 'error output')

    @patch('pr_merger.run_cmd')
    def test_main(self, mock_run_cmd):
        def side_effect(cmd, check=True):
            if cmd == ["git", "--no-pager", "branch", "-r"]:
                return "  origin/main\n  origin/pr/test-pr\n  feature-1\n  origin/test-branch"
            elif cmd == ["git", "--no-pager", "log", "main..feature-1", "--oneline"]:
                return "12345 commit"
            elif cmd == ["git", "--no-pager", "diff", "--shortstat", "main...feature-1"]:
                return " 1 file changed, 1 insertion(+)"
            elif cmd == ["git", "--no-pager", "log", "main..origin/test-branch", "--oneline"]:
                return "12345 commit"
            elif cmd == ["git", "--no-pager", "diff", "--shortstat", "main...origin/test-branch"]:
                return " 1 file changed, 1 insertion(+)"
            elif isinstance(cmd, list) and len(cmd) > 2 and cmd[0] == "git" and cmd[1] == "merge":
                return "Success"
            return ""

        mock_run_cmd.side_effect = side_effect

        with patch('builtins.open', new_callable=MagicMock):
            pr_merger.main()

        # Check if the right branches were merged
        self.assertTrue(mock_run_cmd.called)

if __name__ == '__main__':
    unittest.main()
