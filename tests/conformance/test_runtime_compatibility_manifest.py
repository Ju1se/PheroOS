from __future__ import annotations

from dataclasses import replace
import json
from hashlib import sha256
from pathlib import Path
import pickle
import subprocess
import sys

import pytest

import pheroos.conformance.runtime_compatibility as runtime_compatibility
from pheroos.conformance.runtime_compatibility import (
    RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1,
    RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1,
    RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1,
    RuntimeCompatibilityClaimV1,
    RuntimeCompatibilityCapabilitySpecV1,
    RuntimeCompatibilityComponentClaimV1,
    RuntimeCompatibilityDiagnosticCodeV1,
    RuntimeCompatibilityErrorV1,
    RuntimeCompatibilityManifestV1,
    RuntimeCompatibilityProfileSpecV1,
    RuntimeCompatibilityRequirementV1,
    build_runtime_compatibility_manifest_v1,
    create_runtime_compatibility_claim_v1,
    evaluate_runtime_compatibility_v1,
    load_runtime_compatibility_manifest_v1,
    runtime_compatibility_artifact_digest_v1,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "pheroos/conformance/abi/runtime-compatibility-v1.json"

EXPECTED_REQUIRED_COMPONENTS = {
    "conformance.abi.public-python-api",
    "conformance.abi.public-python-api.digest",
    "conformance.report",
    "conformance.tck.driver-invocation-store",
    "conformance.tck.governance-baseline-output",
    "conformance.tck.governance-state-store",
    "conformance.tck.scoped-trace-store",
    "conformance.tck.runtime-integration",
    "drivers.invocation.checkpoint",
    "drivers.invocation.receipt",
    "drivers.invocation.reply",
    "drivers.invocation.request",
    "drivers.invocation.result",
    "drivers.invocation.store",
    "governance.baseline-output.request",
    "governance.baseline-output.result",
    "governance.state-store",
    "kernel.plan",
    "kernel.runtime-scope",
    "kernel.runtime-scope.schema",
    "protocol.authority-canonical",
    "protocol.baseline-output-policy",
    "protocol.capability.schema",
    "protocol.manifest",
    "protocol.manifest.schema",
    "trace.scoped-event",
    "trace.scoped-store",
    "trace.scoped-store.checkpoint",
    "trace.scoped-store.record",
}
EXPECTED_OPTIONAL_PROFILES = {
    "certified-commit",
    "commit-integrity",
    "core",
    "distributed-commit",
    "hybrid-commit",
}
EXPECTED_OPTIONAL_CAPABILITIES = {
    "governance-authority-session-v2",
    "governance-commit-certificate-v2",
    "governance-commit-decision-v2",
    "governance-commit-evidence-v2",
    "governance-commit-finality-v2",
    "governance-commit-gate-v2",
    "governance-commit-replay-v2",
    "governance-distributed-commit-v2",
    "governance-hybrid-replay-v2",
    "governance-risk-v2",
    "governance-support-v2",
}
EXPECTED_PUBLIC_EXPORTS = {
    "RUNTIME_BASELINE_PROFILE_VERSION_V1",
    "RUNTIME_COMPATIBILITY_ARTIFACT_V1",
    "RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1",
    "RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1",
    "RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1",
    "RUNTIME_COMPATIBILITY_REPORT_VERSION_V1",
    "RuntimeCompatibilityCapabilitySpecV1",
    "RuntimeCompatibilityClaimV1",
    "RuntimeCompatibilityComponentClaimV1",
    "RuntimeCompatibilityDiagnosticCodeV1",
    "RuntimeCompatibilityDiagnosticV1",
    "RuntimeCompatibilityErrorV1",
    "RuntimeCompatibilityManifestV1",
    "RuntimeCompatibilityProfileSpecV1",
    "RuntimeCompatibilityReportV1",
    "RuntimeCompatibilityRequirementV1",
    "RuntimeCompatibilityStatusV1",
    "build_runtime_compatibility_manifest_v1",
    "create_runtime_compatibility_claim_v1",
    "evaluate_runtime_compatibility_v1",
    "load_runtime_compatibility_manifest_v1",
    "runtime_compatibility_artifact_digest_v1",
}


def _required_versions(
    manifest: RuntimeCompatibilityManifestV1,
) -> dict[str, str]:
    return {
        item.component_id: item.version_id
        for item in manifest.required_profile.requirements
    }


def _option_versions(
    manifest: RuntimeCompatibilityManifestV1,
    *,
    profile: str | None = None,
    capability: str | None = None,
) -> dict[str, str]:
    selected: RuntimeCompatibilityProfileSpecV1 | RuntimeCompatibilityCapabilitySpecV1
    if profile is not None:
        selected = next(
            item for item in manifest.optional_profiles if item.profile_id == profile
        )
    else:
        selected = next(
            item
            for item in manifest.optional_capabilities
            if item.capability_id == capability
        )
    return {item.component_id: item.version_id for item in selected.requirements}


def test_public_facade_has_one_canonical_draft_surface() -> None:
    assert set(runtime_compatibility.__all__) == EXPECTED_PUBLIC_EXPORTS
    assert len(runtime_compatibility.__all__) == len(EXPECTED_PUBLIC_EXPORTS)
    for name in EXPECTED_PUBLIC_EXPORTS:
        value = getattr(runtime_compatibility, name)
        if isinstance(value, type) or callable(value):
            assert value.__module__ == "pheroos.conformance.runtime_compatibility"

    manifest = build_runtime_compatibility_manifest_v1()
    assert pickle.loads(pickle.dumps(manifest)) == manifest


def test_checked_manifest_is_exact_canonical_package_artifact() -> None:
    built = build_runtime_compatibility_manifest_v1()
    loaded = load_runtime_compatibility_manifest_v1()

    assert loaded == built
    assert ARTIFACT.read_bytes() == built.canonical_bytes()
    assert RuntimeCompatibilityManifestV1.from_wire(ARTIFACT.read_bytes()) == built
    assert built.manifest_version == RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1
    assert built.manifest_root.startswith("sha256:")
    assert built.artifact_digest == (
        "sha256:" + sha256(ARTIFACT.read_bytes()).hexdigest()
    )
    assert runtime_compatibility_artifact_digest_v1() == built.artifact_digest


def test_catalog_is_baseline_required_and_advanced_profiles_are_opt_in() -> None:
    manifest = build_runtime_compatibility_manifest_v1()

    assert manifest.required_profile.profile_id == "scoped-baseline"
    assert set(_required_versions(manifest)) == EXPECTED_REQUIRED_COMPONENTS
    assert {item.profile_id for item in manifest.optional_profiles} == (
        EXPECTED_OPTIONAL_PROFILES
    )
    assert {item.capability_id for item in manifest.optional_capabilities} == (
        EXPECTED_OPTIONAL_CAPABILITIES
    )
    assert "0.1.0" not in manifest.canonical_bytes().decode()
    assert "reserved" not in manifest.canonical_bytes().decode()
    assert "stable" not in manifest.required_profile.profile_version.lower()


def test_baseline_exact_claim_does_not_require_hybrid_or_commit_profiles() -> None:
    manifest = build_runtime_compatibility_manifest_v1()
    claim = create_runtime_compatibility_claim_v1(_required_versions(manifest))

    report = evaluate_runtime_compatibility_v1(manifest, claim)

    assert report.ok is True
    assert report.status.value == "compatible"
    assert report.diagnostics == ()
    assert report.selected_optional_profiles == ()
    assert report.selected_optional_capabilities == ()


@pytest.mark.parametrize("profile_id", ["hybrid-commit"])
def test_optional_profile_is_checked_only_after_explicit_selection(
    profile_id: str,
) -> None:
    manifest = build_runtime_compatibility_manifest_v1()
    versions = _required_versions(manifest)
    unselected_versions = dict(versions)
    unselected_versions.update(
        {
            component_id: "unselected-profile-version-v999"
            for component_id in _option_versions(manifest, profile=profile_id)
        }
    )
    assert evaluate_runtime_compatibility_v1(
        manifest,
        create_runtime_compatibility_claim_v1(unselected_versions),
    ).ok
    missing = create_runtime_compatibility_claim_v1(
        versions,
        required_optional_profiles=(profile_id,),
    )

    missing_report = evaluate_runtime_compatibility_v1(manifest, missing)
    assert missing_report.ok is False
    assert {item.code for item in missing_report.diagnostics} == {
        RuntimeCompatibilityDiagnosticCodeV1.MISSING_COMPONENT
    }

    versions.update(_option_versions(manifest, profile=profile_id))
    exact = create_runtime_compatibility_claim_v1(
        versions,
        required_optional_profiles=(profile_id,),
    )
    assert evaluate_runtime_compatibility_v1(manifest, exact).ok is True


def test_standalone_tck_capability_is_not_mislabeled_as_a_manifest_profile() -> None:
    manifest = build_runtime_compatibility_manifest_v1()
    capability_id = "governance-commit-finality-v2"

    assert capability_id not in {item.profile_id for item in manifest.optional_profiles}
    missing = create_runtime_compatibility_claim_v1(
        _required_versions(manifest),
        required_optional_capabilities=(capability_id,),
    )
    assert evaluate_runtime_compatibility_v1(manifest, missing).ok is False

    versions = _required_versions(manifest)
    versions.update(_option_versions(manifest, capability=capability_id))
    exact = create_runtime_compatibility_claim_v1(
        versions,
        required_optional_capabilities=(capability_id,),
    )
    assert evaluate_runtime_compatibility_v1(manifest, exact).ok is True


def test_missing_mismatch_unknown_critical_and_noncritical_extra_are_typed() -> None:
    manifest = build_runtime_compatibility_manifest_v1()
    versions = _required_versions(manifest)
    missing_id = "kernel.plan"
    versions.pop(missing_id)
    versions["protocol.manifest"] = "pheroos.protocol.v999"
    versions["vendor.extension"] = "vendor-extension-v1"
    critical = create_runtime_compatibility_claim_v1(
        versions,
        critical_components=("vendor.extension",),
    )

    critical_report = evaluate_runtime_compatibility_v1(manifest, critical)
    assert critical_report.ok is False
    assert {(item.code, item.subject) for item in critical_report.diagnostics} == {
        (RuntimeCompatibilityDiagnosticCodeV1.MISSING_COMPONENT, missing_id),
        (
            RuntimeCompatibilityDiagnosticCodeV1.VERSION_MISMATCH,
            "protocol.manifest",
        ),
        (
            RuntimeCompatibilityDiagnosticCodeV1.UNKNOWN_CRITICAL_COMPONENT,
            "vendor.extension",
        ),
    }

    exact = _required_versions(manifest)
    exact["vendor.extension"] = "vendor-extension-v1"
    noncritical = create_runtime_compatibility_claim_v1(exact)
    noncritical_report = evaluate_runtime_compatibility_v1(manifest, noncritical)
    assert noncritical_report.ok is True
    assert [item.code for item in noncritical_report.diagnostics] == [
        RuntimeCompatibilityDiagnosticCodeV1.EXTRA_NONCRITICAL_COMPONENT
    ]


def test_same_inventory_format_version_with_different_shape_digest_fails() -> None:
    manifest = build_runtime_compatibility_manifest_v1()
    versions = _required_versions(manifest)
    assert versions["conformance.abi.public-python-api"] == (
        "pheroos-public-python-api-v1"
    )
    versions["conformance.abi.public-python-api.digest"] = "sha256:" + "0" * 64

    report = evaluate_runtime_compatibility_v1(
        manifest,
        create_runtime_compatibility_claim_v1(versions),
    )

    assert report.ok is False
    assert [(item.code, item.subject) for item in report.diagnostics] == [
        (
            RuntimeCompatibilityDiagnosticCodeV1.VERSION_MISMATCH,
            "conformance.abi.public-python-api.digest",
        )
    ]


def test_unknown_optional_selections_fail_without_semver_or_fallback() -> None:
    manifest = build_runtime_compatibility_manifest_v1()
    claim = create_runtime_compatibility_claim_v1(
        _required_versions(manifest),
        required_optional_profiles=("future-profile",),
        required_optional_capabilities=("future-capability",),
    )

    report = evaluate_runtime_compatibility_v1(manifest, claim)

    assert report.ok is False
    assert {item.code for item in report.diagnostics} == {
        RuntimeCompatibilityDiagnosticCodeV1.UNKNOWN_OPTIONAL_PROFILE,
        RuntimeCompatibilityDiagnosticCodeV1.UNKNOWN_OPTIONAL_CAPABILITY,
    }


def test_claim_wire_round_trip_and_root_are_exact() -> None:
    manifest = build_runtime_compatibility_manifest_v1()
    claim = create_runtime_compatibility_claim_v1(_required_versions(manifest))

    assert claim.claim_version == RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1
    assert RuntimeCompatibilityClaimV1.from_wire(claim.canonical_bytes()) == claim
    assert claim.artifact_digest.startswith("sha256:")
    assert len(claim.artifact_digest) == 71


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.update({"unknown": "field"}),
        lambda value: value.update(
            {"manifest_version": "pheroos-runtime-compatibility-manifest-v999"}
        ),
        lambda value: value.update({"manifest_root": "sha256:" + "0" * 64}),
        lambda value: value["required_profile"].update(
            {"profile_id": "scoped-baseline\x00forged"}
        ),
        lambda value: value["required_profile"].update(
            {"profile_id": "scope\u0301d-baseline"}
        ),
        lambda value: value["required_profile"]["requirements"].reverse(),
    ],
)
def test_manifest_mutations_fail_closed(mutator: object) -> None:
    payload = build_runtime_compatibility_manifest_v1().to_dict()
    assert callable(mutator)
    mutator(payload)
    wire = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

    with pytest.raises(RuntimeCompatibilityErrorV1):
        RuntimeCompatibilityManifestV1.from_wire(wire)


