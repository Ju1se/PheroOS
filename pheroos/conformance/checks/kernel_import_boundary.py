from __future__ import annotations

import ast
from pathlib import Path

from pheroos.conformance.report import CheckResult


FORBIDDEN_IMPORT_ROOTS = {"app", "runtime", "tools", "capabilities", "fastapi", "langgraph", "litellm"}
PACKAGE_IMPORT_ALLOWLIST = {
    "protocol": {"protocol"},
    "kernel": {"kernel", "protocol", "drivers"},
    "governance": {"governance", "protocol", "trace"},
    "drivers": {"drivers"},
    "trace": {"trace"},
    "conformance": {"conformance", "protocol", "kernel", "governance", "drivers", "trace"},
    "cli": {"cli", "protocol", "kernel", "governance", "drivers", "trace", "conformance"},
}


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
        return
    if not module.startswith("pheroos."):
        return
    source_package = source_package_for(root, path)
    imported_package = module.split(".", 2)[1]
    allowed = PACKAGE_IMPORT_ALLOWLIST.get(source_package)
    if allowed is not None and imported_package not in allowed:
        offenders.append(f"{path.relative_to(root).as_posix()}:{module}")


def source_package_for(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    parts = relative.parts
    if len(parts) < 2 or parts[0] != "pheroos":
        return ""
    if len(parts) == 2:
        return ""
    return parts[1]
