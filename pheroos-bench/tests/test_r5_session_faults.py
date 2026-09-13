"""Harness behavior tests; temporary cases are not a frozen R5 study run."""

import importlib.util
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import sys

import pytest


PATH = Path(__file__).resolve().parents[1] / "tools/r5_session_faults.py"
SPEC = importlib.util.spec_from_file_location("r5_session_faults", PATH)
faults = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(faults)


@pytest.fixture
def installed():
    site = Path(os.environ.get("PHEROOS_RUNTIME_SITE", "/tmp/pheroos-session-site"))
    interpreter = Path(os.environ.get("PHEROOS_RUNTIME_PYTHON", sys.executable))
    if not (site / "pheroos_runtime/session_v1.py").is_file():
        pytest.skip("an explicit installed experimental Session target is required")
    return interpreter, site


def test_matrix_is_finite_explicit_and_not_confirmatory():
    config = faults.configuration()
    assert len(config["cases"]) == len(set(config["cases"])) == 38
    assert config["counts_toward_verdict"] is False
    assert config["gpu_calls"] == config["paid_provider_calls"] == 0
    assert config["runtime_limits"]["max_calls"] == 8
    path = PATH.parents[1] / "r5-session-faults-v1.json"
    assert json.loads(path.read_text()) == config


def test_effect_counter_does_not_hide_duplicate_invocations(tmp_path):
    faults.effect(tmp_path, "one", "inspect")
    faults.effect(tmp_path, "one", "inspect")
    assert len(faults.effects(tmp_path)) == 2
    with pytest.raises(AssertionError, match="duplicate bounded effect"):
        faults.result(tmp_path, None)


@pytest.mark.parametrize("packet", [
    "not JSON", "[]", '{"call_id":"other","response":{}}',
    '{"call_id":"one","response":{},"extra":1}',
    '{"call_id":"one","call_id":"one","response":{}}',
    '{"call_id":"one","response":NaN}', "x" * 4097,
])
def test_transport_rejects_malformed_or_miscorrelated_receipt(packet):
    with pytest.raises(ValueError):
        faults.parse_packet(packet, "one")


def test_transport_does_not_conflate_response_and_control_channel():
    assert faults.parse_packet('{"call_id":"one","response":{"value":1}}', "one") == {"value": 1}
    with pytest.raises(ValueError):
        faults.parse_packet('{"boundary":"one","pid":123}', "one")


@pytest.mark.parametrize("value", [True, 1.0, "1", 2, None])
def test_independent_objective_requires_exact_integer(value):
    assert faults.verified("inspect", dict(kind="bounded_verified_fact", work_id="inspect", version=1, value=value)) is False


@pytest.mark.parametrize("case,unknown,actual,effects", [
    ("reserved_worker_kill:model", 0, 0, 0),
    ("dispatched_worker_kill:tool", 1, 0, 0),
    ("receipt_before_commit:default", 1, 0, 1),
    ("receipt_committed_before_ack:default", 0, 3, 1),
    ("publication_committed_before_ack:default", 1, 0, 1),
])
def test_real_sigkill_exact_boundary_and_fresh_process_reopen(tmp_path, installed, case, unknown, actual, effects):
    row = faults.execute_case(case, tmp_path / "case", *installed)
    assert row["status"] == "PASS", row
    assert row["worker_exitcode"] == -signal.SIGKILL and row["actual_sigkill"]
    assert row["acknowledgment_received"] is False and row["fresh_process_reopen"] is True
    assert row["boundary"]["stage"] == faults.BOUNDARIES[case.split(":")[0]]
    assert row["accounting"]["unknown_calls"] == unknown
    assert row["accounting"]["actual_tokens"] == actual
    assert len(row["effects"]) == effects
    assert row["recovery_elapsed_ns"] >= 0


