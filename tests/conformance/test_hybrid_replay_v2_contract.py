from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.hybrid_replay_v2_contract import (
    GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2,
    run_governance_hybrid_replay_conformance_v2,
)
from pheroos.conformance.report import CheckResult


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "pheroos" / "conformance" / "checks" / "hybrid_replay_v2_contract.py"
PUBLIC_SUPPORT = (
    ROOT / "pheroos" / "conformance" / "checks" / "_hybrid_replay_v2_public_support.py"
)
RESOURCE_SUPPORT = (
    ROOT
    / "pheroos"
    / "conformance"
    / "checks"
    / "_hybrid_replay_v2_resource_support.py"
)


@lru_cache(maxsize=2)
def _matrix_result(
    adapter_type: type[GovernanceStateStoreConformanceAdapterV2],
) -> CheckResult:
    return run_governance_hybrid_replay_conformance_v2(adapter_type())


def test_reference_store_passes_the_active_hybrid_replay_v2_matrix() -> None:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()

    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)
    result = _matrix_result(ReferenceGovernanceStateStoreConformanceAdapterV2)

    assert result.name == "hybrid_replay_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_independent_store_passes_the_same_hybrid_replay_v2_matrix() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()

    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)
    assert not isinstance(adapter, ReferenceGovernanceStateStoreConformanceAdapterV2)
    result = _matrix_result(IndependentStdlibGovernanceStateStoreV2Adapter)

    assert result.name == "hybrid_replay_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_hybrid_replay_v2_conformance_version_is_exact() -> None:
    assert (
        GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2
        == "pheroos-governance-hybrid-replay-conformance-v2"
    )


def test_hybrid_replay_v2_matrix_has_no_skip_lane() -> None:
    for adapter_type in (
        ReferenceGovernanceStateStoreConformanceAdapterV2,
        IndependentStdlibGovernanceStateStoreV2Adapter,
    ):
        result = _matrix_result(adapter_type)

        assert result.ok is True
        assert result.detail == ""
        assert "skip" not in result.detail.lower()
        assert "n/a" not in result.detail.lower()


def test_hybrid_replay_v2_matrix_rejects_incomplete_and_unknown_adapters() -> None:
    class Incomplete:
        implementation_id = "incomplete-hybrid-replay-v2"

    incomplete = run_governance_hybrid_replay_conformance_v2(cast(Any, Incomplete()))
    assert incomplete.ok is False
    assert incomplete.detail == "adapter_protocol"

    class UnknownVersion(IndependentStdlibGovernanceStateStoreV2Adapter):
        conformance_version = "pheroos-governance-state-store-conformance-v999"

    unknown = run_governance_hybrid_replay_conformance_v2(UnknownVersion())
    assert unknown.ok is False
    assert unknown.detail == "adapter_version"


def test_hybrid_replay_v2_matrix_is_total_at_adapter_boundary() -> None:
    class ExplodingAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "exploding-hybrid-replay-v2"

        def create_domain_v2(self, scope_ref: str):  # type: ignore[no-untyped-def]
            raise RuntimeError(f"unavailable:{scope_ref}")

    result = run_governance_hybrid_replay_conformance_v2(ExplodingAdapter())

    assert result.ok is False
    assert result.detail.startswith("adapter_exception:RuntimeError:")


def test_hybrid_replay_v2_matrix_uses_only_public_composition_contracts() -> None:
    source = MATRIX.read_text(encoding="utf-8")
    project_imports = _project_imports(source)

    assert project_imports == {
        "pheroos.conformance.checks._hybrid_replay_v2_public_support",
        "pheroos.conformance.checks.authority_store_v2_contract",
        "pheroos.conformance.report",
        "pheroos.governance",
        "pheroos.governance.authority_session_v2",
        "pheroos.governance.authority_store_v2",
        "pheroos.governance.layer_coordination",
        "pheroos.protocol",
        "pheroos.protocol.authority_v2",
    }
    assert all(".governance._" not in module for module in project_imports)
    assert "evaluate_hybrid_collective_step(" not in source
    assert "_issue_" not in source


def test_hybrid_replay_v2_adversarial_support_uses_only_public_abi_proxies() -> None:
    source = PUBLIC_SUPPORT.read_text(encoding="utf-8")
    project_imports = _project_imports(source)

    assert project_imports == {
        "pheroos.conformance.checks._hybrid_replay_v2_resource_support",
        "pheroos.conformance.checks.authority_store_v2_contract",
        "pheroos.governance",
        "pheroos.governance.authority_session_v2",
        "pheroos.governance.authority_store_v2",
        "pheroos.protocol.authority_v2",
    }
    assert all(".governance._" not in module for module in project_imports)
    for forbidden in (
        "create_failure_injected_store_v2",
        "observe_store_v2",
        "tamper_store_v2",
        "_issue_",
        "monkeypatch",
    ):
        assert forbidden not in source
    for required in (
        "reconciliation_finality_unavailable",
        "historical_parent_finality_unavailable",
        "rehydrate_finality_unavailable",
        "complete_canonical_exact_reconciliation",
        "trace_read_set_root_tamper",
    ):
        assert required in source


def test_hybrid_replay_v2_resource_support_uses_only_public_constructors() -> None:
    source = RESOURCE_SUPPORT.read_text(encoding="utf-8")

    assert _project_imports(source) == {"pheroos.governance"}
    assert ".governance._" not in source
    for forbidden in ("monkeypatch", "setattr(contracts", "_preflight_"):
        assert forbidden not in source
    for required in (
        "resource_causal_exact",
        "resource_causal_over",
        "resource_cycle",
        "resource_depth_exact",
        "resource_depth_over",
        "resource_nodes_exact",
        "resource_nodes_over",
        "resource_text_exact",
        "resource_text_over",
        "resource_lineage_exact",
        "resource_lineage_over",
        "resource_snapshot_exact",
        "resource_snapshot_over",
        "resource_rejection_zero_write",
    ):
        assert required in source


def _project_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    project_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            project_imports.update(
                alias.name for alias in node.names if alias.name.startswith("pheroos")
            )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.startswith("pheroos"):
                project_imports.add(node.module)
    return project_imports
