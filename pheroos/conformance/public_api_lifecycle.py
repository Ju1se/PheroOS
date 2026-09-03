"""Checked lifecycle metadata for the six supported Python facades.

The shape inventory answers *what* the public Python ABI is.  This module
answers *how long* each binding is supported and where consumers should move
when a compatibility binding is retired.  The generated artifact is package
data so source conformance and installed-wheel tooling use the same lifecycle
contract.

This module is intentionally internal to :mod:`pheroos.conformance`; lifecycle
metadata describes public bindings without expanding the public facade itself.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from collections.abc import Mapping
from importlib import import_module
from pathlib import Path
from typing import Any

from pheroos.conformance.public_api_inventory import (
    PUBLIC_PACKAGES,
    build_public_api_inventory,
    public_api_inventory_differences,
)

PUBLIC_API_LIFECYCLE_VERSION = "pheroos-public-python-api-lifecycle-v1"
PUBLIC_API_LIFECYCLE_PATH = Path(
    "pheroos/conformance/abi/public-python-api-lifecycle-v1.json"
)
PUBLIC_API_GROUPS = frozenset(
    {"entrypoint", "record", "verification", "transition", "compatibility"}
)
PUBLIC_API_STABILITIES = frozenset({"draft", "stable", "deprecated"})
PROJECT_API_VERSION = "0.1.0"
DEFAULT_REMOVE_AFTER = "0.3.0"
_VERSION_PATTERN = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)


# These are lifecycle decisions, not inferred implementation facts.  Keeping
# them in one small table makes the remaining Draft compatibility decisions
# explicit and keeps the JSON artifact reproducible.
_EXPORT_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("pheroos.governance", "canonical_pheromone_kind_profiles"): {
        "group": "verification",
    },
    ("pheroos.governance", "normalize_legacy_pheromone_trail"): {
        "group": "compatibility",
        "retained_with_reason": (
            "Canonical Draft migration boundary for legacy scalar-weight trails; "
            "normalization never creates evidence or authority"
        ),
    },
}


_COMPATIBILITY_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {}


# Only package facades with an explicit static compatibility map participate
# here.  The order is stable so adding Conformance does not reorder the
# existing Governance lifecycle records.
_COMPATIBILITY_PACKAGES = (
    "pheroos.governance",
    "pheroos.conformance",
)


_VERIFICATION_PREFIXES = (
    "can_",
    "check_",
    "collect_",
    "effective_",
    "has_",
    "is_",
    "missing_",
    "profile_for_",
    "required_",
    "validate_",
    "verify_",
)
_VERIFICATION_SUFFIXES = (
    "_digest",
    "_fingerprint",
    "_is_authoritative",
    "_matches",
    "_payload",
    "_root",
    "_schema",
)
_TRANSITION_PREFIXES = (
    "advance_",
    "allocate_",
    "apply_",
    "authorize_",
    "bind_",
    "commit_",
    "declare",
    "deposit_",
    "diffuse_",
    "evaluate_",
    "evaporate_",
    "expire_",
    "expose",
    "finalize_",
    "initialize_",
    "invoke",
    "issue_",
    "materialize_",
    "normalize_",
    "observe_",
    "prepare_",
    "probe",
    "record_",
    "register",
    "reinforce_",
    "resolve_",
    "restart_",
    "revoke_",
    "score_",
    "select_",
    "transition_",
)


def build_public_api_lifecycle(
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build canonical lifecycle metadata from the current public ABI."""

    root = (
        Path(source_root).resolve()
        if source_root is not None
        else Path(__file__).resolve().parents[2]
    )
    inventory = build_public_api_inventory()
    packages: dict[str, Any] = {}
    export_count = 0
    for package_name in PUBLIC_PACKAGES:
        shapes = inventory["packages"][package_name]["exports"]
        exports = [
            _export_lifecycle(package_name, shape)
            for shape in sorted(shapes, key=lambda item: item["name"])
        ]
        export_count += len(exports)
        packages[package_name] = {
            "export_count": len(exports),
            "exports": exports,
        }

    compatibility_surfaces = _compatibility_surfaces()
    diagnostic_codes = _diagnostic_code_inventory(root)
    error_types = _public_error_type_inventory(inventory)
    return {
        "artifact_version": PUBLIC_API_LIFECYCLE_VERSION,
        "compatibility_surfaces": compatibility_surfaces,
        "diagnostic_codes": diagnostic_codes,
        "error_types": error_types,
        "groups": sorted(PUBLIC_API_GROUPS),
        "packages": packages,
        "stabilities": sorted(PUBLIC_API_STABILITIES),
        "summary": {
            "compatibility_surface_count": len(compatibility_surfaces),
            "diagnostic_code_count": len(diagnostic_codes),
            "error_type_count": len(error_types),
            "export_count": export_count,
            "package_count": len(PUBLIC_PACKAGES),
        },
    }


