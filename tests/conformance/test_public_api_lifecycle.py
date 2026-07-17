from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from pathlib import Path

from pheroos.conformance._public_api import (
    COMPATIBILITY_MODULES as CONFORMANCE_COMPATIBILITY_MODULES,
)
from pheroos.conformance.public_api_lifecycle import (
    DEFAULT_REMOVE_AFTER,
    PUBLIC_API_GROUPS,
    PUBLIC_API_LIFECYCLE_PATH,
    PUBLIC_API_STABILITIES,
    build_public_api_lifecycle,
    load_public_api_lifecycle,
    public_api_lifecycle_problems,
)
from pheroos.conformance.public_api_inventory import PUBLIC_PACKAGES


ROOT = Path(__file__).resolve().parents[2]


def _entries(lifecycle: dict[str, object], package: str) -> dict[str, dict[str, object]]:
    packages = lifecycle["packages"]
    assert isinstance(packages, dict)
    package_lifecycle = packages[package]
    assert isinstance(package_lifecycle, dict)
    exports = package_lifecycle["exports"]
    assert isinstance(exports, list)
    return {item["name"]: item for item in exports}


def test_checked_lifecycle_matches_every_export_and_has_no_orphans() -> None:
    expected = load_public_api_lifecycle(ROOT)

    assert expected == build_public_api_lifecycle(ROOT)
    assert public_api_lifecycle_problems(expected) == []
    assert set(expected["packages"]) == set(PUBLIC_PACKAGES)
    for package_name in PUBLIC_PACKAGES:
        module = import_module(package_name)
        entries = _entries(expected, package_name)
        assert set(entries) == set(module.__all__)
        assert all(item["package"] == package_name for item in entries.values())
        assert all(item["group"] in PUBLIC_API_GROUPS for item in entries.values())
        assert all(
            item["stability"] in PUBLIC_API_STABILITIES
            for item in entries.values()
        )
        assert all(item["since"] == "0.1.0" for item in entries.values())


def test_removal_ledger_marks_d07_through_d14_without_deprecating_valid_entrypoint() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    driver = _entries(lifecycle, "pheroos.drivers")
    governance = _entries(lifecycle, "pheroos.governance")
    conformance = _entries(lifecycle, "pheroos.conformance")

    for name in (
        "DataProviderDriverDescriptor",
        "ModelDriverDescriptor",
        "SandboxDriverDescriptor",
        "StorageDriverDescriptor",
        "ToolDriverDescriptor",
    ):
        assert driver[name]["stability"] == "deprecated"
        assert driver[name]["replacement"] == "pheroos.drivers.DriverDescriptor"
        assert driver[name]["remove_after"] == DEFAULT_REMOVE_AFTER
    assert driver["DriverHealth"]["replacement"] == (
        "pheroos.drivers.DriverProbeResult"
    )
    assert governance["CanonicalTarget"]["replacement"] == (
        "pheroos.protocol.TargetSpec"
    )
    assert governance["RecoveryTrace"]["replacement"] == (
        "pheroos.trace.TraceEvent"
    )
    assert governance["evaluate_hybrid_commit_evaluation"]["replacement"] == (
        "pheroos.governance.evaluate_hybrid_commit_step"
    )
    for name in (
        "canonical_commit_payload",
        "canonical_commit_set",
        "commit_payload_fingerprint",
    ):
        assert governance[name]["replacement"] == f"pheroos.protocol.{name}"

    run = conformance["run_conformance"]
    assert run["stability"] == "draft"
    assert run["remove_after"] is None
    assert run["replacement"] is None
    assert run["parameter_lifecycle"] == [
        {
            "name": "root",
            "stability": "deprecated",
            "replacement": "pheroos.conformance.run_source_conformance",
            "remove_after": DEFAULT_REMOVE_AFTER,
        }
    ]

    compatibility = {
        (item["package"], item["name"]): item
        for item in lifecycle["compatibility_surfaces"]
    }
    trace = compatibility[("pheroos.governance", "trace")]
    assert trace["stability"] == "deprecated"
    assert trace["replacement"] == "pheroos.trace"
    assert trace["remove_after"] == DEFAULT_REMOVE_AFTER

    conformance_compatibility = {
        name: item
        for (package, name), item in compatibility.items()
        if package == "pheroos.conformance"
    }
    assert set(conformance_compatibility) == {
        "checks",
        "commit_tck",
        "commit_tck_v2_protocol",
        "profile",
        "public_api_inventory",
        "public_api_lifecycle",
        "report",
        "runner",
    }
    assert set(conformance_compatibility) == set(
        CONFORMANCE_COMPATIBILITY_MODULES
    )
    for name, target in CONFORMANCE_COMPATIBILITY_MODULES.items():
        entry = conformance_compatibility[name]
        assert entry["replacement"] == target
        assert entry["stability"] == "draft"
        assert entry["remove_after"] is None


