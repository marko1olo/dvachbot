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


def _load_reports() -> dict[str, dict[str, Any]]:
    return {
        "summary": load_json(SECURITY_CHECK_SUMMARY),
        "inventory": load_json(SECRET_ARTIFACT_INVENTORY),
        "baseline": load_json(SECRET_FINDINGS_BASELINE),
        "remediation": load_json(REMEDIATION_PLAN),
        "env_contract": load_json(ENV_CONTRACT_REPORT),
        "source_integrity": load_json(SOURCE_INTEGRITY_REPORT),
        "repository_health": load_json(REPOSITORY_HEALTH_REPORT),
        "cookie_artifacts": load_json(COOKIE_ARTIFACT_REPORT),
        "local_artifacts": load_json(LOCAL_ARTIFACT_REPORT),
        "gitignore_policy": load_json(GITIGNORE_POLICY_REPORT),
        "python_quality": load_json(PYTHON_QUALITY_REPORT),
        "import_graph": load_json(IMPORT_GRAPH_REPORT),
        "async_blocking": load_json(ASYNC_BLOCKING_REPORT),
    }


def _evaluate_blockers(reports: dict[str, dict[str, Any]], validator_issues: list[Any]) -> list[dict[str, Any]]:
    strict_blockers: list[dict[str, Any]] = []

    summary = reports["summary"]
    source_integrity = reports["source_integrity"]
    repository_health = reports["repository_health"]
    gitignore_policy = reports["gitignore_policy"]
    cookie_artifacts = reports["cookie_artifacts"]
    local_artifacts = reports["local_artifacts"]
    python_quality = reports["python_quality"]
    import_graph = reports["import_graph"]
    async_blocking = reports["async_blocking"]
    env_contract = reports["env_contract"]
    remediation = reports["remediation"]

    if not bool(summary.get("ok", False)):
        add_blocker(strict_blockers, "source_scan_not_ok", 1, "latest security_check summary is not ok")

    if not bool(source_integrity):
        add_blocker(strict_blockers, "source_integrity_missing", 1, "source integrity report is missing")
    add_blocker(strict_blockers, "source_integrity_issues", int(source_integrity.get("issue_count", 0)), "Python source integrity issues")

    if not bool(repository_health):
        add_blocker(strict_blockers, "repository_health_missing", 1, "repository health report is missing")
    add_blocker(strict_blockers, "repository_health_issues", int(repository_health.get("issue_count", 0)), "Git metadata/status issues")

    if not bool(gitignore_policy):
        add_blocker(strict_blockers, "gitignore_policy_missing", 1, "gitignore policy report is missing")
    add_blocker(strict_blockers, "gitignore_missing_patterns", int(gitignore_policy.get("missing_count", 0)), "required local-secret ignore patterns missing")

    if not bool(cookie_artifacts):
        add_blocker(strict_blockers, "cookie_artifacts_missing", 1, "cookie artifact report is missing")
    add_blocker(strict_blockers, "cookie_sensitive_files", int(cookie_artifacts.get("sensitive_file_count", 0)), "sensitive cookie jars remain local")
    add_blocker(strict_blockers, "cookie_parse_issues", int(cookie_artifacts.get("parse_issue_count", 0)), "malformed cookie artifact files")

    if not bool(local_artifacts):
        add_blocker(strict_blockers, "local_artifacts_missing", 1, "local artifact report is missing")
    add_blocker(strict_blockers, "local_sensitive_artifacts", int(local_artifacts.get("artifact_count", 0)), "local env/db/log/archive/session artifacts remain")

    if not bool(python_quality):
        add_blocker(strict_blockers, "python_quality_missing", 1, "Python quality report is missing")
    python_quality_critical_count = int(python_quality.get("critical_file_count", 0)) + int(python_quality.get("critical_function_count", 0))
    add_blocker(strict_blockers, "python_quality_critical_findings", python_quality_critical_count, "critical Python file/function size findings")

    if not bool(import_graph):
        add_blocker(strict_blockers, "import_graph_missing", 1, "import graph report is missing")
    add_blocker(strict_blockers, "import_graph_cycles", int(import_graph.get("cycle_count", 0)), "project import cycles")

    if not bool(async_blocking):
        add_blocker(strict_blockers, "async_blocking_missing", 1, "async blocking report is missing")
    add_blocker(strict_blockers, "async_blocking_high_findings", int(async_blocking.get("high_count", 0)), "high-risk blocking calls inside async functions")

    if not bool(env_contract):
        add_blocker(strict_blockers, "env_contract_missing", 1, "env contract report is missing")
    add_blocker(strict_blockers, "env_contract_missing_keys", int(env_contract.get("missing_count", 0)), "used env keys missing from .env.example")
    add_blocker(strict_blockers, "env_contract_dynamic_refs", int(env_contract.get("dynamic_reference_count", 0)), "dynamic env references remain")

    add_blocker(strict_blockers, "remediation_actions", int(remediation.get("action_count", 0)), "manual secret remediation actions remain")
    add_blocker(strict_blockers, "validator_issues", len(validator_issues), "security report validator issues")

    return strict_blockers