def test_strict_loader_rejects_duplicate_nonfinite_noncanonical_and_oversize() -> None:
    canonical = build_runtime_compatibility_manifest_v1().canonical_bytes()
    duplicate = canonical[:-1] + b',"manifest_version":"duplicate"}'
    nonfinite = canonical[:-1] + b',"unknown":NaN}'
    pretty = json.dumps(json.loads(canonical), indent=2).encode()

    for wire in (
        duplicate,
        nonfinite,
        pretty,
        canonical + b"\n",
        b"{" + b" " * RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1 + b"}",
    ):
        with pytest.raises(RuntimeCompatibilityErrorV1):
            RuntimeCompatibilityManifestV1.from_wire(wire)


def test_direct_contracts_reject_duplicate_unsorted_and_bool_as_int() -> None:
    requirement_a = RuntimeCompatibilityRequirementV1("a", "v1")
    requirement_b = RuntimeCompatibilityRequirementV1("b", "v1")
    with pytest.raises(RuntimeCompatibilityErrorV1, match="deterministic"):
        RuntimeCompatibilityProfileSpecV1(
            "profile", "v1", (requirement_b, requirement_a)
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="duplicate"):
        RuntimeCompatibilityProfileSpecV1(
            "profile", "v1", (requirement_a, requirement_a)
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="boolean"):
        RuntimeCompatibilityComponentClaimV1("component", "v1", 1)  # type: ignore[arg-type]


