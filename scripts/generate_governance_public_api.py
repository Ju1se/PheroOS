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
PREDECESSOR_EXPORT_ORDER_SHA256 = (
    "8dbeb2fccde028655b1090abfe7682ac37594920df45ce60cbf1d1c85bde98f9"
)
EXPECTED_EXPORT_ORDER_SHA256 = (
    "607d19b60814e1486080a405460163a94752caa384974625f06738f480b4a85e"
)
REMOVED_EXPORTS = frozenset({"commit_replay_receipt_v2_from_v1"})
PUBLIC_API_EXTENSION_MODULES = (
    "pheroos.governance.baseline_output_v2",
    "pheroos.governance.risk_v2",
    "pheroos.governance.support_v2",
    "pheroos.governance.commit_gate_v2",
    "pheroos.governance.commit_evidence_v2",
    "pheroos.governance.commit_finality_v2",
    "pheroos.governance.commit_decision_v2",
    "pheroos.governance.commit_certificate_v2",
    "pheroos.governance.distributed_commit_v2",
)
PUBLIC_API_SHARED_ALIASES = {
    "COMMIT_FINALITY_INPUT_SCHEMA_V2": "pheroos.governance.commit_finality_v2",
    "COMMIT_FINALITY_PROJECTION_SCHEMA_V2": "pheroos.governance.commit_finality_v2",
    "CommitFinalityOwnerV2": "pheroos.governance.commit_finality_v2",
    "CommitFinalityProjectionV2": "pheroos.governance.commit_finality_v2",
    "CommitFinalityStatusV2": "pheroos.governance.commit_finality_v2",
    "RiskBand": "pheroos.governance.risk",
    "VerifiedCommitFinalityInputV2": "pheroos.governance.commit_finality_v2",
    "commit_finality_owner_genesis_snapshot_root_v2": (
        "pheroos.governance.commit_finality_v2"
    ),
    "commit_finality_owner_stream_ref_v2": "pheroos.governance.commit_finality_v2",
}
PUBLIC_API_BINDING_OVERRIDES = {
    # These are the exact same vocabulary objects exposed by the frozen v1
    # facades.  Route root lookup through registry-free v2 facades so a v2
    # consumer does not initialize process-local legacy authority merely by
    # asking for shared data vocabulary.
    "ReplayNamespace": ("pheroos.governance.commit_state_v2", "ReplayNamespace"),
    "RiskBand": ("pheroos.governance.risk_v2", "RiskBand"),
    "EvidenceCommitCertificate": (
        "pheroos.governance.historical_certificate",
        "EvidenceCommitCertificate",
    ),
    "evidence_commit_certificate_fingerprint": (
        "pheroos.governance.historical_certificate",
        "evidence_commit_certificate_fingerprint",
    ),
    "evidence_commit_certificate_from_payload": (
        "pheroos.governance.historical_certificate",
        "evidence_commit_certificate_from_payload",
    ),
    "evidence_commit_certificate_payload": (
        "pheroos.governance.historical_certificate",
        "evidence_commit_certificate_payload",
    ),
    "select_terminal_outcome_kind": (
        "pheroos.governance.commit_semantics",
        "select_terminal_outcome_kind",
    ),
    "verify_evidence_commit_certificate": (
        "pheroos.governance.historical_certificate",
        "verify_evidence_commit_certificate",
    ),
}
LINE_LENGTH = 88
COMPATIBILITY_MODULES = (
    "attention",
    "atomic_evaluation",
    "authority",
    "authority_domain",
    "authority_session_v2",
    "authority_store_v2",
    "baseline_output_v2",
    "candidate",
    "certificate",
    "challenge",
    "collective",
    "commit",
    "commit_semantics",
    "commit_numeric",
    "commit_certificate_v2",
    "commit_decision_v2",
    "commit_evidence_v2",
    "commit_finality_v2",
    "commit_gate_v2",
    "commit_state",
    "commit_state_v2",
    "distributed_commit",
    "distributed_commit_v2",
    "errors",
    "evidence",
    "evidence_binding",
    "historical_certificate",
    "hybrid_commit",
    "hybrid_commit_evaluation",
    "hybrid_replay_v2",
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
    "risk_v2",
    "runtime_policy",
    "schema",
    "signal",
    "stop_signal",
    "support_lease",
    "support_v2",
    "target",
    "trace",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    source_order = _checked_export_order()
    order, bindings = _configured_public_api(
        source_order,
        _inventory_bindings(),
    )
    configured_hash = sha256("\n".join(order).encode("utf-8")).hexdigest()
    if configured_hash != EXPECTED_EXPORT_ORDER_SHA256:
        raise ValueError(
            "configured Governance export order changed; update the reviewed hash"
        )
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
    if observed not in {
        PREDECESSOR_EXPORT_ORDER_SHA256,
        EXPECTED_EXPORT_ORDER_SHA256,
    }:
        raise ValueError(
            "Governance export order drifted; an explicit compatibility decision "
            "is required"
        )
    return order


def _configured_public_api(
    source_order: tuple[str, ...],
    inventory_bindings: dict[str, tuple[str, str]],
) -> tuple[tuple[str, ...], dict[str, tuple[str, str]]]:
    """Apply the reviewed WP-05 activation without importing implementation code."""

    order = [name for name in source_order if name not in REMOVED_EXPORTS]
    bindings = {
        name: binding
        for name, binding in inventory_bindings.items()
        if name not in REMOVED_EXPORTS
    }
    for module_name in PUBLIC_API_EXTENSION_MODULES:
        for name in _static_module_all(module_name):
            existing = bindings.get(name)
            if existing is not None:
                if existing == (module_name, name):
                    continue
                preferred = PUBLIC_API_SHARED_ALIASES.get(name)
                if preferred is None or existing[0] != preferred:
                    raise ValueError(
                        f"unreviewed Governance public export collision: {name}"
                    )
                continue
            bindings[name] = (module_name, name)
            if name not in order:
                order.append(name)
    for name, binding in PUBLIC_API_BINDING_OVERRIDES.items():
        if name not in bindings or name not in order:
            raise ValueError(f"Governance public binding override is unknown: {name}")
        bindings[name] = binding
    if len(order) != len(set(order)):
        raise ValueError("configured Governance public export order is not unique")
    return tuple(order), bindings


def _static_module_all(
    module_name: str,
    *,
    seen: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    if module_name in seen:
        raise ValueError(f"cyclic static __all__ alias: {module_name}")
    module_path = ROOT.joinpath(*module_name.split("."))
    path = module_path.with_suffix(".py")
    if not path.is_file():
        path = module_path / "__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            value = _static_all_alias(
                module_name,
                tree,
                node.value,
                seen=seen | {module_name},
            )
        if not isinstance(value, (list, tuple)) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError(f"{module_name} has a non-static __all__ declaration")
        names = tuple(value)
        if len(names) != len(set(names)):
            raise ValueError(f"{module_name} has duplicate public exports")
        return names
    raise ValueError(f"{module_name} has no static __all__ declaration")


def _static_all_alias(
    module_name: str,
    tree: ast.Module,
    value: ast.AST,
    *,
    seen: frozenset[str],
) -> tuple[str, ...]:
    if not (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in {"list", "tuple"}
        and len(value.args) == 1
        and not value.keywords
        and isinstance(value.args[0], ast.Name)
    ):
        raise ValueError(f"{module_name} has an unsupported __all__ expression")
    alias_name = value.args[0].id
    for node in tree.body:
        if (
            not isinstance(node, ast.ImportFrom)
            or node.level != 0
            or node.module is None
        ):
            continue
        for alias in node.names:
            if alias.name == "__all__" and (alias.asname or alias.name) == alias_name:
                return _static_module_all(node.module, seen=seen)
    raise ValueError(f"{module_name} has an unresolved __all__ alias: {alias_name}")


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
        "PUBLIC_API_ORDER_SHA256 = (",
        f'    "{EXPECTED_EXPORT_ORDER_SHA256}"',
        ")",
        "PUBLIC_API = MappingProxyType(",
        "    {",
    ]
    for name in order:
        module_name, attribute = bindings[name]
        rendered = (
            f"        {_quoted(name)}: ({_quoted(module_name)}, {_quoted(attribute)}),"
        )
        if len(rendered) <= LINE_LENGTH:
            lines.append(rendered)
        else:
            lines.extend(
                [
                    f"        {_quoted(name)}: (",
                    f"            {_quoted(module_name)},",
                    f"            {_quoted(attribute)},",
                    "        ),",
                ]
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
        rendered = f"    from {module_name} import {attribute} as {name}"
        if len(rendered) <= LINE_LENGTH:
            lines.append(rendered)
        else:
            lines.extend(
                [
                    f"    from {module_name} import (",
                    f"        {attribute} as {name},",
                    "    )",
                ]
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
            '        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")',
            "    with _PUBLIC_API_LOCK:",
            "        if name in globals():",
            "            return globals()[name]",
            "        if target is not None:",
            "            module_name, attribute = target",
            "            value = getattr(_import_module(module_name), attribute)",
            "        else:",
            "            assert compatibility_module is not None",
            "            value = _import_module(compatibility_module)",
            "        globals()[name] = value",
            "        return value",
            "",
            "",
            "def __dir__() -> list[str]:",
            "    return sorted(set(globals()) | set(_PUBLIC_API) | set(_COMPATIBILITY_MODULES))",
            "",
        ]
    )
    return "\n".join(lines)


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


if __name__ == "__main__":
    raise SystemExit(main())
