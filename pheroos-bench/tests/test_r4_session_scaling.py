"""Behavior checks against the separately installed experimental runtime."""
from copy import deepcopy
import json

import pytest

pytest.importorskip("pheroos_runtime.session_v1")
from pheroos_bench import r4_session_scaling as runner


class Model:
    identity = {"fixture": "bounded-test-adapter"}
    def __init__(self, *, hook=None, reply=None, token_count=30):
        self.hook, self.reply, self.token_count = hook, reply, token_count
        self.calls = []

    def count_tokens(self, messages):
        return self.token_count

    def generate(self, messages, max_new_tokens, seed):
        self.calls.append((deepcopy(messages), max_new_tokens, seed))
        if self.hook:
            self.hook()
        return dict(text=self.reply or '{"action":"inspect","target":"missing"}',
                    prompt_tokens=self.token_count, completion_tokens=5, elapsed_ns=1,
                    peak_cuda_bytes=0)


class Models:
    def __init__(self, model):
        self.model, self.selected = model, []
    def get(self, key):
        self.selected.append(key)
        self.model.identity = {"model_manifest": {name: value for name, value in runner.configuration()["models"][key].items()
                                                  if name != "manifest_sha256"}, "fixture": "bounded-test-adapter"}
        return self.model


def run(tmp_path, *, model=None, condition=None, config=None, clock=None):
    config = config or runner.configuration()
    condition = condition or config["conditions"][0]
    return runner.episode(tmp_path / "episode", config["worlds"][0], condition,
                          config, Models(model or Model()), **({"clock": clock} if clock else {}))


@pytest.mark.parametrize("n", runner.COUNTS)
def test_declared_agents_act_under_same_aggregate_budget(tmp_path, n):
    config = runner.configuration()
    condition = next(c for c in config["conditions"] if c["id"] == f"fixed_calls-small-private-n{n}")
    row = run(tmp_path, condition=condition)
    assert row["status"] == "complete"
    assert row["accounting"]["model_calls"] == row["accounting"]["tool_calls"] == 32
    assert row["active_agents"] == n
    assert row["accounting"]["actual_tokens"] == 32 * 35
    assert row["accounting"]["unknown_calls"] == 0
    assert row["success"] is False  # Unknown inspection targets are ordinary failed actions.
    assert len(row["ledger_calls"]) == 64
    assert [r["agent"] for r in row["records"]] == [f"agent{i % n}" for i in range(32)]


def test_late_known_generation_cannot_publish_or_become_free(tmp_path):
    now = [0]
    def late():
        now[0] += 31_000_000_000
    config = runner.configuration()
    condition = next(c for c in config["conditions"] if c["regime"] == "fixed_deadline")
    row = run(tmp_path, model=Model(hook=late), condition=condition, clock=lambda: now[0])
    assert row["status"] == "complete" and row["stop_reason"] == "deadline"
    assert row["accounting"]["actual_tokens"] == 35
    assert row["accounting"]["model_calls"] == 1 and row["accounting"]["tool_calls"] == 0
    assert row["records"][0]["response"] is not None
    assert row["records"][0]["evaluation"] is None
    assert row["records"][0]["published"] is False
    snapshot = json.loads((tmp_path / "episode/snapshot.json").read_text())
    assert snapshot["run"]["status"] == "cancelled" and not snapshot["artifacts"]


def test_deadline_rechecks_publication_after_tool_execution(tmp_path, monkeypatch):
    now = [0]
    actual_apply = runner.tasks.apply
    def slow(*args):
        value = actual_apply(*args)
        now[0] += 31_000_000_000
        return value
    monkeypatch.setattr(runner.tasks, "apply", slow)
    config = runner.configuration()
    condition = next(c for c in config["conditions"] if c["regime"] == "fixed_deadline")
    row = run(tmp_path, condition=condition, clock=lambda: now[0])
    assert row["status"] == "complete" and row["stop_reason"] == "deadline"
    assert row["accounting"]["actual_tokens"] == 35
    assert row["accounting"]["tool_calls"] == 1
    assert row["records"][0]["evaluation"] is not None
    assert not row["records"][0]["published"]
    assert not json.loads((tmp_path / "episode/snapshot.json").read_text())["artifacts"]


