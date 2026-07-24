"""Validation and compatibility comparison for the Stable API candidate."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from typing import Any

from pheroos.conformance.public_api_inventory import (
    PUBLIC_PACKAGES,
    public_api_inventory_differences,
)
from pheroos.conformance.stable_api_roots import (
    STABLE_API_CANDIDATE_STABILITY,
    STABLE_API_CANDIDATE_STATUS,
    STABLE_API_CANDIDATE_VERSION,
    STABLE_API_COMPATIBILITY_MAJOR,
    STABLE_API_CURRENT_ROOT_TARGET,
    STABLE_API_FORBIDDEN_BINDINGS,
)


def stable_api_candidate_problems(candidate: Mapping[str, Any]) -> list[str]:
    """Validate candidate metadata, closure, ownership, and size budgets."""

    problems = _metadata_problems(candidate)
    packages = candidate.get("packages")
    if not isinstance(packages, dict) or set(packages) != set(PUBLIC_PACKAGES):
        return [*problems, "packages"]
    bindings: set[str] = set()
    identities: dict[str, str] = {}
    roots: set[str] = set()
    references: dict[str, set[str]] = {}
    constant_references: dict[str, set[str]] = {}
    for package_name in PUBLIC_PACKAGES:
        problems.extend(
            _package_problems(
                package_name,
                packages[package_name],
                bindings,
                identities,
                roots,
                references,
                constant_references,
            )
        )
    constants, constant_problems = _constant_dependency_index(
        candidate.get("constant_dependencies")
    )
    problems.extend(constant_problems)
    problems.extend(_missing_reference_problems(references, bindings))
    problems.extend(
        _missing_constant_problems(constant_references, constants, bindings)
    )
    problems.extend(_budget_problems(candidate, packages, roots, bindings, constants))
    if candidate.get("resolution_diagnostics") != []:
        problems.append("resolution_diagnostics")
    surface = candidate.get("surface_diagnostics")
    if surface != []:
        if isinstance(surface, list):
            problems.extend(f"surface:{item}" for item in surface)
        else:
            problems.append("surface_diagnostics")
    if candidate.get("artifact_root") != artifact_root(candidate):
        problems.append("artifact_root")
    return sorted(set(problems))


def promotion_candidate_differences(
    expected: Any,
    observed: Any,
    *,
    limit: int = 64,
) -> list[str]:
    """Return structural candidate drift, regardless of Draft lifecycle state."""

    return public_api_inventory_differences(expected, observed, limit=limit)


def stable_api_breaking_differences(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    *,
    limit: int = 64,
) -> list[str]:
    """Return same-major breakage only after formal Stable promotion."""

    lifecycle = expected.get("lifecycle")
    if not isinstance(lifecycle, dict) or lifecycle.get("stability") != "stable":
        return []
    if expected.get("compatibility_major") != observed.get("compatibility_major"):
        return []
    return promotion_candidate_differences(expected, observed, limit=limit)


def stable_public_inventory_breaking_differences(
    stable_candidate: Mapping[str, Any],
    expected_inventory: Mapping[str, Any],
    observed_inventory: Mapping[str, Any],
    *,
    observed_compatibility_major: int,
    limit: int = 64,
) -> list[str]:
    """Compare only formally Stable closure bindings in two full inventories."""

    lifecycle = stable_candidate.get("lifecycle")
    if not isinstance(lifecycle, dict) or lifecycle.get("stability") != "stable":
        return []
    if stable_candidate.get("compatibility_major") != observed_compatibility_major:
        return []
    return promotion_candidate_public_inventory_differences(
        stable_candidate,
        expected_inventory,
        observed_inventory,
        limit=limit,
    )


def promotion_candidate_public_inventory_differences(
    candidate: Mapping[str, Any],
    expected_inventory: Mapping[str, Any],
    observed_inventory: Mapping[str, Any],
    *,
    limit: int = 64,
) -> list[str]:
    """Compare only the candidate's reviewed closure in two full inventories.

    This comparison is intentionally independent of formal Stable lifecycle
    state.  It is the WP-07A promotion-candidate drift gate, while
    :func:`stable_public_inventory_breaking_differences` remains the later
    same-major Stable compatibility gate.  Expert Draft exports outside the
    reviewed closure cannot affect this result.
    """

    bindings = _artifact_bindings(candidate) | _artifact_constant_bindings(candidate)
    expected = _inventory_subset(expected_inventory, bindings)
    observed = _inventory_subset(observed_inventory, bindings)
    return public_api_inventory_differences(expected, observed, limit=limit)


def artifact_root(candidate: Mapping[str, Any]) -> str:
    """Return the canonical candidate digest without its self-root field."""

    body = dict(candidate)
    body.pop("artifact_root", None)
    encoded = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def candidate_summary(
    packages: Mapping[str, Any],
    constants: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    """Return deterministic aggregate root and closure counts."""

    return {
        "closure_count": sum(item["closure_count"] for item in packages.values()),
        "constant_dependency_count": len(constants or {}),
        "governance_closure_count": packages["pheroos.governance"]["closure_count"],
        "governance_root_count": packages["pheroos.governance"]["root_count"],
        "package_count": len(packages),
        "root_count": sum(item["root_count"] for item in packages.values()),
    }


def _metadata_problems(candidate: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if candidate.get("artifact_version") != STABLE_API_CANDIDATE_VERSION:
        problems.append("artifact_version")
    if candidate.get("compatibility_major") != STABLE_API_COMPATIBILITY_MAJOR:
        problems.append("compatibility_major")
    expected = {
        "formal_stable": False,
        "stability": STABLE_API_CANDIDATE_STABILITY,
        "status": STABLE_API_CANDIDATE_STATUS,
    }
    if candidate.get("lifecycle") != expected:
        problems.append("lifecycle")
    expected_policy = {
        "canonical_owner_required": True,
        "compatibility_bindings_allowed": False,
        "declared_public_exceptions": True,
        "dataclass_fields": True,
        "deprecated_bindings_allowed": False,
        "direct_class_methods_and_properties": True,
        "nonportable_opaque_authority_allowed": False,
        "public_constant_value_dependencies": True,
        "public_base_types": True,
        "signature_parameters_and_returns": True,
    }
    if candidate.get("closure_policy") != expected_policy:
        problems.append("closure_policy")
    if candidate.get("review_targets") != {"roots": STABLE_API_CURRENT_ROOT_TARGET}:
        problems.append("review_targets")
    return problems


def _package_problems(
    package_name: str,
    package: Any,
    bindings: set[str],
    identities: dict[str, str],
    roots: set[str],
    references: dict[str, set[str]],
    constant_references: dict[str, set[str]],
) -> list[str]:
    if not isinstance(package, dict) or not isinstance(package.get("exports"), list):
        return [f"package:{package_name}"]
    problems: list[str] = []
    exports = package["exports"]
    for entry in exports:
        problems.extend(
            _entry_problems(
                package_name,
                entry,
                bindings,
                identities,
                roots,
                references,
                constant_references,
            )
        )
    declared_roots = package.get("roots")
    expected_roots = sorted(
        item.rsplit(".", 1)[1] for item in roots if item.startswith(f"{package_name}.")
    )
    if declared_roots != expected_roots:
        problems.append(f"roots:{package_name}")
    if package.get("closure_count") != len(exports):
        problems.append(f"closure_count:{package_name}")
    if package.get("root_count") != len(expected_roots):
        problems.append(f"root_count:{package_name}")
    return problems


def _entry_problems(
    package_name: str,
    entry: Any,
    bindings: set[str],
    identities: dict[str, str],
    roots: set[str],
    references: dict[str, set[str]],
    constant_references: dict[str, set[str]],
) -> list[str]:
    if not isinstance(entry, dict):
        return [f"entry:{package_name}:invalid"]
    binding = entry.get("binding")
    if not isinstance(binding, str) or not binding.startswith(f"{package_name}."):
        return [f"entry:{package_name}:binding"]
    problems = _binding_problems(entry, binding, bindings)
    if entry.get("membership") == "root":
        roots.add(binding)
    elif entry.get("membership") != "dependency":
        problems.append(f"membership:{binding}")
    problems.extend(_identity_problems(entry, binding, identities))
    targets, target_problems = _reference_field(entry, binding, "references")
    references[binding] = targets
    problems.extend(target_problems)
    exceptions, exception_problems = _reference_field(
        entry,
        binding,
        "exception_references",
    )
    problems.extend(exception_problems)
    if not exceptions <= targets:
        problems.append(f"exception_reference_not_closed:{binding}")
    public_bases, base_problems = _reference_field(
        entry,
        binding,
        "public_bases",
    )
    problems.extend(base_problems)
    if not public_bases <= targets:
        problems.append(f"public_base_not_closed:{binding}")
    constants, constant_problems = _reference_field(
        entry,
        binding,
        "constant_dependencies",
    )
    constant_references[binding] = constants
    problems.extend(constant_problems)
    problems.extend(_owner_problems(entry, binding))
    return problems


def _reference_field(
    entry: Mapping[str, Any],
    binding: str,
    field: str,
) -> tuple[set[str], list[str]]:
    value = entry.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return set(), [f"{field}:{binding}"]
    if value != sorted(set(value)):
        return set(value), [f"{field}_order:{binding}"]
    return set(value), []


def _binding_problems(
    entry: Mapping[str, Any],
    binding: str,
    bindings: set[str],
) -> list[str]:
    problems: list[str] = []
    if binding in bindings:
        problems.append(f"duplicate_binding:{binding}")
    bindings.add(binding)
    if entry.get("canonical_binding") != binding:
        problems.append(f"non_canonical_owner:{binding}")
    stability = entry.get("lifecycle_stability")
    if stability == "deprecated":
        problems.append(f"deprecated:{binding}")
    elif stability != "draft":
        problems.append(f"lifecycle_stability:{binding}")
    group = entry.get("lifecycle_group")
    if not isinstance(group, str) or group == "compatibility":
        problems.append(f"compatibility:{binding}")
    if binding in STABLE_API_FORBIDDEN_BINDINGS:
        problems.append(f"forbidden_binding:{binding}")
    return problems


def _owner_problems(entry: Mapping[str, Any], binding: str) -> list[str]:
    shape = entry.get("shape")
    if not isinstance(shape, dict):
        return [f"shape:{binding}"]
    problems: list[str] = []
    for field in ("binding_owner", "owner"):
        owner = shape.get(field)
        if owner is not None and not _is_public_owner(owner):
            problems.append(f"internal_owner:{binding}:{field}")
    return problems


def _is_public_owner(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("pheroos.")
        and not any(part.startswith("_") for part in value.split("."))
    )


def _identity_problems(
    entry: Mapping[str, Any],
    binding: str,
    identities: dict[str, str],
) -> list[str]:
    shape = entry.get("shape")
    identity = shape.get("identity") if isinstance(shape, dict) else None
    if not isinstance(identity, str):
        return []
    duplicate = identities.get(identity)
    identities[identity] = binding
    if duplicate is None or duplicate == binding:
        return []
    return [f"canonical_owner_duplicate:{duplicate}:{binding}"]


def _missing_reference_problems(
    references: Mapping[str, set[str]],
    bindings: set[str],
) -> list[str]:
    return [
        f"closure_missing:{binding}:{missing}"
        for binding, targets in references.items()
        for missing in sorted(targets - bindings)
    ]


def _constant_dependency_index(value: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(value, list):
        return {}, ["constant_dependencies"]
    constants: dict[str, Any] = {}
    problems: list[str] = []
    for entry in value:
        binding = entry.get("binding") if isinstance(entry, dict) else None
        if not isinstance(binding, str):
            problems.append("constant_dependency:binding")
            continue
        if binding in constants:
            problems.append(f"constant_dependency_duplicate:{binding}")
        constants[binding] = entry
        problems.extend(_constant_dependency_problems(entry, binding))
    if [entry.get("binding") for entry in value if isinstance(entry, dict)] != sorted(
        constants
    ):
        problems.append("constant_dependency_order")
    return constants, problems


def _constant_dependency_problems(
    entry: Mapping[str, Any],
    binding: str,
) -> list[str]:
    problems: list[str] = []
    stability = entry.get("lifecycle_stability")
    if stability == "deprecated":
        problems.append(f"constant_deprecated:{binding}")
    elif stability != "draft":
        problems.append(f"constant_lifecycle_stability:{binding}")
    group = entry.get("lifecycle_group")
    if not isinstance(group, str) or group == "compatibility":
        problems.append(f"constant_compatibility:{binding}")
    shape = entry.get("shape")
    if not isinstance(shape, dict) or set(shape) != {
        "attribute",
        "binding_owner",
        "constant",
        "kind",
        "name",
    }:
        return [*problems, f"constant_shape:{binding}"]
    if (
        shape.get("kind") != "constant"
        or shape.get("name") != binding.rsplit(".", 1)[1]
    ):
        problems.append(f"constant_kind:{binding}")
    if not _is_public_owner(shape.get("binding_owner")):
        problems.append(f"constant_internal_owner:{binding}")
    if not isinstance(shape.get("constant"), dict):
        problems.append(f"constant_value:{binding}")
    return problems


def _missing_constant_problems(
    references: Mapping[str, set[str]],
    constants: Mapping[str, Any],
    bindings: set[str],
) -> list[str]:
    return [
        f"constant_dependency_missing:{source}:{target}"
        for source, targets in references.items()
        if source in bindings
        for target in sorted(targets - set(constants))
    ]


def _budget_problems(
    candidate: Mapping[str, Any],
    packages: Mapping[str, Any],
    roots: set[str],
    bindings: set[str],
    constants: Mapping[str, Any],
) -> list[str]:
    governance = packages["pheroos.governance"]
    counts = {
        "roots": len(roots),
        "closure": len(bindings),
        "governance_roots": governance.get("root_count"),
        "governance_closure": governance.get("closure_count"),
    }
    budgets = candidate.get("budgets")
    if not isinstance(budgets, dict):
        return ["budgets"]
    problems = [
        f"budget:{name}"
        for name, count in counts.items()
        if not isinstance(count, int)
        or not isinstance(budgets.get(name), int)
        or count > budgets[name]
    ]
    if len(roots) > STABLE_API_CURRENT_ROOT_TARGET:
        problems.append("review_target:roots")
    if candidate.get("summary") != candidate_summary(packages, constants):
        problems.append("summary")
    return problems


def _artifact_bindings(candidate: Mapping[str, Any]) -> set[str]:
    packages = candidate.get("packages")
    if not isinstance(packages, dict):
        return set()
    return {
        entry["binding"]
        for package in packages.values()
        if isinstance(package, dict)
        for entry in package.get("exports", ())
        if isinstance(entry, dict) and isinstance(entry.get("binding"), str)
    }


def _artifact_constant_bindings(candidate: Mapping[str, Any]) -> set[str]:
    constants = candidate.get("constant_dependencies")
    if not isinstance(constants, list):
        return set()
    return {
        entry["binding"]
        for entry in constants
        if isinstance(entry, dict) and isinstance(entry.get("binding"), str)
    }


def _inventory_subset(
    inventory: Mapping[str, Any],
    bindings: set[str],
) -> dict[str, Any]:
    packages = inventory.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("public ABI inventory packages must be an object")
    subset: dict[str, Any] = {}
    for package_name in PUBLIC_PACKAGES:
        package = packages.get(package_name)
        if not isinstance(package, dict) or not isinstance(
            package.get("exports"), list
        ):
            raise ValueError(f"public ABI inventory package is invalid: {package_name}")
        exports = package["exports"]
        names: set[str] = set()
        for item in exports:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise ValueError(
                    f"public ABI inventory export is invalid: {package_name}"
                )
            name = item["name"]
            if name in names:
                raise ValueError(
                    f"public ABI inventory export is duplicated: {package_name}.{name}"
                )
            names.add(name)
        subset[package_name] = {
            item["name"]: item
            for item in exports
            if f"{package_name}.{item['name']}" in bindings
        }
    return subset


__all__ = [
    "artifact_root",
    "candidate_summary",
    "promotion_candidate_differences",
    "promotion_candidate_public_inventory_differences",
    "stable_api_breaking_differences",
    "stable_api_candidate_problems",
    "stable_public_inventory_breaking_differences",
]
