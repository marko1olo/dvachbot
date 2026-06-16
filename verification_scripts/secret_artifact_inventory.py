from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import ROOT, SECRET_ARTIFACT_INVENTORY
from security_report_utils import atomic_write_json
from secret_scan import count_secret_patterns, should_scan_all


DEFAULT_REPORT = SECRET_ARTIFACT_INVENTORY


def classify_artifact(path: Path) -> str:
    suffix = path.suffix.lower()
    if path.name.startswith(".env"):
        return "env"
    if suffix == ".txt":
        return "text-log"
    if suffix == ".log":
        return "runtime-log"
    if suffix == ".sql":
        return "sql-dump"
    return "text-artifact"


def recommended_action(category: str) -> str:
    if category == "env":
        return "rotate secrets, then keep local only"
    if category == "sql-dump":
        return "encrypt or destroy after verified backup"
    if category in {"runtime-log", "text-log"}:
        return "rotate exposed tokens, then redact or destroy"
    return "manual review without printing secret values"


def count_file_secrets(path: Path) -> dict[str, int]:
    totals: dict[str, int] = {}
    try:
        handle = path.open("r", encoding="utf-8", errors="ignore")
    except OSError:
        return totals

    with handle:
        for line in handle:
            counts = count_secret_patterns(line)
            for pattern_name, count in counts.items():
                totals[pattern_name] = totals.get(pattern_name, 0) + count
    return totals


def build_inventory(root: Path, include_env: bool = False) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue

        relative = path.relative_to(root)
        if not should_scan_all(relative, include_env=include_env):
            continue

        secret_counts = count_file_secrets(path)
        total_count = sum(secret_counts.values())
        if total_count == 0:
            continue

        stat = path.stat()
        category = classify_artifact(relative)
        findings.append(
            {
                "path": relative.as_posix(),
                "secret_like_count": total_count,
                "pattern_counts": secret_counts,
                "size_bytes": stat.st_size,
                "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "category": category,
                "recommended_action": recommended_action(category),
            }
        )

    findings.sort(key=lambda item: (-int(item["secret_like_count"]), str(item["path"])))
    return findings


def write_report(report_path: Path, findings: list[dict[str, Any]]) -> None:
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "total_secret_like_count": sum(int(item["secret_like_count"]) for item in findings),
        "files": findings,
    }
    atomic_write_json(report_path, payload)


def main() -> int:
    args = set(sys.argv[1:])
    include_env = "--include-env" in args
    to_stdout = "--stdout" in args
    fail_on_findings = "--fail-on-findings" in args

    findings = build_inventory(ROOT, include_env=include_env)
    report_path = DEFAULT_REPORT
    write_report(report_path, findings)

    total = sum(int(item["secret_like_count"]) for item in findings)
    if to_stdout:
        try:
            sys.stdout.buffer.write(report_path.read_bytes())
            sys.stdout.flush()
        except BrokenPipeError:
            return 0
    print(f"secret_artifact_inventory: files={len(findings)} secret_like_count={total}")
    print(f"secret_artifact_inventory: report={report_path.relative_to(ROOT)}")

    if fail_on_findings and findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
