"""Synthetic campaign checks; never load a model or execute the frozen runner."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import threading

import pytest

PATH = Path(__file__).resolve().parents[1] / "tools/run_scaling_replication.py"
SPEC = importlib.util.spec_from_file_location("scaling_replication", PATH)
replication = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replication)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(replication.wire(value) + "\n")


def source_accounting(value):
    return [dict(row_index=0, reported_accounting={key: value if key == "actual_tokens" else 0
                                                for key in replication.COUNTERS}),
            dict(row_index=1, reported_accounting={})]


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    bench = tmp_path / "bench"
    original = bench / "results/original"
    old_config = dict(conditions=[dict(id=f"c{i}") for i in range(66)],
                      worlds=[f"world{i}" for i in range(4)], steps=32)
    put(bench / "original.json", old_config)
    frozen = dict(method_version=replication.INNER_METHOD, counts_toward_verdict=False,
                  interpreter=sys.executable, python=sys.version, config=old_config)
    old_summary = dict(status="INVALID_ABORT", reason="source_abort", aborted_row_indices=list(range(204, 264)),
                       source_accounting=source_accounting(10))
    order = [dict(world_id=w, condition_id=c["id"]) for c in old_config["conditions"] for w in old_config["worlds"]]
    failed = dict(status="INVALID_ABORT", condition_id="failed-condition", world_id="failed-world")
    for name, value in {"freeze.json": frozen, "summary.json": old_summary, "order.json": order,
                        "failed.json": failed, "episodes.jsonl": [dict(original=True)]}.items():
        put(original / name, value)
    audit_path = bench / "audit.json"
    put(audit_path, dict(audit_method=replication.AUDIT_METHOD, audit_status=replication.AUDIT_STATUS,
        source_status="INVALID_ABORT", inference_status="FULL_GRID_INVALID_NO_USABLE_PAIRED_EXPORT",
        counts_toward_verdict=False, original_evidence_unchanged=True, source_config=old_config,
        retained_source_accounting=old_summary["source_accounting"],
        evidence_sha256={str(original / name): replication.hash_file(original / name)
                         for name in ("freeze.json", "summary.json", "order.json", "failed.json", "episodes.jsonl")}))
    config = dict(method_version=replication.METHOD, inner_method_version=replication.INNER_METHOD,
        campaign_id="replication-v1", counts_toward_verdict=False, attempts=1,
        original_result_directory="results/original", original_config="original.json",
        original_config_sha256=replication.hash_file(bench / "original.json"),
        original_sha256={name: replication.hash_file(original / name)
                         for name in ("freeze.json", "summary.json", "order.json", "failed.json", "episodes.jsonl")},
        failed_episode="failed.json", failed_condition="failed-condition", failed_world="failed-world",
        model_paths=dict(small="fixture-small", medium="fixture-medium"),
        clock_observer=dict(period_seconds=5, max_samples=20_000),
        original_audit=dict(path="audit.json", sha256=replication.hash_file(audit_path), status=replication.AUDIT_STATUS))
    config_path = bench / "campaign.json"
    put(config_path, config)
    for name in ("SCALING-replication-v1-contract.md", "tests/test_scaling_replication.py"):
        path = bench / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic campaign source")

    class Runner:
        calls = 0
        freezes = 0
        change_after = False
        abort = False
        exception = False

        def configuration(self):
            return deepcopy(old_config)

        def freeze(self, path, models):
            self.freezes += 1
            value = deepcopy(frozen)
            if self.change_after and self.freezes > 1:
                value["drift"] = True
            return value

        def run(self, path, output, models):
            self.calls += 1
            assert not output.exists()
            assert Path(path) == bench / "original.json"
            output.mkdir()
            if self.exception:
                raise RuntimeError("synthetic collection interruption")
            summary = dict(status="INVALID_ABORT" if self.abort else "PILOT_COMPLETE",
                           n_episodes=264, n_worlds=4, source_accounting=source_accounting(20))
            put(output / "freeze.json", frozen)
            put(output / "order.json", order)
            put(output / "summary.json", summary)
            return summary

    runner = Runner()
    monkeypatch.setattr(replication, "BENCH", bench)
    monkeypatch.setattr(replication, "CONFIG", config_path)
    monkeypatch.setattr(replication, "load_runner", lambda: runner)
    return config_path, bench / "results/replication-v1", runner, config


def test_success_is_one_fresh_attempt_with_original_costs_and_no_acceptance(campaign):
    config_path, output, runner, config = campaign
    before = {name: replication.hash_file(output.parents[1] / config["original_result_directory"] / name)
              for name in config["original_sha256"]}
    result = replication.run(config_path, output)
    assert result["status"] == "REPLICATION_COLLECTED_PENDING_INDEPENDENT_AUDIT"
    assert runner.calls == result["attempts"] == 1 and runner.freezes == 2
    assert result["original_status"] == "INVALID_ABORT" and result["counts_toward_verdict"] is False
    total = result["accounting"]["across_attempt_reported_subtotals"]["actual_tokens"]
    assert total == dict(known_subtotal=30, unavailable_campaigns=[], missing_rows=dict(original=[1], replication=[1]))
    assert result["accounting"]["original"]["source_accounting"][0]["reported_accounting"]["actual_tokens"] == 10
    clock = result["clock_observer"]
    assert clock["status"] == "OBSERVED" and clock["joined"] and clock["samples"] == 2
    assert clock["serialized_bytes"] == (output / "clock-observations.jsonl").stat().st_size
    assert result["campaign_timing"]["monotonic_elapsed_ns"] >= 0
    assert not any(t.name == "r4-clock-observer" for t in threading.enumerate())
    assert before == config["original_sha256"]
    assert all(replication.hash_file(output.parents[1] / config["original_result_directory"] / name) == expected
               for name, expected in before.items())
    assert not (output / "pairs").exists()


@pytest.mark.parametrize("failure", ["abort", "exception", "change_after"])
def test_abort_exception_and_drift_are_retained_without_retry(campaign, failure):
    config_path, output, runner, _ = campaign
    setattr(runner, failure, True)
    result = replication.run(config_path, output)
    assert result["status"] == "INVALID_ABORT" and runner.calls == 1 and result["attempts"] == 1
    assert result["accounting"]["original"]["reported_subtotals"]["actual_tokens"]["known_subtotal"] == 10
    assert result["clock_observer"]["joined"]
    if failure != "exception":
        assert result["accounting"]["replication"]["reported_subtotals"]["actual_tokens"]["known_subtotal"] == 20
    else:
        assert result["accounting"]["across_attempt_reported_subtotals"]["actual_tokens"]["unavailable_campaigns"] == ["replication"]


@pytest.mark.parametrize("failure", ["missing_audit", "audit_hash", "audit_status", "original_drift", "source_drift"])
def test_preflight_failures_never_start_runner(campaign, monkeypatch, failure):
    config_path, output, runner, config = campaign
    if failure == "missing_audit":
        config["original_audit"] = dict(path=None, sha256=None, status=None)
        put(config_path, config)
    elif failure == "audit_hash":
        put(config_path.parent / "audit.json", dict(status="changed"))
    elif failure == "audit_status":
        config["original_audit"]["status"] = "FAIL"
        put(config_path, config)
    elif failure == "original_drift":
        put(config_path.parent / "results/original/failed.json", dict(status="complete"))
    else:
        monkeypatch.setattr(runner, "freeze", lambda *args: dict(changed=True))
    result = replication.run(config_path, output)
    assert result["status"] == "INVALID_ABORT" and runner.calls == 0 and result["attempts"] == 0
    assert not (output / "collection").exists()


def test_existing_output_is_never_overwritten(campaign):
    config_path, output, runner, _ = campaign
    output.mkdir()
    (output / "keep").write_text("original")
    with pytest.raises(FileExistsError):
        replication.run(config_path, output)
    assert runner.calls == 0 and (output / "keep").read_text() == "original"


def test_same_original_evidence_directory_is_forbidden(campaign):
    config_path, output, runner, config = campaign
    with pytest.raises(ValueError, match="original evidence"):
        replication.run(config_path, config_path.parent / config["original_result_directory"] / config["campaign_id"])
    assert runner.calls == 0


@pytest.mark.parametrize("bad", [True, -1, 1.5, "5"])
def test_malformed_known_accounting_is_not_zero(bad):
    with pytest.raises(ValueError, match="invalid reported accounting"):
        replication.accounting(dict(source_accounting=[dict(reported_accounting=dict(actual_tokens=bad))]))
    result = replication.combined_accounting(None, None)
    assert result["across_attempt_reported_subtotals"]["actual_tokens"]["unavailable_campaigns"] == ["original", "replication"]


def test_bounded_observer_records_jump_without_changing_execution(tmp_path, monkeypatch):
    readings = iter([dict(utc="first", realtime_ns=100, monotonic_ns=100, boottime_ns=100),
                     dict(utc="last", realtime_ns=10_000, monotonic_ns=200, boottime_ns=10_000)])
    monkeypatch.setattr(replication, "clocks", lambda: next(readings))
    observer = replication.ClockObserver(tmp_path / "clocks.jsonl", period_seconds=5, max_samples=2)
    observer.start()
    result = observer.finish()
    assert result["status"] == "OBSERVED" and result["samples"] == 2 and result["joined"]
    assert result["maximum_absolute_realtime_minus_monotonic_interval_ns"] == 9800


def test_observer_cap_and_write_failure_are_explicit_and_finite(tmp_path, monkeypatch):
    observer = replication.ClockObserver(tmp_path / "clock.jsonl", period_seconds=5, max_samples=2)
    observer.sample("startup")
    monkeypatch.setattr(observer.stop_event, "wait", lambda _: False)
    observer._watch()
    result = observer.finish()
    assert result["status"] == "INVALID_ABORT" and result["samples"] == 2
    assert "cap reached" in result["errors"][0]
    broken = replication.ClockObserver(tmp_path / "absent/clock.jsonl", period_seconds=5, max_samples=3)
    with pytest.raises(FileNotFoundError):
        broken.start()
    assert broken.finish()["status"] == "INVALID_ABORT"


def test_observer_failure_does_not_retry_or_hide_collection(campaign, monkeypatch):
    config_path, output, runner, _ = campaign
    original = replication.ClockObserver.finish
    def fail_finish(observer):
        result = original(observer)
        result.update(status="INVALID_ABORT", errors=["synthetic diagnostic failure"])
        return result
    monkeypatch.setattr(replication.ClockObserver, "finish", fail_finish)
    result = replication.run(config_path, output)
    assert result["status"] == "INVALID_ABORT" and result["collection_status"] == "PILOT_COMPLETE"
    assert runner.calls == 1 and result["accounting"]["replication"]["reported_subtotals"]["actual_tokens"]["known_subtotal"] == 20
    assert replication.read(output / "collection/summary.json")["status"] == "PILOT_COMPLETE"


def test_final_write_failure_retains_invalid_campaign_and_known_costs(campaign, monkeypatch):
    config_path, output, runner, _ = campaign
    original = replication.save
    def fail_hashes(path, value):
        if Path(path).name == "campaign-artifact-hashes.json":
            raise OSError("synthetic output failure")
        return original(path, value)
    monkeypatch.setattr(replication, "save", fail_hashes)
    result = replication.run(config_path, output)
    assert result["status"] == "INVALID_ABORT" and runner.calls == 1
    assert replication.read(output / "campaign-summary.json")["status"] == "INVALID_ABORT"
    assert result["accounting"]["across_attempt_reported_subtotals"]["actual_tokens"]["known_subtotal"] == 30


@pytest.mark.parametrize("field,value", [("audit_status", "PENDING"), ("audit_method", "another_audit"),
    ("source_status", "PILOT_COMPLETE"), ("counts_toward_verdict", True), ("original_evidence_unchanged", False),
    ("evidence_sha256", {}), ("source_config", {}), ("retained_source_accounting", [])])
def test_pinned_unapproved_or_foreign_audit_cannot_admit_collection(campaign, field, value):
    config_path, output, runner, config = campaign
    path = config_path.parent / "audit.json"
    report = replication.read(path)
    report[field] = value
    put(path, report)
    config["original_audit"]["sha256"] = replication.hash_file(path)
    put(config_path, config)
    result = replication.run(config_path, output)
    assert result["status"] == "INVALID_ABORT" and runner.calls == 0
    assert result["accounting"]["original"]["reported_subtotals"]["actual_tokens"]["known_subtotal"] == 10


@pytest.mark.parametrize("fault", ["thread_start", "finish_after_join"])
def test_clock_startup_or_cleanup_exception_retains_accounting(campaign, monkeypatch, fault):
    config_path, output, runner, _ = campaign
    if fault == "thread_start":
        monkeypatch.setattr(threading.Thread, "start", lambda _: (_ for _ in ()).throw(RuntimeError("cannot start")))
    else:
        finish = replication.ClockObserver.finish
        def broken_finish(observer):
            finish(observer)
            raise RuntimeError("failure after join")
        monkeypatch.setattr(replication.ClockObserver, "finish", broken_finish)
    result = replication.run(config_path, output)
    assert result["status"] == "INVALID_ABORT"
    assert result["accounting"]["original"]["reported_subtotals"]["actual_tokens"]["known_subtotal"] == 10
    assert runner.calls == int(fault == "finish_after_join")
    assert replication.read(output / "campaign-summary.json")["status"] == "INVALID_ABORT"


def test_failed_invalid_summary_rewrite_removes_prior_success(campaign, monkeypatch):
    config_path, output, runner, _ = campaign
    original = replication.save
    def fail_hashes(path, value):
        if Path(path).name == "campaign-artifact-hashes.json":
            raise OSError("synthetic hash failure")
        return original(path, value)
    original_write = Path.write_text
    def fail_rewrite(path, *args, **kwargs):
        if path.name == "campaign-summary.json":
            raise OSError("synthetic persistent summary failure")
        return original_write(path, *args, **kwargs)
    monkeypatch.setattr(replication, "save", fail_hashes)
    monkeypatch.setattr(Path, "write_text", fail_rewrite)
    result = replication.run(config_path, output)
    assert result["status"] == "INVALID_ABORT" and runner.calls == 1
    assert not (output / "campaign-summary.json").exists()
    assert any(error["stage"] == "finalization_recovery" for error in result["errors"])


def test_missing_inner_summary_retains_known_raw_costs_and_missing_rows(campaign, monkeypatch):
    config_path, output, runner, _ = campaign
    def fail_after_rows(path, collection, models):
        runner.calls += 1
        collection.mkdir()
        with (collection / "episodes.jsonl").open("x") as stream:
            stream.write(replication.wire(dict(status="complete", accounting=source_accounting(7)[0]["reported_accounting"])) + "\n")
            stream.write('{"truncated":')
        raise OSError("inner terminal summary unavailable")
    monkeypatch.setattr(runner, "run", fail_after_rows)
    result = replication.run(config_path, output)
    assert result["status"] == "INVALID_ABORT" and runner.calls == 1
    recovered = result["accounting"]["replication"]["reported_subtotals"]["actual_tokens"]
    assert recovered["known_subtotal"] == 7 and recovered["missing_row_indices"] == list(range(1, 264))
    assert result["raw_accounting_recovery"]["accounting_recovery_errors"]


@pytest.mark.parametrize("bad", ['{"accounting":{"actual_tokens":1,"actual_tokens":2}}',
                                '{"accounting":{"actual_tokens":true}}', '{"accounting":{"actual_tokens":NaN}}'])
def test_partial_accounting_does_not_blame_or_erase_a_valid_prior_row(tmp_path, bad):
    path = tmp_path / "episodes.jsonl"
    path.write_text('{"accounting":{"actual_tokens":7}}\n' + bad + '\n')
    result = replication.accounting(replication.partial_accounting(tmp_path))
    assert result["reported_subtotals"]["actual_tokens"]["known_subtotal"] == 7
    assert result["reported_subtotals"]["actual_tokens"]["missing_row_indices"] == list(range(1, 264))


def test_new_files_do_not_enter_frozen_test_glob():
    assert Path(__file__).name == "test_scaling_replication.py"
    assert not Path(__file__).match("test_r4_*.py")