def _build_status_dict(reports: dict[str, dict[str, Any]], validator_issues: list[Any], strict_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    summary = reports["summary"]
    inventory = reports["inventory"]
    baseline = reports["baseline"]
    remediation = reports["remediation"]
    env_contract = reports["env_contract"]
    source_integrity = reports["source_integrity"]
    repository_health = reports["repository_health"]
    cookie_artifacts = reports["cookie_artifacts"]
    local_artifacts = reports["local_artifacts"]
    gitignore_policy = reports["gitignore_policy"]
    python_quality = reports["python_quality"]
    import_graph = reports["import_graph"]
    async_blocking = reports["async_blocking"]

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "source_scan_ok": bool(summary.get("ok", False)),
        "source_integrity_exists": bool(source_integrity),
        "source_integrity_issue_count": int(source_integrity.get("issue_count", 0)),
        "repository_health_exists": bool(repository_health),
        "repository_health_issue_count": int(repository_health.get("issue_count", 0)),
        "git_status_ok": bool(repository_health.get("git_status_ok", False)),
        "gitignore_policy_exists": bool(gitignore_policy),
        "gitignore_missing_count": int(gitignore_policy.get("missing_count", 0)),
        "cookie_artifacts_exists": bool(cookie_artifacts),
        "cookie_artifact_file_count": int(cookie_artifacts.get("cookie_file_count", 0)),
        "cookie_sensitive_file_count": int(cookie_artifacts.get("sensitive_file_count", 0)),
        "cookie_parse_issue_count": int(cookie_artifacts.get("parse_issue_count", 0)),
        "local_artifacts_exists": bool(local_artifacts),
        "local_artifact_count": int(local_artifacts.get("artifact_count", 0)),
        "local_artifact_total_size_bytes": int(local_artifacts.get("total_size_bytes", 0)),
        "python_quality_exists": bool(python_quality),
        "python_quality_large_file_count": int(python_quality.get("large_file_count", 0)),
        "python_quality_critical_file_count": int(python_quality.get("critical_file_count", 0)),
        "python_quality_flagged_function_count": int(python_quality.get("flagged_function_count", 0)),
        "python_quality_critical_function_count": int(python_quality.get("critical_function_count", 0)),
        "python_quality_critical_count": int(python_quality.get("critical_file_count", 0)) + int(python_quality.get("critical_function_count", 0)),
        "import_graph_exists": bool(import_graph),
        "import_graph_module_count": int(import_graph.get("module_count", 0)),
        "import_graph_edge_count": int(import_graph.get("edge_count", 0)),
        "import_graph_cycle_count": int(import_graph.get("cycle_count", 0)),
        "async_blocking_exists": bool(async_blocking),
        "async_blocking_finding_count": int(async_blocking.get("finding_count", 0)),
        "async_blocking_high_count": int(async_blocking.get("high_count", 0)),
        "async_blocking_medium_count": int(async_blocking.get("medium_count", 0)),
        "env_contract_exists": bool(env_contract),
        "env_contract_missing_count": int(env_contract.get("missing_count", 0)),
        "env_contract_dynamic_reference_count": int(env_contract.get("dynamic_reference_count", 0)),
        "inventory_files": len(inventory.get("files", [])),
        "inventory_secret_like_count": int(inventory.get("total_secret_like_count", 0)),
        "baseline_total_secret_like_count": int(baseline.get("total_secret_like_count", 0)),
        "remediation_actions": int(remediation.get("action_count", 0)),
        "destructive_action_performed": bool(remediation.get("destructive_action_performed", False)),
        "validator_ok": not validator_issues,
        "validator_issues": validator_issues,
        "strict_blocker_count": len(strict_blockers),
        "strict_blockers": strict_blockers,
        "strict_ready": len(strict_blockers) == 0,
    }


def build_status(include_summary_validation: bool = True) -> dict[str, Any]:
    reports = _load_reports()
    validator_issues = validate_reports(include_summary=include_summary_validation)
    strict_blockers = _evaluate_blockers(reports, validator_issues)
    return _build_status_dict(reports, validator_issues, strict_blockers)


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
