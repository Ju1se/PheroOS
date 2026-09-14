"""Installed runtime orchestration failures; these are synthetic, not model data."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import pytest
from pheroos_bench import coordination_repair_v2_pilot as pilot

PREDECESSOR = Path(__file__).resolve().parents[2] / "next-cycle/coordination-repair-v1"


@pytest.fixture
def orchestration(tmp_path, monkeypatch):
    # Only the orchestration shell uses these doubles; no model is loaded or
    # generated. Real SessionDriver/authority coverage lives in consumer tests.
    import pheroos_runtime.recorded_local_v2 as adapter
    import pheroos_bench.coordination_repair_v2 as episode
    config = pilot.configuration()
    model_path = tmp_path / "synthetic-model"
    model_path.mkdir()
    manifest = model_path / "manifest.json"
    manifest.write_text('{}')
    config["model"]["manifest_sha256"] = sha256(manifest.read_bytes()).hexdigest()
    monkeypatch.setattr(pilot, "configuration", lambda: deepcopy(config))
    version = pilot.importlib.metadata.version
    monkeypatch.setattr(pilot.importlib.metadata, "version", lambda name:
        config["bench_version"] if name == "pheroos-bench" else version(name))
    class SyntheticAdapter:
        identity = {"adapter": "provider_free_orchestration_test_double"}
        def __init__(self, _path):
            pass
    monkeypatch.setattr(adapter, "RecordedLocalModelAdapter", SyntheticAdapter)
    return config, model_path, tmp_path / "cohort", adapter, episode


def collect_fixture(fixture):
    config, model_path, output, *_ = fixture
    return pilot.collect(config, output, model_path, "actionability", PREDECESSOR,
                         additional_campaign_authorized=True)


def test_model_initialization_failure_retains_full_unstarted_grid(orchestration, monkeypatch):
    config, _, output, adapter, _ = orchestration
    def fail(_path):
        raise RuntimeError("synthetic loader failure; zero inference")
    monkeypatch.setattr(adapter, "RecordedLocalModelAdapter", fail)
    report = collect_fixture(orchestration)
    completed = json.loads((output / "actionability/campaign-completion.json").read_text())
    assert completed["status"] == "INVALID_ABORT" and completed["executed"] == 0
    assert len(completed["unstarted"]) == 28
    assert all(r["cost"] is None and r["outcome"] is None for r in completed["unstarted"])
    combined = json.loads((output / "actionability/combined-accounting.json").read_text())
    assert combined["held_intent_slots"] == 1 and combined["held_token_upper_bound"] == 0
    assert report["measurement_status"] == "UNMEASURED"
    with pytest.raises(FileExistsError, match="cannot be rerun"):
        collect_fixture(orchestration)


def test_raised_episode_is_started_invalid_not_an_unstarted_cell(orchestration, monkeypatch):
    _, _, output, _, episode = orchestration
    calls = []
    def fail(**arguments):
        calls.append(arguments["world"])
        raise PermissionError("synthetic failure after entering consumer")
    monkeypatch.setattr(episode, "run_episode", fail)
    report = collect_fixture(orchestration)
    assert len(calls) == 1 and report["admitted"] is False
    completed = json.loads((output / "actionability/campaign-completion.json").read_text())
    assert completed["executed"] == 1 and len(completed["unstarted"]) == 27
    rows = json.loads((output / "actionability/records.json").read_text())
    assert rows[0]["status"] == "INVALID_ABORT" and rows[0]["metrics"] is None
    assert rows[0]["error"]["stage"] == "capability_permission"


def test_multiple_episode_results_flush_once_without_overwriting_frozen_files(orchestration, monkeypatch):
    _, _, output, _, episode = orchestration
    calls = []
    def row(**a):
        calls.append(a["world"])
        return dict(world_id=a["world"], family=a["world"].split("/")[0], arm=a["arm"], n=a["n"],
                    condition=a["condition"], status="VALID_KNOWN", success=True, complete_rollout=True,
                    stop="public_accepted_submission", metrics={"tool_calls":0,"inspection_dispatches":0},
                    turns=[dict(model_response={"text":"synthetic orchestration fixture"},
                                validation={"valid":True,"stage":"accepted","normalized_action":{"action":"submit"}},
                                materialized_receipts=[])])
    monkeypatch.setattr(episode, "run_episode", row)
    report = collect_fixture(orchestration)
    assert len(calls) == 28
    completed = json.loads((output / "actionability/campaign-completion.json").read_text())
    assert completed["status"] == "COMPLETE" and completed["unstarted"] == []
    rows = json.loads((output / "actionability/records.json").read_text())
    journal = (output / "actionability/completed.jsonl").read_text().splitlines()
    assert len(rows) == len(journal) == 28
    assert not report["checks"]["intervention_relevance"]
    assert report["admitted"] is False


def test_incomplete_rollout_stops_even_with_known_accounting_status(orchestration, monkeypatch):
    _, _, output, _, episode = orchestration
    calls = []
    def incomplete(**a):
        calls.append(a["world"])
        return dict(world_id=a["world"],family=a["world"].split("/")[0],arm=a["arm"],n=a["n"],
                    condition=a["condition"],status="VALID_KNOWN",success=False,complete_rollout=False,turns=[])
    monkeypatch.setattr(episode, "run_episode", incomplete)
    report = collect_fixture(orchestration)
    completed = json.loads((output / "actionability/campaign-completion.json").read_text())
    assert len(calls) == 1 and completed["status"] == "INVALID_ABORT"
    assert completed["executed"] == 1 and len(completed["unstarted"]) == 27
    assert report["admitted"] is False


def test_accounting_read_failure_remains_unknown_in_terminal_record(orchestration, monkeypatch):
    from pheroos_runtime.campaign_v1 import CampaignBudget
    _, _, output, adapter, _ = orchestration
    def loader_failure(_path):
        raise RuntimeError("synthetic loader failure")
    def read_failure(_self):
        raise OSError("synthetic unreadable accounting")
    monkeypatch.setattr(adapter, "RecordedLocalModelAdapter", loader_failure)
    monkeypatch.setattr(CampaignBudget, "snapshot", read_failure)
    report = collect_fixture(orchestration)
    combined = json.loads((output / "actionability/combined-accounting.json").read_text())
    assert combined["held_token_upper_bound"] is None and combined["held_intent_slots"] is None
    assert combined["current"]["status"] == "INVALID_ABORT"
    assert combined["predecessor"]["retained_intent_slots"] == 1
    assert not report["admitted"]
