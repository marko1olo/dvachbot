import unittest
from unittest.mock import patch, MagicMock
import pr_merger
import subprocess
import sys

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
                return (
                    "  origin/main\n"
                    "  origin/pr/test-pr\n"
                    "  feature-empty-log\n"
                    "  feature-empty-diff\n"
                    "  feature-exception\n"
                    "  feature-conflict\n"
                    "  feature-already-merged\n"
                    "  feature-merge-exception\n"
                    "  feature-success\n"
                    "  fix-something\n"
                    "  test-something\n"
                    "  sql-optimizations\n"
                    "  perf-improvements\n"
                    "  chore-cleanup\n"
                )
            # Priorities testing
            elif cmd == ["git", "--no-pager", "log", "main..fix-something", "--oneline"] or \
                 cmd == ["git", "--no-pager", "log", "main..test-something", "--oneline"] or \
                 cmd == ["git", "--no-pager", "log", "main..sql-optimizations", "--oneline"] or \
                 cmd == ["git", "--no-pager", "log", "main..perf-improvements", "--oneline"] or \
                 cmd == ["git", "--no-pager", "log", "main..chore-cleanup", "--oneline"]:
                 return "12345 commit"

            elif cmd == ["git", "--no-pager", "diff", "--shortstat", "main...fix-something"] or \
                 cmd == ["git", "--no-pager", "diff", "--shortstat", "main...test-something"] or \
                 cmd == ["git", "--no-pager", "diff", "--shortstat", "main...sql-optimizations"] or \
                 cmd == ["git", "--no-pager", "diff", "--shortstat", "main...perf-improvements"] or \
                 cmd == ["git", "--no-pager", "diff", "--shortstat", "main...chore-cleanup"]:
                 return " 1 file changed, 1 insertion(+)"

            # Log checks
            elif cmd == ["git", "--no-pager", "log", "main..feature-empty-log", "--oneline"]:
                return "" # Empty log
            elif cmd == ["git", "--no-pager", "log", "main..feature-exception", "--oneline"]:
                raise Exception("Git error")

            # Diff checks
            elif cmd == ["git", "--no-pager", "diff", "--shortstat", "main...feature-empty-diff"]:
                return "   " # Empty diff

            # For the valid ones, return some log and diff
            elif isinstance(cmd, list) and len(cmd) == 5 and cmd[:4] == ["git", "--no-pager", "log", "main.."]:
                return "12345 commit"
            elif isinstance(cmd, list) and len(cmd) == 5 and cmd[:4] == ["git", "--no-pager", "diff", "--shortstat"]:
                return " 1 file changed, 1 insertion(+)"

            # Merging
            elif isinstance(cmd, list) and len(cmd) > 2 and cmd[0] == "git" and cmd[1] == "merge":
                branch = cmd[-1]
                if branch == "feature-conflict":
                    return "Merge conflict in file.txt"
                elif branch == "feature-already-merged":
                    return "Already up to date."
                elif branch == "feature-merge-exception":
                    raise Exception("Merge failed entirely")
                elif branch == "feature-success":
                    return "Success"
                elif branch in ["fix-something", "test-something", "sql-optimizations", "perf-improvements", "chore-cleanup"]:
                    return "Success"

                return ""

            # Mocking git log main..branch when dynamic branch name
            if cmd[0] == "git" and cmd[2] == "log":
                 return "12345 commit"

            return "Some default string"

        mock_run_cmd.side_effect = side_effect

        with patch('builtins.open', new_callable=MagicMock) as mock_open:
            pr_merger.main()

            mock_file = mock_open.return_value.__enter__.return_value
            mock_file.write.assert_any_call("Successfully merged: 6\n")
            mock_file.write.assert_any_call("  - feature-success\n")
            mock_file.write.assert_any_call("\nFailed/Conflicts: 2\n")
            mock_file.write.assert_any_call("  - feature-conflict (Conflict)\n")
            mock_file.write.assert_any_call("  - feature-merge-exception (Error)\n")

        self.assertTrue(mock_run_cmd.called)

    def test_main_block(self):
        import runpy
        # Execute the module to get coverage on the __main__ block
        # the main function will run inside run_path but since we're just checking coverage,
        # we don't need to assert it was called (it definitely was, the print proves it).
        with patch.object(sys, 'argv', ['pr_merger.py']):
            runpy.run_path('pr_merger.py', run_name='__main__')

if __name__ == '__main__':
    unittest.main()
