from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import LOCAL_ARTIFACT_REPORT, ROOT
from security_report_utils import atomic_write_json


EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "venv",
    "security_reports",
}
SENSITIVE_FILE_NAMES = {
    ".env",
    "bot.lock",
    "cookies.json",
    "cookies_4chan.json",
}
SENSITIVE_SUFFIXES = (
    ".db",
    ".db-shm",
    ".db-wal",
    ".dump",
    ".log",
    ".rar",
    ".session",
    ".session-journal",
    ".sql",
    ".sqlite",
    ".sqlite3",
    ".zip",
    ".7z",
)
SENSITIVE_COMPOUND_SUFFIXES = (
    ".sql.gz",
    ".tar.gz",
)
SENSITIVE_DIRS = {
    "sessions": "session-directory",
}


def excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def inside_aggregated_sensitive_dir(path: Path) -> bool:
    return any(part.lower() in SENSITIVE_DIRS for part in path.parts[:-1])


def artifact_category(path: Path) -> str | None:
    name = path.name.lower()
    suffix = path.suffix.lower()

    if name == ".env":
        return "env"
    if name.startswith("cookies") and suffix == ".json":
        return "cookie-jar"
    if name == "bot.lock":
        return "runtime-lock"
    if name.startswith("db_backup_") and name.endswith(".sql.gz"):
        return "database-backup"
    if name.startswith("tgach_backup_") or suffix in {".rar", ".zip", ".7z"}:
        return "archive"
    if name.endswith(SENSITIVE_COMPOUND_SUFFIXES):
        return "compressed-dump"
    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return "database"
    if name.endswith((".db-wal", ".db-shm")):
        return "database-sidecar"
    if suffix == ".sql":
        return "sql-dump"
    if suffix in {".log"} or ".log." in name:
        return "runtime-log"
    if suffix in {".session", ".session-journal"}:
        return "session-file"
    if name in SENSITIVE_FILE_NAMES or suffix in SENSITIVE_SUFFIXES:
        return "local-sensitive"
    return None


def directory_item(path: Path, root: Path, category: str) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    for child in path.rglob("*"):
        if child.is_file():
            file_count += 1
            try:
                total_bytes += child.stat().st_size
            except OSError:
                pass

    stat = path.stat()
    return {
        "path": path.relative_to(root).as_posix(),
        "category": category,
        "kind": "directory",
        "file_count": file_count,
        "size_bytes": total_bytes,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "recommended_action": "keep local-only; rotate credentials if copied or exposed",
    }


def file_item(path: Path, root: Path, category: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": path.relative_to(root).as_posix(),
        "category": category,
        "kind": "file",
        "file_count": 1,
        "size_bytes": stat.st_size,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "recommended_action": "keep local-only; encrypt, move, or destroy after verified backup",
    }


def build_local_artifact_report(root: Path = ROOT) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []

    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if excluded(relative):
            continue

        if path.is_dir():
            category = SENSITIVE_DIRS.get(path.name.lower())
            if category:
                artifacts.append(directory_item(path, root, category))
            continue

        if not path.is_file():
            continue

        if inside_aggregated_sensitive_dir(relative):
            continue

        category = artifact_category(relative)
        if category:
            artifacts.append(file_item(path, root, category))

    artifacts.sort(key=lambda item: (str(item["category"]), str(item["path"])))
    total_bytes = sum(int(item["size_bytes"]) for item in artifacts)
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "artifact_count": len(artifacts),
        "total_size_bytes": total_bytes,
        "artifacts": artifacts,
    }


def write_report(report: dict[str, Any]) -> None:
    atomic_write_json(LOCAL_ARTIFACT_REPORT, report)


def main() -> int:
    args = set(sys.argv[1:])
    report = build_local_artifact_report(ROOT)
    write_report(report)
    print(
        "local_artifact_audit: "
        f"artifacts={report['artifact_count']} "
        f"total_size_bytes={report['total_size_bytes']}"
    )
    print(f"local_artifact_audit: report={LOCAL_ARTIFACT_REPORT.relative_to(ROOT)}")
    if "--fail-on-artifacts" in args and report["artifact_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
