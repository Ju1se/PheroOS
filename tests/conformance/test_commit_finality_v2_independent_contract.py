from __future__ import annotations

from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.conformance.checks.commit_finality_v2_contract import (
    run_governance_commit_finality_conformance_v2,
)


def test_independent_store_passes_the_same_commit_finality_v2_matrix() -> None:
    result = run_governance_commit_finality_conformance_v2(
        IndependentStdlibGovernanceStateStoreV2Adapter()
    )
    assert result.name == "commit_finality_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""