def test_claim_wrong_version_root_and_duplicate_component_fail_closed() -> None:
    manifest = build_runtime_compatibility_manifest_v1()
    claim = create_runtime_compatibility_claim_v1(_required_versions(manifest))

    with pytest.raises(RuntimeCompatibilityErrorV1, match="unsupported"):
        replace(claim, claim_version="pheroos-runtime-compatibility-claim-v999")
    with pytest.raises(RuntimeCompatibilityErrorV1, match="root"):
        replace(claim, claim_root="sha256:" + "0" * 64)
    with pytest.raises(RuntimeCompatibilityErrorV1, match="duplicate"):
        RuntimeCompatibilityClaimV1(components=(claim.components[0],) * 2)


@pytest.mark.parametrize(
    ("loader", "payload", "detail"),
    [
        (
            RuntimeCompatibilityRequirementV1.from_dict,
            {"component_id": "component"},
            "requirement fields",
        ),
        (
            RuntimeCompatibilityProfileSpecV1.from_dict,
            {
                "profile_id": "profile",
                "profile_version": "v1",
                "requirements": [],
                "extra": True,
            },
            "profile fields",
        ),
        (
            RuntimeCompatibilityProfileSpecV1.from_dict,
            {
                "profile_id": "profile",
                "profile_version": "v1",
                "requirements": (),
            },
            "requirements must be an array",
        ),
        (
            RuntimeCompatibilityCapabilitySpecV1.from_dict,
            {"capability_id": "capability"},
            "capability fields",
        ),
        (
            RuntimeCompatibilityCapabilitySpecV1.from_dict,
            {"capability_id": "capability", "requirements": ()},
            "requirements must be an array",
        ),
        (
            RuntimeCompatibilityComponentClaimV1.from_dict,
            {"component_id": "component", "version_id": "v1"},
            "component claim fields",
        ),
        (
            RuntimeCompatibilityManifestV1.from_dict,
            {"manifest_version": RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1},
            "manifest fields",
        ),
        (
            RuntimeCompatibilityManifestV1.from_dict,
            {
                **build_runtime_compatibility_manifest_v1().to_dict(),
                "optional_profiles": (),
            },
            "option declarations must be arrays",
        ),
        (
            RuntimeCompatibilityClaimV1.from_dict,
            {"claim_version": RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1},
            "claim fields",
        ),
        (
            RuntimeCompatibilityClaimV1.from_dict,
            {
                **create_runtime_compatibility_claim_v1(
                    _required_versions(build_runtime_compatibility_manifest_v1())
                ).to_dict(),
                "components": (),
            },
            "claim collections must be arrays",
        ),
    ],
)
def test_nested_contract_loaders_reject_wrong_shapes(
    loader: object,
    payload: object,
    detail: str,
) -> None:
    assert callable(loader)
    with pytest.raises(RuntimeCompatibilityErrorV1, match=detail):
        loader(payload)


