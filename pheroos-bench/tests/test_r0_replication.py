"""Independent counterexamples for the optional frozen-capture comparison tool."""

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil

import pytest


BENCH = Path(__file__).resolve().parents[1]
REFERENCE = BENCH / "results/r0/runtime"
SPEC = importlib.util.spec_from_file_location(
    "compare_r0_replication", BENCH / "tools/compare_r0_replication.py"
)
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


@pytest.fixture
def candidate(tmp_path):
    directory = tmp_path / "candidate"
    shutil.copytree(REFERENCE, directory)
    return directory


def rewrite(directory, name, change):
    path = directory / f"{name}.json"
    snapshot = json.loads(path.read_bytes())
    change(snapshot)
    snapshot["event_bytes"] = sum(len(event["payload"].encode()) for event in snapshot["events"])
    snapshot["payload_bytes"] = sum(
        len(call["request"].encode()) + len((call["response"] or "").encode())
        for call in snapshot["calls"]
    )
    path.write_text(json.dumps(snapshot) + "\n")
    provenance_path = directory / "provenance.json"
    provenance = json.loads(provenance_path.read_bytes())
    provenance["snapshots"][name] = sha256(path.read_bytes()).hexdigest()
    provenance_path.write_text(json.dumps(provenance))


def test_reference_bundle_passes_and_declares_limits(candidate):
    report = comparison.compare(REFERENCE, candidate)
    assert report["status"] == "R0_REPLICATION_PASSED"
    assert report["snapshots"]["completed"]["final_value"] == 204
    assert report["counts_toward_verdict"] is False
    assert "not authentication" in report["guarantee"]


def test_independent_interleaving_and_worker_identifiers_do_not_change_semantics(candidate):
    def reorder(snapshot):
        tasks = [task["id"] for task in snapshot["tasks"]]
        events = snapshot["events"]
        snapshot["events"] = [events[0]] + [
            event for task in tasks for event in events if event["task_id"] == task
        ]
        for sequence, event in enumerate(snapshot["events"], 1):
            event["seq"] = sequence
            payload = json.loads(event["payload"])
            if payload["reason"] == "claimed":
                payload["lineage"]["owner"] = "independent-linux-worker"
            event["payload"] = json.dumps(payload)

    rewrite(candidate, "completed", reorder)
    assert comparison.compare(REFERENCE, candidate)["status"] == "R0_REPLICATION_PASSED"


@pytest.mark.parametrize("case", ["arithmetic", "parents", "scope", "authority", "receipt"])
def test_semantic_corruption_is_rejected_even_with_updated_raw_hash(candidate, case):
    def corrupt(snapshot):
        artifact = next(a for a in snapshot["artifacts"] if a["task_id"] == "total")
        if case == "arithmetic":
            artifact["value"] = 205
        elif case == "parents":
            artifact["parents"] = '["pair-1"]'
        elif case == "scope":
            artifact["scope_ref"] = "sha256:" + "0" * 64
        else:
            kind = "dispatched" if case == "authority" else "received"
            event = next(e for e in snapshot["events"] if e["event_type"].endswith("." + kind))
            payload = json.loads(event["payload"])
            if case == "authority":
                payload["lineage"]["authority"]["reusable_authority"] = True
            else:
                payload["lineage"]["driver_receipt"]["request_digest"] = "sha256:" + "0" * 64
            event["payload"] = json.dumps(payload)

    rewrite(candidate, "completed", corrupt)
    assert comparison.compare(REFERENCE, candidate)["status"] == "R0_REPLICATION_FAILED"


def test_identical_forged_results_fail_independent_arithmetic(candidate):
    rewrite(candidate, "completed", lambda s: s["artifacts"][-1].update(value=205))
    report = comparison.compare(candidate, candidate)
    assert report["status"] == "R0_REPLICATION_FAILED"
    assert "independent arithmetic" in report["differences"][0]


def test_child_claim_before_parent_publication_is_rejected(candidate):
    def reorder(snapshot):
        events = snapshot["events"]
        child = next(e for e in events if e["task_id"] == "pair-1"
                     and e["event_type"] == "ext.runtime.claimed")
        events.remove(child)
        events.insert(1, child)
        for sequence, event in enumerate(events, 1):
            event["seq"] = sequence

    rewrite(candidate, "completed", reorder)
    report = comparison.compare(REFERENCE, candidate)
    assert report["status"] == "R0_REPLICATION_FAILED"
    assert "child claimed before parent publication" in report["differences"][0]


def test_late_receipt_must_extend_the_original_cancelled_trace(candidate):
    def alter(snapshot):
        payload = json.loads(snapshot["events"][1]["payload"])
        payload["lineage"]["owner"] = "a-different-claim"
        snapshot["events"][1]["payload"] = json.dumps(payload)

    rewrite(candidate, "cancelled_late_receipt", alter)
    report = comparison.compare(REFERENCE, candidate)
    assert report["status"] == "R0_REPLICATION_FAILED"
    assert "late receipt prefix" in report["differences"][0]


def test_source_drift_is_not_equivalent_execution(candidate):
    path = candidate / "provenance.json"
    provenance = json.loads(path.read_bytes())
    provenance["runtime_source_sha256"]["store.py"] = "0" * 64
    path.write_text(json.dumps(provenance))
    assert "runtime source fingerprints differ" in comparison.compare(REFERENCE, candidate)["differences"]


def test_bad_digest_and_missing_snapshot_fail_closed(candidate):
    (candidate / "completed.json").write_text("{}")
    assert "raw digest: completed" in comparison.compare(REFERENCE, candidate)["differences"]
    (candidate / "completed.json").unlink()
    assert comparison.compare(REFERENCE, candidate)["status"] == "R0_REPLICATION_FAILED"


def test_cli_records_failure_and_never_overwrites(candidate, tmp_path):
    output = tmp_path / "report.json"
    (candidate / "completed.json").write_text("{}")
    argv = ["--reference", str(REFERENCE), "--candidate", str(candidate), "--output", str(output)]
    assert comparison.main(argv) == 2
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        comparison.main(argv)
    assert output.read_bytes() == original


def test_duplicate_json_keys_are_rejected():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        comparison.decode('{"status":"cancelled","status":"completed"}')
