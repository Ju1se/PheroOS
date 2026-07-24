from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

from pheroos.conformance.checks.commit_certificate_v2_contract import (
    GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2,
    CommitCertificateConformanceAdapterV2,
    IndependentStdlibCommitCertificateConformanceAdapterV2,
    ReferenceCommitCertificateConformanceAdapterV2,
    run_governance_commit_certificate_conformance_v2,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "pheroos/conformance/checks/commit_certificate_v2_contract.py"


def test_commit_certificate_v2_conformance_version_is_exact() -> None:
    assert GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2 == (
        "pheroos-governance-commit-certificate-conformance-v2"
    )


def test_reference_verifier_passes_commit_certificate_v2_matrix() -> None:
    result = run_governance_commit_certificate_conformance_v2(
        ReferenceCommitCertificateConformanceAdapterV2()
    )
    assert result.name == "commit_certificate_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_independent_stdlib_verifier_passes_the_same_matrix() -> None:
    result = run_governance_commit_certificate_conformance_v2(
        IndependentStdlibCommitCertificateConformanceAdapterV2()
    )
    assert result.name == "commit_certificate_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_matrix_rejects_incomplete_and_unknown_adapters() -> None:
    class Incomplete:
        implementation_id = "incomplete"

    incomplete = cast(CommitCertificateConformanceAdapterV2, Incomplete())
    assert run_governance_commit_certificate_conformance_v2(incomplete).detail == (
        "adapter_protocol"
    )

    class UnknownVersion(IndependentStdlibCommitCertificateConformanceAdapterV2):
        conformance_version = "pheroos-certificate-conformance-v999"

    assert (
        run_governance_commit_certificate_conformance_v2(UnknownVersion()).detail
        == "adapter_version"
    )


def test_matrix_imports_only_public_governance_surfaces() -> None:
    source = CONTRACT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    assert not any(item.startswith("pheroos.governance._") for item in imports)
    assert not any(item.startswith("tests.") for item in imports)


def test_matrix_is_explicitly_portable_and_does_not_claim_store_ownership() -> None:
    source = CONTRACT.read_text(encoding="utf-8")
    assert source.startswith(
        '"""Public-only portable Commit Certificate v2 conformance matrix.'
    )
    assert "GovernanceStateStoreV2" not in source
    assert "rehydrate_commit_certificate_state_v2" not in source


def test_matrix_covers_independent_verification_and_each_truth_layer() -> None:
    source = CONTRACT.read_text(encoding="utf-8")
    for required in (
        "canonical_round_trip",
        "body_mutation",
        "authority_leaf_mutation",
        "envelope_mutation",
        "unknown_envelope_field",
        "boolean_integer_substitution",
        "expected_context_binding",
        "raw_mapping_as_authority",
        "ReferenceCommitCertificateConformanceAdapterV2",
        "IndependentStdlibCommitCertificateConformanceAdapterV2",
    ):
        assert required in source


def test_commit_certificate_v2_conformance_module_stays_below_limit() -> None:
    assert len(CONTRACT.read_text(encoding="utf-8").splitlines()) < 600
