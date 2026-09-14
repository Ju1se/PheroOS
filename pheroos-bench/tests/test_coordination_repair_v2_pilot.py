"""Provider-free counterexamples for the separately authorized retry runner."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from pheroos_bench import coordination_repair_v2_pilot as pilot


PREDECESSOR = Path(__file__).resolve().parents[1] / "next-cycle/coordination-repair-v1"


def test_proposal_preserves_worlds_gates_sampling_and_reserves_prior_intent():
    previous, proposed = pilot.original_configuration(), pilot.configuration()
    for key in ("actionability", "collaboration", "model", "generation", "context_tokens",
                "max_new_tokens", "seed", "attention", "stop_rule"):
        assert proposed[key] == previous[key]
    assert proposed["cycle_caps"]["model_dispatches"] + 1 == previous["cycle_caps"]["model_dispatches"]
    assert proposed["cycle_caps"]["tokens"] == previous["cycle_caps"]["tokens"]
    actionability = pilot.expected_grid(proposed, "actionability")
    collaboration = pilot.expected_grid(proposed, "collaboration")
    assert len(actionability) == 28 and len(collaboration) == 28
    all_fork_caps = 4 * 3 * proposed["collaboration"]["token_cap"]
    assert sum(r["token_cap"] for r in actionability + collaboration) + all_fork_caps == 499712
    assert sum(r["steps"] for r in actionability + collaboration) + 4 * 3 * 8 < 999
    assert proposed["model_adapter"].startswith("pheroos_runtime.recorded_local_v2.")
    assert proposed["counts_toward_verdict"] is False


def test_authorization_required_before_loading_models_or_creating_outputs(tmp_path):
    output = tmp_path / "not-started"
    with pytest.raises(PermissionError, match="separate user authorization"):
        pilot.collect(pilot.configuration(), output, tmp_path / "missing-model", "actionability", PREDECESSOR)
    assert not output.exists()


def test_predecessor_identity_and_liability_are_checked_without_opening_database(tmp_path):
    config = pilot.configuration()
    result = pilot.verify_predecessor(PREDECESSOR, config)
    assert result["retained_intent_slots"] == 1 and result["settled_preparation_tools"] == 3
    assert result["token_upper_bound"] == 0 and result["observed_model_dispatches"] == 0
    for name in config["continuation"]["predecessor_files"]:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PREDECESSOR / name, dest)
    accounting = tmp_path / "local-cycle-v1/actionability/accounting.json"
    old = accounting.read_bytes()
    accounting.write_bytes(old + b" ")
    with pytest.raises(ValueError, match="identity mismatch"):
        pilot.verify_predecessor(tmp_path, config)
    changed = json.loads(old)
    changed["held_token_upper_bound"] = 902
    accounting.write_text(json.dumps(changed))
    altered_config = deepcopy(config)
    altered_config["continuation"]["predecessor_files"]["local-cycle-v1/actionability/accounting.json"] = sha256(accounting.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="declared settled"):
        pilot.verify_predecessor(tmp_path, altered_config)


def test_empty_model_denominator_is_unmeasured_and_cannot_admit():
    report = pilot.admission([], pilot.configuration())
    assert report["admitted"] is False
    assert report["model_action_denominator"] == 0
    assert report["measurement_status"] == "UNMEASURED"
    assert report["interface_rejection_fraction"] is None
    assert all(value is None for value in report["fractions"].values())
    assert report["empty_denominator_gate_sentinels"]["interface_rejection_fraction"] == 1


def declared_records(config):
    return [dict(world_id=item["world"], family=item["world"].split("/")[0], arm=item["arm"], n=item["n"],
                 condition=item["condition"], campaign_component=item["component"], status="VALID_KNOWN", success=True, complete_rollout=True,
                 stop="public_accepted_submission", metrics={"tool_calls":2,"inspection_dispatches":int(item["arm"] != "candidate")},
                 turns=[dict(model_response={"text":"synthetic gate input"},
                             validation={"valid":True,"stage":"accepted","normalized_action":{"action":"submit"}},
                             materialized_receipts=[])]) for item in pilot.expected_grid(config,"actionability")]


def test_missing_probe_cannot_be_called_complete_even_after_capability_succeeds():
    config = pilot.configuration()
    rows = declared_records(config)
    assert pilot.admission(rows, config)["admitted"]
    rows.pop()
    report = pilot.admission(rows, config)
    assert report["checks"]["complete_known_records"]
    assert not report["checks"]["full_declared_grid"]
    assert report["measurement_status"] == "INCOMPLETE" and not report["admitted"]


@pytest.mark.parametrize("change", ["source", "predecessor", "completion", "records", "gate"])
def test_collaboration_rechecks_complete_source_bound_diagnostic_records(tmp_path, change):
    config = pilot.configuration()
    records = declared_records(config)
    predecessor = {"known_tokens":0,"retained_intent_slots":1}
    sources = {"frozen-module.py":"original-source-digest"}
    phase = tmp_path / "actionability"
    phase.mkdir()
    files = {
        tmp_path / "frozen-config.json":config,
        phase / "freeze.json":dict(config_sha256=pilot.digest(config), sources=sources, predecessor=predecessor,
                                  runtime_version=config["runtime_version"],bench_version=config["bench_version"]),
        phase / "campaign-completion.json":dict(status="COMPLETE",unstarted=[],failure=None,
                                                executed=28,declared=28,records_sha256=pilot.digest(records)),
        phase / "records.json":records,
        phase / "admission.json":pilot.admission(records,config),
    }
    for path, value in files.items():
        path.write_text(json.dumps(value))
    assert pilot.validate_actionability(tmp_path,config,predecessor,sources)["admitted"]
    if change == "source":
        sources = {"frozen-module.py":"changed-source-digest"}
    elif change == "predecessor":
        predecessor = {"known_tokens":0,"retained_intent_slots":0}
    elif change == "completion":
        completed = files[phase / "campaign-completion.json"]
        completed["status"] = "INVALID_ABORT"
        (phase / "campaign-completion.json").write_text(json.dumps(completed))
    elif change == "records":
        (phase / "records.json").write_text(json.dumps(records[:-1]))
    else:
        (phase / "admission.json").write_text('{"admitted":true}')
    with pytest.raises(ValueError):
        pilot.validate_actionability(tmp_path,config,predecessor,sources)


@pytest.mark.parametrize("failure", ["phase_aborted", "missing_prefixes", "missing_forks"])
def test_whole_phase_failure_or_missing_declared_prefixes_cannot_yield_valid_subset(monkeypatch, failure):
    config = pilot.configuration()
    records = [dict(world_id=r["world"],arm=r["arm"],n=r["n"],status="VALID_KNOWN",complete_rollout=True)
               for r in pilot.expected_grid(config,"collaboration")]
    def forbidden(*args, **kwargs):
        raise AssertionError("incomplete phase must not invoke a subset analyzer")
    monkeypatch.setattr(pilot,"analyze_forks",forbidden)
    monkeypatch.setattr(pilot,"paired_call_export",forbidden)
    phase_status = "INVALID_ABORT" if failure == "phase_aborted" else "COMPLETE"
    prefixes = [] if failure == "missing_prefixes" else [dict(world_id=w,prefix_id="step-1",eligible=True)
                                                        for w in config["collaboration"]["worlds"]]
    report, exports = pilot.collaboration_analysis(config,{"status":phase_status},records,prefixes,[])
    assert report["status"] == "INVALID" and report["partial_record_count"] == 28
    assert report["raw_records_retained"] is True
    assert all(value["status"] == "INVALID" and not value["measurement_exported"] for value in exports.values())
