"""Provider-free capability consumer checks; model responses/usage are fixtures."""

from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from pheroos_bench import r3_session_capability as pilot


PATCH = {"action": "submit", "candidate": {"code_lines": [
    "def clamp(value, lower, upper):", "    return max(lower, min(value, upper))"]}}


class ModelFixture:
    identity = {"model_id": "test-only", "synthetic_usage": True}

    def __init__(self, text="not JSON", fault=None):
        self.text, self.fault, self.calls, self.prompts = text, fault, 0, []

    def count_tokens(self, messages):
        return 10

    def generate(self, messages, maximum, seed):
        self.calls += 1
        self.prompts.append(deepcopy(messages))
        assert maximum == 256
        assert seed >= 2081
        if self.fault:
            raise RuntimeError(self.fault)
        return dict(text=self.text, prompt_tokens=10, completion_tokens=2,
                    elapsed_ns=1, peak_cuda_bytes=1)


@pytest.fixture
def installed_runtime():
    pytest.importorskip("pheroos_runtime.session_v1", reason="explicit separately installed Session required")
    return pilot.runtime()


def test_declared_config_and_indexes_are_frozen_public_surfaces():
    path = Path(__file__).parents[1] / "r3-session-capability-v1.json"
    assert json.loads(path.read_text()) == pilot.configuration()
    assert pilot.inspection_targets("code_repair/clamp") == ["below_lower", "inside_bounds", "above_upper"]
    assert pilot.inspection_targets("code_repair/chunk_count") == ["empty", "full_chunks", "partial_chunk"]
    assert pilot.inspection_targets("evidence_revision/dispatch_limit") == ["policy", "capacity"]
    assert pilot.configuration()["counts_toward_verdict"] is False
    assert pilot.configuration()["models"]["qwen_3b"]["revision"] == "488639f1ff808d1d3d0ba301aef8c11461451ec5"


@pytest.mark.parametrize("model_id", list(pilot.MODELS))
@pytest.mark.parametrize("condition", pilot.CONDITIONS)
def test_actual_session_framed_model_tool_receipts_and_publication(tmp_path, installed_runtime, model_id, condition):
    model = ModelFixture("```json\n" + json.dumps(PATCH) + "\n```")
    row = pilot.episode(model, pilot.configuration(), model_id, "code_repair/clamp", condition, tmp_path / "episode")
    assert row["outcome"] == "success", row["error"]
    expected = (6, 6) if condition == pilot.CONDITIONS[0] else (1, 4)
    assert (row["model_calls"], row["tool_calls"]) == expected
    assert model.calls == expected[0]
    assert row["actual_tokens"] == model.calls * 12
    assert row["accounting_status"] == "KNOWN"
    assert row["ledger"]["run"]["status"] == "completed"
    assert len(row["ledger"]["artifacts"]) == expected[1]
    for turn in row["turns"]:
        call = turn["tool_call"]
        assert call["response"] == turn["evaluation_response"]
        assert turn["publication"]["call_id"] == call["id"]
        assert turn["publication"]["scope_ref"]
        assert turn["publication"]["value"]["kind"] == "r3_evaluation_fact_v1"
        assert turn["verification_recomputations"] == 1
        if turn["response"]:
            assert turn["model_call"]["response"]["text"] == model.text
            assert turn["framing"]["kind"] == "sole_json_fence"
            assert turn["model_call"]["request"]["seed"] == 2081 + turn["step"]
    assert all(row[key] > 0 for key in ("request_bytes", "response_bytes", "trace_bytes"))


def test_diagnostic_receipts_are_all_current_and_obtained_before_only_model_call(tmp_path, installed_runtime):
    model = ModelFixture()
    row = pilot.episode(model, pilot.configuration(), "qwen_3b", "evidence_revision/dispatch_limit", pilot.CONDITIONS[1], tmp_path / "episode")
    assert row["outcome"] == "failed"
    assert (row["model_calls"], row["tool_calls"]) == (1, 3)
    public = json.loads(model.prompts[0][1]["content"])
    assert public["task"]["turn"] == 6
    assert public["task"]["task_version"] == 2
    receipts = public["tool_receipts"]
    assert [r["artifact"]["receipt"]["source_id"] for r in receipts] == ["policy", "capacity"]
    assert [r["artifact"]["receipt"]["version"] for r in receipts] == [1, 2]
    assert all(r["step"] == 5 and r["task_version"] == 2 for r in receipts)
    assert all(r["id"] == row["turns"][index]["publication"]["ref"] for index, r in enumerate(receipts))
    assert len(row["turns"][-1]["consumed_ids"]) == 2


