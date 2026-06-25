from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import ROOT, SECURITY_CHECK_SUMMARY
from security_report_utils import atomic_write_json


SUMMARY_PATH = SECURITY_CHECK_SUMMARY


def run_step(args: list[str], required: bool = True) -> dict[str, Any]:
    print(f"security_check: running {' '.join(args)}", flush=True)
    started = time.perf_counter()
    import os
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    if required and result.returncode != 0:
        print(f"security_check: required step failed: {' '.join(args)}", file=sys.stderr)
    return {
        "args": args,
        "required": required,
        "exit_code": result.returncode,
        "elapsed_ms": elapsed_ms,
    }


def run_inventory(strict_enabled: bool) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    steps.append(run_step(["verification_scripts/secret_artifact_inventory.py"]))
    if steps[-1]["exit_code"] != 0:
        return steps

    steps.append(run_step(["verification_scripts/secret_findings_baseline.py"]))
    if steps[-1]["exit_code"] != 0:
        return steps

    steps.append(run_step(["verification_scripts/secret_artifact_redactor.py", "--from-report"]))
    if steps[-1]["exit_code"] != 0:
        return steps

    plan_args = ["verification_scripts/secret_remediation_plan.py"]
    if strict_enabled:
        plan_args.append("--fail-on-actions")
    steps.append(run_step(plan_args))
    if steps[-1]["exit_code"] != 0:
        return steps

    steps.append(run_step(["verification_scripts/security_report_validator.py"]))
    if steps[-1]["exit_code"] != 0:
        return steps

    return steps


def write_summary(steps: list[dict[str, Any]], inventory_enabled: bool, strict_enabled: bool) -> None:
    failed = [step for step in steps if step["required"] and step["exit_code"] != 0]
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "inventory_enabled": inventory_enabled,
        "strict_enabled": strict_enabled,
        "ok": not failed,
        "steps": steps,
    }
    atomic_write_json(SUMMARY_PATH, payload)


def main() -> int:
    inventory_enabled = "--inventory" in sys.argv[1:]
    strict_enabled = "--strict" in sys.argv[1:]
    steps: list[dict[str, Any]] = []
    repository_args = ["verification_scripts/repository_health.py"]
    cookie_args = ["verification_scripts/cookie_artifact_audit.py", "--fail-on-parse-issues"]
    local_artifact_args = ["verification_scripts/local_artifact_audit.py"]
    python_quality_args = ["verification_scripts/python_quality_audit.py"]
    import_graph_args = ["verification_scripts/import_graph_audit.py"]
    async_blocking_args = ["verification_scripts/async_blocking_audit.py"]
    if strict_enabled:
        repository_args.append("--fail-on-issues")
        cookie_args.append("--fail-on-sensitive")
        local_artifact_args.append("--fail-on-artifacts")
        python_quality_args.append("--fail-on-critical")
        import_graph_args.append("--fail-on-cycles")
        async_blocking_args.append("--fail-on-high")

    checks = [
        ["verification_scripts/source_integrity_audit.py", "--fail-on-issues"],
        repository_args,
        ["verification_scripts/gitignore_policy_audit.py", "--fail-on-missing"],
        cookie_args,
        local_artifact_args,
        python_quality_args,
        import_graph_args,
        async_blocking_args,
        ["-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        ["verification_scripts/env_example_validator.py"],
        ["verification_scripts/env_contract_audit.py", "--fail-on-missing"],
        ["verification_scripts/secret_scan.py"],
    ]

    for args in checks:
        step = run_step(args)
        steps.append(step)
        if step["exit_code"] != 0:
            write_summary(steps, inventory_enabled, strict_enabled)
            return int(step["exit_code"])

    if inventory_enabled:
        inventory_steps = run_inventory(strict_enabled)
        steps.extend(inventory_steps)
        for step in inventory_steps:
            if step["exit_code"] != 0:
                write_summary(steps, inventory_enabled, strict_enabled)
                return int(step["exit_code"])

    write_summary(steps, inventory_enabled, strict_enabled)
    if inventory_enabled:
        status_step = run_step(["verification_scripts/security_status.py"])
        steps.append(status_step)
        if status_step["exit_code"] != 0:
            write_summary(steps, inventory_enabled, strict_enabled)
            return int(status_step["exit_code"])
        write_summary(steps, inventory_enabled, strict_enabled)

    print("security_check: ok", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
