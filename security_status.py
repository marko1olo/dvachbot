import json
import sys
from datetime import datetime, timezone
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
    REMEDIATION_PLAN,
    REPOSITORY_HEALTH_REPORT,
    SECRET_ARTIFACT_INVENTORY,
    SECRET_FINDINGS_BASELINE,
    SECURITY_CHECK_SUMMARY,
    SECURITY_STATUS_REPORT,
    SOURCE_INTEGRITY_REPORT,
)
from security_report_utils import atomic_write_json
from security_report_validator import validate_reports


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def add_blocker(blockers: list[dict[str, Any]], code: str, count: int, detail: str) -> None:
    if count > 0:
        blockers.append({"code": code, "count": count, "detail": detail})


def _process_summary(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    summary = load_json(SECURITY_CHECK_SUMMARY)
    ok = bool(summary.get("ok", False))
    if not ok:
        add_blocker(strict_blockers, "source_scan_not_ok", 1, "latest security_check summary is not ok")
    return {"source_scan_ok": ok}

def _process_source_integrity(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_json(SOURCE_INTEGRITY_REPORT)
    exists = bool(report)
    issue_count = int(report.get("issue_count", 0))
    if not exists:
        add_blocker(strict_blockers, "source_integrity_missing", 1, "source integrity report is missing")
    add_blocker(strict_blockers, "source_integrity_issues", issue_count, "Python source integrity issues")
    return {
        "source_integrity_exists": exists,
        "source_integrity_issue_count": issue_count,
    }

def _process_repository_health(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_json(REPOSITORY_HEALTH_REPORT)
    exists = bool(report)
    issue_count = int(report.get("issue_count", 0))
    if not exists:
        add_blocker(strict_blockers, "repository_health_missing", 1, "repository health report is missing")
    add_blocker(strict_blockers, "repository_health_issues", issue_count, "Git metadata/status issues")
    return {
        "repository_health_exists": exists,
        "repository_health_issue_count": issue_count,
        "git_status_ok": bool(report.get("git_status_ok", False)),
    }

def _process_gitignore_policy(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_json(GITIGNORE_POLICY_REPORT)
    exists = bool(report)
    missing_count = int(report.get("missing_count", 0))
    if not exists:
        add_blocker(strict_blockers, "gitignore_policy_missing", 1, "gitignore policy report is missing")
    add_blocker(strict_blockers, "gitignore_missing_patterns", missing_count, "required local-secret ignore patterns missing")
    return {
        "gitignore_policy_exists": exists,
        "gitignore_missing_count": missing_count,
    }

def _process_cookie_artifacts(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_json(COOKIE_ARTIFACT_REPORT)
    exists = bool(report)
    sensitive_count = int(report.get("sensitive_file_count", 0))
    parse_issue_count = int(report.get("parse_issue_count", 0))
    if not exists:
        add_blocker(strict_blockers, "cookie_artifacts_missing", 1, "cookie artifact report is missing")
    add_blocker(strict_blockers, "cookie_sensitive_files", sensitive_count, "sensitive cookie jars remain local")
    add_blocker(strict_blockers, "cookie_parse_issues", parse_issue_count, "malformed cookie artifact files")
    return {
        "cookie_artifacts_exists": exists,
        "cookie_artifact_file_count": int(report.get("cookie_file_count", 0)),
        "cookie_sensitive_file_count": sensitive_count,
        "cookie_parse_issue_count": parse_issue_count,
    }

def _process_local_artifacts(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_json(LOCAL_ARTIFACT_REPORT)
    exists = bool(report)
    artifact_count = int(report.get("artifact_count", 0))
    if not exists:
        add_blocker(strict_blockers, "local_artifacts_missing", 1, "local artifact report is missing")
    add_blocker(strict_blockers, "local_sensitive_artifacts", artifact_count, "local env/db/log/archive/session artifacts remain")
    return {
        "local_artifacts_exists": exists,
        "local_artifact_count": artifact_count,
        "local_artifact_total_size_bytes": int(report.get("total_size_bytes", 0)),
    }

def _process_python_quality(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_json(PYTHON_QUALITY_REPORT)
    exists = bool(report)
    critical_file_count = int(report.get("critical_file_count", 0))
    critical_function_count = int(report.get("critical_function_count", 0))
    critical_count = critical_file_count + critical_function_count
    if not exists:
        add_blocker(strict_blockers, "python_quality_missing", 1, "Python quality report is missing")
    add_blocker(strict_blockers, "python_quality_critical_findings", critical_count, "critical Python file/function size findings")
    return {
        "python_quality_exists": exists,
        "python_quality_large_file_count": int(report.get("large_file_count", 0)),
        "python_quality_critical_file_count": critical_file_count,
        "python_quality_flagged_function_count": int(report.get("flagged_function_count", 0)),
        "python_quality_critical_function_count": critical_function_count,
        "python_quality_critical_count": critical_count,
    }

def _process_import_graph(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_json(IMPORT_GRAPH_REPORT)
    exists = bool(report)
    cycle_count = int(report.get("cycle_count", 0))
    if not exists:
        add_blocker(strict_blockers, "import_graph_missing", 1, "import graph report is missing")
    add_blocker(strict_blockers, "import_graph_cycles", cycle_count, "project import cycles")
    return {
        "import_graph_exists": exists,
        "import_graph_module_count": int(report.get("module_count", 0)),
        "import_graph_edge_count": int(report.get("edge_count", 0)),
        "import_graph_cycle_count": cycle_count,
    }

def _process_async_blocking(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_json(ASYNC_BLOCKING_REPORT)
    exists = bool(report)
    high_count = int(report.get("high_count", 0))
    medium_count = int(report.get("medium_count", 0))
    if not exists:
        add_blocker(strict_blockers, "async_blocking_missing", 1, "async blocking report is missing")
    add_blocker(strict_blockers, "async_blocking_high_findings", high_count, "high-risk blocking calls inside async functions")
    return {
        "async_blocking_exists": exists,
        "async_blocking_finding_count": int(report.get("finding_count", 0)),
        "async_blocking_high_count": high_count,
        "async_blocking_medium_count": medium_count,
    }

def _process_env_contract(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_json(ENV_CONTRACT_REPORT)
    exists = bool(report)
    missing_count = int(report.get("missing_count", 0))
    dynamic_count = int(report.get("dynamic_reference_count", 0))
    if not exists:
        add_blocker(strict_blockers, "env_contract_missing", 1, "env contract report is missing")
    add_blocker(strict_blockers, "env_contract_missing_keys", missing_count, "used env keys missing from .env.example")
    add_blocker(strict_blockers, "env_contract_dynamic_refs", dynamic_count, "dynamic env references remain")
    return {
        "env_contract_exists": exists,
        "env_contract_missing_count": missing_count,
        "env_contract_dynamic_reference_count": dynamic_count,
    }

def _process_inventory_and_baseline() -> dict[str, Any]:
    inventory = load_json(SECRET_ARTIFACT_INVENTORY)
    baseline = load_json(SECRET_FINDINGS_BASELINE)
    return {
        "inventory_files": len(inventory.get("files", [])),
        "inventory_secret_like_count": int(inventory.get("total_secret_like_count", 0)),
        "baseline_total_secret_like_count": int(baseline.get("total_secret_like_count", 0)),
    }

def _process_remediation(strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_json(REMEDIATION_PLAN)
    action_count = int(report.get("action_count", 0))
    add_blocker(strict_blockers, "remediation_actions", action_count, "manual secret remediation actions remain")
    return {
        "remediation_actions": action_count,
        "destructive_action_performed": bool(report.get("destructive_action_performed", False)),
    }

def _process_validator(strict_blockers: list[dict[str, Any]], include_summary_validation: bool) -> dict[str, Any]:
    issues = validate_reports(include_summary=include_summary_validation)
    add_blocker(strict_blockers, "validator_issues", len(issues), "security report validator issues")
    return {
        "validator_ok": not issues,
        "validator_issues": issues,
    }

def build_status(include_summary_validation: bool = True) -> dict[str, Any]:
    strict_blockers: list[dict[str, Any]] = []

    status: dict[str, Any] = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
    }

    status.update(_process_summary(strict_blockers))
    status.update(_process_source_integrity(strict_blockers))
    status.update(_process_repository_health(strict_blockers))
    status.update(_process_gitignore_policy(strict_blockers))
    status.update(_process_cookie_artifacts(strict_blockers))
    status.update(_process_local_artifacts(strict_blockers))
    status.update(_process_python_quality(strict_blockers))
    status.update(_process_import_graph(strict_blockers))
    status.update(_process_async_blocking(strict_blockers))
    status.update(_process_env_contract(strict_blockers))
    status.update(_process_inventory_and_baseline())
    status.update(_process_remediation(strict_blockers))
    status.update(_process_validator(strict_blockers, include_summary_validation))

    status.update({
        "strict_blocker_count": len(strict_blockers),
        "strict_blockers": strict_blockers,
        "strict_ready": len(strict_blockers) == 0,
    })

    return status


def write_status(status: dict[str, Any]) -> None:
    atomic_write_json(SECURITY_STATUS_REPORT, status)


def main() -> int:
    status = build_status(include_summary_validation="--skip-summary-validation" not in sys.argv[1:])
    write_status(status)
    print(
        "security_status: "
        f"source_scan_ok={status['source_scan_ok']} "
        f"source_integrity_issues={status['source_integrity_issue_count']} "
        f"repo_issues={status['repository_health_issue_count']} "
        f"gitignore_missing={status['gitignore_missing_count']} "
        f"cookie_sensitive_files={status['cookie_sensitive_file_count']} "
        f"local_artifacts={status['local_artifact_count']} "
        f"quality_critical={status['python_quality_critical_count']} "
        f"import_cycles={status['import_graph_cycle_count']} "
        f"async_blocking_high={status['async_blocking_high_count']} "
        f"env_missing={status['env_contract_missing_count']} "
        f"inventory_files={status['inventory_files']} "
        f"secret_like_count={status['inventory_secret_like_count']} "
        f"remediation_actions={status['remediation_actions']} "
        f"validator_ok={status['validator_ok']} "
        f"strict_blockers={status['strict_blocker_count']} "
        f"strict_ready={status['strict_ready']}"
    )
    print(f"security_status: report={SECURITY_STATUS_REPORT}")
    if "--fail-if-not-strict-ready" in sys.argv[1:] and not status["strict_ready"]:
        return 1
    return 0 if status["validator_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
