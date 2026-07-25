from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "commit-decision-v2-protocol"
SCRIPT = EXAMPLE / "run.py"


def test_commit_decision_v2_example_runs_from_an_external_working_directory(
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
        "conformance_version": ("pheroos-governance-commit-decision-conformance-v2"),
        "durable_journeys": [
            "initialize_missing_progress_deadline_safe_fallback",
            "initialize_ready_stability_seal_evidence_commit",
            "store_restart_rehydrate_lost_response_exact_retry",
            "competing_successor_cas_retry",
        ],
        "implementations": [
            "pheroos-in-memory-governance-state-store-v2",
            "pheroos-independent-stdlib-governance-state-store-v2",
        ],
        "network_used": False,
        "proved_invariants": [
            "public_governance_abi_only",
            "reference_and_independent_store_parity",
            "fixed_stream_complete_replacement_state",
            "bounded_missing_input_progress",
            "typed_deliverable_deadline_outcome",
            "closed_candidate_and_evidence_assessment",
            "two_step_stability_window",
            "same_step_output_seal",
            "evidence_bound_finality",
            "atomic_trace_lineage",
            "restart_rehydration",
            "lost_response_exact_retry",
            "stale_parent_cas_retry",
        ],
        "provider_free": True,
        "results": [
            {"detail": "", "name": "commit_decision_v2_contract", "ok": True},
            {"detail": "", "name": "commit_decision_v2_contract", "ok": True},
        ],
        "schema": "pheroos-commit-decision-v2-example-result-v1",
    }


def test_commit_decision_v2_example_imports_no_private_governance_or_tests() -> None:
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
    assert "pheroos.conformance.checks.commit_decision_v2_contract" in imports