def test_lifecycle_rejects_missing_and_orphan_compatibility_surfaces() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    malformed = deepcopy(lifecycle)
    surfaces = malformed["compatibility_surfaces"]
    surfaces[:] = [
        item
        for item in surfaces
        if (item["package"], item["name"])
        != ("pheroos.conformance", "checks")
    ]
    surfaces.append(
        {
            "group": "compatibility",
            "name": "not_a_module",
            "package": "pheroos.conformance",
            "remove_after": None,
            "replacement": "pheroos.conformance.not_a_module",
            "retained_with_reason": "test-only orphan",
            "since": "0.1.0",
            "stability": "draft",
        }
    )

    problems = public_api_lifecycle_problems(malformed)

    assert (
        "compatibility_surfaces:missing:pheroos.conformance:checks"
        in problems
    )
    assert (
        "compatibility_surfaces:orphan:pheroos.conformance:not_a_module"
        in problems
    )


def test_lifecycle_rejects_missing_orphan_and_nonreferencable_replacement() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    malformed = deepcopy(lifecycle)
    protocol = malformed["packages"]["pheroos.protocol"]
    removed = protocol["exports"].pop()
    protocol["exports"].append(
        {
            **removed,
            "name": "NoSuchExport",
            "stability": "deprecated",
            "replacement": "pheroos.protocol.NoSuchReplacement",
            "remove_after": DEFAULT_REMOVE_AFTER,
        }
    )

    problems = public_api_lifecycle_problems(malformed)

    assert any(item.startswith("package:pheroos.protocol:missing:") for item in problems)
    assert "package:pheroos.protocol:orphan:NoSuchExport" in problems
    assert (
        "entry:pheroos.protocol.NoSuchExport:replacement" in problems
    )


def test_lifecycle_checks_public_error_types_and_diagnostic_code_registry() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    diagnostics = {
        (item["package"], item["family"], item["code"], item["kind"])
        for item in lifecycle["diagnostic_codes"]
    }

    assert (
        "pheroos.protocol",
        "manifest-validation",
        "protocol_version_unsupported",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.kernel",
        "kernel-planning",
        "driver_probe_missing",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.protocol",
        "schema-document",
        "capability_schema_version_missing",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.protocol",
        "schema-document",
        "protocol_schema_version_unsupported",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.drivers",
        "driver-schema-document",
        "driver_descriptor_v1_not_migratable",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.drivers",
        "driver-schema-document",
        "driver_descriptor_version_missing",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.kernel",
        "kernel-plan-document",
        "kernel_plan_v1_driver_authority_missing",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.kernel",
        "kernel-plan-document",
        "kernel_plan_version_unsupported",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.kernel",
        "kernel-planning",
        "manifest_*",
        "prefix",
    ) in diagnostics
    assert (
        "pheroos.governance",
        "hybrid-commit-evaluation",
        "invalid_evaluation_request",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.governance",
        "atomic-hybrid-commit",
        "governance_transition_committed",
        "exact",
    ) in diagnostics

    error_types = {
        (item["package"], item["name"]) for item in lifecycle["error_types"]
    }
    assert ("pheroos.protocol", "CommitWireError") in error_types
    assert ("pheroos.protocol", "ProtocolSchemaVersionError") in error_types
    assert ("pheroos.drivers", "DriverSchemaVersionError") in error_types
    assert ("pheroos.kernel", "KernelPlanVersionError") in error_types
    assert PUBLIC_API_LIFECYCLE_PATH.parts[:3] == (
        "pheroos",
        "conformance",
        "abi",
    )
