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
from pheroos.conformance.checks.commit_gate_v2_contract import (
    GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2,
    run_governance_commit_gate_conformance_v2,
)
from pheroos.conformance.report import CheckResult


ROOT = Path(__file__).resolve().parents[2]
CHECKS = ROOT / "pheroos/conformance/checks"
FILES = (
    CHECKS / "commit_gate_v2_contract.py",
    CHECKS / "_commit_gate_v2_context_support.py",
    CHECKS / "_commit_gate_v2_adversarial_support.py",
)


@lru_cache(maxsize=2)
def _result(
    adapter_type: type[GovernanceStateStoreConformanceAdapterV2],
) -> CheckResult:
    return run_governance_commit_gate_conformance_v2(adapter_type())


def test_commit_gate_v2_conformance_version_is_exact() -> None:
    assert GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2 == (
        "pheroos-governance-commit-gate-conformance-v2"
    )


def test_reference_store_passes_commit_gate_v2_matrix() -> None:
    result = _result(ReferenceGovernanceStateStoreConformanceAdapterV2)
    assert result.name == "commit_gate_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_independent_store_passes_the_same_commit_gate_v2_matrix() -> None:
    result = _result(IndependentStdlibGovernanceStateStoreV2Adapter)
    assert result.name == "commit_gate_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_commit_gate_v2_matrix_rejects_incomplete_or_unknown_adapters() -> None:
    class Incomplete:
        implementation_id = "incomplete-commit-gate-v2"

    assert (
        run_governance_commit_gate_conformance_v2(cast(Any, Incomplete())).detail
        == "adapter_protocol"
    )

    class UnknownVersion(IndependentStdlibGovernanceStateStoreV2Adapter):
        conformance_version = "pheroos-governance-state-store-conformance-v999"

    assert run_governance_commit_gate_conformance_v2(UnknownVersion()).detail == (
        "adapter_version"
    )


def test_commit_gate_v2_matrix_uses_only_public_governance_surfaces() -> None:
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        imports = _project_imports(source)
        assert all("pheroos.governance._" not in item for item in imports)
        assert not any(item.startswith("tests.") for item in imports)
        for forbidden in (
            "observe_store_v2(",
            "tamper_store_v2(",
            "create_failure_injected_store_v2(",
            "pheroos.governance.stop_signal",
            "pheroos.governance.permission",
        ):
            assert forbidden not in source


def test_commit_gate_v2_matrix_covers_both_independent_ledgers() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in FILES)
    for required in (
        "commit_stop_resolved_v2",
        "commit_permission_issued_v2",
        "eight_entry_read_set",
        "verification_toctou_not_closed",
        "lost_response_exact_retry_after_restart",
        "conflicting_genesis_retry",
        "portable_source_forgery",
        "restart_rehydrate",
        "finality_not_fail_closed",
        "inclusion_tamper_not_fail_closed",
        "position_tamper_not_fail_closed",
        "race_32_identical_exact_retry",
        "race_32_conflicting_one_winner",
        "sealed_historical_exact_retry",
        "sealed_new_write_not_denied",
    ):
        assert required in source


def test_commit_gate_v2_conformance_modules_stay_below_structure_limit() -> None:
    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) < 600 for path in FILES
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
