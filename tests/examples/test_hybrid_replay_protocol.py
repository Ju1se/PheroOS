from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "hybrid-replay-protocol"
SCRIPT = EXAMPLE / "run.py"
CAPABILITY = EXAMPLE / "capability.json"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _payload(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    return payload


def test_hybrid_replay_example_is_external_cwd_and_deterministic(
    tmp_path: Path,
) -> None:
    first_run = _run(cwd=tmp_path)
    repeated = _run(cwd=tmp_path)
    assert first_run.returncode == 0, first_run.stderr
    assert repeated.returncode == 0, repeated.stderr
    assert repeated.stdout == first_run.stdout
    payload = _payload(first_run)

    assert payload["schema"] == "pheroos-hybrid-replay-example-result-v1"
    assert payload["mode"] == "restart"
    assert payload["capability"] | {"manifest_root": "<root>"} == {
        "schema_version": "pheroos-capability-schema-v3",
        "protocol_version": "pheroos.protocol.v2",
        "protocol_id": "swarm.hybrid-replay",
        "manifest_root": "<root>",
    }
    assert payload["reference_store"] == {
        "implementation": "InMemoryGovernanceStateStoreV2:test-reference-only",
        "restart_between_steps": True,
        "production_persistence": False,
    }

    steps = payload["steps"]
    assert isinstance(steps, list) and len(steps) == 2
    assert [item["revision"] for item in steps] == [1, 2]
    assert [item["current_step"] for item in steps] == [1, 2]
    assert [item["position"] for item in steps] == ["superseded", "current"]
    assert {item["authority_event"] for item in steps} == {"hybrid_replay_advanced"}
    assert steps[1]["receipt_kinds"] == {
        "adjustment": 2,
        "deposit": 4,
        "diffusion": 6,
        "feedback": 4,
    }
    assert steps[1]["overlay_fields"] == [
        "pheromone_exploration_floor",
        "pheromone_positive_weight",
    ]
    assert all(
        step["source"]["decision"]
        == {
            "candidate_ref": "candidate:alpha",
            "reason": "collective_consensus",
        }
        for step in steps
    )

    feature_path = payload["feature_path"]
    assert feature_path["receipt_kinds"] == [
        "adjustment",
        "deposit",
        "diffusion",
        "feedback",
    ]
    assert {
        "pheromone_deposit",
        "pheromone_diffuse",
        "pheromone_reinforce",
        "layer_proposal",
        "coordination_assess",
        "coordination_resolve",
        "policy_adjustment",
        "commit",
    }.issubset(feature_path["event_types"])
    assert payload["next_roots"] == {
        "request_root": steps[1]["request_root"],
        "snapshot_root": steps[1]["snapshot_root"],
        "trace_root": steps[1]["trace_root"],
    }


def test_fresh_subprocess_prepare_resume_matches_uninterrupted_roots(
    tmp_path: Path,
) -> None:
    uninterrupted = _payload(_run("uninterrupted", cwd=tmp_path))
    checkpoint = tmp_path / "hybrid-replay-reference-checkpoint.json"

    prepared = _payload(_run("prepare", "--checkpoint", str(checkpoint), cwd=tmp_path))
    assert checkpoint.is_file()
    assert prepared["schema"] == "pheroos-hybrid-replay-prepare-result-v1"
    assert prepared["checkpoint_schema"] == (
        "pheroos-hybrid-replay-reference-checkpoint-v1"
    )
    checkpoint_payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert checkpoint_payload["purpose"] == (
        "deterministic-reference-test-data-not-authority"
    )
    assert checkpoint_payload["reference_store_implementation"] == (
        "InMemoryGovernanceStateStoreV2:test-reference-only"
    )
    assert set(checkpoint_payload) == {
        "schema",
        "purpose",
        "reference_store_implementation",
        "manifest_root",
        "first_request",
        "first_source_observation",
        "reference_store_snapshot",
    }

    # A distinct interpreter invocation restores Store state, rehydrates the
    # committed parent, evaluates step two, and performs a new atomic advance.
    resumed = _payload(_run("resume", "--checkpoint", str(checkpoint), cwd=tmp_path))
    assert resumed["mode"] == "resumed"
    assert resumed["reference_store"]["restart_between_steps"] is True
    assert uninterrupted["mode"] == "uninterrupted"
    assert uninterrupted["reference_store"]["restart_between_steps"] is False

    assert resumed["next_roots"] == uninterrupted["next_roots"]
    assert resumed["steps"] == uninterrupted["steps"]
    assert resumed["feature_path"] == uninterrupted["feature_path"]
    assert prepared["first"] | {"position": "superseded"} == resumed["steps"][0]


def test_hybrid_replay_capability_passes_v3_wire_validation(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pheroos.cli.main",
            "wire",
            "validate",
            "capability-v3",
            str(CAPABILITY),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload == {
        "diagnostics": [],
        "ok": True,
        "report_version": "pheroos-wire-validation-report-v1",
        "subject": str(CAPABILITY),
        "surface": "capability-v3",
    }
