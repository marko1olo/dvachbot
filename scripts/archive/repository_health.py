from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import REPOSITORY_HEALTH_REPORT, ROOT
from security_report_utils import atomic_write_json


def has_git_objects(git_dir: Path) -> bool:
    objects = git_dir / "objects"
    if not objects.is_dir():
        return False
    for path in objects.iterdir():
        if path.name not in {"info", "pack"}:
            return True
        if path.is_dir() and any(path.iterdir()):
            return True
    return False


def build_repository_health(root: Path = ROOT) -> dict[str, Any]:
    git_dir = root / ".git"
    issues: list[str] = []
    status_exit_code: int | None = None
    status_error = ""

    git_dir_exists = git_dir.exists()
    git_head_exists = (git_dir / "HEAD").exists()
    git_objects_present = has_git_objects(git_dir) if git_dir_exists else False

    if not git_dir_exists:
        issues.append("missing_git_dir")
    else:
        if not git_head_exists:
            issues.append("missing_git_head")
        if not git_objects_present:
            issues.append("missing_or_empty_git_objects")

        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            text=True,
            capture_output=True,
        )
        status_exit_code = result.returncode
        if result.returncode != 0:
            issues.append("git_status_failed")
            status_error = (result.stderr or result.stdout).splitlines()[0] if (result.stderr or result.stdout) else ""

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "git_dir_exists": git_dir_exists,
        "git_head_exists": git_head_exists,
        "git_objects_present": git_objects_present,
        "git_status_exit_code": status_exit_code,
        "git_status_ok": status_exit_code == 0,
        "git_status_error": status_error,
        "issue_count": len(issues),
        "issues": issues,
    }


def write_report(report: dict[str, Any]) -> None:
    atomic_write_json(REPOSITORY_HEALTH_REPORT, report)


def main() -> int:
    args = set(sys.argv[1:])
    report = build_repository_health(ROOT)
    write_report(report)
    print(
        "repository_health: "
        f"git_status_ok={report['git_status_ok']} "
        f"issues={report['issue_count']}"
    )
    print(f"repository_health: report={REPOSITORY_HEALTH_REPORT.relative_to(ROOT)}")
    if "--fail-on-issues" in args and report["issue_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
