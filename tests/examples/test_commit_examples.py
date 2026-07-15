from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _run(script: str, *, cwd: Path) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_hybrid_commit_example_executes_full_declared_paths(tmp_path: Path) -> None:
    payload = _run("examples/hybrid-commit-protocol/run.py", cwd=tmp_path)

    assert set(payload) == {
        "attention_channel_separation",
        "critical_counterevidence",
        "current_publication_gate",
        "deadline_terminal",
        "declared_safe_fallback",
        "first_ready_pending",
        "no_assurance_downgrade",
        "stable_evidence_commit",
    }
    assert all(item["case"] for item in payload.values())


def test_certificate_replay_example_executes_mutations(tmp_path: Path) -> None:
    payload = _run("examples/commit-certificate-replay/replay.py", cwd=tmp_path)

    assert set(payload) == {"24", "25", "26"}
    assert all(item["variants_passed"] for item in payload.values())


def test_distributed_commit_example_executes_quorum_and_conflict(
    tmp_path: Path,
) -> None:
    payload = _run("examples/distributed-commit-protocol/run.py", cwd=tmp_path)

    assert set(payload) == {
        "byzantine_intersection",
        "certificate_conflict_freeze",
        "deadline_finality_unavailable",
        "insufficient_partition_quorum",
        "single_final_quorum",
    }
