from __future__ import annotations

import re
import sys
from pathlib import Path


SECRET_PATTERNS = {
    "telegram_bot_token": re.compile(r"(?<!\d)\d{8,12}:[A-Za-z0-9_-]{30,}"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    "huggingface_token": re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    "github_token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "openai_token": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "groq_token": re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"),
}
SECRET_PATTERN_GATES = {
    "telegram_bot_token": (":",),
    "bearer_token": ("Bearer", "bearer"),
    "huggingface_token": ("hf_",),
    "github_token": ("ghp_", "github_pat_"),
    "openai_token": ("sk-",),
    "groq_token": ("gsk_",),
}
TOKEN_PATTERN = SECRET_PATTERNS["telegram_bot_token"]
INCLUDED_SUFFIXES = {
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".example",
    ".dockerignore",
    ".gitignore",
}
EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "venv",
    "data",
    "sessions",
    "security_reports",
}
EXCLUDED_SUFFIXES = {
    ".db",
    ".db-shm",
    ".db-wal",
    ".db-journal",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".sql",
    ".rar",
    ".zip",
    ".txt",
    ".mmdb",
    ".pyc",
}
ALL_MODE_EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "venv",
    "sessions",
    "security_reports",
}
ALL_MODE_EXCLUDED_SUFFIXES = {
    ".db",
    ".db-shm",
    ".db-wal",
    ".db-journal",
    ".sqlite",
    ".sqlite3",
    ".rar",
    ".zip",
    ".gz",
    ".7z",
    ".pyc",
    ".mmdb",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ttf",
    ".woff2",
    ".exe",
    ".dll",
    ".pyd",
}


def is_secret_env_file(path: Path) -> bool:
    return path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example")


def has_excluded_suffix(path: Path, excluded_suffixes: set[str]) -> bool:
    for suffix in path.suffixes:
        if suffix.lower() in excluded_suffixes:
            return True
    return path.suffix.lower() in excluded_suffixes


def should_scan(path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if is_secret_env_file(path):
        return False
    if has_excluded_suffix(path, EXCLUDED_SUFFIXES):
        return False
    return path.suffix.lower() in INCLUDED_SUFFIXES or path.name == "Dockerfile"


def should_scan_all(path: Path, include_env: bool) -> bool:
    if any(part in ALL_MODE_EXCLUDED_PARTS for part in path.parts):
        return False
    if is_secret_env_file(path) and not include_env:
        return False
    if has_excluded_suffix(path, ALL_MODE_EXCLUDED_SUFFIXES):
        return False
    return True


def count_token_patterns(line: str) -> int:
    if ":" not in line:
        return 0

    count = 0
    for _ in TOKEN_PATTERN.finditer(line):
        count += 1
    return count


def count_secret_patterns(line: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, pattern in SECRET_PATTERNS.items():
        gates = SECRET_PATTERN_GATES[name]
        if not any(gate in line for gate in gates):
            continue

        pattern_count = 0
        for _ in pattern.finditer(line):
            pattern_count += 1
        if pattern_count:
            counts[name] = pattern_count
    return counts


def main() -> int:
    args = set(sys.argv[1:])
    scan_all = "--all" in args
    include_env = "--include-env" in args
    summary = "--summary" in args
    root = Path(__file__).resolve().parent
    findings: list[tuple[Path, int, int]] = []
    summary_counts: dict[Path, int] = {}
    pattern_counts: dict[str, int] = {}

    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if not path.is_file():
            continue

        if scan_all:
            should_scan_file = should_scan_all(relative, include_env)
        else:
            should_scan_file = should_scan(relative)

        if not should_scan_file:
            continue

        try:
            handle = path.open("r", encoding="utf-8", errors="ignore")
        except OSError:
            continue

        with handle:
            for line_number, line in enumerate(handle, start=1):
                counts = count_secret_patterns(line)
                count = sum(counts.values())
                if count:
                    for pattern_name, pattern_count in counts.items():
                        pattern_counts[pattern_name] = pattern_counts.get(pattern_name, 0) + pattern_count
                    if summary:
                        summary_counts[relative] = summary_counts.get(relative, 0) + count
                    else:
                        findings.append((relative, line_number, count))

    total = sum(summary_counts.values()) if summary else sum(count for _, _, count in findings)
    if total == 0:
        print("secret_scan: ok")
        return 0

    print(f"secret_scan: secret-like patterns found ({total} matches)", file=sys.stderr)
    for pattern_name in sorted(pattern_counts):
        print(f"secret_scan: {pattern_name} count={pattern_counts[pattern_name]}", file=sys.stderr)
    if summary:
        for path in sorted(summary_counts):
            print(f"{path}: count={summary_counts[path]}", file=sys.stderr)
    else:
        for path, line_number, count in findings:
            print(f"{path}:{line_number}: count={count}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
