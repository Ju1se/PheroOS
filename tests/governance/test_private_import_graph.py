from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "pheroos/governance"


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _governance_import_graph() -> dict[str, set[str]]:
    paths = sorted(PACKAGE_ROOT.rglob("*.py"))
    modules = {_module_name(path): path for path in paths}
    graph = {module: set() for module in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module)
        for candidate in imported:
            owner = next(
                (
                    known
                    for known in sorted(modules, key=len, reverse=True)
                    if candidate == known or candidate.startswith(known + ".")
                ),
                None,
            )
            if owner is not None and owner != module:
                graph[module].add(owner)
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


def test_governance_private_import_graph_has_no_cycles() -> None:
    cycles = [
        component
        for component in _strongly_connected_components(
            _governance_import_graph()
        )
        if len(component) > 1
    ]

    assert cycles == []


def test_private_modules_never_import_the_aggregate_facade() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "pheroos.governance":
                offenders.append(path.relative_to(ROOT).as_posix())
            elif isinstance(node, ast.Import) and any(
                alias.name == "pheroos.governance" for alias in node.names
            ):
                offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []


def test_private_engines_have_no_module_global_lock_or_install_registry() -> None:
    offenders: list[str] = []
    allowed = {
        "pheroos/governance/__init__.py",
        "pheroos/governance/_legacy/authority_registry.py",
    }
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                if value.func.id in {"Lock", "RLock"}:
                    offenders.append(f"{relative}:global-{value.func.id}")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                node.name.startswith("install_") or node.name.startswith("register_")
            ):
                # A private static registry is acceptable only when it declares
                # ABI data at import time. Runtime installer functions turn
                # dependency direction into hidden mutable global state.
                if "/_" in relative:
                    offenders.append(f"{relative}:{node.name}")

    assert offenders == []
