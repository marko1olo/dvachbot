from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.secret_redaction import redact_secrets
from security_paths import REDACTED_ARTIFACTS_DIR, REDACTION_MANIFEST, ROOT
from security_report_utils import atomic_write_json
from secret_artifact_inventory import build_inventory
from secret_artifact_inventory import DEFAULT_REPORT as INVENTORY_REPORT


OUTPUT_ROOT = REDACTED_ARTIFACTS_DIR
MANIFEST_PATH = REDACTION_MANIFEST


def safe_output_path(relative_path: Path, output_root: Path) -> Path:
    safe_parts = [part.replace(":", "_") for part in relative_path.parts]
    return output_root.joinpath(*safe_parts)


def redact_file(source: Path, target: Path) -> int:
    replacements = 0
    target.parent.mkdir(parents=True, exist_ok=True)

    with source.open("r", encoding="utf-8", errors="ignore") as reader:
        with target.open("w", encoding="utf-8", newline="") as writer:
            for line in reader:
                redacted = redact_secrets(line)
                if redacted != line:
                    replacements += 1
                writer.write(redacted)

    return replacements


def redact_inventory_items(
    root: Path,
    findings: list[dict[str, Any]],
    output_root: Path | None = None,
) -> dict[str, Any]:
    if output_root is None:
        output_root = root / "security_reports" / "redacted_artifacts"

    manifest_items: list[dict[str, Any]] = []
    expected_targets: set[Path] = set()
    for finding in findings:
        relative = Path(str(finding["path"]))
        source = root / relative
        target = safe_output_path(relative, output_root)
        expected_targets.add(target.resolve())
        changed_lines = redact_file(source, target)
        manifest_items.append(
            {
                "source_path": relative.as_posix(),
                "redacted_path": target.relative_to(root).as_posix(),
                "secret_like_count": finding["secret_like_count"],
                "pattern_counts": finding["pattern_counts"],
                "changed_lines": changed_lines,
                "contains_secret_values": False,
            }
        )

    if output_root.exists():
        for stale_path in output_root.rglob("*"):
            if stale_path.is_file() and stale_path.resolve() not in expected_targets:
                stale_path.unlink()

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "redacted_files": manifest_items,
    }


def redact_inventory(
    root: Path,
    include_env: bool = False,
    output_root: Path | None = None,
) -> dict[str, Any]:
    return redact_inventory_items(
        root,
        build_inventory(root, include_env=include_env),
        output_root=output_root,
    )


def load_inventory_report(report_path: Path) -> list[dict[str, Any]]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    return list(data.get("files", []))


def write_manifest(manifest: dict[str, Any]) -> None:
    atomic_write_json(MANIFEST_PATH, manifest)


def main() -> int:
    args = set(sys.argv[1:])
    include_env = "--include-env" in args
    if "--from-report" in args and INVENTORY_REPORT.exists():
        findings = load_inventory_report(INVENTORY_REPORT)
        manifest = redact_inventory_items(ROOT, findings)
    else:
        manifest = redact_inventory(ROOT, include_env=include_env)
    write_manifest(manifest)
    total_files = len(manifest["redacted_files"])
    total_matches = sum(int(item["secret_like_count"]) for item in manifest["redacted_files"])
    print(f"secret_artifact_redactor: files={total_files} secret_like_count={total_matches}")
    print(f"secret_artifact_redactor: manifest={MANIFEST_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