def test_manifest_declaration_bounds_and_namespace_fail_closed() -> None:
    requirement_a = RuntimeCompatibilityRequirementV1("a", "v1")
    requirement_b = RuntimeCompatibilityRequirementV1("b", "v1")
    profile_a = RuntimeCompatibilityProfileSpecV1("a-profile", "v1", (requirement_a,))
    profile_b = RuntimeCompatibilityProfileSpecV1("b-profile", "v1", (requirement_b,))
    capability = RuntimeCompatibilityCapabilitySpecV1(
        "capability", (RuntimeCompatibilityRequirementV1("c", "v1"),)
    )

    with pytest.raises(RuntimeCompatibilityErrorV1, match="1..256"):
        RuntimeCompatibilityProfileSpecV1("empty", "v1", ())
    with pytest.raises(RuntimeCompatibilityErrorV1, match="exact"):
        RuntimeCompatibilityProfileSpecV1(
            "wrong-item",
            "v1",
            (object(),),  # type: ignore[arg-type]
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="required profile"):
        RuntimeCompatibilityManifestV1(
            required_profile=object(),  # type: ignore[arg-type]
            optional_profiles=(profile_a,),
            optional_capabilities=(capability,),
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="1..32"):
        RuntimeCompatibilityManifestV1(
            required_profile=profile_a,
            optional_profiles=(),
            optional_capabilities=(capability,),
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="invalid entry"):
        RuntimeCompatibilityManifestV1(
            required_profile=profile_a,
            optional_profiles=(object(),),  # type: ignore[arg-type]
            optional_capabilities=(capability,),
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="duplicate identities"):
        RuntimeCompatibilityManifestV1(
            required_profile=profile_b,
            optional_profiles=(profile_a, profile_a),
            optional_capabilities=(capability,),
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="identity order"):
        RuntimeCompatibilityManifestV1(
            required_profile=profile_a,
            optional_profiles=(profile_b, profile_a),
            optional_capabilities=(capability,),
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="one declared owner"):
        RuntimeCompatibilityManifestV1(
            required_profile=profile_a,
            optional_profiles=(
                RuntimeCompatibilityProfileSpecV1(
                    "optional",
                    "v1",
                    (requirement_a,),
                ),
            ),
            optional_capabilities=(capability,),
        )


