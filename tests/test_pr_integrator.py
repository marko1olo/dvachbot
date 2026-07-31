import unittest
from unittest.mock import patch, MagicMock
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


    @patch('subprocess.run')
    def test_run_git_success(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  branch_output\n "
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        output = pr_integrator.run_git(["branch"], cwd="/test/dir")

        self.assertEqual(output, "branch_output")
        mock_run.assert_called_once_with(
            ["git", "branch"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd="/test/dir"
        )

    @patch('subprocess.run')
    def test_run_git_failure(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "fatal: not a git repository"
        mock_run.return_value = mock_result

        with self.assertRaises(RuntimeError) as context:
            pr_integrator.run_git(["status"])

        self.assertIn("Git command failed: git status", str(context.exception))
        self.assertIn("fatal: not a git repository", str(context.exception))
        mock_run.assert_called_once_with(
            ["git", "status"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd="."
        )

if __name__ == '__main__':
    unittest.main()
