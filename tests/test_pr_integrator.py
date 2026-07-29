import unittest
from unittest.mock import patch, MagicMock, mock_open
import pr_integrator
import subprocess
import sys

class TestPrIntegrator(unittest.TestCase):
    @patch('subprocess.run')
    def test_run_tests_success(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "OK"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        success, output = pr_integrator.run_tests(cwd="/fake/dir")

        self.assertTrue(success)
        self.assertEqual(output, "OK\n")
        mock_run.assert_called_once_with(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd="/fake/dir"
        )

    @patch('subprocess.run')
    def test_run_tests_failure(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "FAILED (errors=1)"
        mock_result.stderr = "Traceback..."
        mock_run.return_value = mock_result

        success, output = pr_integrator.run_tests(cwd=".")

        self.assertFalse(success)
        self.assertEqual(output, "FAILED (errors=1)\nTraceback...")
        mock_run.assert_called_once_with(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd="."
        )

    @patch('pr_integrator.get_unmerged_branches')
    @patch('sys.exit')
    def test_main_exception(self, mock_sys_exit, mock_get_unmerged_branches):
        mock_get_unmerged_branches.side_effect = Exception("Test Exception")

        pr_integrator.main()

        mock_sys_exit.assert_called_once_with(1)

    @patch('pr_integrator.get_unmerged_branches')
    @patch('pr_integrator.run_tests')
    @patch('pr_integrator.count_test_issues')
    @patch('pr_integrator.classify_branch')
    @patch('pr_integrator.verify_syntax_locally')
    @patch('subprocess.run')
    @patch('pr_integrator.run_git')
    @patch('builtins.open', new_callable=mock_open)
    def test_main_success(self, mock_open, mock_run_git, mock_subprocess_run,
                          mock_verify_syntax_locally, mock_classify_branch,
                          mock_count_test_issues, mock_run_tests,
                          mock_get_unmerged_branches):

        # Setup mocks
        mock_get_unmerged_branches.return_value = ["branch1", "branch2", "branch3"]
        mock_run_tests.return_value = (True, "OK")
        mock_count_test_issues.return_value = 0

        mock_classify_branch.side_effect = [
            ("ACCEPT", "Accept reason", ["file1.py"], 10, 5),
            ("REJECT", "Reject reason", ["file2.py"], 5, 2),
            ("MANUAL_REVIEW", "Review reason", ["file3.py"], 2, 1)
        ]

        mock_verify_syntax_locally.return_value = (True, "")
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        # Execute main
        pr_integrator.main()

        # Verify get_unmerged_branches called
        mock_get_unmerged_branches.assert_called_once()

        # Verify branches classified
        self.assertEqual(mock_classify_branch.call_count, 3)

        # Verify syntax checked for ACCEPT branch
        mock_verify_syntax_locally.assert_called_once()

        # Verify subprocess.run called for merge
        self.assertTrue(mock_subprocess_run.called)

        # Verify file writes (audit_report.json, merge_summary.json)
        self.assertTrue(mock_open.call_count >= 2)

if __name__ == '__main__':
    unittest.main()
