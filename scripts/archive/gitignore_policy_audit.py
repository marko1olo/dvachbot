from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import GITIGNORE_POLICY_REPORT, ROOT
from security_report_utils import atomic_write_json


REQUIRED_PATTERNS = (
    ".env",
    ".env.*",
    "!.env.example",
    "sessions/",
    "*.session",
    "*.session-journal",
    "*.db",
    "*.db-wal",
    "*.db-shm",
    "*.sql",
    "*.sql.gz",
    "*.log",
    "*.log.*",
    "*.rar",
    "*.zip",
    "cookies*.json",
    "data/db_backup_*",
    "security_reports/",
)


def read_patterns(path: Path) -> set[str]:
    if not path.exists():
        return set()
    patterns: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.add(line)
    return patterns


def build_gitignore_policy_report(root: Path = ROOT) -> dict[str, Any]:
    gitignore = root / ".gitignore"
    present = read_patterns(gitignore)
    missing = sorted(pattern for pattern in REQUIRED_PATTERNS if pattern not in present)
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "gitignore_exists": gitignore.exists(),
        "required_count": len(REQUIRED_PATTERNS),
        "missing_count": len(missing),
        "missing_patterns": missing,
    }


def write_report(report: dict[str, Any]) -> None:
    atomic_write_json(GITIGNORE_POLICY_REPORT, report)


def main() -> int:
    args = set(sys.argv[1:])
    report = build_gitignore_policy_report(ROOT)
    write_report(report)
    print(
        "gitignore_policy_audit: "
        f"required={report['required_count']} "
        f"missing={report['missing_count']}"
    )
    print(f"gitignore_policy_audit: report={GITIGNORE_POLICY_REPORT.relative_to(ROOT)}")
    if "--fail-on-missing" in args and report["missing_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
