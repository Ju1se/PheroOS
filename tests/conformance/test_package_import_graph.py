from __future__ import annotations

import ast
from pathlib import Path

from pheroos.conformance._manifest_check_registry import (
    REGISTERED_MANIFEST_CHECK_NAMES,
    project_active_manifest_checks,
)
from pheroos.conformance.runner import MANIFEST_CHECKS


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "pheroos"


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _absolute_import_base(module: str, path: Path, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    parts = package.split(".")
    keep = len(parts) - (node.level - 1)
    if keep < 0:
        return ""
    suffix = [node.module] if node.module else []
    return ".".join([*parts[:keep], *suffix])


def _package_import_graph() -> dict[str, set[str]]:
    paths = sorted(PACKAGE_ROOT.rglob("*.py"))
    modules = {_module_name(path): path for path in paths}
    known = sorted(modules, key=len, reverse=True)
    graph = {module: set() for module in modules}

    def owner(candidate: str) -> str | None:
        return next(
            (
                module
                for module in known
                if candidate == module or candidate.startswith(module + ".")
            ),
            None,
        )

    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        candidates: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                candidates.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = _absolute_import_base(module, path, node)
                if not base:
                    continue
                candidates.append(base)
                candidates.extend(
                    f"{base}.{alias.name}" for alias in node.names if alias.name != "*"
                )
        for candidate in candidates:
            dependency = owner(candidate)
            if dependency is not None and dependency != module:
                graph[module].add(dependency)
    return graph


def _strongly_connected_components(
    graph: dict[str, set[str]],
) -> list[tuple[str, ...]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for adjacent in sorted(graph[node]):
            if adjacent not in indices:
                visit(adjacent)
                lowlinks[node] = min(lowlinks[node], lowlinks[adjacent])
            elif adjacent in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[adjacent])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(tuple(sorted(component)))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return components


def test_complete_pheroos_import_graph_has_no_strongly_connected_components() -> None:
    graph = _package_import_graph()
    cycles = [
        component
        for component in _strongly_connected_components(graph)
        if len(component) > 1
    ]

    assert cycles == []
    assert (
        "pheroos.conformance.runner"
        not in graph["pheroos.conformance._commit_tck.reference_adapter"]
    )
    assert (
        "pheroos.conformance.checks.commit_metrics_contract"
        in graph["pheroos.conformance.runner"]
    )


def test_leaf_manifest_check_projection_matches_runner_without_import_back_edge() -> (
    None
):
    assert tuple(MANIFEST_CHECKS) == REGISTERED_MANIFEST_CHECK_NAMES
    projection = project_active_manifest_checks(
        ("manifest_schema", *REGISTERED_MANIFEST_CHECK_NAMES, "unknown_check")
    )

    assert projection.registered == (
        "manifest_schema",
        *REGISTERED_MANIFEST_CHECK_NAMES,
    )
    assert projection.missing == ("unknown_check",)
    assert projection.skipped_or_na == ()

    path = ROOT / "pheroos/conformance/_manifest_check_registry.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(
        name.startswith(
            (
                "pheroos.conformance.runner",
                "pheroos.conformance.checks",
                "pheroos.conformance.commit_tck",
                "pheroos.conformance._commit_tck",
            )
        )
        for name in imported
    )
