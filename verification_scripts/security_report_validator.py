from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from security_paths import (
    ASYNC_BLOCKING_REPORT,
    COOKIE_ARTIFACT_REPORT,
    ENV_CONTRACT_REPORT,
    GITIGNORE_POLICY_REPORT,
    IMPORT_GRAPH_REPORT,
    LOCAL_ARTIFACT_REPORT,
    PYTHON_QUALITY_REPORT,
    REDACTED_ARTIFACTS_DIR,
    REPOSITORY_HEALTH_REPORT,
    ROOT,
    SECRET_FINDINGS_BASELINE,
    SECURITY_CHECK_SUMMARY,
    SECURITY_STATUS_REPORT,
    SOURCE_INTEGRITY_REPORT,
)
from secret_artifact_inventory import DEFAULT_REPORT as INVENTORY_REPORT
from secret_artifact_redactor import MANIFEST_PATH
from secret_remediation_plan import PLAN_PATH
from secret_scan import count_secret_patterns


SUMMARY_PATH = SECURITY_CHECK_SUMMARY
REPORTS = [
    INVENTORY_REPORT,
    ENV_CONTRACT_REPORT,
    SOURCE_INTEGRITY_REPORT,
    REPOSITORY_HEALTH_REPORT,
    COOKIE_ARTIFACT_REPORT,
    LOCAL_ARTIFACT_REPORT,
    GITIGNORE_POLICY_REPORT,
    PYTHON_QUALITY_REPORT,
    IMPORT_GRAPH_REPORT,
    ASYNC_BLOCKING_REPORT,
    MANIFEST_PATH,
    PLAN_PATH,
    SECRET_FINDINGS_BASELINE,
]
REQUIRED_KEYS_BY_REPORT = {
    INVENTORY_REPORT: {"generated_utc", "contains_secret_values", "total_secret_like_count", "files"},
    ENV_CONTRACT_REPORT: {"generated_utc", "contains_secret_values", "used_count", "missing_count", "dynamic_reference_count"},
    SOURCE_INTEGRITY_REPORT: {"generated_utc", "contains_secret_values", "checked_count", "issue_count", "issues"},
    REPOSITORY_HEALTH_REPORT: {"generated_utc", "contains_secret_values", "git_status_ok", "issue_count", "issues"},
    COOKIE_ARTIFACT_REPORT: {"generated_utc", "contains_secret_values", "cookie_file_count", "sensitive_file_count", "parse_issue_count", "files"},
    LOCAL_ARTIFACT_REPORT: {"generated_utc", "contains_secret_values", "artifact_count", "total_size_bytes", "artifacts"},
    GITIGNORE_POLICY_REPORT: {"generated_utc", "contains_secret_values", "required_count", "missing_count", "missing_patterns"},
    PYTHON_QUALITY_REPORT: {"generated_utc", "contains_secret_values", "checked_count", "large_file_count", "critical_file_count", "flagged_function_count"},
    IMPORT_GRAPH_REPORT: {"generated_utc", "contains_secret_values", "module_count", "edge_count", "cycle_count", "cycles"},
    ASYNC_BLOCKING_REPORT: {"generated_utc", "contains_secret_values", "checked_count", "finding_count", "high_count", "medium_count", "findings"},
    MANIFEST_PATH: {"generated_utc", "contains_secret_values", "redacted_files"},
    PLAN_PATH: {"generated_utc", "contains_secret_values", "action_count", "destructive_action_performed", "actions"},
    SECRET_FINDINGS_BASELINE: {"generated_utc", "contains_secret_values", "total_secret_like_count", "files"},
    SUMMARY_PATH: {"generated_utc", "contains_secret_values", "ok", "steps"},
    SECURITY_STATUS_REPORT: {"generated_utc", "contains_secret_values", "strict_ready", "strict_blockers", "validator_ok"},
}


def count_text_secret_patterns(text: str) -> int:
    total = 0
    for line in text.splitlines():
        total += sum(count_secret_patterns(line).values())
    return total


def schema_missing_keys(path: Path, data: dict[str, Any]) -> list[str]:
    return sorted(REQUIRED_KEYS_BY_REPORT.get(path, set()) - set(data))


def load_report(path: Path, issues: list[str]) -> dict[str, Any]:
    if not path.exists():
        issues.append(f"missing_report:{path.relative_to(ROOT).as_posix()}")
        return {}

    text = path.read_text(encoding="utf-8")
    secret_count = count_text_secret_patterns(text)
    if secret_count:
        issues.append(f"report_contains_secret_pattern:{path.relative_to(ROOT).as_posix()}:{secret_count}")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        issues.append(f"invalid_json:{path.relative_to(ROOT).as_posix()}")
        return {}

    if data.get("contains_secret_values") is not False:
        issues.append(f"missing_false_contains_secret_values:{path.relative_to(ROOT).as_posix()}")
    missing_keys = schema_missing_keys(path, data)
    if missing_keys:
        issues.append(f"report_schema_missing_keys:{path.relative_to(ROOT).as_posix()}:{','.join(missing_keys)}")
    return data


def validate_redacted_artifacts(manifest: dict[str, Any], issues: list[str]) -> None:
    expected_paths: set[Path] = set()
    for item in manifest.get("redacted_files", []):
        redacted_path = ROOT / str(item.get("redacted_path", ""))
        expected_paths.add(redacted_path.resolve())
        if not redacted_path.exists():
            issues.append(f"missing_redacted_artifact:{redacted_path.relative_to(ROOT).as_posix()}")
            continue

        total = 0
        with redacted_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                total += sum(count_secret_patterns(line).values())
        if total:
            issues.append(f"redacted_artifact_contains_secret_pattern:{redacted_path.relative_to(ROOT).as_posix()}:{total}")

    redacted_root = REDACTED_ARTIFACTS_DIR
    if redacted_root.exists():
        for path in redacted_root.rglob("*"):
            if path.is_file() and path.resolve() not in expected_paths:
                issues.append(f"stale_redacted_artifact:{path.relative_to(ROOT).as_posix()}")


def validate_reports(include_summary: bool = False) -> list[str]:
    issues: list[str] = []
    report_paths = [*REPORTS]
    if include_summary:
        report_paths.append(SUMMARY_PATH)
        report_paths.append(SECURITY_STATUS_REPORT)

    loaded = {path: load_report(path, issues) for path in report_paths}

    remediation = loaded.get(PLAN_PATH, {})
    if remediation.get("destructive_action_performed") is not False:
        issues.append("remediation_plan_destructive_action_not_false")

    summary = loaded.get(SUMMARY_PATH, {})
    if include_summary and summary.get("ok") is not True:
        issues.append("security_summary_not_ok")

    validate_redacted_artifacts(loaded.get(MANIFEST_PATH, {}), issues)
    return issues


def main() -> int:
    issues = validate_reports(include_summary="--include-summary" in sys.argv[1:])
    if issues:
        for issue in issues:
            print(f"security_report_validator: issue={issue}", file=sys.stderr)
        return 1

    print("security_report_validator: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
