from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import ENV_CONTRACT_REPORT, ROOT
from security_report_utils import atomic_write_json


EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "venv",
    "data",
    "sessions",
    "security_reports",
}
ENV_HELPER_NAMES = {
    "get_token",
    "get_admins",
}


def should_scan_python(path: Path) -> bool:
    return path.suffix == ".py" and not any(part in EXCLUDED_PARTS for part in path.parts)


def parse_env_example(path: Path) -> set[str]:
    if not path.exists():
        return set()

    keys: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _ = line.split("=", 1)
        if key.strip():
            keys.add(key.strip())
    return keys


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def collect_env_usages(path: Path, root: Path) -> tuple[dict[str, list[str]], list[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return {}, [f"{path.relative_to(root).as_posix()}:syntax_error"]

    usages: dict[str, list[str]] = {}
    dynamic_references: list[str] = []
    relative = path.relative_to(root).as_posix()

    for node in ast.walk(tree):
        key: str | None = None
        line = getattr(node, "lineno", 0)

        if isinstance(node, ast.Call):
            name = call_name(node.func)
            if name == "os.getenv" and node.args:
                key = literal_string(node.args[0])
                if key is None:
                    dynamic_references.append(f"{relative}:{line}:os.getenv")
            elif name == "os.environ.get" and node.args:
                key = literal_string(node.args[0])
                if key is None:
                    dynamic_references.append(f"{relative}:{line}:os.environ.get")
            elif name in ENV_HELPER_NAMES and node.args:
                key = literal_string(node.args[0])
                if key is None:
                    dynamic_references.append(f"{relative}:{line}:{name}")

        elif isinstance(node, ast.Subscript):
            name = call_name(node.value)
            if name == "os.environ":
                key = literal_string(node.slice)
                if key is None:
                    dynamic_references.append(f"{relative}:{line}:os.environ[]")

        if key:
            usages.setdefault(key, []).append(f"{relative}:{line}")

    return usages, dynamic_references


def build_env_contract(root: Path = ROOT) -> dict[str, Any]:
    documented = parse_env_example(root / ".env.example")
    usages: dict[str, list[str]] = {}
    dynamic_references: list[str] = []

    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if not should_scan_python(relative):
            continue

        file_usages, file_dynamic = collect_env_usages(path, root)
        for key, locations in file_usages.items():
            usages.setdefault(key, []).extend(locations)
        dynamic_references.extend(file_dynamic)

    used_keys = set(usages)
    missing = sorted(used_keys - documented)
    unused_documented = sorted(documented - used_keys)

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "documented_count": len(documented),
        "used_count": len(used_keys),
        "missing_count": len(missing),
        "unused_documented_count": len(unused_documented),
        "dynamic_reference_count": len(dynamic_references),
        "missing_keys": missing,
        "unused_documented_keys": unused_documented,
        "dynamic_references": dynamic_references,
        "usages": {key: sorted(locations) for key, locations in sorted(usages.items())},
    }


def write_report(report: dict[str, Any]) -> None:
    atomic_write_json(ENV_CONTRACT_REPORT, report)


def main() -> int:
    args = set(sys.argv[1:])
    report = build_env_contract(ROOT)
    write_report(report)
    print(
        "env_contract_audit: "
        f"used={report['used_count']} "
        f"documented={report['documented_count']} "
        f"missing={report['missing_count']} "
        f"dynamic={report['dynamic_reference_count']}"
    )
    print(f"env_contract_audit: report={ENV_CONTRACT_REPORT.relative_to(ROOT)}")
    if "--fail-on-missing" in args and report["missing_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
