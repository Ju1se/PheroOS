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
from pheroos.conformance.checks.distributed_commit_v2_contract import (
    GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2,
    run_governance_distributed_commit_conformance_v2,
)
from pheroos.conformance.report import CheckResult


ROOT = Path(__file__).resolve().parents[2]
CHECKS = ROOT / "pheroos/conformance/checks"
DISTRIBUTED_FILES = (
    CHECKS / "distributed_commit_v2_contract.py",
    CHECKS / "_distributed_v2_context_support.py",
    CHECKS / "_distributed_v2_input_support.py",
    CHECKS / "_distributed_v2_decision_support.py",
    CHECKS / "_distributed_v2_vertical_support.py",
)


@lru_cache(maxsize=2)
def _matrix_result(
    adapter_type: type[GovernanceStateStoreConformanceAdapterV2],
) -> CheckResult:
    return run_governance_distributed_commit_conformance_v2(adapter_type())


def test_distributed_v2_conformance_version_and_public_identity_are_exact() -> None:
    assert GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2 == (
        "pheroos-governance-distributed-commit-conformance-v2"
    )
    assert run_governance_distributed_commit_conformance_v2.__module__ == (
        "pheroos.conformance"
    )


def test_reference_store_passes_complete_distributed_v2_matrix() -> None:
    result = _matrix_result(ReferenceGovernanceStateStoreConformanceAdapterV2)
    assert result.name == "distributed_commit_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_independent_store_passes_same_distributed_v2_matrix() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)
    assert not isinstance(adapter, ReferenceGovernanceStateStoreConformanceAdapterV2)
    result = _matrix_result(IndependentStdlibGovernanceStateStoreV2Adapter)
    assert result.name == "distributed_commit_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_distributed_v2_matrix_rejects_incomplete_and_unknown_adapters() -> None:
    class Incomplete:
        implementation_id = "incomplete-distributed-v2"

    incomplete = run_governance_distributed_commit_conformance_v2(
        cast(Any, Incomplete())
    )
    assert incomplete.ok is False
    assert incomplete.detail == "adapter_protocol"

    class UnknownVersion(IndependentStdlibGovernanceStateStoreV2Adapter):
        conformance_version = "pheroos-governance-state-store-conformance-v999"

    unknown = run_governance_distributed_commit_conformance_v2(UnknownVersion())
    assert unknown.ok is False
    assert unknown.detail == "adapter_version"


def test_distributed_v2_matrix_is_public_only_bounded_and_has_two_exports() -> None:
    for path in DISTRIBUTED_FILES:
        source = path.read_text(encoding="utf-8")
        imports = _project_imports(source)
        assert all("pheroos.governance._" not in item for item in imports), path
        assert not any(item.startswith("tests.") for item in imports), path
        assert len(source.splitlines()) < 600, path
        assert "typing.Any" not in source, path
        assert "type: ignore" not in source, path
    module = ast.parse(DISTRIBUTED_FILES[0].read_text(encoding="utf-8"))
    exported = next(
        node.value
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        )
    )
    assert isinstance(exported, ast.List)
    assert [item.value for item in exported.elts if isinstance(item, ast.Constant)] == [
        "GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2",
        "run_governance_distributed_commit_conformance_v2",
    ]


def _project_imports(source: str) -> tuple[str, ...]:
    imports: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    return tuple(imports)
