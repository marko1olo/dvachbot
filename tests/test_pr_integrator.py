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



class TestPrIntegratorMain(unittest.TestCase):
    @patch('pr_integrator.get_unmerged_branches')
    @patch('sys.exit')
    def test_main_get_branches_exception(self, mock_exit, mock_get_branches):
        mock_get_branches.side_effect = Exception("Failed")
        mock_exit.side_effect = SystemExit(1)
        with self.assertRaises(SystemExit):
            pr_integrator.main()
        mock_exit.assert_called_once_with(1)

    @patch('pr_integrator.get_unmerged_branches')
    @patch('pr_integrator.run_tests')
    @patch('pr_integrator.count_test_issues')
    @patch('pr_integrator.classify_branch')
    @patch('pr_integrator.verify_syntax_locally')
    @patch('pr_integrator.subprocess.run')
    @patch('pr_integrator.run_git')
    @patch('builtins.open', new_callable=mock_open)
    def test_main_happy_path(self, mock_file, mock_run_git, mock_subproc_run,
                             mock_verify_syntax, mock_classify, mock_count_issues,
                             mock_run_tests, mock_get_branches):

        mock_get_branches.return_value = ["branch1", "branch2", "branch3"]
        mock_run_tests.return_value = (True, "output")
        mock_count_issues.return_value = 0

        def classify_side_effect(branch, cwd):
            if branch == "branch1":
                return "ACCEPT", "good", ["f1.py"], 10, 5
            elif branch == "branch2":
                return "REJECT", "bad", ["f2.py"], 500, 0
            else:
                return "MANUAL_REVIEW", "hmm", ["f3.py"], 50, 50
        mock_classify.side_effect = classify_side_effect

        mock_verify_syntax.return_value = (True, "")

        pr_integrator.main()

        mock_get_branches.assert_called_once()
        self.assertEqual(mock_run_tests.call_count, 2)
        mock_subproc_run.assert_called_with(
            ["git", "merge", "--no-ff", "-m", "Merge remote-tracking branch 'branch1'", "branch1"],
            cwd="C:\\Users\\danat\\Desktop\\dvachbot",
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertEqual(mock_file.call_count, 2)

    @patch('pr_integrator.get_unmerged_branches')
    @patch('pr_integrator.run_tests')
    @patch('pr_integrator.count_test_issues')
    @patch('pr_integrator.classify_branch')
    @patch('pr_integrator.subprocess.run')
    @patch('pr_integrator.run_git')
    @patch('builtins.open', new_callable=mock_open)
    def test_main_merge_conflict(self, mock_file, mock_run_git, mock_subproc_run, mock_classify,
                                 mock_count_issues, mock_run_tests, mock_get_branches):

        mock_get_branches.return_value = ["branch1"]
        mock_run_tests.return_value = (True, "output")
        mock_count_issues.return_value = 0
        mock_classify.return_value = ("ACCEPT", "good", ["f1.py"], 10, 5)

        def subproc_side_effect(*args, **kwargs):
            if "merge" in args[0] and "--abort" not in args[0]:
                raise pr_integrator.subprocess.CalledProcessError(1, args[0])
            return MagicMock()
        mock_subproc_run.side_effect = subproc_side_effect
        mock_run_git.return_value = "M f1.py"

        pr_integrator.main()

        # Check that we aborted the merge
        abort_call_found = False
        for call in mock_subproc_run.call_args_list:
            if call[0][0] == ["git", "merge", "--abort"]:
                abort_call_found = True
        self.assertTrue(abort_call_found)

    @patch('pr_integrator.get_unmerged_branches')
    @patch('pr_integrator.run_tests')
    @patch('pr_integrator.count_test_issues')
    @patch('pr_integrator.classify_branch')
    @patch('pr_integrator.verify_syntax_locally')
    @patch('pr_integrator.subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_main_test_failure_rollback(self, mock_file, mock_subproc_run,
                                        mock_verify_syntax, mock_classify, mock_count_issues,
                                        mock_run_tests, mock_get_branches):

        mock_get_branches.return_value = ["branch1"]

        # baseline test passes, final test fails, rollback test passes
        mock_run_tests.side_effect = [(True, "ok"), (False, "fail"), (True, "ok")]
        mock_count_issues.side_effect = [0, 5, 0]

        mock_classify.return_value = ("ACCEPT", "good", ["f1.py"], 10, 5)
        mock_verify_syntax.return_value = (True, "")

        pr_integrator.main()

        reset_call_found = False
        for call in mock_subproc_run.call_args_list:
            if call[0][0] == ["git", "reset", "--hard", "HEAD~1"]:
                reset_call_found = True
        self.assertTrue(reset_call_found)

if __name__ == '__main__':
    unittest.main()