def test_deadline_rechecked_after_authority_callback(tmp_path, monkeypatch):
    import pheroos_runtime.session_driver_v1 as runtime_driver
    now = [0]
    original = runtime_driver.current_authorization
    def slow(*args):
        record = original(*args)
        now[0] += 31_000_000_000
        return record
    monkeypatch.setattr(runtime_driver, "current_authorization", slow)
    config = runner.configuration()
    condition = next(c for c in config["conditions"] if c["regime"] == "fixed_deadline")
    model = Model()
    row = run(tmp_path, model=model, condition=condition, clock=lambda: now[0])
    assert row["status"] == "complete" and row["stop_reason"] == "deadline"
    assert row["accounting"]["actual_tokens"] == row["accounting"]["model_calls"] == 0
    assert row["accounting"]["unknown_calls"] == 0 and not model.calls
    assert row["ledger_calls"][0]["state"] == "abandoned"


def test_unknown_backend_retains_reservation_and_never_retries(tmp_path):
    def crash():
        raise RuntimeError("lost backend after dispatch")
    model = Model(hook=crash)
    row = run(tmp_path, model=model)
    assert row["status"] == "INVALID_ABORT" and row["success"] is None
    assert len(model.calls) == row["accounting"]["model_calls"] == 1
    assert row["accounting"]["actual_tokens"] == 0
    assert row["accounting"]["unknown_tokens"] == 286
    assert row["accounting"]["unknown_calls"] == 1
    assert row["ledger_calls"][0]["state"] == "dispatched"


def test_budget_denial_is_valid_stop_with_no_invented_receipt(tmp_path):
    config = runner.configuration()
    config["token_cap"] = 285
    row = run(tmp_path, config=config)
    assert row["status"] == "complete" and row["stop_reason"] == "budget"
    assert row["accounting"]["model_calls"] == row["accounting"]["actual_tokens"] == 0
    assert row["records"][0]["receipt_ids"] == []
    assert row["accounting"]["monetary_cost"] is None


def test_raw_receipt_substitution_is_invalid_before_task_evaluation(tmp_path, monkeypatch):
    from pheroos_runtime.session_v1 import Session
    original = Session.call
    def substitute(self, key):
        value = original(self, key)
        value["request"]["seed"] += 1
        return value
    monkeypatch.setattr(Session, "call", substitute)
    row = run(tmp_path)
    assert row["status"] == "INVALID_ABORT"
    assert row["accounting"]["actual_tokens"] == 35 and row["accounting"]["tool_calls"] == 0
    assert "differs from durable" in row["errors"][0]["message"]


def test_unreadable_snapshot_is_explicit_unknown_accounting(tmp_path, monkeypatch):
    from pheroos_runtime.session_v1 import Session
    monkeypatch.setattr(Session, "snapshot", lambda self: (_ for _ in ()).throw(OSError("read lost")))
    config = runner.configuration()
    config["token_cap"] = 0
    row = run(tmp_path, config=config)
    assert row["status"] == "INVALID_ABORT" and row["accounting"] is None
    assert row["ledger_calls"] is None
    assert (tmp_path / "episode/session.sqlite").exists()


def test_malformed_snapshot_accounting_retains_abort_record(tmp_path, monkeypatch):
    from pheroos_runtime.session_v1 import Session
    original = Session.snapshot
    def broken(self):
        value = original(self)
        value["calls"][0]["response"] = "{broken JSON"
        return value
    monkeypatch.setattr(Session, "snapshot", broken)
    config = runner.configuration()
    config["token_cap"] = 300
    row = run(tmp_path, config=config)
    assert row["status"] == "INVALID_ABORT" and row["accounting"] is None
    assert row["ledger_calls"][0]["response"] == "{broken JSON"
    assert (tmp_path / "episode/episode.json").exists()


def test_hidden_scorer_time_cannot_change_deadline_execution(tmp_path, monkeypatch):
    now = [0]
    def slow_score(*args):
        now[0] += 31_000_000_000
        return False
    monkeypatch.setattr(runner.tasks, "score", slow_score)
    config = runner.configuration()
    condition = next(c for c in config["conditions"] if c["regime"] == "fixed_deadline")
    row = run(tmp_path, condition=condition, clock=lambda: now[0])
    assert row["status"] == "complete" and row["accounting"]["model_calls"] == 32
    assert row["accounting"]["elapsed_ns"] == 0
    assert row["accounting"]["evaluator_elapsed_ns"] > 30_000_000_000


