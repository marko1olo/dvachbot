from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import ASYNC_BLOCKING_REPORT, ROOT
from security_report_utils import atomic_write_json


EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "venv",
    "data",
    "sessions",
    "security_reports",
}
MAX_REPORTED_FINDINGS = 100
HIGH_RISK_CALLS = {
    "time.sleep",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
    "sqlite3.connect",
}
MEDIUM_RISK_CALLS = {
    "open",
    "json.load",
    "json.dump",
    "Image.open",
}
MEDIUM_RISK_SUFFIXES = (
    ".read_text",
    ".write_text",
    ".read_bytes",
    ".write_bytes",
)
HIGH_RISK_PREFIXES = (
    "requests.",
    "urllib.request.",
)


def should_scan_python(path: Path) -> bool:
    return path.suffix == ".py" and not any(part in EXCLUDED_PARTS for part in path.parts)


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def classify_call(name: str) -> tuple[str, str] | None:
    if name in HIGH_RISK_CALLS or any(name.startswith(prefix) for prefix in HIGH_RISK_PREFIXES):
        return "high", "blocking-call-in-async"
    if name in MEDIUM_RISK_CALLS or any(name.endswith(suffix) for suffix in MEDIUM_RISK_SUFFIXES):
        return "medium", "sync-io-or-cpu-call-in-async"
    return None


class AsyncBlockingVisitor(ast.NodeVisitor):
    def __init__(self, relative: str):
        self.relative = relative
        self.async_stack: list[str] = []
        self.findings: list[dict[str, Any]] = []

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.async_stack.append(node.name)
        self.generic_visit(node)
        self.async_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self.async_stack:
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self.async_stack:
            name = call_name(node.func)
            classified = classify_call(name)
            if classified:
                severity, issue = classified
                self.findings.append(
                    {
                        "path": self.relative,
                        "function": self.async_stack[-1],
                        "line": int(getattr(node, "lineno", 0) or 0),
                        "call": name,
                        "severity": severity,
                        "issue": issue,
                    }
                )
        self.generic_visit(node)


def inspect_file(path: Path, root: Path) -> list[dict[str, Any]]:
    relative = path.relative_to(root).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=relative)
    visitor = AsyncBlockingVisitor(relative)
    visitor.visit(tree)
    return visitor.findings


def build_async_blocking_report(root: Path = ROOT) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    checked_count = 0

    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if not should_scan_python(relative):
            continue
        checked_count += 1
        findings.extend(inspect_file(path, root))

    findings.sort(key=lambda item: (str(item["severity"]), str(item["path"]), int(item["line"])))
    high_count = sum(1 for item in findings if item["severity"] == "high")
    medium_count = sum(1 for item in findings if item["severity"] == "medium")
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "checked_count": checked_count,
        "finding_count": len(findings),
        "high_count": high_count,
        "medium_count": medium_count,
        "findings": findings[:MAX_REPORTED_FINDINGS],
    }


def write_report(report: dict[str, Any]) -> None:
    atomic_write_json(ASYNC_BLOCKING_REPORT, report)


def main() -> int:
    args = set(sys.argv[1:])
    report = build_async_blocking_report(ROOT)
    write_report(report)
    print(
        "async_blocking_audit: "
        f"checked={report['checked_count']} "
        f"findings={report['finding_count']} "
        f"high={report['high_count']} "
        f"medium={report['medium_count']}"
    )
    print(f"async_blocking_audit: report={ASYNC_BLOCKING_REPORT.relative_to(ROOT)}")
    if "--fail-on-high" in args and report["high_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