def test_invalid_actions_publish_only_valid_evaluation_facts_not_task_evidence(tmp_path, installed_runtime):
    row = pilot.episode(ModelFixture(), pilot.configuration(), "qwen_1_5b", "code_repair/clamp", pilot.CONDITIONS[0], tmp_path / "episode")
    assert row["outcome"] == "failed"
    assert row["actual_tokens"] == 72
    assert len(row["ledger"]["artifacts"]) == 6
    assert all(not record["valid"] and record["artifact"] is None for record in row["records"])
    for artifact in row["ledger"]["artifacts"]:
        fact = json.loads(artifact["value"])
        assert fact["kind"] == "r3_evaluation_fact_v1"
        assert fact["result"]["valid"] is False and fact["result"]["artifact"] is None


def test_unknown_execution_aborts_but_retains_reserved_usage_without_retry(tmp_path, installed_runtime):
    model = ModelFixture(fault="interrupted after dispatch")
    row = pilot.episode(model, pilot.configuration(), "qwen_3b", "code_repair/clamp", pilot.CONDITIONS[0], tmp_path / "episode")
    assert row["outcome"] == "INVALID_ABORT"
    assert model.calls == row["model_calls"] == 1
    assert row["ledger"]["unknown_calls"] == 1
    assert row["ledger"]["unknown_tokens"] == 266
    assert row["actual_tokens"] == 0
    assert row["accounting_status"] == "UNRESOLVED"


def test_snapshot_failure_retains_original_error_and_reports_unavailable_costs(tmp_path, installed_runtime, monkeypatch):
    Session, _, _ = installed_runtime
    def unreadable(self):
        raise OSError("snapshot unavailable")
    monkeypatch.setattr(Session, "snapshot", unreadable)
    row = pilot.episode(ModelFixture(fault="original interruption"), pilot.configuration(), "qwen_3b", "code_repair/clamp", pilot.CONDITIONS[0], tmp_path / "episode")
    assert row["outcome"] == "INVALID_ABORT"
    assert row["error"]["message"] == "original interruption"
    assert "snapshot unavailable" in row["error"]["snapshot_error"]
    assert row["ledger"] is row["usage"] is row["actual_tokens"] is row["model_calls"] is row["tool_calls"] is None
    assert json.loads((tmp_path / "episode/episode.json").read_text()) == row


def test_malformed_snapshot_cannot_erase_a_started_episode_report(tmp_path, installed_runtime, monkeypatch):
    Session, _, _ = installed_runtime
    snapshot = Session.snapshot
    def malformed(self):
        result = snapshot(self)
        result["calls"][0]["actual"] = False
        return result
    monkeypatch.setattr(Session, "snapshot", malformed)
    row = pilot.episode(ModelFixture(), pilot.configuration(), "qwen_3b", "code_repair/clamp", pilot.CONDITIONS[0], tmp_path / "episode")
    assert row["outcome"] == "INVALID_ABORT" and row["accounting_status"] == "UNRESOLVED"
    assert row["actual_tokens"] is row["usage"] is row["model_calls"] is None
    assert row["ledger"]["calls"] and row["turns"]
    assert row["error"]["reporting_error"]
    assert json.loads((tmp_path / "episode/episode.json").read_text()) == row


def test_known_tokens_survive_publication_failure(tmp_path, installed_runtime, monkeypatch):
    Session, _, _ = installed_runtime
    def deny(*args, **kwargs):
        raise PermissionError("current publication denied")
    monkeypatch.setattr(Session, "publish", deny)
    row = pilot.episode(ModelFixture(json.dumps(PATCH)), pilot.configuration(), "qwen_1_5b", "code_repair/clamp", pilot.CONDITIONS[0], tmp_path / "episode")
    assert row["outcome"] == "INVALID_ABORT"
    assert row["actual_tokens"] == 12
    assert row["accounting_status"] == "KNOWN"
    assert row["records"] == row["ledger"]["artifacts"] == []
    assert row["turns"][0]["response"]["text"] == json.dumps(PATCH)


