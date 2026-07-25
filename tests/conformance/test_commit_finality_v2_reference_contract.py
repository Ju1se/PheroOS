from __future__ import annotations

from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.commit_finality_v2_contract import (
    run_governance_commit_finality_conformance_v2,
)


def test_reference_store_passes_the_commit_finality_v2_matrix() -> None:
    result = run_governance_commit_finality_conformance_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2()
    )
    assert result.name == "commit_finality_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""
