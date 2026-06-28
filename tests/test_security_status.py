import unittest
from unittest.mock import patch, MagicMock
import asyncio

# Since we might have aiogram/asyncio initialization issues as mentioned in memory,
# but we are just testing a synchronous script, it should be fine. We will just import build_status.
import sys
import os
from pathlib import Path

# Add verification_scripts to path if not already there, though PYTHONPATH usually handles it
import security_status


class TestSecurityStatus(unittest.TestCase):
    @patch("security_status.validate_reports")
    @patch("security_status.load_json")
    def test_build_status_happy_path(self, mock_load_json, mock_validate_reports):
        def load_json_side_effect(path):
            if "security_check_summary" in path.name:
                return {"ok": True}
            return {"dummy": "exists"}

        mock_load_json.side_effect = load_json_side_effect
        mock_validate_reports.return_value = []

        status = security_status.build_status(include_summary_validation=False)

        self.assertTrue(status["strict_ready"])
        self.assertEqual(status["strict_blocker_count"], 0)
        self.assertTrue(status["validator_ok"])
        self.assertEqual(status["strict_blockers"], [])

    @patch("security_status.validate_reports")
    @patch("security_status.load_json")
    def test_build_status_missing_reports(self, mock_load_json, mock_validate_reports):
        mock_load_json.return_value = {}
        mock_validate_reports.return_value = []

        status = security_status.build_status(include_summary_validation=False)

        self.assertFalse(status["strict_ready"])
        self.assertTrue(status["strict_blocker_count"] > 0)

        blocker_codes = [b["code"] for b in status["strict_blockers"]]
        expected_codes = [
            "source_scan_not_ok",
            "source_integrity_missing",
            "repository_health_missing",
            "gitignore_policy_missing",
            "cookie_artifacts_missing",
            "local_artifacts_missing",
            "python_quality_missing",
            "import_graph_missing",
            "async_blocking_missing",
            "env_contract_missing",
        ]

        for code in expected_codes:
            self.assertIn(code, blocker_codes)

    @patch("security_status.validate_reports")
    @patch("security_status.load_json")
    def test_build_status_issues_present(self, mock_load_json, mock_validate_reports):
        mock_load_json.return_value = {
            "ok": True,
            "issue_count": 1,
            "missing_count": 1,
            "sensitive_file_count": 1,
            "parse_issue_count": 1,
            "artifact_count": 1,
            "critical_file_count": 1,
            "critical_function_count": 0,
            "cycle_count": 1,
            "high_count": 1,
            "medium_count": 0,
            "action_count": 1,
            "dynamic_reference_count": 1,
        }
        mock_validate_reports.return_value = [{"issue": "test issue"}]

        status = security_status.build_status(include_summary_validation=False)

        self.assertFalse(status["strict_ready"])
        self.assertFalse(status["validator_ok"])
        self.assertTrue(status["strict_blocker_count"] > 0)

        blocker_codes = [b["code"] for b in status["strict_blockers"]]
        expected_codes = [
            "source_integrity_issues",
            "repository_health_issues",
            "gitignore_missing_patterns",
            "cookie_sensitive_files",
            "cookie_parse_issues",
            "local_sensitive_artifacts",
            "python_quality_critical_findings",
            "import_graph_cycles",
            "async_blocking_high_findings",
            "env_contract_missing_keys",
            "env_contract_dynamic_refs",
            "remediation_actions",
            "validator_issues",
        ]

        for code in expected_codes:
            self.assertIn(code, blocker_codes)


if __name__ == "__main__":
    unittest.main()
