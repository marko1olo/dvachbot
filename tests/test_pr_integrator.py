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



class TestClassifyBranch(unittest.TestCase):

    @patch('pr_integrator.run_git')
    def test_classify_branch_diff_files_error(self, mock_run_git):
        mock_run_git.side_effect = Exception("git error")
        decision, reason, files, add_count, del_count = pr_integrator.classify_branch("origin/test-branch")
        self.assertEqual(decision, "MANUAL_REVIEW")
        self.assertIn("Failed to get diff files", reason)
        self.assertEqual(files, [])
        self.assertEqual(add_count, 0)
        self.assertEqual(del_count, 0)

    @patch('pr_integrator.run_git')
    def test_classify_branch_diff_text_error(self, mock_run_git):
        # First call works, second fails
        mock_run_git.side_effect = ["file1.py\nfile2.py", Exception("git error")]
        decision, reason, files, add_count, del_count = pr_integrator.classify_branch("origin/test-branch")
        self.assertEqual(decision, "MANUAL_REVIEW")
        self.assertIn("Failed to get diff text", reason)
        self.assertEqual(files, ["file1.py", "file2.py"])
        self.assertEqual(add_count, 0)
        self.assertEqual(del_count, 0)

    @patch('pr_integrator.run_git')
    @patch('pr_integrator._check_noise')
    def test_classify_branch_noise(self, mock_check_noise, mock_run_git):
        mock_run_git.side_effect = ["file1.py\n", "+ line1\n- line2"]
        mock_check_noise.return_value = ("REJECT", "Noise detected")
        decision, reason, files, add_count, del_count = pr_integrator.classify_branch("origin/test-branch")
        self.assertEqual(decision, "REJECT")
        self.assertEqual(reason, "Noise detected")
        self.assertEqual(files, ["file1.py"])
        self.assertEqual(add_count, 1)
        self.assertEqual(del_count, 1)

    @patch('pr_integrator.run_git')
    @patch('pr_integrator._check_noise')
    @patch('pr_integrator._check_reject_criteria')
    def test_classify_branch_reject(self, mock_check_reject, mock_check_noise, mock_run_git):
        mock_run_git.side_effect = ["file1.py\n", "+ line1\n- line2"]
        mock_check_noise.return_value = None
        mock_check_reject.return_value = ("REJECT", "Reject criteria met")
        decision, reason, files, add_count, del_count = pr_integrator.classify_branch("origin/test-branch")
        self.assertEqual(decision, "REJECT")
        self.assertEqual(reason, "Reject criteria met")

    @patch('pr_integrator.run_git')
    @patch('pr_integrator._check_noise')
    @patch('pr_integrator._check_reject_criteria')
    @patch('pr_integrator._check_manual_review')
    def test_classify_branch_manual_review(self, mock_check_manual, mock_check_reject, mock_check_noise, mock_run_git):
        mock_run_git.side_effect = ["file1.py\n", "+ line1\n- line2"]
        mock_check_noise.return_value = None
        mock_check_reject.return_value = None
        mock_check_manual.return_value = ("MANUAL_REVIEW", "Needs review")
        decision, reason, files, add_count, del_count = pr_integrator.classify_branch("origin/test-branch")
        self.assertEqual(decision, "MANUAL_REVIEW")
        self.assertEqual(reason, "Needs review")

    @patch('pr_integrator.run_git')
    @patch('pr_integrator._check_noise')
    @patch('pr_integrator._check_reject_criteria')
    @patch('pr_integrator._check_manual_review')
    @patch('pr_integrator._check_accept_criteria')
    def test_classify_branch_accept(self, mock_check_accept, mock_check_manual, mock_check_reject, mock_check_noise, mock_run_git):
        mock_run_git.side_effect = ["file1.py\n", "+ line1\n- line2"]
        mock_check_noise.return_value = None
        mock_check_reject.return_value = None
        mock_check_manual.return_value = None
        mock_check_accept.return_value = ("ACCEPT", "Looks good")
        decision, reason, files, add_count, del_count = pr_integrator.classify_branch("origin/test-branch")
        self.assertEqual(decision, "ACCEPT")
        self.assertEqual(reason, "Looks good")

    @patch('pr_integrator.run_git')
    @patch('pr_integrator._check_noise')
    @patch('pr_integrator._check_reject_criteria')
    @patch('pr_integrator._check_manual_review')
    @patch('pr_integrator._check_accept_criteria')
    def test_classify_branch_fallthrough(self, mock_check_accept, mock_check_manual, mock_check_reject, mock_check_noise, mock_run_git):
        mock_run_git.side_effect = ["file1.py\n", "+ line1\n- line2"]
        mock_check_noise.return_value = None
        mock_check_reject.return_value = None
        mock_check_manual.return_value = None
        mock_check_accept.return_value = None
        decision, reason, files, add_count, del_count = pr_integrator.classify_branch("origin/test-branch")
        self.assertEqual(decision, "MANUAL_REVIEW")
        self.assertEqual(reason, "Does not clearly match auto-accept/auto-reject criteria.")

if __name__ == '__main__':
    unittest.main()
