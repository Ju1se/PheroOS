from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "examples" / "scoped-output-protocol" / "run.py"


def test_scoped_output_protocol_executes_from_outside_repository(
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
    repeated = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert repeated.stdout == completed.stdout

    assert payload["schema"] == "pheroos-scoped-output-example-result-v1"
    assert payload["capability"] == {
        "schema_version": "pheroos-capability-schema-v3",
        "protocol_id": "scoped.output.review",
        "protocol_version": "pheroos.protocol.v2",
        "manifest_root": payload["capability"]["manifest_root"],
    }
    assert payload["grant"]["operations"] == [
        "verify_signal",
        "evaluate_quorum",
        "qualify_evidence",
        "resolve_stop",
        "issue_action_permission",
        "authorize_output",
    ]
    assert len(payload["signals"]) == 2
    assert {item["source_ref"] for item in payload["signals"]} == {
        "source:alpha",
        "source:beta",
    }
    assert payload["permission"] | {"permission_root": "<root>"} == {
        "commit_disposition": "committed",
        "position": "current",
        "disposition": "authorized",
        "terminal_status": "evidence_commit",
        "candidate_ref": "candidate:accept",
        "permission_root": "<root>",
    }
    assert payload["output"] | {"result_root": "<root>"} == {
        "commit_disposition": "committed",
        "position": "current",
        "delivery_disposition": "deliverable",
        "action_disposition": "authorized",
        "terminal_status": "evidence_commit",
        "candidate_ref": "candidate:accept",
        "result_root": "<root>",
    }

    durable = payload["durable"]
    assert durable["positions"] == {
        "manifest": "current",
        "evidence": "current",
        "stop": "current",
        "decision": "current",
        "permission": "current",
        "output": "current",
    }
    assert durable["trace_events"] == [
        "baseline_manifest_activated",
        "baseline_evidence_qualified",
        "baseline_stop_resolved",
        "baseline_decision_evaluated",
        "baseline_action_permission_issued",
        "baseline_output_committed",
    ]
    assert len(durable["output_read_set"]) == 8
    assert durable["output_read_set"] == sorted(
        durable["output_read_set"],
        key=lambda item: item.encode("utf-8"),
    )
    assert len(set(durable["output_read_set"])) == 8
    assert "authority:domain-lifecycle" in durable["output_read_set"]
    for kind in (
        "baseline-action-permission",
        "baseline-decision",
        "baseline-evidence",
        "baseline-manifest",
        "baseline-output",
        "baseline-stop",
        "issuer-grant",
    ):
        assert (
            sum(
                item.startswith(f"authority:{kind}:")
                for item in durable["output_read_set"]
            )
            == 1
        )
    assert set(durable["state_schemas"]) == {
        "manifest",
        "evidence",
        "stop",
        "decision",
        "permission",
        "output",
    }
