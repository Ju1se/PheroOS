from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from pheroos.conformance import checks
from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.support_v2_contract import (
    GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2,
    run_governance_support_conformance_v2,
)
from pheroos.conformance.report import CheckResult


ROOT = Path(__file__).resolve().parents[2]
CHECKS = ROOT / "pheroos/conformance/checks"
SUPPORT_FILES = (
    CHECKS / "support_v2_contract.py",
    CHECKS / "_support_v2_manifest_support.py",
    CHECKS / "_support_v2_context_support.py",
    CHECKS / "_support_v2_core_support.py",
    CHECKS / "_support_v2_integrity_support.py",
    CHECKS / "_support_v2_finality_race_support.py",
)


@lru_cache(maxsize=2)
def _matrix_result(
    adapter_type: type[GovernanceStateStoreConformanceAdapterV2],
) -> CheckResult:
    return run_governance_support_conformance_v2(adapter_type())


def test_support_v2_conformance_version_is_exact() -> None:
    assert GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2 == (
        "pheroos-governance-support-conformance-v2"
    )


def test_reference_store_passes_the_active_support_v2_matrix() -> None:
    result = _matrix_result(ReferenceGovernanceStateStoreConformanceAdapterV2)
    assert result.name == "support_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_independent_store_passes_the_same_support_v2_matrix() -> None:
    result = _matrix_result(IndependentStdlibGovernanceStateStoreV2Adapter)
    assert result.name == "support_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_support_v2_matrix_rejects_incomplete_or_unknown_adapters() -> None:
    class Incomplete:
        implementation_id = "incomplete-support-v2"

    assert (
        run_governance_support_conformance_v2(cast(Any, Incomplete())).detail
        == "adapter_protocol"
    )

    class UnknownVersion(IndependentStdlibGovernanceStateStoreV2Adapter):
        conformance_version = "pheroos-governance-state-store-conformance-v999"

    assert run_governance_support_conformance_v2(UnknownVersion()).detail == (
        "adapter_version"
    )


def test_support_v2_runner_is_exported_by_public_checks_package() -> None:
    assert checks.support_v2_contract.run_governance_support_conformance_v2 is (
        run_governance_support_conformance_v2
    )
    assert run_governance_support_conformance_v2.__module__ == "pheroos.conformance"


def test_support_v2_matrix_uses_only_public_governance_surfaces() -> None:
    for path in SUPPORT_FILES:
        source = path.read_text(encoding="utf-8")
        imports = _project_imports(source)
        assert all("pheroos.governance._" not in item for item in imports)
        assert not any(item.startswith("tests.") for item in imports)
        assert "pheroos.governance.support import" not in source
        assert "pheroos.governance._support." not in source
        for forbidden in (
            "create_failure_injected_store_v2(",
            "observe_store_v2(",
            "tamper_store_v2(",
            "monkeypatch",
        ):
            assert forbidden not in source


def test_support_v2_matrix_covers_all_active_authority_lanes() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in SUPPORT_FILES)
    for required in (
        "principal_verification_set_advanced",
        "membership_epoch_committed",
        "support_state_advanced",
        "support_lease_issued_v2",
        "support_lease_revoked_v2",
        "restart_rehydrate",
        "lost_response_exact_retry",
        "stale_parent_not_retry_required",
        "stale_membership_not_retry_required",
        "issuer_rotation_fixed_lineage",
        "noncanonical_wire_accepted",
        "resource_limit_accepted",
        "finality_not_fail_closed",
        "tamper_not_fail_closed",
        "sealed_exact_retry",
        "race_32_same_request",
        "race_32_forks_one_winner",
    ):
        assert required in source


def test_support_v2_conformance_modules_stay_below_structure_limit() -> None:
    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) < 600
        for path in SUPPORT_FILES
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
