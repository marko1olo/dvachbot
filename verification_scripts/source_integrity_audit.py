from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import ROOT, SOURCE_INTEGRITY_REPORT
from security_report_utils import atomic_write_json


EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "venv",
    "data",
    "sessions",
    "security_reports",
}


def should_scan_python(path: Path) -> bool:
    return path.suffix == ".py" and not any(part in EXCLUDED_PARTS for part in path.parts)


def inspect_python_file(path: Path, root: Path) -> dict[str, Any] | None:
    relative = path.relative_to(root).as_posix()
    raw = path.read_bytes()

    nul_index = raw.find(b"\x00")
    if nul_index != -1:
        return {"path": relative, "issue": "nul_byte", "byte_offset": nul_index}

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {
            "path": relative,
            "issue": "utf8_decode_error",
            "byte_offset": exc.start,
        }

    try:
        ast.parse(text, filename=relative)
    except SyntaxError as exc:
        return {
            "path": relative,
            "issue": "syntax_error",
            "line": exc.lineno,
            "offset": exc.offset,
            "message": exc.msg,
        }

    return None


def build_source_integrity_report(root: Path = ROOT) -> dict[str, Any]:
    checked_count = 0
    issues: list[dict[str, Any]] = []

    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if not should_scan_python(relative):
            continue

        checked_count += 1
        issue = inspect_python_file(path, root)
        if issue is not None:
            issues.append(issue)

    issues.sort(key=lambda item: item["path"])
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "checked_count": checked_count,
        "issue_count": len(issues),
        "issues": issues,
    }


def write_report(report: dict[str, Any]) -> None:
    atomic_write_json(SOURCE_INTEGRITY_REPORT, report)


def main() -> int:
    args = set(sys.argv[1:])
    report = build_source_integrity_report(ROOT)
    write_report(report)
    print(
        "source_integrity_audit: "
        f"checked={report['checked_count']} "
        f"issues={report['issue_count']}"
    )
    print(f"source_integrity_audit: report={SOURCE_INTEGRITY_REPORT.relative_to(ROOT)}")
    if "--fail-on-issues" in args and report["issue_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
