#!/usr/bin/env python3
"""Generate or verify the static Governance lazy-facade declarations."""

from __future__ import annotations

import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "pheroos/conformance/abi/public-python-api-v1.json"
FACADE = ROOT / "pheroos/governance/__init__.py"
TARGET = ROOT / "pheroos/governance/_public_api.py"
EXPECTED_EXPORT_ORDER_SHA256 = (
    "c1fe92393513b8b3e2aa956d3fcfae0ee49285a89e30bcda11fe8514603f054d"
)
COMPATIBILITY_MODULES = (
    "attention",
    "atomic_evaluation",
    "authority",
    "authority_domain",
    "candidate",
    "certificate",
    "challenge",
    "collective",
    "commit",
    "commit_numeric",
    "commit_state",
    "distributed_commit",
    "errors",
    "evidence",
    "evidence_binding",
    "hybrid_commit",
    "hybrid_commit_evaluation",
    "layer_coordination",
    "observation",
    "output",
    "permission",
    "pheromone",
    "pheromone_feedback",
    "policy_adjustment",
    "principal",
    "quorum",
    "recovery",
    "replay",
    "risk",
    "runtime_policy",
    "schema",
    "signal",
    "stop_signal",
    "support_lease",
    "target",
    "trace",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    order = _checked_export_order()
    bindings = _inventory_bindings()
    if set(order) != set(bindings):
        missing = sorted(set(bindings) - set(order))
        extra = sorted(set(order) - set(bindings))
        print(f"public export mismatch; missing={missing}, extra={extra}")
        return 1

    mapping_rendered = _render_mapping(order, bindings)
    facade_rendered = _render_facade(order, bindings)
    if args.write:
        TARGET.write_bytes(mapping_rendered.encode("utf-8"))
        FACADE.write_bytes(facade_rendered.encode("utf-8"))
        print(f"wrote {TARGET.relative_to(ROOT)}")
        print(f"wrote {FACADE.relative_to(ROOT)}")
        return 0

    stale = []
    for path, rendered in ((TARGET, mapping_rendered), (FACADE, facade_rendered)):
        try:
            checked = path.read_bytes().decode("utf-8")
        except FileNotFoundError:
            stale.append(f"missing:{path.relative_to(ROOT)}")
        else:
            if checked != rendered:
                stale.append(f"stale:{path.relative_to(ROOT)}")
    if stale:
        print(", ".join(stale))
        print("run scripts/generate_governance_public_api.py --write")
        return 1
    print("verified static Governance public API mapping and facade")
    return 0


def _inventory_bindings() -> dict[str, tuple[str, str]]:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    exports = payload["packages"]["pheroos.governance"]["exports"]
    bindings: dict[str, tuple[str, str]] = {}
    for export in exports:
        name = export["name"]
        owner = export["binding_owner"]
        if not isinstance(name, str) or not isinstance(owner, str):
            raise ValueError("Governance inventory binding must contain text")
        bindings[name] = (owner, name)
    if len(bindings) != len(exports):
        raise ValueError("Governance inventory contains duplicate exports")
    return bindings


def _checked_export_order() -> tuple[str, ...]:
    order = _mapping_order(TARGET) if TARGET.is_file() else _legacy_all_order(FACADE)
    observed = sha256("\n".join(order).encode("utf-8")).hexdigest()
    if observed != EXPECTED_EXPORT_ORDER_SHA256:
        raise ValueError(
            "Governance export order drifted; an explicit compatibility decision "
            "is required"
        )
    return order


def _mapping_order(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "PUBLIC_API"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Call) or not node.value.args:
            break
        mapping = ast.literal_eval(node.value.args[0])
        if not isinstance(mapping, dict):
            break
        return tuple(mapping)
    raise ValueError("static Governance PUBLIC_API mapping is malformed")


def _legacy_all_order(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            continue
        value = ast.literal_eval(node.value)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return tuple(value)
    raise ValueError("legacy Governance __all__ declaration is malformed")


def _render_mapping(
    order: tuple[str, ...],
    bindings: dict[str, tuple[str, str]],
) -> str:
    lines = [
        '"""Generated static declarations for the Governance public facade.',
        "",
        "Regenerate with ``scripts/generate_governance_public_api.py --write``.",
        '"""',
        "",
        "from types import MappingProxyType",
        "",
        "",
        f'PUBLIC_API_ORDER_SHA256 = "{EXPECTED_EXPORT_ORDER_SHA256}"',
        "PUBLIC_API = MappingProxyType(",
        "    {",
    ]
    for name in order:
        module_name, attribute = bindings[name]
        lines.append(
            f"        {_quoted(name)}: ({_quoted(module_name)}, {_quoted(attribute)}),"
        )
    lines.extend(
        [
            "    }",
            ")",
            "COMPATIBILITY_MODULES = MappingProxyType(",
            "    {",
        ]
    )
    for name in COMPATIBILITY_MODULES:
        lines.append(
            f"        {_quoted(name)}: {_quoted(f'pheroos.governance.{name}')},"
        )
    lines.extend(
        [
            "    }",
            ")",
            "",
            "",
            '__all__ = ["COMPATIBILITY_MODULES", "PUBLIC_API", "PUBLIC_API_ORDER_SHA256"]',
            "",
        ]
    )
    return "\n".join(lines)


def _render_facade(
    order: tuple[str, ...],
    bindings: dict[str, tuple[str, str]],
) -> str:
    lines = [
        '"""Static, thread-safe lazy facade for the Governance public ABI."""',
        "",
        "from importlib import import_module as _import_module",
        "from threading import RLock as _RLock",
        "from typing import TYPE_CHECKING, Any as _Any",
        "",
        "from pheroos.governance._public_api import (",
        "    COMPATIBILITY_MODULES as _COMPATIBILITY_MODULES,",
        "    PUBLIC_API as _PUBLIC_API,",
        ")",
        "",
        "",
        "if TYPE_CHECKING:",
    ]
    for name in order:
        module_name, attribute = bindings[name]
        lines.append(
            f"    from {module_name} import {attribute} as {name}"
        )
    lines.extend(
        [
            "",
            "del TYPE_CHECKING",
            "",
            "__all__ = list(_PUBLIC_API)",
            "",
            "_PUBLIC_API_LOCK = _RLock()",
            "",
            "",
            "def __getattr__(name: str) -> _Any:",
            "    target = _PUBLIC_API.get(name)",
            "    compatibility_module = _COMPATIBILITY_MODULES.get(name)",
            "    if target is None and compatibility_module is None:",
            "        raise AttributeError(",
            '            f"module {__name__!r} has no attribute {name!r}"',
            "        )",
            "    with _PUBLIC_API_LOCK:",
            "        if name in globals():",
            "            return globals()[name]",
            "        if target is not None:",
            "            module_name, attribute = target",
            "            value = getattr(_import_module(module_name), attribute)",
            "        else:",
            "            value = _import_module(compatibility_module)",
            "        globals()[name] = value",
            "        return value",
            "",
            "",
            "def __dir__() -> list[str]:",
            "    return sorted(",
            "        set(globals()) | set(_PUBLIC_API) | set(_COMPATIBILITY_MODULES)",
            "    )",
            "",
        ]
    )
    return "\n".join(lines)


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


if __name__ == "__main__":
    raise SystemExit(main())
