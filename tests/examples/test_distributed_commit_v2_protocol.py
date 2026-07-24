from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/distributed-commit-v2-protocol"
SCRIPT = EXAMPLE / "run.py"


def test_distributed_commit_v2_example_is_external_cwd_and_provider_free(
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
        "schema": "pheroos-distributed-commit-v2-example-result-v1",
        "provider_free": True,
        "network_used": False,
        "production_persistence": False,
        "implementation": "pheroos-in-memory-governance-state-store-v2",
        "conformance_version": ("pheroos-governance-distributed-commit-conformance-v2"),
        "result": {
            "name": "distributed_commit_v2_contract",
            "ok": True,
            "detail": "",
        },
        "proved_invariants": [
            "four_fixed_state_store_streams",
            "sealed_decision_and_central_certificate_binding",
            "static_epoch_membership_binding",
            "trusted_witness_attestation",
            "quorum_certificate_verification",
            "canonical_distributed_finality_handle",
            "full_parent_dependency_grant_lifecycle_cas",
            "restart_rehydration_currentness",
            "portable_request_tamper_rejection",
            "external_byzantine_witness_freeze_only",
            "conflict_observation_restart_and_exact_retry",
            "conflict_finality_decision_safety_violation",
            "closed_conflict_trace",
        ],
    }


def test_distributed_commit_v2_example_uses_public_protocol_core_only() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    imports = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(name.startswith("pheroos.governance._") for name in imports)
    assert not any(name.startswith("tests.") for name in imports)
    assert imports & {"requests", "httpx", "urllib", "socket"} == set()
    assert "pheroos.conformance.checks.distributed_commit_v2_contract" in imports
