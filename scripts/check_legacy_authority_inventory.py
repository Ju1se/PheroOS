#!/usr/bin/env python3
"""Generate or verify the shrink-only legacy authority inventory.

The inventory is a migration gate, not an authority mechanism.  It recursively
observes process-local compatibility surfaces under ``pheroos/governance`` and
refuses additions relative to the checked artifact.  Removing an observed
surface is intentional progress and must be recorded with ``--write``.
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable, Mapping
import json
import os
from pathlib import Path
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_ROOT = ROOT / "pheroos" / "governance"
INVENTORY_PATH = ROOT / "docs" / "process" / "legacy-authority-inventory-v1.json"
INVENTORY_VERSION = "pheroos-legacy-authority-inventory-v1"
REGISTRY_MODULE = "pheroos.governance._legacy.authority_registry"

# These reviewed tokens protect local, non-portable handle construction.  They
# are not durable authority: every usable v2 handle is issued from exact Store
# observations and its parent/dependency/grant/lifecycle preconditions are
# rechecked by the atomic consumer.  The Decision and Distributed source
# tokens bind prepared input bundles; the neutral finality token binds an owner
# projection plus the owner CAS precondition.  None survives serialization or
# makes portable bytes authoritative.
# A new bare object token is deliberately treated as a sentinel candidate
# until this reviewed classification is extended.
STORE_REHYDRATABLE_OPAQUE_TOKENS = frozenset(
    {
        (
            "pheroos/governance/_authority_session_v2/contracts.py",
            "_CAPABILITY_TOKEN",
        ),
        (
            "pheroos/governance/_authority_session_v2/contracts.py",
            "_SESSION_TOKEN",
        ),
        (
            "pheroos/governance/_commit_decision_v2/source_proof.py",
            "_SOURCE_TOKEN_V2",
        ),
        (
            "pheroos/governance/_commit_finality_v2.py",
            "_FINALITY_INPUT_TOKEN_V2",
        ),
        (
            "pheroos/governance/_distributed_v2/source.py",
            "_SOURCE_TOKEN_V2",
        ),
    }
)

INVENTORY_KEYS = (
    "registry_importers",
    "legacy_namespaces",
    "cursor_types",
    "sentinel_only_issuance_candidates",
    "store_rehydratable_opaque_tokens",
)

POLICY = {
    "direction": "shrink-only",
    "governance_root": "pheroos/governance",
    "registry_module": REGISTRY_MODULE,
    "registry_rule": (
        "direct, re-exported, relative, and literal dynamic imports are importers"
    ),
    "sentinel_candidate_rule": (
        "every module-scope *_ISSUANCE binding and every other bare object() "
        "assignment except the reviewed store-rehydratable opaque tokens"
    ),
    "v2_opaque_token_rule": (
        "local handle identity is not portable authority; StateStore inclusion, "
        "currentness, scope, and grant bounds must be reverified before reissuance"
    ),
}


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def _source_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError as error:
        raise ValueError(
            f"governance source is outside repository root: {path}"
        ) from error


def _is_bare_object_call(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "object"
        and not node.args
        and not node.keywords
    )


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    targets: Iterable[ast.expr]
    if isinstance(node, ast.Assign):
        targets = node.targets
    else:
        targets = (node.target,)
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
    return tuple(names)


def _assignment_value(node: ast.Assign | ast.AnnAssign) -> ast.AST | None:
    return node.value


def _module_scope_assignments(tree: ast.Module) -> Iterable[ast.Assign | ast.AnnAssign]:
    for statement in tree.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            yield statement


def _list_length(value: object) -> int:
    assert isinstance(value, list)
    return len(value)


def _imports_legacy_registry(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.name == REGISTRY_MODULE
                or alias.name == "pheroos.governance._legacy"
                for alias in node.names
            ):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            aliases = {alias.name for alias in node.names}
            if module == REGISTRY_MODULE or module.endswith(
                "_legacy.authority_registry"
            ):
                return True
            if (
                module == "pheroos.governance._legacy" or module.endswith("_legacy")
            ) and aliases & {"LEGACY_AUTHORITY_REGISTRY", "LegacyAuthorityRegistry"}:
                return True
        elif isinstance(node, ast.Call) and node.args:
            first = node.args[0]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value in {REGISTRY_MODULE, "pheroos.governance._legacy"}
            ):
                function = node.func
                if (
                    isinstance(function, ast.Name)
                    and function.id in {"__import__", "import_module"}
                ) or (
                    isinstance(function, ast.Attribute)
                    and function.attr == "import_module"
                ):
                    return True
    return False


def _parse_sources(governance_root: Path) -> Iterable[tuple[Path, ast.Module]]:
    for path in sorted(governance_root.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as error:
            raise ValueError(
                f"cannot parse governance source {path}: {error}"
            ) from error
        yield path, tree


def _cursor_entries(tree: ast.Module, source_path: str) -> set[tuple[str, str]]:
    return {
        (source_path, node.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name.endswith("Cursor")
    }


def _namespace_entries(
    tree: ast.Module,
    source_path: str,
) -> set[tuple[str, str, str]]:
    entries: set[tuple[str, str, str]] = set()
    declared_nodes: set[int] = set()
    for assignment in _module_scope_assignments(tree):
        value = _assignment_value(assignment)
        if (
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and value.value.startswith("legacy.")
            and value.value != "legacy."
        ):
            declared_nodes.add(id(value))
            for name in _assigned_names(assignment):
                entries.add((source_path, name, value.value))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("legacy.")
            and node.value != "legacy."
            and id(node) not in declared_nodes
        ):
            entries.add((source_path, "<literal>", node.value))
    return entries


def _sentinel_entries(
    tree: ast.Module,
    source_path: str,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    candidates: set[tuple[str, str]] = set()
    opaque_tokens: set[tuple[str, str]] = set()
    for assignment in _module_scope_assignments(tree):
        value = _assignment_value(assignment)
        for name in _assigned_names(assignment):
            key = (source_path, name)
            if _is_bare_object_call(value):
                if key in STORE_REHYDRATABLE_OPAQUE_TOKENS:
                    opaque_tokens.add(key)
                else:
                    candidates.add(key)
            elif name.endswith("_ISSUANCE"):
                candidates.add(key)
    return candidates, opaque_tokens


def build_inventory(governance_root: Path = GOVERNANCE_ROOT) -> dict[str, Any]:
    """Return the deterministic recursive inventory for ``governance_root``."""

    if not governance_root.is_dir():
        raise ValueError(f"governance root is not a directory: {governance_root}")

    importers: set[str] = set()
    namespaces: set[tuple[str, str, str]] = set()
    cursors: set[tuple[str, str]] = set()
    sentinel_candidates: set[tuple[str, str]] = set()
    opaque_tokens: set[tuple[str, str]] = set()

    for path, tree in _parse_sources(governance_root):
        source_path = _source_path(path)
        if _imports_legacy_registry(tree):
            importers.add(source_path)
        cursors.update(_cursor_entries(tree, source_path))
        namespaces.update(_namespace_entries(tree, source_path))
        source_candidates, source_tokens = _sentinel_entries(tree, source_path)
        sentinel_candidates.update(source_candidates)
        opaque_tokens.update(source_tokens)

    inventory: dict[str, object] = {
        "registry_importers": sorted(importers),
        "legacy_namespaces": [
            {"namespace": namespace, "path": path, "symbol": symbol}
            for path, symbol, namespace in sorted(namespaces)
        ],
        "cursor_types": [
            {"path": path, "type": type_name} for path, type_name in sorted(cursors)
        ],
        "sentinel_only_issuance_candidates": [
            {"path": path, "symbol": symbol}
            for path, symbol in sorted(sentinel_candidates)
        ],
        "store_rehydratable_opaque_tokens": [
            {"path": path, "symbol": symbol} for path, symbol in sorted(opaque_tokens)
        ],
    }
    for category in INVENTORY_KEYS[1:]:
        entries = inventory[category]
        assert isinstance(entries, list)
        entries.sort(key=lambda entry: json.dumps(entry, sort_keys=True))
    return {
        "counts": {key: _list_length(inventory[key]) for key in INVENTORY_KEYS},
        "inventory": inventory,
        "policy": dict(POLICY),
        "version": INVENTORY_VERSION,
    }


def render_inventory(inventory: Mapping[str, object]) -> bytes:
    """Render a canonical checked artifact."""

    return (
        json.dumps(
            inventory,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def load_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    try:
        loaded = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load legacy authority inventory: {error}") from error
    if not isinstance(loaded, dict):
        raise ValueError("legacy authority inventory must be a JSON object")
    failures = inventory_shape_failures(loaded)
    if failures:
        raise ValueError("invalid legacy authority inventory: " + "; ".join(failures))
    return loaded


def _sorted_unique(values: object) -> bool:
    return (
        isinstance(values, list)
        and values
        == sorted(
            values,
            key=lambda value: json.dumps(value, sort_keys=True),
        )
        and len(values) == len({json.dumps(value, sort_keys=True) for value in values})
    )


def _entry_shape_failures(
    values: object,
    *,
    keys: set[str],
    label: str,
) -> list[str]:
    if not _sorted_unique(values):
        return [f"{label} must be a sorted unique array"]
    assert isinstance(values, list)
    failures: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict) or set(value) != keys:
            failures.append(f"{label}[{index}] has invalid keys")
            continue
        if not all(isinstance(item, str) and item for item in value.values()):
            failures.append(f"{label}[{index}] values must be non-empty strings")
    return failures


def _header_shape_failures(value: Mapping[str, object]) -> list[str]:
    failures: list[str] = []
    if set(value) != {"counts", "inventory", "policy", "version"}:
        return ["top-level keys differ from the v1 inventory schema"]
    if value.get("version") != INVENTORY_VERSION:
        failures.append(f"version must be {INVENTORY_VERSION!r}")
    if value.get("policy") != POLICY:
        failures.append("policy differs from the shrink-only v1 policy")
    inventory = value.get("inventory")
    counts = value.get("counts")
    if not isinstance(inventory, dict) or set(inventory) != set(INVENTORY_KEYS):
        failures.append("inventory categories differ from the v1 schema")
        return failures
    if not isinstance(counts, dict) or set(counts) != set(INVENTORY_KEYS):
        failures.append("inventory counts differ from the v1 schema")
    return failures


def _inventory_content_shape_failures(
    inventory: Mapping[str, object],
) -> list[str]:
    failures: list[str] = []
    importers = inventory["registry_importers"]
    if (
        not _sorted_unique(importers)
        or not isinstance(importers, list)
        or not all(isinstance(item, str) and item for item in importers)
    ):
        failures.append("registry_importers must be a sorted unique string array")
    failures.extend(
        _entry_shape_failures(
            inventory["legacy_namespaces"],
            keys={"namespace", "path", "symbol"},
            label="legacy_namespaces",
        )
    )
    failures.extend(
        _entry_shape_failures(
            inventory["cursor_types"],
            keys={"path", "type"},
            label="cursor_types",
        )
    )
    for category in (
        "sentinel_only_issuance_candidates",
        "store_rehydratable_opaque_tokens",
    ):
        failures.extend(
            _entry_shape_failures(
                inventory[category],
                keys={"path", "symbol"},
                label=category,
            )
        )
    return failures


def _count_shape_failures(
    counts: Mapping[str, object],
    inventory: Mapping[str, object],
) -> list[str]:
    failures: list[str] = []
    for key in INVENTORY_KEYS:
        observed_count = counts.get(key)
        if type(observed_count) is not int or observed_count < 0:
            failures.append(f"count {key} must be a non-negative exact integer")
        elif observed_count != _list_length(inventory[key]):
            failures.append(f"count {key} does not match its inventory array")
    return failures


def inventory_shape_failures(value: Mapping[str, object]) -> list[str]:
    """Validate the closed v1 artifact shape and embedded counts."""

    failures = _header_shape_failures(value)
    if failures:
        return failures
    inventory = value["inventory"]
    counts = value["counts"]
    assert isinstance(inventory, Mapping)
    assert isinstance(counts, Mapping)
    failures.extend(_inventory_content_shape_failures(inventory))
    failures.extend(_count_shape_failures(counts, inventory))
    return failures


def _entry_set(value: Mapping[str, object], category: str) -> set[str]:
    inventory = value["inventory"]
    assert isinstance(inventory, Mapping)
    entries = inventory[category]
    assert isinstance(entries, list)
    return {json.dumps(entry, sort_keys=True) for entry in entries}


def inventory_failures(
    checked: Mapping[str, object],
    observed: Mapping[str, object],
) -> list[str]:
    """Return drift or expansion failures against the checked artifact."""

    failures = inventory_shape_failures(checked)
    failures.extend(
        f"observed inventory is invalid: {failure}"
        for failure in inventory_shape_failures(observed)
    )
    if failures:
        return failures
    for category in INVENTORY_KEYS:
        expected = _entry_set(checked, category)
        current = _entry_set(observed, category)
        additions = current - expected
        removals = expected - current
        if additions:
            failures.append(
                f"legacy authority expansion in {category}: {sorted(additions)}"
            )
        if removals:
            failures.append(
                f"legacy authority inventory can tighten in {category}; run --write"
            )
    return failures


def write_inventory(
    path: Path,
    *,
    observed: Mapping[str, object],
) -> None:
    """Atomically write only an initial inventory or a strict subset."""

    observed_failures = inventory_shape_failures(observed)
    if observed_failures:
        raise ValueError(
            "cannot write invalid inventory: " + "; ".join(observed_failures)
        )
    if path.is_file():
        checked = load_inventory(path)
        expansions: list[str] = []
        for category in INVENTORY_KEYS:
            additions = _entry_set(observed, category) - _entry_set(checked, category)
            if category == "store_rehydratable_opaque_tokens":
                reviewed = {
                    json.dumps(
                        {"path": path, "symbol": symbol},
                        sort_keys=True,
                    )
                    for path, symbol in STORE_REHYDRATABLE_OPAQUE_TOKENS
                }
                additions -= reviewed
            if additions:
                expansions.append(f"{category}: {sorted(additions)}")
        if expansions:
            raise ValueError(
                "legacy authority inventory write would expand: "
                + "; ".join(expansions)
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_inventory(observed)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(rendered)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _count_summary(value: Mapping[str, object]) -> str:
    counts = value["counts"]
    assert isinstance(counts, Mapping)
    return ", ".join(f"{key}={counts[key]}" for key in INVENTORY_KEYS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true")
    action.add_argument("--write", action="store_true")
    parser.add_argument("--path", type=Path, default=INVENTORY_PATH)
    args = parser.parse_args(argv)

    try:
        observed = build_inventory()
        if args.write:
            write_inventory(args.path, observed=observed)
            print(f"wrote legacy authority inventory: {_count_summary(observed)}")
            return 0
        checked = load_inventory(args.path)
        failures = inventory_failures(checked, observed)
        if args.path.read_bytes() != render_inventory(checked):
            failures.append("checked artifact is not canonical JSON")
    except ValueError as error:
        print(f"FAIL: {error}")
        return 1

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(f"legacy authority inventory satisfied: {_count_summary(observed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
