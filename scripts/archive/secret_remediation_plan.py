from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import REMEDIATION_PLAN, ROOT
from secret_artifact_inventory import DEFAULT_REPORT as INVENTORY_REPORT
from secret_artifact_redactor import MANIFEST_PATH
from security_report_utils import atomic_write_json


PLAN_PATH = REMEDIATION_PLAN


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def index_redacted_paths(manifest: dict[str, Any]) -> dict[str, str]:
    indexed: dict[str, str] = {}
    for item in manifest.get("redacted_files", []):
        indexed[str(item.get("source_path", ""))] = str(item.get("redacted_path", ""))
    return indexed


def severity_for_count(secret_count: int) -> str:
    if secret_count >= 100:
        return "critical"
    if secret_count >= 10:
        return "high"
    return "medium"


def build_plan(inventory: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    redacted_paths = index_redacted_paths(manifest)
    actions: list[dict[str, Any]] = []

    for item in inventory.get("files", []):
        source_path = str(item.get("path", ""))
        secret_count = int(item.get("secret_like_count", 0))
        actions.append(
            {
                "source_path": source_path,
                "redacted_path": redacted_paths.get(source_path, ""),
                "secret_like_count": secret_count,
                "pattern_counts": item.get("pattern_counts", {}),
                "severity": severity_for_count(secret_count),
                "destructive_action_performed": False,
                "required_manual_actions": [
                    "rotate every credential class reported for this source before reuse or publication",
                    "compare source with redacted copy if historical content must be preserved",
                    "replace published/shared artifact with the redacted copy only after manual review",
                    "delete or encrypt the original artifact after backups and token rotation are confirmed",
                ],
            }
        )

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "destructive_action_performed": False,
        "action_count": len(actions),
        "actions": actions,
    }


def write_plan(plan: dict[str, Any]) -> None:
    atomic_write_json(PLAN_PATH, plan)


def main() -> int:
    inventory_path = INVENTORY_REPORT
    manifest_path = MANIFEST_PATH
    inventory = load_json(inventory_path)
    manifest = load_json(manifest_path)
    plan = build_plan(inventory, manifest)
    write_plan(plan)
    print(f"secret_remediation_plan: actions={plan['action_count']}")
    print(f"secret_remediation_plan: report={PLAN_PATH.relative_to(ROOT)}")
    if "--fail-on-actions" in sys.argv[1:] and plan["action_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
