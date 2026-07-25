from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
from typing import cast

from pheroos.conformance.checks import commit_finality_v2_contract
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.commit_finality_v2_contract import (
    GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2,
    run_governance_commit_finality_conformance_v2,
)


ROOT = Path(__file__).resolve().parents[2]
CHECKS = ROOT / "pheroos/conformance/checks"
CONTRACT = CHECKS / "commit_finality_v2_contract.py"
PRODUCTION_FILES = (
    CONTRACT,
    CHECKS / "_commit_finality_v2_certificate_support.py",
    CHECKS / "_commit_finality_v2_decision_support.py",
    CHECKS / "_commit_finality_v2_distributed_support.py",
    CHECKS / "_distributed_v2_vertical_support.py",
    CHECKS / "_commit_decision_v2_context_support.py",
    CHECKS / "_commit_evidence_v2_context_support.py",
    CHECKS / "_support_v2_context_support.py",
)
DOC = ROOT / "docs/protocol/commit-finality-v2.md"


def test_commit_finality_v2_conformance_version_and_exports_are_exact() -> None:
    assert GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2 == (
        "pheroos-governance-commit-finality-conformance-v2"
    )
    assert commit_finality_v2_contract.__all__ == [
        "GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2",
        "run_governance_commit_finality_conformance_v2",
    ]


def test_commit_finality_v2_matrix_rejects_bad_adapters() -> None:
    class Incomplete:
        implementation_id = "incomplete"

    incomplete = cast(GovernanceStateStoreConformanceAdapterV2, Incomplete())
    assert run_governance_commit_finality_conformance_v2(incomplete).detail == (
        "adapter_protocol"
    )


def test_production_matrix_imports_only_public_governance_and_no_tests() -> None:
    for path in PRODUCTION_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module)
        assert not any(item.startswith("pheroos.governance._") for item in imports), (
            path
        )
        assert not any(item.startswith("tests.") for item in imports), path


def test_fresh_contract_import_does_not_load_the_legacy_authority_registry() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
import pheroos.conformance.checks.commit_finality_v2_contract

print("pheroos.governance._legacy.authority_registry" in sys.modules)
""",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "False"


def test_matrix_covers_publicly_reachable_durable_journeys() -> None:
    source = CONTRACT.read_text(encoding="utf-8")
    for invariant in (
        "certificate_verified",
        "portable_substituted_handle",
        "certificate_owner_successor_cas",
        "certificate_conflict",
        "distributed_verified",
        "distributed_conflict_not_frozen",
        "distributed_conflict_handle_exact_type",
        "distributed_conflict",
        "distributed_conflict_reason",
        "distributed_owner_successor_cas",
        "missing_handle_deadline",
        "finality:verified_owner_handle_missing_at_deadline",
    ):
        assert invariant in source
    assert "freeze_current_witness_v2" not in source
    doc = DOC.read_text(encoding="utf-8")
    assert "public\nfreeze-only observation ABI" in doc
    assert "`SAFETY_VIOLATION` with `finality:conflict`" in doc


def test_commit_finality_v2_conformance_files_stay_locally_small() -> None:
    for path in PRODUCTION_FILES:
        assert len(path.read_text(encoding="utf-8").splitlines()) < 600, path
