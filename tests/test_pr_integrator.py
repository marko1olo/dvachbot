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


    def test_count_test_issues_summary(self):
        output = "FAILED (failures=2, errors=1)"
        self.assertEqual(pr_integrator.count_test_issues(output), 3)

    def test_count_test_issues_ok(self):
        output = "Ran 15 tests in 0.052s\n\nOK\n"
        self.assertEqual(pr_integrator.count_test_issues(output), 0)

    def test_count_test_issues_no_summary_but_failed(self):
        output = "======================================================================\nFAIL: test_something\n======================================================================\nFAILED"
        self.assertEqual(pr_integrator.count_test_issues(output), 2)

    def test_count_test_issues_zero_if_no_failed(self):
        output = "Some random output without FAILED or OK"
        self.assertEqual(pr_integrator.count_test_issues(output), 0)

if __name__ == '__main__':
    unittest.main()
