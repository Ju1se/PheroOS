"""Exact malformed-JSON oracle correction; synthetic files, no fault runs."""

import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "tools/audit_r5_session_faults_v2.py"
SPEC = importlib.util.spec_from_file_location("r5_audit_v2", PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def sample(directory):
    call = dict(id="one", action="model.generate", state="dispatched", prompt=2, maximum=8, reserved=10, actual=None, response=None)
    try:
        json.loads("malformed JSON")
    except json.JSONDecodeError as error:
        refusal = f"{type(error).__name__}: {error}"
    child = dict(status="PASS", snapshot=dict(calls=[call], artifacts=[]), before={}, refusals=[refusal],
                 accounting=dict(actual_tokens=0, reserved_tokens=0, unknown_tokens=10, unknown_calls=1),
                 action_counts=dict(model_dispatches=1, tool_dispatches=0), effects=[], effects_by_call={}, inspection_sequence_elapsed_ns=1)
    row = dict(method_version=audit.base.METHOD, case=audit.CASE, counts_toward_verdict=False, elapsed_ns=2, **child)
    (directory / "transport.json").write_text(audit.base.wire(dict(raw_packet="malformed JSON")))
    synchronize_inspector(directory, row)
    return row


def synchronize_inspector(directory, row):
    parent = {"method_version", "case", "counts_toward_verdict", "elapsed_ns"}
    child = {k: v for k, v in row.items() if k not in parent}
    (directory / "inspector-transport.json").write_text(audit.base.wire(dict(stdout=audit.base.wire(child), stderr="")))


def test_preserved_v1_fails_and_exact_adapter_runs_all_other_checks(tmp_path):
    row = sample(tmp_path)
    with pytest.raises(ValueError, match="reported refusal observation differs"):
        audit.base.observations(audit.CASE, row, tmp_path)
    applied, equal_before = [], audit.base.equal
    audit.observations(audit.base.observations, audit.CASE, row, tmp_path, applied)
    assert len(applied) == 1 and applied[0]["corrected_expected_label"] == "JSONDecodeError"
    assert audit.base.equal is equal_before
    assert row["accounting"]["unknown_tokens"] == 10 and row["accounting"]["unknown_calls"] == 1


@pytest.mark.parametrize("change", [
    lambda row: row.update(refusals=["ValueError: Expecting value: line 1 column 1 (char 0)"]),
    lambda row: row.update(refusals=["JSONDecodeError: another error"]),
    lambda row: row["accounting"].pop("unknown_calls"),
    lambda row: row["accounting"].update(unknown_calls=0, unknown_tokens=0),
    lambda row: row["snapshot"]["calls"][0].update(state="received", actual=3),
])
def test_correction_rejects_other_labels_text_or_missing_unknown(change, tmp_path):
    row = sample(tmp_path)
    change(row)
    synchronize_inspector(tmp_path, row)
    with pytest.raises(ValueError):
        audit.observations(audit.base.observations, audit.CASE, row, tmp_path, [])


@pytest.mark.parametrize("packet", ["[]", "not the declared malformed packet", '{"call_id":"other","response":{}}'])
def test_wrong_packet_is_not_accepted(packet, tmp_path):
    row = sample(tmp_path)
    (tmp_path / "transport.json").write_text(audit.base.wire(dict(raw_packet=packet)))
    with pytest.raises(ValueError, match="exact retained malformed packet"):
        audit.observations(audit.base.observations, audit.CASE, row, tmp_path, [])


def test_original_raw_binding_still_runs_and_override_is_restored(tmp_path):
    row = sample(tmp_path)
    (tmp_path / "inspector-transport.json").write_text(audit.base.wire(dict(stdout="{}", stderr="")))
    original_equal = audit.base.equal
    with pytest.raises(ValueError, match="raw inspector fields missing"):
        audit.observations(audit.base.observations, audit.CASE, row, tmp_path, [])
    assert audit.base.equal is original_equal


def test_every_other_case_uses_the_original_observer_unchanged(tmp_path):
    seen, row = [], {"fixture": "unchanged"}
    def original(case, value, directory):
        seen.append((case, value, directory))
        return "original result"
    assert audit.observations(original, "transport:wrong_correlation", row, tmp_path, []) == "original result"
    assert seen == [("transport:wrong_correlation", row, tmp_path)]


def test_adapter_refuses_a_different_legacy_expectation(tmp_path):
    row = sample(tmp_path)
    def changed_original(*args):
        audit.base.equal(["JSONDecodeError"], ["AnotherError"], "reported refusal observation differs")
    with pytest.raises(ValueError, match="preserved v1 expectation changed"):
        audit.observations(changed_original, audit.CASE, row, tmp_path, [])
