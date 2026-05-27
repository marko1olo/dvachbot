from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import ROOT, SECRET_FINDINGS_BASELINE
from secret_artifact_inventory import DEFAULT_REPORT as INVENTORY_REPORT
from security_report_utils import atomic_write_json


BASELINE_PATH = SECRET_FINDINGS_BASELINE


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for item in inventory.get("files", []):
        path = str(item.get("path", ""))
        files[path] = {
            "secret_like_count": int(item.get("secret_like_count", 0)),
            "pattern_counts": dict(item.get("pattern_counts", {})),
        }

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "total_secret_like_count": sum(int(item["secret_like_count"]) for item in files.values()),
        "files": files,
    }


def compare_to_baseline(current: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    current_files = current.get("files", {})
    baseline_files = baseline.get("files", {})

    if int(current.get("total_secret_like_count", 0)) > int(baseline.get("total_secret_like_count", 0)):
        issues.append("total_secret_like_count_increased")

    for path, current_item in current_files.items():
        baseline_item = baseline_files.get(path)
        if baseline_item is None:
            issues.append(f"new_secret_artifact:{path}")
            continue

        if int(current_item.get("secret_like_count", 0)) > int(baseline_item.get("secret_like_count", 0)):
            issues.append(f"secret_count_increased:{path}")

        current_patterns = current_item.get("pattern_counts", {})
        baseline_patterns = baseline_item.get("pattern_counts", {})
        for pattern_name, current_count in current_patterns.items():
            if int(current_count) > int(baseline_patterns.get(pattern_name, 0)):
                issues.append(f"pattern_count_increased:{path}:{pattern_name}")

    return issues


def write_baseline(baseline: dict[str, Any]) -> None:
    atomic_write_json(BASELINE_PATH, baseline)


def main() -> int:
    args = set(sys.argv[1:])
    inventory = load_json(INVENTORY_REPORT)
    current = normalize_inventory(inventory)

    if "--update" in args or not BASELINE_PATH.exists():
        write_baseline(current)
        print(f"secret_findings_baseline: baseline_written={BASELINE_PATH.relative_to(ROOT)}")
        return 0

    baseline = load_json(BASELINE_PATH)
    issues = compare_to_baseline(current, baseline)
    if issues:
        for issue in issues:
            print(f"secret_findings_baseline: issue={issue}", file=sys.stderr)
        return 1

    print("secret_findings_baseline: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
