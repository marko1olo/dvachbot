from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SECURITY_REPORTS_DIR = Path(__file__).resolve().parent / "security_reports"
REDACTED_ARTIFACTS_DIR = SECURITY_REPORTS_DIR / "redacted_artifacts"
SECRET_ARTIFACT_INVENTORY = SECURITY_REPORTS_DIR / "secret_artifact_inventory.json"
REDACTION_MANIFEST = SECURITY_REPORTS_DIR / "redaction_manifest.json"
REMEDIATION_PLAN = SECURITY_REPORTS_DIR / "remediation_plan.json"
SECURITY_CHECK_SUMMARY = SECURITY_REPORTS_DIR / "security_check_summary.json"
SECRET_FINDINGS_BASELINE = SECURITY_REPORTS_DIR / "secret_findings_baseline.json"
SECURITY_STATUS_REPORT = SECURITY_REPORTS_DIR / "security_status.json"
ENV_CONTRACT_REPORT = SECURITY_REPORTS_DIR / "env_contract.json"
SOURCE_INTEGRITY_REPORT = SECURITY_REPORTS_DIR / "source_integrity.json"
REPOSITORY_HEALTH_REPORT = SECURITY_REPORTS_DIR / "repository_health.json"
COOKIE_ARTIFACT_REPORT = SECURITY_REPORTS_DIR / "cookie_artifacts.json"
LOCAL_ARTIFACT_REPORT = SECURITY_REPORTS_DIR / "local_artifacts.json"
GITIGNORE_POLICY_REPORT = SECURITY_REPORTS_DIR / "gitignore_policy.json"
PYTHON_QUALITY_REPORT = SECURITY_REPORTS_DIR / "python_quality.json"
IMPORT_GRAPH_REPORT = SECURITY_REPORTS_DIR / "import_graph.json"
ASYNC_BLOCKING_REPORT = SECURITY_REPORTS_DIR / "async_blocking.json"
