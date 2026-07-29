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


    @patch('os.path.exists')
    @patch('subprocess.run')
    def test_verify_syntax_locally_success(self, mock_run, mock_exists):
        mock_exists.return_value = True
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        success, msg = pr_integrator.verify_syntax_locally(['valid.py'], cwd="/fake/dir")

        self.assertTrue(success)
        self.assertEqual(msg, "")
        mock_run.assert_called_once_with(
            [sys.executable, "-m", "py_compile", "valid.py"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd="/fake/dir"
        )

    @patch('os.path.exists')
    @patch('subprocess.run')
    def test_verify_syntax_locally_failure(self, mock_run, mock_exists):
        mock_exists.return_value = True
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "SyntaxError: invalid syntax"
        mock_run.return_value = mock_result

        success, msg = pr_integrator.verify_syntax_locally(['invalid.py'], cwd=".")

        self.assertFalse(success)
        self.assertEqual(msg, "Syntax check failed for invalid.py:\nSyntaxError: invalid syntax")
        mock_run.assert_called_once_with(
            [sys.executable, "-m", "py_compile", "invalid.py"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd="."
        )

    @patch('os.path.exists')
    @patch('subprocess.run')
    def test_verify_syntax_locally_non_existent(self, mock_run, mock_exists):
        mock_exists.return_value = False

        success, msg = pr_integrator.verify_syntax_locally(['missing.py'], cwd=".")

        self.assertTrue(success)
        self.assertEqual(msg, "")
        mock_run.assert_not_called()

    @patch('os.path.exists')
    @patch('subprocess.run')
    def test_verify_syntax_locally_non_python(self, mock_run, mock_exists):
        success, msg = pr_integrator.verify_syntax_locally(['README.md'], cwd=".")

        self.assertTrue(success)
        self.assertEqual(msg, "")
        mock_exists.assert_not_called()
        mock_run.assert_not_called()

if __name__ == '__main__':
    unittest.main()
