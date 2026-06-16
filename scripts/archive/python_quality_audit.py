from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import PYTHON_QUALITY_REPORT, ROOT
from security_report_utils import atomic_write_json


EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "venv",
    "data",
    "sessions",
    "security_reports",
}
LARGE_FILE_LINES = 1000
CRITICAL_FILE_LINES = 5000
LONG_FUNCTION_LINES = 120
CRITICAL_FUNCTION_LINES = 500
HIGH_BRANCH_COUNT = 80
TOP_LEVEL_EXEC_LIMIT = 20
MAX_REPORTED_ITEMS = 25
BRANCH_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.BoolOp,
    ast.IfExp,
    ast.ExceptHandler,
    ast.Match,
)
PASSIVE_TOP_LEVEL = (
    ast.Import,
    ast.ImportFrom,
    ast.Assign,
    ast.AnnAssign,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
)


def should_scan_python(path: Path) -> bool:
    return path.suffix == ".py" and not any(part in EXCLUDED_PARTS for part in path.parts)


def node_line_count(node: ast.AST) -> int:
    start = getattr(node, "lineno", 0) or 0
    end = getattr(node, "end_lineno", start) or start
    return max(1, end - start + 1)


def branch_count(node: ast.AST) -> int:
    return sum(1 for child in ast.walk(node) if isinstance(child, BRANCH_NODES))


def function_items(tree: ast.AST, relative: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        lines = node_line_count(node)
        branches = branch_count(node)
        if lines < LONG_FUNCTION_LINES and branches < HIGH_BRANCH_COUNT:
            continue

        items.append(
            {
                "path": relative,
                "name": node.name,
                "line": int(getattr(node, "lineno", 0) or 0),
                "line_count": lines,
                "branch_count": branches,
                "critical": lines >= CRITICAL_FUNCTION_LINES,
            }
        )
    items.sort(key=lambda item: (-int(item["line_count"]), str(item["path"]), int(item["line"])))
    return items


def is_passive_expr(node: ast.Expr) -> bool:
    return isinstance(node.value, ast.Constant)


def top_level_exec_count(tree: ast.Module) -> int:
    count = 0
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
            ):
                continue
        if isinstance(node, ast.Expr) and is_passive_expr(node):
            continue
        if not isinstance(node, PASSIVE_TOP_LEVEL):
            count += 1
    return count


def inspect_file(path: Path, root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    relative = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="ignore")
    line_count = len(text.splitlines())
    tree = ast.parse(text, filename=relative)
    functions = function_items(tree, relative)
    top_level_exec = top_level_exec_count(tree)
    critical = line_count >= CRITICAL_FILE_LINES or any(item["critical"] for item in functions)
    item = {
        "path": relative,
        "line_count": line_count,
        "function_count": sum(1 for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))),
        "class_count": sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef)),
        "top_level_exec_count": top_level_exec,
        "large_file": line_count >= LARGE_FILE_LINES,
        "critical": critical,
    }
    return item, functions


def build_python_quality_report(root: Path = ROOT) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    flagged_functions: list[dict[str, Any]] = []

    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if not should_scan_python(relative):
            continue

        item, functions = inspect_file(path, root)
        files.append(item)
        flagged_functions.extend(functions)

    files.sort(key=lambda item: (-int(item["line_count"]), str(item["path"])))
    flagged_functions.sort(key=lambda item: (-int(item["line_count"]), str(item["path"]), int(item["line"])))

    large_files = [item for item in files if item["large_file"]]
    critical_files = [item for item in files if item["critical"]]
    top_level_heavy = [item for item in files if int(item["top_level_exec_count"]) > TOP_LEVEL_EXEC_LIMIT]
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "checked_count": len(files),
        "total_line_count": sum(int(item["line_count"]) for item in files),
        "large_file_count": len(large_files),
        "critical_file_count": len(critical_files),
        "flagged_function_count": len(flagged_functions),
        "critical_function_count": sum(1 for item in flagged_functions if item["critical"]),
        "top_level_heavy_file_count": len(top_level_heavy),
        "largest_files": files[:MAX_REPORTED_ITEMS],
        "flagged_functions": flagged_functions[:MAX_REPORTED_ITEMS],
        "top_level_heavy_files": top_level_heavy[:MAX_REPORTED_ITEMS],
    }


def write_report(report: dict[str, Any]) -> None:
    atomic_write_json(PYTHON_QUALITY_REPORT, report)


def main() -> int:
    args = set(sys.argv[1:])
    report = build_python_quality_report(ROOT)
    write_report(report)
    print(
        "python_quality_audit: "
        f"checked={report['checked_count']} "
        f"large_files={report['large_file_count']} "
        f"critical_files={report['critical_file_count']} "
        f"flagged_functions={report['flagged_function_count']}"
    )
    print(f"python_quality_audit: report={PYTHON_QUALITY_REPORT.relative_to(ROOT)}")
    if "--fail-on-critical" in args and (report["critical_file_count"] or report["critical_function_count"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
