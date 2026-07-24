from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.commit_decision_v2_contract import (
    GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2,
    run_governance_commit_decision_conformance_v2,
)
from pheroos.governance import AuthorityDomainV2


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "pheroos/conformance/checks/commit_decision_v2_contract.py"
SUPPORT = ROOT / "pheroos/conformance/checks/_commit_decision_v2_context_support.py"


def test_commit_decision_v2_conformance_version_is_exact() -> None:
    assert GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2 == (
        "pheroos-governance-commit-decision-conformance-v2"
    )


def test_reference_store_passes_the_full_commit_decision_v2_matrix() -> None:
    result = run_governance_commit_decision_conformance_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2()
    )
    assert result.name == "commit_decision_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_independent_store_passes_the_same_commit_decision_v2_matrix() -> None:
    result = run_governance_commit_decision_conformance_v2(
        IndependentStdlibGovernanceStateStoreV2Adapter()
    )
    assert result.name == "commit_decision_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_commit_decision_v2_matrix_rejects_bad_adapters() -> None:
    class Incomplete:
        implementation_id = "incomplete"

    incomplete = cast(GovernanceStateStoreConformanceAdapterV2, Incomplete())
    assert run_governance_commit_decision_conformance_v2(incomplete).detail == (
        "adapter_protocol"
    )

    class UnknownVersion(IndependentStdlibGovernanceStateStoreV2Adapter):
        conformance_version = "pheroos-governance-state-store-v999"

    assert (
        run_governance_commit_decision_conformance_v2(UnknownVersion()).detail
        == "adapter_version"
    )


def test_commit_decision_v2_matrix_totalizes_adapter_boundary_failures() -> None:
    class BlankImplementation(ReferenceGovernanceStateStoreConformanceAdapterV2):
        implementation_id = ""

    class ExplodingIdentity(ReferenceGovernanceStateStoreConformanceAdapterV2):
        @property
        def implementation_id(self) -> str:
            raise OSError("identity unavailable")

    class ExplodingDomain(ReferenceGovernanceStateStoreConformanceAdapterV2):
        def create_domain_v2(self, scope_ref: str) -> AuthorityDomainV2:
            raise OSError("domain unavailable")

    assert (
        run_governance_commit_decision_conformance_v2(BlankImplementation()).detail
        == "adapter_implementation_id"
    )
    assert (
        run_governance_commit_decision_conformance_v2(ExplodingIdentity()).detail
        == "adapter_exception:OSError"
    )
    result = run_governance_commit_decision_conformance_v2(ExplodingDomain())
    assert not result.ok
    assert result.detail == "adapter_exception:OSError:domain unavailable"


def test_production_matrix_and_fixture_import_only_public_governance() -> None:
    for path in (CONTRACT, SUPPORT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module)
        assert not any(item.startswith("pheroos.governance._") for item in imports), (
            path
        )
        assert not any(item.startswith("tests.") for item in imports), path


def test_matrix_covers_the_real_durable_journeys() -> None:
    source = CONTRACT.read_text(encoding="utf-8")
    for invariant in (
        "bounded_missing_progress",
        "missing_deadline_typed_terminal",
        "same_process_exact_retry",
        "restart_lost_response_exact_retry",
        "decision_parent_cas_race",
        "ready_window",
        "same_step_seal_commit",
        "evidence_finality_commit",
        "ready_typed_terminal",
        "terminal_restart_currentness",
        "commit_decision_outcome_committed_v2",
    ):
        assert invariant in source


def test_commit_decision_v2_conformance_files_stay_locally_small() -> None:
    assert len(CONTRACT.read_text(encoding="utf-8").splitlines()) < 600
    assert len(SUPPORT.read_text(encoding="utf-8").splitlines()) < 600
