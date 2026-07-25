from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, cast

from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.conformance.checks.authority_session_v2_contract import (
    GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2,
    run_governance_authority_session_conformance_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)


ROOT = Path(__file__).resolve().parents[2]
MATRIX = (
    ROOT / "pheroos" / "conformance" / "checks" / "authority_session_v2_contract.py"
)


def test_reference_store_passes_the_complete_authority_session_v2_matrix() -> None:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()

    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)
    result = run_governance_authority_session_conformance_v2(adapter)

    assert result.name == "authority_session_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_independent_store_passes_the_same_authority_session_v2_matrix() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()

    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)
    result = run_governance_authority_session_conformance_v2(adapter)

    assert result.name == "authority_session_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_authority_session_v2_conformance_version_is_exact() -> None:
    assert (
        GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2
        == "pheroos-governance-authority-session-conformance-v2"
    )


def test_authority_session_v2_matrix_rejects_incomplete_and_unknown_adapters() -> None:
    class Incomplete:
        implementation_id = "incomplete-authority-session-v2"

    incomplete = run_governance_authority_session_conformance_v2(
        cast(Any, Incomplete())
    )
    assert incomplete.ok is False
    assert incomplete.detail == "adapter_protocol"

    class UnknownVersion(IndependentStdlibGovernanceStateStoreV2Adapter):
        conformance_version = "pheroos-governance-state-store-conformance-v999"

    unknown = run_governance_authority_session_conformance_v2(UnknownVersion())
    assert unknown.ok is False
    assert unknown.detail == "adapter_version"


def test_authority_session_v2_matrix_is_total_at_adapter_boundary() -> None:
    class ExplodingAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "exploding-authority-session-v2"

        def create_domain_v2(self, scope_ref: str):  # type: ignore[no-untyped-def]
            raise RuntimeError(f"unavailable:{scope_ref}")

    result = run_governance_authority_session_conformance_v2(ExplodingAdapter())

    assert result.ok is False
    assert result.detail.startswith("adapter_exception:RuntimeError:")


def test_authority_session_v2_matrix_uses_only_public_composition_contracts() -> None:
    tree = ast.parse(MATRIX.read_text(encoding="utf-8"))
    project_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            project_imports.update(
                alias.name for alias in node.names if alias.name.startswith("pheroos")
            )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.startswith("pheroos"):
                project_imports.add(node.module)

    assert project_imports == {
        "pheroos.conformance.checks.authority_store_v2_contract",
        "pheroos.conformance.report",
        "pheroos.governance.authority_session_v2",
        "pheroos.governance.authority_store_v2",
        "pheroos.protocol.authority_v2",
        "pheroos.trace",
    }
    assert all(".governance._" not in module for module in project_imports)
