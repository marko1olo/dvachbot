import os
import unittest
from unittest.mock import patch, MagicMock
import pr_integrator
import subprocess
import sys

class TestPrIntegrator(unittest.TestCase):
    @patch('pr_integrator.subprocess.run')
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

    @patch('pr_integrator.subprocess.run')
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


    @patch('os.path.exists', return_value=True)
    @patch('pr_integrator.subprocess.run')
    def test_verify_syntax_locally_success(self, mock_run, mock_exists):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        success, error = pr_integrator.verify_syntax_locally(['valid.py'], cwd="/fake/dir")

        self.assertTrue(success)
        self.assertEqual(error, "")
        mock_run.assert_called_once_with(
            [sys.executable, "-m", "py_compile", "valid.py"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd="/fake/dir"
        )

    @patch('os.path.exists', return_value=True)
    @patch('pr_integrator.subprocess.run')
    def test_verify_syntax_locally_failure(self, mock_run, mock_exists):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "SyntaxError: invalid syntax"
        mock_run.return_value = mock_result

        success, error = pr_integrator.verify_syntax_locally(['invalid.py'], cwd="/fake/dir")

        self.assertFalse(success)
        self.assertIn("Syntax check failed for invalid.py", error)
        self.assertIn("SyntaxError", error)

    @patch('os.path.exists', return_value=False)
    @patch('pr_integrator.subprocess.run')
    def test_verify_syntax_locally_missing_file(self, mock_run, mock_exists):
        success, error = pr_integrator.verify_syntax_locally(['missing.py'])

        self.assertTrue(success)
        self.assertEqual(error, "")
        mock_run.assert_not_called()

    @patch('os.path.exists')
    @patch('pr_integrator.subprocess.run')
    def test_verify_syntax_locally_non_python(self, mock_run, mock_exists):
        success, error = pr_integrator.verify_syntax_locally(['readme.md'])

        self.assertTrue(success)
        self.assertEqual(error, "")
        mock_exists.assert_not_called()
        mock_run.assert_not_called()

if __name__ == '__main__':
    unittest.main()
