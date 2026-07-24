from __future__ import annotations

from pathlib import Path

from pheroos.conformance import (
    GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
    run_governance_commit_replay_conformance_v2,
)
from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2Adapter,
)


def test_commit_replay_v2_conformance_version_is_exact() -> None:
    assert GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2 == (
        "pheroos-governance-commit-replay-conformance-v2"
    )


def test_reference_commit_replay_v2_matrix_passes() -> None:
    result = run_governance_commit_replay_conformance_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2()
    )
    assert result.ok, result.detail


def test_independent_commit_replay_v2_matrix_passes() -> None:
    result = run_governance_commit_replay_conformance_v2(
        IndependentStdlibGovernanceStateStoreV2Adapter()
    )
    assert result.ok, result.detail


def test_commit_replay_runner_owns_public_module_identity() -> None:
    assert run_governance_commit_replay_conformance_v2.__module__ == (
        "pheroos.conformance"
    )


def test_commit_replay_adversarial_support_uses_only_public_store_surfaces() -> None:
    root = Path(__file__).resolve().parents[2]
    for name in (
        "_commit_replay_v2_finality_support.py",
        "_commit_replay_v2_integrity_support.py",
        "_commit_replay_v2_public_support.py",
        "_commit_replay_v2_race_support.py",
        "_commit_replay_v2_resource_support.py",
        "_commit_replay_v2_store_support.py",
    ):
        source = (root / "pheroos/conformance/checks" / name).read_text(
            encoding="utf-8"
        )
        assert "pheroos.governance._" not in source
        assert "observe_store_v2(" not in source
        assert "tamper_store_v2(" not in source
        assert "create_failure_injected_store_v2(" not in source