@pytest.mark.parametrize("case", [
    "coordinator_restart_after_checkpoint:default", "transient_store_lock:receive",
    "cancellation_dispatch_order:dispatch_first", "stale_lease_publication:default",
    "mailbox:reverse", "mailbox:count", "provenance_substitution:boolean_objective",
    "oversized_reply_known_usage:default", "transport:delayed_reply", "transport:lost_reply",
    "adapter_failure:tool_after_effect", "stale_checkpoint:default", "corrupted_database_copy:default",
])
def test_selected_cross_boundary_counterexamples(tmp_path, installed, case):
    row = faults.execute_case(case, tmp_path / "case", *installed)
    assert row["status"] == "PASS", row
    assert all(count == 1 for count in row["effects_by_call"].values())
    if case == "corrupted_database_copy:default":
        assert row["accounting"] is None and row["runtime_disposition"] == "ABORT_UNAVAILABLE"
    else:
        assert isinstance(row["snapshot"]["events"], list)
    if case == "transport:lost_reply":
        assert row["transport_timeout_observed"] is True


def test_result_directory_cannot_be_reused(tmp_path, installed):
    output = tmp_path / "case"
    output.mkdir()
    with pytest.raises(FileExistsError):
        faults.execute_case("stale_checkpoint:default", output, *installed)


def test_missed_precommit_hook_cannot_fall_through_to_an_ack_boundary(monkeypatch, tmp_path):
    class Session:
        def claim(self, *args, **kwargs):
            return object()
        def receive(self, *args):
            return None
    @contextmanager
    def missed(*args):
        yield
    monkeypatch.setattr(faults, "new_session", lambda *args: Session())
    monkeypatch.setattr(faults, "reserve", lambda *args, **kwargs: None)
    monkeypatch.setattr(faults, "dispatch", lambda *args: None)
    monkeypatch.setattr(faults, "reply", lambda *args, **kwargs: {})
    monkeypatch.setattr(faults, "before_commit_pause", missed)
    monkeypatch.setattr(faults, "pause", lambda *args, **kwargs: pytest.fail("wrong fallback marker emitted"))
    with pytest.raises(RuntimeError, match="hook did not fire"):
        faults.crash_worker("receipt_before_commit:default", tmp_path, 0)


def valid_snapshot():
    return dict(call_count=1, actual_tokens=3, reserved_tokens=0, unknown_tokens=0, unknown_calls=0,
                calls=[dict(id="one", action="model.generate", state="received", prompt=2, maximum=8,
                            reserved=10, actual=3, response='{"prompt_tokens":2,"completion_tokens":1}')])


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(actual_tokens=True), lambda s: s.update(actual_tokens=-1),
    lambda s: s["calls"][0].update(actual=True), lambda s: s["calls"][0].update(actual=None),
    lambda s: s["calls"][0].update(actual=4), lambda s: s["calls"][0].update(reserved=-1),
    lambda s: s["calls"][0].update(response="invalid JSON"),
    lambda s: s["calls"][0].update(response='{"prompt_tokens":true,"completion_tokens":2}'),
    lambda s: s["calls"][0].update(response='{"prompt_tokens":2,"completion_tokens":1,"completion_tokens":1}'),
    lambda s: s["calls"][0].update(response='{"prompt_tokens":2,"completion_tokens":9}'),
    lambda s: s["calls"][0].update(state="dispatched"),
])
def test_accounting_rejects_malformed_components_without_coercing_zero(mutation):
    snapshot = valid_snapshot()
    mutation(snapshot)
    with pytest.raises((ValueError, AssertionError)):
        faults.accounting(snapshot)


def test_zero_token_unknown_call_is_still_unknown():
    snapshot = dict(call_count=1, actual_tokens=0, reserved_tokens=0, unknown_tokens=0, unknown_calls=1,
        calls=[dict(id="one", action="tool.evaluate", state="dispatched", prompt=0, maximum=0,
                    reserved=0, actual=None, response=None)])
    assert faults.accounting(snapshot)["unknown_calls"] == 1


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.pop(), lambda rows: rows.append(deepcopy(rows[0])),
    lambda rows: rows[0].update(case=rows[1]["case"]), lambda rows: rows[0].update(status="UNKNOWN"),
    lambda rows: rows[0].update(counts_toward_verdict=True),
])
def test_fault_grid_rejects_missing_duplicate_and_misidentified_results(mutation):
    rows = [dict(method_version=faults.METHOD, case=case, counts_toward_verdict=False, status="PASS") for case in faults.CASES]
    faults.validate_outcomes(rows)
    mutation(rows)
    with pytest.raises(ValueError):
        faults.validate_outcomes(rows)