def render_public_api_lifecycle(lifecycle: dict[str, Any]) -> str:
    """Render the artifact in a deterministic, reviewable representation."""

    return (
        json.dumps(
            lifecycle,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def load_public_api_lifecycle(root: str | Path) -> dict[str, Any]:
    path = Path(root) / PUBLIC_API_LIFECYCLE_PATH
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("public API lifecycle artifact must be a JSON object")
    return loaded


def public_api_lifecycle_differences(
    expected: Any,
    observed: Any,
    *,
    limit: int = 32,
) -> list[str]:
    """Return bounded paths whose lifecycle metadata differs."""

    return public_api_inventory_differences(expected, observed, limit=limit)


def public_api_lifecycle_problems(
    lifecycle: dict[str, Any],
) -> list[str]:
    """Validate coverage, transitions, replacements, and diagnostic registry."""

    problems = _lifecycle_root_problems(lifecycle)
    packages = lifecycle.get("packages")
    if not isinstance(packages, dict) or set(packages) != set(PUBLIC_PACKAGES):
        problems.append("packages")
        return problems
    package_problems, total = _package_lifecycle_problems(packages)
    problems.extend(package_problems)
    compatibility = lifecycle.get("compatibility_surfaces")
    problems.extend(_compatibility_surface_problems(compatibility))
    problems.extend(_diagnostic_registry_problems(lifecycle.get("diagnostic_codes")))
    problems.extend(_error_type_registry_problems(lifecycle.get("error_types")))
    problems.extend(
        _lifecycle_summary_problems(
            lifecycle,
            compatibility=compatibility,
            export_count=total,
        )
    )
    return problems


def _lifecycle_root_problems(lifecycle: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if lifecycle.get("artifact_version") != PUBLIC_API_LIFECYCLE_VERSION:
        problems.append("artifact_version")
    if lifecycle.get("groups") != sorted(PUBLIC_API_GROUPS):
        problems.append("groups")
    if lifecycle.get("stabilities") != sorted(PUBLIC_API_STABILITIES):
        problems.append("stabilities")
    return problems


def _package_lifecycle_problems(
    packages: Mapping[str, Any],
) -> tuple[list[str], int]:
    problems: list[str] = []
    total = 0
    for package_name in PUBLIC_PACKAGES:
        module = import_module(package_name)
        package = packages.get(package_name)
        if not isinstance(package, dict):
            problems.append(f"package:{package_name}:invalid")
            continue
        exports = package.get("exports")
        if not isinstance(exports, list):
            problems.append(f"package:{package_name}:exports_invalid")
            continue
        names = [
            item["name"]
            for item in exports
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        if len(names) != len(exports) or len(names) != len(set(names)):
            problems.append(f"package:{package_name}:duplicate_or_invalid")
            continue
        declared = set(module.__all__)
        observed = set(names)
        for missing in sorted(declared - observed):
            problems.append(f"package:{package_name}:missing:{missing}")
        for orphan in sorted(observed - declared):
            problems.append(f"package:{package_name}:orphan:{orphan}")
        if package.get("export_count") != len(exports):
            problems.append(f"package:{package_name}:count")
        total += len(exports)
        for item in exports:
            if isinstance(item, dict):
                problems.extend(_entry_problems(item, expected_package=package_name))
    return problems, total


def _lifecycle_summary_problems(
    lifecycle: Mapping[str, Any],
    *,
    compatibility: Any,
    export_count: int,
) -> list[str]:
    problems: list[str] = []
    summary = lifecycle.get("summary")
    if not isinstance(summary, dict):
        problems.append("summary")
    else:
        expected_counts = {
            "compatibility_surface_count": (
                len(compatibility) if isinstance(compatibility, list) else -1
            ),
            "diagnostic_code_count": (
                len(lifecycle.get("diagnostic_codes", ()))
                if isinstance(lifecycle.get("diagnostic_codes"), list)
                else -1
            ),
            "error_type_count": (
                len(lifecycle.get("error_types", ()))
                if isinstance(lifecycle.get("error_types"), list)
                else -1
            ),
            "export_count": export_count,
            "package_count": len(PUBLIC_PACKAGES),
        }
        for key, value in expected_counts.items():
            if summary.get(key) != value:
                problems.append(f"summary:{key}")
    return problems


def _export_lifecycle(package_name: str, shape: dict[str, Any]) -> dict[str, Any]:
    name = shape["name"]
    entry: dict[str, Any] = {
        "group": _infer_group(name, shape["kind"]),
        "name": name,
        "package": package_name,
        "remove_after": None,
        "replacement": None,
        "retained_with_reason": None,
        "since": PROJECT_API_VERSION,
        "stability": "draft",
    }
    entry.update(_EXPORT_OVERRIDES.get((package_name, name), {}))
    parameter_lifecycle = entry.get("parameter_lifecycle")
    if parameter_lifecycle is not None:
        entry["parameter_lifecycle"] = [dict(item) for item in parameter_lifecycle]
    return entry


def _infer_group(name: str, kind: str) -> str:
    if kind != "function":
        return "record"
    if name.startswith(_VERIFICATION_PREFIXES) or name.endswith(_VERIFICATION_SUFFIXES):
        return "verification"
    if name.startswith(_TRANSITION_PREFIXES):
        return "transition"
    return "entrypoint"


def _compatibility_surfaces() -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    for package_name in _COMPATIBILITY_PACKAGES:
        package = import_module(package_name)
        mapping = package.__dict__.get("_COMPATIBILITY_MODULES", {})
        for name, target in sorted(mapping.items()):
            entry: dict[str, Any] = {
                "group": "compatibility",
                "name": name,
                "package": package_name,
                "remove_after": None,
                "replacement": target,
                "retained_with_reason": (
                    "Lazy module attribute retained for package-level import "
                    "compatibility"
                ),
                "since": PROJECT_API_VERSION,
                "stability": "draft",
            }
            entry.update(_COMPATIBILITY_OVERRIDES.get((package_name, name), {}))
            surfaces.append(entry)
    return surfaces


def _entry_problems(
    entry: dict[str, Any],
    *,
    expected_package: str,
) -> list[str]:
    identity = f"{expected_package}.{entry.get('name', '<unknown>')}"
    required = {
        "group",
        "name",
        "package",
        "remove_after",
        "replacement",
        "retained_with_reason",
        "since",
        "stability",
    }
    allowed = required | {"parameter_lifecycle"}
    problems: list[str] = []
    if not required.issubset(entry) or not set(entry).issubset(allowed):
        problems.append(f"entry:{identity}:fields")
        return problems
    problems.extend(_basic_entry_problems(entry, expected_package, identity))
    problems.extend(_entry_lifecycle_problems(entry, identity))
    problems.extend(_parameter_lifecycle_problems(entry, expected_package, identity))
    return problems


def _basic_entry_problems(
    entry: dict[str, Any],
    expected_package: str,
    identity: str,
) -> list[str]:
    problems: list[str] = []
    if entry["package"] != expected_package:
        problems.append(f"entry:{identity}:package")
    if not isinstance(entry["name"], str) or not entry["name"]:
        problems.append(f"entry:{identity}:name")
    if entry["group"] not in PUBLIC_API_GROUPS:
        problems.append(f"entry:{identity}:group")
    if entry["stability"] not in PUBLIC_API_STABILITIES:
        problems.append(f"entry:{identity}:stability")
    if not _valid_version(entry["since"]):
        problems.append(f"entry:{identity}:since")
    return problems


def _entry_lifecycle_problems(
    entry: dict[str, Any],
    identity: str,
) -> list[str]:
    problems: list[str] = []
    replacement = entry["replacement"]
    if replacement is not None:
        if not isinstance(replacement, str) or not _external_reference_exists(
            replacement
        ):
            problems.append(f"entry:{identity}:replacement")
    remove_after = entry["remove_after"]
    if remove_after is not None and not _valid_version(remove_after):
        problems.append(f"entry:{identity}:remove_after")
    elif remove_after is not None and _version_tuple(remove_after) <= _version_tuple(
        entry["since"]
    ):
        problems.append(f"entry:{identity}:remove_after_order")
    if entry["stability"] == "deprecated":
        if remove_after is None:
            problems.append(f"entry:{identity}:remove_after_missing")
        if replacement is None and not entry["retained_with_reason"]:
            problems.append(f"entry:{identity}:replacement_missing")
    elif remove_after is not None:
        problems.append(f"entry:{identity}:unexpected_remove_after")
    reason = entry["retained_with_reason"]
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        problems.append(f"entry:{identity}:retained_with_reason")
    return problems


def _parameter_lifecycle_problems(
    entry: dict[str, Any],
    expected_package: str,
    identity: str,
) -> list[str]:
    problems: list[str] = []
    parameters = entry.get("parameter_lifecycle", [])
    if not isinstance(parameters, list):
        problems.append(f"entry:{identity}:parameter_lifecycle")
        return problems
    names: set[str] = set()
    try:
        signature_parameters: Mapping[str, inspect.Parameter] = inspect.signature(
            getattr(import_module(expected_package), entry["name"])
        ).parameters
    except (AttributeError, TypeError, ValueError):
        signature_parameters = {}
    for parameter in parameters:
        problems.extend(
            _parameter_entry_problems(
                parameter,
                identity=identity,
                names=names,
                signature_parameters=signature_parameters,
            )
        )
    return problems


def _parameter_entry_problems(
    parameter: object,
    *,
    identity: str,
    names: set[str],
    signature_parameters: Mapping[str, inspect.Parameter],
) -> list[str]:
    problems: list[str] = []
    if not isinstance(parameter, dict):
        return [f"entry:{identity}:parameter_invalid"]
    expected_fields = {"name", "stability", "replacement", "remove_after"}
    if set(parameter) != expected_fields:
        return [f"entry:{identity}:parameter_fields"]
    parameter_name = parameter["name"]
    if not isinstance(parameter_name, str) or not parameter_name:
        problems.append(f"entry:{identity}:parameter_name")
    elif parameter_name in names:
        problems.append(f"entry:{identity}:parameter_duplicate")
    names.add(parameter_name)
    if parameter_name not in signature_parameters:
        problems.append(f"entry:{identity}:parameter_orphan:{parameter_name}")
    if parameter["stability"] != "deprecated":
        problems.append(f"entry:{identity}:parameter_stability")
    if not _valid_version(parameter["remove_after"]):
        problems.append(f"entry:{identity}:parameter_remove_after")
    if not _external_reference_exists(parameter["replacement"]):
        problems.append(f"entry:{identity}:parameter_replacement")
    return problems


def _compatibility_surface_problems(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["compatibility_surfaces"]
    declared = _declared_compatibility_surfaces()
    entries = [item for item in value if isinstance(item, dict)]
    if len(entries) != len(value):
        return ["compatibility_surfaces:entry_invalid"]
    identities = _compatibility_identities(entries)
    problems = _compatibility_identity_problems(declared, identities)
    for entry in entries:
        entry_package = entry.get("package")
        if isinstance(entry_package, str) and entry_package in _COMPATIBILITY_PACKAGES:
            problems.extend(_entry_problems(entry, expected_package=entry_package))
    return problems


def _declared_compatibility_surfaces() -> dict[tuple[str, str], str]:
    declared: dict[tuple[str, str], str] = {}
    for package_name in _COMPATIBILITY_PACKAGES:
        package = import_module(package_name)
        mapping = package.__dict__.get("_COMPATIBILITY_MODULES", {})
        for name, target in mapping.items():
            declared[(package_name, name)] = target
    return declared


def _compatibility_identities(
    entries: list[dict[object, object]],
) -> list[tuple[str, str]]:
    identities: list[tuple[str, str]] = []
    for item in entries:
        observed_package = item.get("package")
        observed_name = item.get("name")
        if isinstance(observed_package, str) and isinstance(observed_name, str):
            identities.append((observed_package, observed_name))
    return identities


def _compatibility_identity_problems(
    declared: Mapping[tuple[str, str], str],
    identities: list[tuple[str, str]],
) -> list[str]:
    problems: list[str] = []
    if len(identities) != len(set(identities)):
        problems.append("compatibility_surfaces:duplicate")
    for package_name, name in sorted(set(declared) - set(identities)):
        problems.append(f"compatibility_surfaces:missing:{package_name}:{name}")
    for package_name, name in sorted(set(identities) - set(declared)):
        problems.append(f"compatibility_surfaces:orphan:{package_name}:{name}")
    return problems


def _diagnostic_registry_problems(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["diagnostic_codes"]
    fields = {"code", "family", "kind", "owner", "package"}
    keys: set[tuple[str, str, str]] = set()
    problems: list[str] = []
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != fields:
            problems.append("diagnostic_codes:fields")
            continue
        key = (entry["package"], entry["family"], entry["code"])
        if key in keys:
            problems.append("diagnostic_codes:duplicate")
        keys.add(key)
        if entry["package"] not in PUBLIC_PACKAGES:
            problems.append(f"diagnostic_codes:package:{entry['package']}")
        if entry["kind"] not in {"exact", "prefix"}:
            problems.append(f"diagnostic_codes:kind:{entry['kind']}")
        if not all(
            isinstance(entry[name], str) and bool(entry[name].strip())
            for name in fields
        ):
            problems.append("diagnostic_codes:value")
        if entry["kind"] == "prefix" and not entry["code"].endswith("*"):
            problems.append(f"diagnostic_codes:prefix:{entry['code']}")
        if not _external_reference_exists(entry["owner"]):
            problems.append(f"diagnostic_codes:owner:{entry['owner']}")
    return problems


def _error_type_registry_problems(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["error_types"]
    fields = {"name", "owner", "package"}
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != fields:
            problems.append("error_types:fields")
            continue
        key = (entry["package"], entry["name"])
        if key in seen:
            problems.append("error_types:duplicate")
        seen.add(key)
        if entry["package"] not in PUBLIC_PACKAGES:
            problems.append(f"error_types:package:{entry['package']}")
        if not _external_reference_exists(f"{entry['package']}.{entry['name']}"):
            problems.append(f"error_types:orphan:{entry['package']}.{entry['name']}")
        if not isinstance(entry["owner"], str) or ":" not in entry["owner"]:
            problems.append(f"error_types:owner:{entry.get('owner')}")
    return problems


def _public_error_type_inventory(inventory: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for package_name in PUBLIC_PACKAGES:
        for shape in inventory["packages"][package_name]["exports"]:
            if shape["kind"] == "class" and shape["name"].endswith("Error"):
                errors.append(
                    {
                        "name": shape["name"],
                        "owner": shape["identity"],
                        "package": package_name,
                    }
                )
    return sorted(errors, key=lambda item: (item["package"], item["name"]))


def _diagnostic_code_inventory(root: Path) -> list[dict[str, str]]:
    protocol_validation_sources = (
        root / "pheroos/protocol/validation.py",
        *sorted((root / "pheroos/protocol").glob("_validation_*_rules.py")),
    )
    protocol_validation_calls: dict[str, tuple[int | None, str | None]] = {
        "error": (0, None),
        "validation_error": (0, None),
    }
    kernel_planning_source = root / "pheroos/kernel/capability_resolution.py"
    producers: tuple[
        tuple[
            str,
            str,
            str,
            Path,
            dict[str, tuple[int | None, str | None]],
        ],
        ...,
    ] = tuple(
        (
            "pheroos.protocol",
            "manifest-validation",
            "pheroos.protocol.validation",
            path,
            protocol_validation_calls,
        )
        for path in protocol_validation_sources
    ) + (
        (
            "pheroos.protocol",
            "schema-document",
            "pheroos.protocol.ProtocolSchemaVersionError",
            root / "pheroos/protocol/schema_document.py",
            {"ProtocolSchemaVersionError": (0, None)},
        ),
        (
            "pheroos.drivers",
            "driver-schema-document",
            "pheroos.drivers.DriverSchemaVersionError",
            root / "pheroos/drivers/document.py",
            {"DriverSchemaVersionError": (0, None)},
        ),
        (
            "pheroos.kernel",
            "kernel-planning",
            "pheroos.kernel.KernelDiagnostic",
            kernel_planning_source,
            {"KernelDiagnostic": (None, "code")},
        ),
        (
            "pheroos.kernel",
            "kernel-plan-document",
            "pheroos.kernel.KernelPlanVersionError",
            root / "pheroos/kernel/plan_document.py",
            {"KernelPlanVersionError": (0, None)},
        ),
        (
            "pheroos.governance",
            "hybrid-commit-evaluation",
            "pheroos.governance.HybridCommitDiagnostic",
            root / "pheroos/governance/_hybrid/pipeline.py",
            {"_diagnostic": (0, None), "_diagnostic_from_exception": (0, None)},
        ),
        (
            "pheroos.governance",
            "hybrid-commit-evaluation",
            "pheroos.governance.HybridCommitDiagnostic",
            root / "pheroos/governance/_hybrid/attention.py",
            {"_diagnostic": (0, None)},
        ),
        (
            "pheroos.governance",
            "atomic-hybrid-commit",
            "pheroos.governance.AtomicHybridCommitResult",
            root / "pheroos/governance/atomic_evaluation.py",
            {
                "_failure_result": (None, "reason_code"),
                "_standalone_failure_result": (None, "reason_code"),
                "_result": (None, "reason_code"),
            },
        ),
    )
    entries: list[dict[str, str]] = []
    for package, family, owner, path, call_specs in producers:
        for code, kind in _extract_static_codes(path, call_specs):
            entries.append(
                {
                    "code": code,
                    "family": family,
                    "kind": kind,
                    "owner": owner,
                    "package": package,
                }
            )
    for code, kind in _extract_static_diagnostic_tuples(kernel_planning_source):
        entries.append(
            {
                "code": code,
                "family": "kernel-planning",
                "kind": kind,
                "owner": "pheroos.kernel.KernelDiagnostic",
                "package": "pheroos.kernel",
            }
        )
    # Authority v2 is a closed, versioned Protocol registry rather than a set
    # of string literals inferred from individual Governance call sites.
    from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2

    entries.extend(
        {
            "code": diagnostic.value,
            "family": "scoped-authority-v2",
            "kind": "exact",
            "owner": "pheroos.protocol.AuthorityDiagnosticCodeV2",
            "package": "pheroos.protocol",
        }
        for diagnostic in AuthorityDiagnosticCodeV2
    )
    # Kernel re-emits the closed Protocol diagnostic namespace with a stable
    # prefix.  The suffix is intentionally open to Protocol-version additions.
    entries.append(
        {
            "code": "manifest_*",
            "family": "kernel-planning",
            "kind": "prefix",
            "owner": "pheroos.kernel.KernelDiagnostic",
            "package": "pheroos.kernel",
        }
    )
    unique = {(item["package"], item["family"], item["code"]): item for item in entries}
    return [unique[key] for key in sorted(unique)]


def _extract_static_codes(
    path: Path,
    call_specs: dict[str, tuple[int | None, str | None]],
) -> list[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else (node.target,))
        if isinstance(target, ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        spec = call_specs.get(call_name)
        if spec is None:
            continue
        position, keyword = spec
        expression: ast.expr | None = None
        if position is not None and len(node.args) > position:
            expression = node.args[position]
        elif keyword is not None:
            expression = next(
                (item.value for item in node.keywords if item.arg == keyword),
                None,
            )
        code = _static_code(expression, constants)
        if code is not None:
            found.add(code)
    return sorted(found)


def _extract_static_diagnostic_tuples(path: Path) -> list[tuple[str, str]]:
    """Extract ``(code, message, severity)`` diagnostics returned by helpers."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Tuple) or len(node.elts) != 3:
            continue
        severity = node.elts[2]
        if not (
            isinstance(severity, ast.Constant)
            and severity.value in {"error", "warning"}
        ):
            continue
        code = _static_code(node.elts[0], {})
        if code is not None:
            found.add(code)
    return sorted(found)


def _static_code(
    expression: ast.expr | None,
    constants: dict[str, str],
) -> tuple[str, str] | None:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return expression.value, "exact"
    if isinstance(expression, ast.Name) and expression.id in constants:
        return constants[expression.id], "exact"
    if isinstance(expression, ast.JoinedStr):
        parts: list[str] = []
        for value in expression.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("*")
            else:
                return None
        return "".join(parts), "prefix"
    return None


def _call_name(value: ast.expr) -> str:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return ""


def _valid_version(value: object) -> bool:
    return isinstance(value, str) and bool(_VERSION_PATTERN.fullmatch(value))


def _version_tuple(value: object) -> tuple[int, int, int]:
    if not isinstance(value, str) or not _VERSION_PATTERN.fullmatch(value):
        return (0, 0, 0)
    major, minor, patch = (int(part) for part in value.split("."))
    return major, minor, patch


def _external_reference_exists(reference: object) -> bool:
    if not isinstance(reference, str) or not reference.startswith("pheroos."):
        return False
    try:
        import_module(reference)
    except ModuleNotFoundError:
        module_name, separator, attribute = reference.rpartition(".")
        if not separator:
            return False
        try:
            module = import_module(module_name)
        except (ImportError, ModuleNotFoundError):
            return False
        return attribute in getattr(module, "__all__", ()) and hasattr(
            module, attribute
        )
    except ImportError:
        return False
    return True


__all__ = [
    "DEFAULT_REMOVE_AFTER",
    "PROJECT_API_VERSION",
    "PUBLIC_API_GROUPS",
    "PUBLIC_API_LIFECYCLE_PATH",
    "PUBLIC_API_LIFECYCLE_VERSION",
    "PUBLIC_API_STABILITIES",
    "build_public_api_lifecycle",
    "load_public_api_lifecycle",
    "public_api_lifecycle_differences",
    "public_api_lifecycle_problems",
    "render_public_api_lifecycle",
]
