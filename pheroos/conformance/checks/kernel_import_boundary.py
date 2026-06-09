from __future__ import annotations

import ast
from pathlib import Path

from pheroos.conformance.report import CheckResult


FORBIDDEN_IMPORT_ROOTS = {"app", "runtime", "tools", "capabilities", "fastapi", "langgraph", "litellm"}


def check(root: Path) -> CheckResult:
    offenders: list[str] = []
    for path in (root / "pheroos").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    record_if_forbidden(root, path, module, offenders)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                record_if_forbidden(root, path, module, offenders)
    return CheckResult("kernel_import_boundary", not offenders, "; ".join(offenders))


def record_if_forbidden(root: Path, path: Path, module: str, offenders: list[str]) -> None:
    if module.split(".", 1)[0] in FORBIDDEN_IMPORT_ROOTS:
        offenders.append(f"{path.relative_to(root).as_posix()}:{module}")
