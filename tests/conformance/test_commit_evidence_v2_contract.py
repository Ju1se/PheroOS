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
from pheroos.conformance.checks.commit_evidence_v2_contract import (
    GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2,
    run_governance_commit_evidence_conformance_v2,
)
from pheroos.conformance.report import CheckResult


ROOT = Path(__file__).resolve().parents[2]
CHECKS = ROOT / "pheroos" / "conformance" / "checks"
EVIDENCE_FILES = (
    CHECKS / "commit_evidence_v2_contract.py",
    CHECKS / "_commit_evidence_v2_context_support.py",
)


@lru_cache(maxsize=2)
def _matrix_result(
    adapter_type: type[GovernanceStateStoreConformanceAdapterV2],
) -> CheckResult:
    return run_governance_commit_evidence_conformance_v2(adapter_type())


def test_commit_evidence_v2_conformance_version_is_exact() -> None:
    assert GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2 == (
        "pheroos-governance-commit-evidence-conformance-v2"
    )
    assert run_governance_commit_evidence_conformance_v2.__module__ == (
        "pheroos.conformance"
    )


def test_reference_and_independent_stores_pass_the_same_public_matrix() -> None:
    for adapter_type in (
        ReferenceGovernanceStateStoreConformanceAdapterV2,
        IndependentStdlibGovernanceStateStoreV2Adapter,
    ):
        result = _matrix_result(adapter_type)
        assert result.name == "commit_evidence_v2_contract"
        assert result.ok is True, result.detail
        assert result.detail == ""


def test_commit_evidence_v2_matrix_rejects_bad_adapters_and_is_total() -> None:
    class Incomplete:
        implementation_id = "incomplete-commit-evidence-v2"

    incomplete = run_governance_commit_evidence_conformance_v2(cast(Any, Incomplete()))
    assert incomplete.ok is False
    assert incomplete.detail == "adapter_protocol"

    class Exploding(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "exploding-commit-evidence-v2"

        def create_domain_v2(self, scope_ref: str):  # type: ignore[no-untyped-def]
            raise RuntimeError(f"unavailable:{scope_ref}")

    exploded = run_governance_commit_evidence_conformance_v2(Exploding())
    assert exploded.ok is False
    assert exploded.detail.startswith("adapter_exception:RuntimeError:")


def test_commit_evidence_v2_matrix_uses_public_governance_surfaces_only() -> None:
    for path in EVIDENCE_FILES:
        source = path.read_text(encoding="utf-8")
        imports = _project_imports(source)
        assert all("pheroos.governance._" not in item for item in imports)
        assert not any(item.startswith("tests.") for item in imports)
        assert "observe_store_v2(" not in source
        assert "tamper_store_v2(" not in source
        assert "create_failure_injected_store_v2(" not in source
        assert len(source.splitlines()) < 600


def test_commit_evidence_v2_matrix_names_required_invariants() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in EVIDENCE_FILES)
    for invariant in (
        "complete_authority_read_set",
        "atomic_trace_lineage",
        "current_rehydration",
        "qualified_success_projection_evaluation",
        "single_source_insufficient",
        "lost_response_exact_retry",
        "restart_rehydration",
        "restart_exact_retry",
        "input_order_determinism",
        "non_authoritative_source",
        "fork_stale_loser",
        "fork_single_head",
        "candidate_claim_subject_isolation",
    ):
        assert invariant in source


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
