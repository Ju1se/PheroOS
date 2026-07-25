from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "commit-finality-v2-protocol"
SCRIPT = EXAMPLE / "run.py"


def test_commit_finality_v2_example_runs_from_an_external_working_directory(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload == {
        "authority_source": "governance-state-store-v2",
        "conformance_version": ("pheroos-governance-commit-finality-conformance-v2"),
        "coverage_notes": [
            "distributed_conflict_uses_public_freeze_only_ingress",
        ],
        "durable_journeys": [
            "certificate_verified_to_evidence_commit",
            "certificate_conflict_to_safety_violation",
            "certificate_owner_successor_cas_retry",
            "distributed_verified_to_evidence_commit",
            "distributed_frozen_to_safety_violation",
            "distributed_owner_successor_cas_retry",
            "missing_opaque_handle_to_finality_unavailable",
        ],
        "implementations": [
            "pheroos-in-memory-governance-state-store-v2",
            "pheroos-independent-stdlib-governance-state-store-v2",
        ],
        "network_used": False,
        "proved_invariants": [
            "public_governance_abi_only",
            "reference_and_independent_store_parity",
            "opaque_owner_verified_finality_input",
            "portable_projection_cannot_replace_owner_handle",
            "portable_projection_root_cannot_replace_owner_handle",
            "durable_certificate_conflict_safety_terminal",
            "durable_distributed_conflict_safety_terminal",
            "atomic_owner_successor_currentness",
            "bounded_missing_handle_deadline_terminal",
        ],
        "provider_free": True,
        "results": [
            {"detail": "", "name": "commit_finality_v2_contract", "ok": True},
            {"detail": "", "name": "commit_finality_v2_contract", "ok": True},
        ],
        "schema": "pheroos-commit-finality-v2-example-result-v1",
    }


def test_commit_finality_v2_example_imports_no_private_governance_or_tests() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    assert not any(item.startswith("pheroos.governance._") for item in imports)
    assert not any(item.startswith("tests.") for item in imports)
    assert imports & {"requests", "httpx", "urllib", "socket"} == set()
    assert "pheroos.conformance.checks.commit_finality_v2_contract" in imports
