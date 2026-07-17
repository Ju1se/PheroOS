from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path

from pheroos.conformance.report import CheckResult


FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "anthropic",
    "app",
    "capabilities",
    "celery",
    "django",
    "fastapi",
    "flask",
    "httpx",
    "kafka",
    "langgraph",
    "litellm",
    "openai",
    "psycopg",
    "pymongo",
    "redis",
    "requests",
    "runtime",
    "sqlalchemy",
    "sqlite3",
    "starlette",
    "tools",
    "uvicorn",
}
ROOT_FOUNDATION_MODULES = {"_digest", "_immutable", "_scope", "_version"}
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
    package_root = root / "pheroos"
    if not package_root.is_dir():
        return CheckResult("package_import_boundary", False, "missing:pheroos")
    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    record_if_forbidden(root, path, alias.name, offenders)
            elif isinstance(node, ast.ImportFrom):
                for module in resolved_import_from_modules(root, path, node):
                    record_if_forbidden(root, path, module, offenders)
    return CheckResult("package_import_boundary", not offenders, "; ".join(sorted(set(offenders))))


def resolved_import_from_modules(root: Path, path: Path, node: ast.ImportFrom) -> tuple[str, ...]:
    if node.level == 0:
        if node.module == "pheroos":
            return tuple(f"pheroos.{alias.name}" for alias in node.names)
        return (node.module or "",)
    package = package_for_path(root, path)
    if not package:
        return (node.module or "",)
    relative_name = "." * node.level + (node.module or "")
    try:
        resolved = resolve_name(relative_name, package)
    except (ImportError, ValueError):
        return (node.module or "",)
    # ``from .. import governance`` names the imported package only through
    # the alias.  Include it so relative cross-package imports cannot evade the
    # same allowlist applied to absolute imports.
    if node.module is None:
        return tuple(f"{resolved}.{alias.name}" for alias in node.names)
    return (resolved,)


def package_for_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = relative.parts
    if not parts or parts[0] != "pheroos":
        return ""
    if parts[-1] == "__init__":
        parts = parts[:-1]
    else:
        parts = parts[:-1]
    return ".".join(parts)


def record_if_forbidden(root: Path, path: Path, module: str, offenders: list[str]) -> None:
    if module.split(".", 1)[0] in FORBIDDEN_IMPORT_ROOTS:
        offenders.append(f"{path.relative_to(root).as_posix()}:{module}")
        return
    if not module.startswith("pheroos."):
        return
    source_package = source_package_for(root, path)
    imported_package = module.split(".", 2)[1]
    if imported_package in ROOT_FOUNDATION_MODULES:
        return
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
