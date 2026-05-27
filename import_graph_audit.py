from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_paths import IMPORT_GRAPH_REPORT, ROOT
from security_report_utils import atomic_write_json


EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "venv",
    "data",
    "sessions",
    "security_reports",
}
MAX_REPORTED_CYCLES = 25
MAX_REPORTED_MODULES = 25


def should_scan_python(path: Path) -> bool:
    return path.suffix == ".py" and not any(part in EXCLUDED_PARTS for part in path.parts)


def module_name(path: Path) -> str:
    if path.name == "__init__.py":
        return ".".join(path.parent.parts)
    return ".".join(path.with_suffix("").parts)


def collect_modules(root: Path) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if should_scan_python(relative):
            modules[module_name(relative)] = relative
    return modules


def resolve_project_module(name: str, known_modules: set[str]) -> str | None:
    parts = name.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in known_modules:
            return candidate
    return None


def imports_for_file(path: Path, root: Path, known_modules: set[str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = resolve_project_module(alias.name, known_modules)
                if resolved:
                    deps.add(resolved)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            base = node.module or ""
            for alias in node.names:
                candidates = [f"{base}.{alias.name}" if base else alias.name, base]
                for candidate in candidates:
                    resolved = resolve_project_module(candidate, known_modules)
                    if resolved:
                        deps.add(resolved)
                        break
    return deps


def build_graph(root: Path = ROOT) -> dict[str, set[str]]:
    modules = collect_modules(root)
    known = set(modules)
    graph: dict[str, set[str]] = {}
    for name, relative in modules.items():
        path = root / relative
        graph[name] = {dep for dep in imports_for_file(path, root, known) if dep != name}
    return graph


def canonical_cycle(cycle: list[str]) -> tuple[str, ...]:
    body = cycle[:-1] if cycle and cycle[0] == cycle[-1] else cycle
    if not body:
        return tuple(cycle)
    rotations = [tuple(body[i:] + body[:i]) for i in range(len(body))]
    best = min(rotations)
    return best + (best[0],)


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    cycles: set[tuple[str, ...]] = set()
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> None:
        if node in visiting:
            index = stack.index(node)
            cycles.add(canonical_cycle(stack[index:] + [node]))
            return
        if node in visited:
            return

        visiting.add(node)
        stack.append(node)
        for dep in sorted(graph.get(node, ())):
            visit(dep)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)

    return [list(cycle) for cycle in sorted(cycles)]


def fan_in_counts(graph: dict[str, set[str]]) -> dict[str, int]:
    counts = {module: 0 for module in graph}
    for deps in graph.values():
        for dep in deps:
            counts[dep] = counts.get(dep, 0) + 1
    return counts


def top_counts(counts: dict[str, int]) -> list[dict[str, Any]]:
    items = [{"module": module, "count": count} for module, count in counts.items() if count > 0]
    items.sort(key=lambda item: (-int(item["count"]), str(item["module"])))
    return items[:MAX_REPORTED_MODULES]


def build_import_graph_report(root: Path = ROOT) -> dict[str, Any]:
    graph = build_graph(root)
    cycles = find_cycles(graph)
    fan_in = fan_in_counts(graph)
    fan_out = {module: len(deps) for module, deps in graph.items()}
    edge_count = sum(len(deps) for deps in graph.values())
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contains_secret_values": False,
        "module_count": len(graph),
        "edge_count": edge_count,
        "cycle_count": len(cycles),
        "cycles": cycles[:MAX_REPORTED_CYCLES],
        "top_fan_in": top_counts(fan_in),
        "top_fan_out": top_counts(fan_out),
    }


def write_report(report: dict[str, Any]) -> None:
    atomic_write_json(IMPORT_GRAPH_REPORT, report)


def main() -> int:
    args = set(sys.argv[1:])
    report = build_import_graph_report(ROOT)
    write_report(report)
    print(
        "import_graph_audit: "
        f"modules={report['module_count']} "
        f"edges={report['edge_count']} "
        f"cycles={report['cycle_count']}"
    )
    print(f"import_graph_audit: report={IMPORT_GRAPH_REPORT.relative_to(ROOT)}")
    if "--fail-on-cycles" in args and report["cycle_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