def test_mixed_cohort_never_hides_larger_model_work():
    config = runner.configuration()
    condition = next(c for c in config["conditions"] if c["cohort"] == "mixed")
    assert [runner.model_for(condition, step) for step in range(32)] == ["small"] * 28 + ["medium"] * 4
    assert len({c["id"] for c in config["conditions"]}) == len(config["conditions"])


def test_token_regime_has_an_independent_binding_ceiling():
    config = runner.configuration()
    condition = next(c for c in config["conditions"] if c["regime"] == "fixed_tokens")
    assert runner.episode_token_cap(config, condition) == 8192
    condition = next(c for c in config["conditions"] if c["regime"] == "fixed_calls")
    assert runner.episode_token_cap(config, condition) == 65536


def test_execution_order_is_deterministic_complete_and_varies_treatments():
    config = runner.configuration()
    order = runner.execution_order(config)
    assert order == runner.execution_order(config)
    assert len(order) == len({(w, c["id"]) for w, c in order}) == 264
    assert len({c["id"] for _, c in order[:8]}) > 1


def test_failed_model_loading_is_recorded(tmp_path, monkeypatch):
    import pheroos_runtime.session_driver_v1 as adapter
    def fail(_):
        raise RuntimeError("controlled load failure")
    monkeypatch.setattr(adapter, "LocalModelAdapter", fail)
    pool = runner.LocalModels({"small": tmp_path})
    with pytest.raises(RuntimeError, match="controlled load failure"):
        pool.get("small")
    assert len(pool.loads) == 1 and pool.loads[0]["status"] == "INVALID_ABORT"
    assert pool.loads[0]["elapsed_ns"] >= 0 and pool.loads[0]["model_ref"] == "small"


def test_unstarted_grid_member_retains_unavailable_accounting(tmp_path):
    config = runner.configuration()
    row = runner.uncollected(tmp_path, config["worlds"][0], config["conditions"][0], {"type": "PriorAbort"})
    assert row["status"] == "INVALID_ABORT" and row["stop_reason"] == "not_started"
    assert row["accounting"] is None and row["ledger_calls"] is None


def test_history_projection_cannot_carry_hidden_scores_or_raw_transcripts():
    record = dict(id="s0", world_id="world", step=0, agent="agent0", task_version=1,
                  valid=False, feedback="invalid", artifact=None, origin_identity="origin",
                  action="invalid", semantic_action={"invalid": True}, runtime_artifact_ref="ref",
                  prefix_success=False, response={"text": "raw"}, messages=["raw transcript"])
    before = runner.history_record(record)
    record["prefix_success"] = True
    record["messages"].append("hidden diagnosis")
    assert runner.history_record(record) == before
    assert not {"prefix_success", "response", "messages"} & before.keys()


def test_cleanup_failure_preserves_complete_invalid_grid(tmp_path, monkeypatch):
    import pheroos_bench.r4_measurement as measurement
    config = runner.configuration()
    config_path = tmp_path / "config.json"
    config_path.write_text(runner.wire(config))
    class BrokenCleanup:
        loads = []
        def __init__(self, paths):
            pass
        def get(self, key):
            raise RuntimeError("load unavailable")
        def close(self):
            raise RuntimeError("cleanup unavailable")
    monkeypatch.setattr(runner, "LocalModels", BrokenCleanup)
    monkeypatch.setattr(runner, "freeze", lambda *args: {"frozen": True})
    monkeypatch.setattr(runner, "environment", lambda: {})
    monkeypatch.setattr(measurement, "summarize", lambda rows, config: {"status": "INVALID_ABORT"})
    output = tmp_path / "study"
    result = runner.run(config_path, output, {})
    rows = [json.loads(line) for line in (output / "episodes.jsonl").read_text().splitlines()]
    assert len(rows) == 264 and all(row["accounting"] is None for row in rows)
    assert result["collection_abort"]["stage"] == "model_cleanup"
    assert result["collection_abort"]["prior_abort"]["message"] == "load unavailable"
