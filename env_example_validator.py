from __future__ import annotations

import sys
from pathlib import Path

from security_paths import ROOT
from secret_scan import count_secret_patterns


ENV_EXAMPLE = ROOT / ".env.example"
SECRET_KEY_MARKERS = (
    "TOKEN",
    "SECRET",
    "API_KEY",
    "API_HASH",
    "PASSWORD",
    "PRIVATE",
)


def is_sensitive_key(key: str) -> bool:
    upper = key.upper()
    return any(marker in upper for marker in SECRET_KEY_MARKERS)


def validate_env_example(path: Path = ENV_EXAMPLE) -> list[str]:
    issues: list[str] = []
    if not path.exists():
        return ["missing_env_example"]

    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            issues.append(f"malformed_line:{line_number}")
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            issues.append(f"empty_key:{line_number}")
            continue

        if key in seen:
            issues.append(f"duplicate_key:{key}:{line_number}")
        seen.add(key)

        secret_count = sum(count_secret_patterns(value).values())
        if secret_count:
            issues.append(f"secret_pattern_value:{key}:{line_number}:{secret_count}")

        if is_sensitive_key(key) and value:
            issues.append(f"sensitive_key_has_default:{key}:{line_number}")

    return issues


def main() -> int:
    issues = validate_env_example()
    if issues:
        for issue in issues:
            print(f"env_example_validator: issue={issue}", file=sys.stderr)
        return 1

    print("env_example_validator: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
