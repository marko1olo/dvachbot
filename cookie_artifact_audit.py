from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import COOKIE_ARTIFACT_REPORT, ROOT
from security_report_utils import atomic_write_json


EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "venv",
    "data",
    "sessions",
    "security_reports",
}
SENSITIVE_KEY_FRAGMENTS = (
    "auth",
    "bm",
    "cf_",
    "clearance",
    "session",
    "token",
)


def should_scan_cookie_file(path: Path) -> bool:
    return (
        path.name.lower().startswith("cookies")
        and path.suffix.lower() == ".json"
        and not any(part in EXCLUDED_PARTS for part in path.parts)
    )


def is_sensitive_cookie_key(key: str) -> bool:
    lower = key.lower()
    return any(fragment in lower for fragment in SENSITIVE_KEY_FRAGMENTS)


def inspect_cookie_file(path: Path, root: Path) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    stat = path.stat()
    item: dict[str, Any] = {
        "path": relative,
        "size_bytes": stat.st_size,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "cookie_count": 0,
        "sensitive_key_count": 0,
        "sensitive_keys": [],
        "has_user_agent": False,
        "parse_ok": False,
        "recommended_action": "keep local-only; refresh exposed cookies; never commit cookie jars",
    }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        item["recommended_action"] = "repair or remove malformed local cookie artifact"
        return item

    if not isinstance(data, dict):
        item["recommended_action"] = "review non-object cookie artifact"
        return item

    keys = [str(key) for key in data]
    sensitive_keys = sorted(key for key in keys if is_sensitive_cookie_key(key))
    item["parse_ok"] = True
    item["cookie_count"] = len(keys)
    item["sensitive_key_count"] = len(sensitive_keys)
    item["sensitive_keys"] = sensitive_keys
    item["has_user_agent"] = "user_agent" in data
    return item


def build_cookie_artifact_report(root: Path = ROOT) -> dict[str, Any]:
    files = [
        inspect_cookie_file(path, root)
        for path in root.rglob("cookies*.json")
        if path.is_file() and should_scan_cookie_file(path.relative_to(root))
    ]
    files.sort(key=lambda item: item["path"])
    sensitive_file_count = sum(1 for item in files if int(item["sensitive_key_count"]) > 0)
    parse_issue_count = sum(1 for item in files if not item["parse_ok"])

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "cookie_file_count": len(files),
        "sensitive_file_count": sensitive_file_count,
        "parse_issue_count": parse_issue_count,
        "files": files,
    }


def write_report(report: dict[str, Any]) -> None:
    atomic_write_json(COOKIE_ARTIFACT_REPORT, report)


def main() -> int:
    args = set(sys.argv[1:])
    report = build_cookie_artifact_report(ROOT)
    write_report(report)
    print(
        "cookie_artifact_audit: "
        f"files={report['cookie_file_count']} "
        f"sensitive_files={report['sensitive_file_count']} "
        f"parse_issues={report['parse_issue_count']}"
    )
    print(f"cookie_artifact_audit: report={COOKIE_ARTIFACT_REPORT.relative_to(ROOT)}")
    if "--fail-on-sensitive" in args and report["sensitive_file_count"]:
        return 1
    if "--fail-on-parse-issues" in args and report["parse_issue_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
