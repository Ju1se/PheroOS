from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.conformance import checks
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.risk_v2_contract import (
    GOVERNANCE_RISK_CONFORMANCE_VERSION_V2,
    run_governance_risk_conformance_v2,
)
from pheroos.conformance.report import CheckResult


ROOT = Path(__file__).resolve().parents[2]
CHECKS = ROOT / "pheroos" / "conformance" / "checks"
RISK_FILES = (
    CHECKS / "risk_v2_contract.py",
    CHECKS / "_risk_v2_context_support.py",
    CHECKS / "_risk_v2_core_support.py",
    CHECKS / "_risk_v2_public_support.py",
    CHECKS / "_risk_v2_store_support.py",
    CHECKS / "_risk_v2_finality_support.py",
    CHECKS / "_risk_v2_integrity_support.py",
    CHECKS / "_risk_v2_race_support.py",
    CHECKS / "_risk_v2_resource_support.py",
)


@lru_cache(maxsize=2)
def _matrix_result(
    adapter_type: type[GovernanceStateStoreConformanceAdapterV2],
) -> CheckResult:
    return run_governance_risk_conformance_v2(adapter_type())


def test_risk_v2_conformance_version_is_exact() -> None:
    assert GOVERNANCE_RISK_CONFORMANCE_VERSION_V2 == (
        "pheroos-governance-risk-conformance-v2"
    )


def test_reference_store_passes_the_active_risk_v2_matrix() -> None:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)

    result = _matrix_result(ReferenceGovernanceStateStoreConformanceAdapterV2)

    assert result.name == "risk_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_independent_store_passes_the_same_risk_v2_matrix() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)
    assert not isinstance(adapter, ReferenceGovernanceStateStoreConformanceAdapterV2)

    result = _matrix_result(IndependentStdlibGovernanceStateStoreV2Adapter)

    assert result.name == "risk_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_risk_v2_matrix_has_no_skip_lane() -> None:
    for adapter_type in (
        ReferenceGovernanceStateStoreConformanceAdapterV2,
        IndependentStdlibGovernanceStateStoreV2Adapter,
    ):
        result = _matrix_result(adapter_type)
        assert result.ok is True
        assert result.detail == ""
        assert "skip" not in result.detail.lower()
        assert "n/a" not in result.detail.lower()


def test_risk_v2_matrix_rejects_incomplete_and_unknown_adapters() -> None:
    class Incomplete:
        implementation_id = "incomplete-risk-v2"

    incomplete = run_governance_risk_conformance_v2(cast(Any, Incomplete()))
    assert incomplete.ok is False
    assert incomplete.detail == "adapter_protocol"

    class UnknownVersion(IndependentStdlibGovernanceStateStoreV2Adapter):
        conformance_version = "pheroos-governance-state-store-conformance-v999"

    unknown = run_governance_risk_conformance_v2(UnknownVersion())
    assert unknown.ok is False
    assert unknown.detail == "adapter_version"


def test_risk_v2_matrix_is_total_at_adapter_boundary() -> None:
    class ExplodingAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "exploding-risk-v2"

        def create_domain_v2(self, scope_ref: str):  # type: ignore[no-untyped-def]
            raise RuntimeError(f"unavailable:{scope_ref}")

    result = run_governance_risk_conformance_v2(ExplodingAdapter())

    assert result.ok is False
    assert result.detail.startswith("adapter_exception:RuntimeError:")


def test_risk_v2_runner_is_exported_by_the_public_checks_package() -> None:
    assert checks.risk_v2_contract.run_governance_risk_conformance_v2 is (
        run_governance_risk_conformance_v2
    )
    assert run_governance_risk_conformance_v2.__module__ == "pheroos.conformance"


def test_risk_v2_matrix_uses_only_public_protocol_and_governance_surfaces() -> None:
    runner_imports = _project_imports(RISK_FILES[0].read_text(encoding="utf-8"))
    assert runner_imports == {
        "pheroos.conformance.checks._risk_v2_context_support",
        "pheroos.conformance.checks._risk_v2_core_support",
        "pheroos.conformance.checks._risk_v2_public_support",
        "pheroos.conformance.checks.authority_store_v2_contract",
        "pheroos.conformance.report",
    }
    for path in RISK_FILES:
        source = path.read_text(encoding="utf-8")
        imports = _project_imports(source)
        assert all("pheroos.governance._" not in item for item in imports)
        assert not any(item.startswith("tests.") for item in imports)
        for forbidden in (
            "create_failure_injected_store_v2(",
            "observe_store_v2(",
            "tamper_store_v2(",
            "def _issue_",
            "._issue_",
            "monkeypatch",
        ):
            assert forbidden not in source


def test_risk_v2_matrix_covers_the_required_public_adversarial_lanes() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in RISK_FILES)
    for required in (
        "atomic_trace_lineage",
        "complete_authority_read_set",
        "current_rehydration",
        "lost_response_exact_retry",
        "canonical_transition_conflict",
        "reconciliation_finality_unavailable",
        "historical_parent_finality_unavailable",
        "rehydrate_finality_unavailable",
        "source_or_session_binding",
        "scope_domain_run_binding",
        "issuer_binding",
        "authority_selector",
        "retry_not_typed_fail_closed",
        "race_32_same_request",
        "race_32_forks_one_winner",
        "resource_input_exact",
        "resource_input_over",
        "resource_snapshot_exact",
        "resource_snapshot_over",
        "resource_rejection_zero_write",
        "fixed_lineage_epoch_130",
        "fixed_lineage_130_portable_epochs",
        "sealed_domain_historical_or_zero_write",
        "sealed_domain_exact_retry",
        "noncanonical_wire_empty_roots",
        "noncanonical_wire_reordered_arrays",
        "bool_epoch_exact_type",
    ):
        assert required in source
    for mutation in ("inclusion", "position", "state", "trace", "read_set"):
        assert f'"{mutation}"' in source


def test_risk_v2_matrix_modules_stay_below_the_owner_structure_limit() -> None:
    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) < 600 for path in RISK_FILES
    )


def _project_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(
                alias.name for alias in node.names if alias.name.startswith("pheroos")
            )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.startswith("pheroos") or node.module.startswith("tests"):
                result.add(node.module)
    return result