def test_rejected_large_reply_retains_known_usage_and_zero_token_unknown_is_unresolved(tmp_path, installed_runtime, monkeypatch):
    row = pilot.episode(ModelFixture("x" * 65537), pilot.configuration(), "qwen_3b", "code_repair/clamp", pilot.CONDITIONS[0], tmp_path / "large")
    assert row["outcome"] == "INVALID_ABORT" and row["accounting_status"] == "KNOWN"
    assert row["actual_tokens"] == 12 and row["ledger"]["calls"][0]["state"] == "response_rejected"
    assert row["response_bytes"] > row["retained_response_bytes"]
    assert pilot.reconcile(row)["actual_tokens"] == 12
    def failed_tool(arguments):
        raise RuntimeError("tool interrupted after dispatch")
    monkeypatch.setattr(pilot, "evaluation", failed_tool)
    row = pilot.episode(ModelFixture(), pilot.configuration(), "qwen_3b", "code_repair/clamp", pilot.CONDITIONS[1], tmp_path / "unknown")
    assert row["outcome"] == "INVALID_ABORT" and row["accounting_status"] == "UNRESOLVED"
    assert row["ledger"]["unknown_calls"] == 1 and row["ledger"]["unknown_tokens"] == 0
    assert row["model_calls"] == 0 and row["tool_calls"] == 1
    assert pilot.reconcile(row)["unknown_calls"] == 1


def test_fitted_history_evicts_only_autonomous_whole_receipts():
    class Sized:
        def count_tokens(self, messages):
            return 2000 if json.loads(messages[1]["content"])["tool_receipts"] else 100
    result = pilot.tasks.apply("code_repair/clamp", 0, [], '{"action":"inspect","target":"below_lower"}')
    record = pilot.record("ref", "code_repair/clamp", 0, {"result": result})
    _, memory, preflight, dropped = pilot.fitted_messages(Sized(), "code_repair/clamp", 1, [record], True)
    assert memory == [] and dropped == ["ref"] and len(preflight) == 2
    with pytest.raises(ValueError, match="context bound"):
        pilot.fitted_messages(Sized(), "code_repair/clamp", 5, [record], False)


def test_bound_receipt_rejects_request_substitution_with_known_reply(tmp_path, installed_runtime, monkeypatch):
    Session, _, _ = installed_runtime
    call = Session.call
    def substituted(self, call_id):
        result = call(self, call_id)
        if result["action"] == "model.generate":
            result["request"]["seed"] += 1
        return result
    monkeypatch.setattr(Session, "call", substituted)
    row = pilot.episode(ModelFixture(), pilot.configuration(), "qwen_3b", "code_repair/clamp", pilot.CONDITIONS[0], tmp_path / "episode")
    assert row["outcome"] == "INVALID_ABORT"
    assert row["actual_tokens"] == 12
    assert row["turns"][0]["response"] is not None
    assert not row["records"]


def test_changed_adapter_reply_cannot_replace_the_settled_proposal(tmp_path, installed_runtime, monkeypatch):
    _, Driver, _ = installed_runtime
    generate = Driver.generate
    def substituted(self, *args, **kwargs):
        result = generate(self, *args, **kwargs)
        result["text"] = json.dumps(PATCH)
        return result
    monkeypatch.setattr(Driver, "generate", substituted)
    row = pilot.episode(ModelFixture(), pilot.configuration(), "qwen_3b", "code_repair/clamp", pilot.CONDITIONS[0], tmp_path / "episode")
    assert row["outcome"] == "INVALID_ABORT" and row["actual_tokens"] == 12
    assert row["turns"][0]["response"]["text"] == json.dumps(PATCH)
    assert json.loads(row["ledger"]["calls"][0]["response"])["text"] == "not JSON"
    assert row["records"] == []