def test_claim_selection_and_component_bounds_fail_closed() -> None:
    component_a = RuntimeCompatibilityComponentClaimV1("a", "v1", False)
    component_b = RuntimeCompatibilityComponentClaimV1("b", "v1", False)

    with pytest.raises(RuntimeCompatibilityErrorV1, match="bounded components"):
        RuntimeCompatibilityClaimV1(components=())
    with pytest.raises(RuntimeCompatibilityErrorV1, match="components are invalid"):
        RuntimeCompatibilityClaimV1(
            components=(object(),),  # type: ignore[arg-type]
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="must be sorted"):
        RuntimeCompatibilityClaimV1(components=(component_b, component_a))
    with pytest.raises(RuntimeCompatibilityErrorV1, match="selection bound"):
        RuntimeCompatibilityClaimV1(
            components=(component_a,),
            required_optional_profiles=tuple(
                f"profile-{index:03d}" for index in range(129)
            ),
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="duplicates"):
        RuntimeCompatibilityClaimV1(
            components=(component_a,),
            required_optional_profiles=("profile", "profile"),
        )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="identity order"):
        RuntimeCompatibilityClaimV1(
            components=(component_a,),
            required_optional_capabilities=("z-capability", "a-capability"),
        )


def test_manifest_and_claim_construction_enforce_wire_size_bound() -> None:
    huge_requirements = tuple(
        RuntimeCompatibilityRequirementV1(
            f"{index:03d}-" + "c" * 500,
            "v" * 512,
        )
        for index in range(256)
    )
    required = RuntimeCompatibilityProfileSpecV1(
        "huge-profile",
        "v1",
        huge_requirements,
    )
    optional_profile = RuntimeCompatibilityProfileSpecV1(
        "optional",
        "v1",
        (RuntimeCompatibilityRequirementV1("optional-component", "v1"),),
    )
    optional_capability = RuntimeCompatibilityCapabilitySpecV1(
        "capability",
        (RuntimeCompatibilityRequirementV1("capability-component", "v1"),),
    )

    with pytest.raises(RuntimeCompatibilityErrorV1, match="manifest exceeds"):
        RuntimeCompatibilityManifestV1(
            required_profile=required,
            optional_profiles=(optional_profile,),
            optional_capabilities=(optional_capability,),
        )

    components = tuple(
        RuntimeCompatibilityComponentClaimV1(
            f"{index:03d}-" + "c" * 500,
            "v" * 512,
            False,
        )
        for index in range(256)
    )
    with pytest.raises(RuntimeCompatibilityErrorV1, match="claim exceeds"):
        RuntimeCompatibilityClaimV1(components=components)


def test_claim_wire_rejects_noncanonical_but_semantically_equal_json() -> None:
    manifest = build_runtime_compatibility_manifest_v1()
    claim = create_runtime_compatibility_claim_v1(_required_versions(manifest))
    pretty = json.dumps(claim.to_dict(), indent=2).encode()

    with pytest.raises(RuntimeCompatibilityErrorV1, match="not canonical"):
        RuntimeCompatibilityClaimV1.from_wire(pretty)


def test_generator_check_detects_no_artifact_drift() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/generate_runtime_compatibility_manifest.py"),
            "--check",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (
        f"root={build_runtime_compatibility_manifest_v1().manifest_root}"
        in completed.stdout
    )