def test_full_grid_summary_reconciles_failed_costs_and_rejects_corruption(tmp_path, installed_runtime):
    rows = [pilot.episode(ModelFixture(), pilot.configuration(), model, world, condition, tmp_path / str(index))
            for index, (model, world, condition) in enumerate(
                (m, w, c) for m in pilot.MODELS for w in pilot.tasks.world_ids() for c in pilot.CONDITIONS)]
    report = pilot.summarize(rows)
    assert report["status"] == "CAPABILITY_DIAGNOSTIC_COMPLETE"
    assert report["counts_toward_verdict"] is False
    for model in pilot.MODELS:
        assert report["groups"][model][pilot.CONDITIONS[0]]["known_tokens"] == 288
        assert report["groups"][model][pilot.CONDITIONS[1]]["known_tokens"] == 48
        assert sum(group["failed"] for group in report["groups"][model].values()) == 8
    with pytest.raises(ValueError, match="missing or duplicate"):
        pilot.summarize(rows[:-1] + rows[:1])
    corrupt = deepcopy(rows)
    corrupt[0]["actual_tokens"] = 0
    with pytest.raises(ValueError, match="reconcile"):
        pilot.summarize(corrupt)
    mutations = [(field, value) for field in ("prompt", "maximum", "reserved", "actual")
                 for value in (-1, True, 1.5, "1", None)]
    mutations += [("state", "invented"), ("work_id", "missing"), ("version", True), ("epoch", -1)]
    for field, value in mutations:
        row = deepcopy(rows[0])
        row["ledger"]["calls"][0][field] = value
        with pytest.raises(ValueError):
            pilot.summarize([row, *rows[1:]])
    for field in ("prompt_tokens", "completion_tokens"):
        for value in (-1, True, 1.5, "1", None):
            row = deepcopy(rows[0])
            call = row["ledger"]["calls"][0]
            response = json.loads(call["response"])
            response[field] = value
            call["response"] = json.dumps(response)
            with pytest.raises(ValueError):
                pilot.summarize([row, *rows[1:]])
    for member, field, value in (("request", "task_id", "turn-5"), ("request", "version", 2),
                                 ("response", "model_ref", "other")):
        row = deepcopy(rows[0])
        call = row["ledger"]["calls"][0]
        payload = json.loads(call[member])
        payload[field] = value
        call[member] = json.dumps(payload)
        with pytest.raises(ValueError, match="binding"):
            pilot.summarize([row, *rows[1:]])
    row = deepcopy(rows[0])
    row["ledger"]["calls"][1]["id"] = row["ledger"]["calls"][0]["id"]
    with pytest.raises(ValueError, match="duplicate"):
        pilot.summarize([row, *rows[1:]])


def test_sources_freeze_before_loading_and_changed_sources_invalidate_known_costs(tmp_path, installed_runtime, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "collection"
    source.write_text("before")
    freeze = {"config": pilot.configuration(), "models": {name: {} for name in pilot.MODELS},
              "files_sha256": {str(source): pilot.file_hash(source)}}
    monkeypatch.setattr(pilot, "verified_inputs", lambda *args: freeze)
    class LocalFixture(ModelFixture):
        def __init__(self, path):
            assert json.loads((output / "freeze.json").read_text()) == freeze
            super().__init__()
            self.identity = {"model_manifest": {}}
            self.model = SimpleNamespace(model=type("Qwen2ForCausalLM", (), {})())
        def generate(self, *args):
            source.write_text("after")
            return super().generate(*args)
    Session, Driver, _ = installed_runtime
    monkeypatch.setattr(pilot, "runtime", lambda: (Session, Driver, LocalFixture))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0,
        memory_allocated=lambda: 0, empty_cache=lambda: None)))
    status = pilot.main(["--output", str(output), "--config", "fixture", "--runtime-site", "fixture",
                         "--small-model", "fixture-small", "--large-model", "fixture-large"])
    assert status == 2
    summary = json.loads((output / "summary.json").read_text())
    assert summary["status"] == "INVALID_ABORT" and summary["frozen_inputs_unchanged"] is False
    assert all(group["known_tokens"] > 0 for model in summary["groups"].values() for group in model.values())
    assert len(json.loads((output / "episodes.json").read_text())) == 16


def test_existing_output_is_rejected_before_model_or_runtime_loading(tmp_path, monkeypatch):
    def forbidden(*args):
        pytest.fail("must not inspect or load models")
    monkeypatch.setattr(pilot, "verified_inputs", forbidden)
    with pytest.raises(FileExistsError):
        pilot.main(["--output", str(tmp_path), "--config", "none", "--runtime-site", "none",
                    "--small-model", "none", "--large-model", "none"])
