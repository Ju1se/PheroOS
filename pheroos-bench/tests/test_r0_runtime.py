"""Hand-built records provide an independent oracle for G1 accounting."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from pheroos_bench.r0_runtime import PROFILE, reconcile_snapshot


def _encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _event(snapshot: dict, kind: str, task_id: str = "task", **lineage: object) -> None:
    event_type = f"ext.runtime.{kind}"
    snapshot["events"].append(
        {
            "seq": len(snapshot["events"]) + 1,
            "event_type": event_type,
            "task_id": task_id,
            "payload": _encode(
                {
                    "event_type": event_type,
                    "protocol_id": "g1.local.mock",
                    "target": task_id or "run",
                    "reason": kind,
                    "lineage": lineage,
                }
            ),
        }
    )


def _bytes(snapshot: dict) -> dict:
    snapshot["event_bytes"] = sum(
        len(event["payload"].encode()) for event in snapshot["events"]
    )
    snapshot["payload_bytes"] = sum(
        len(call["request"].encode()) + len((call["response"] or "").encode())
        for call in snapshot["calls"]
    )
    return snapshot


def _snapshot(state: str = "received", *, transition: str | None = None) -> dict:
    snapshot = {
        "run": {"status": "running", "scope_ref": "scope", "budget": 2},
        "tasks": [{"id": "task"}],
        "calls": [
            {
                "id": "call",
                "task_id": "task",
                "version": 1,
                "epoch": 1,
                "action": "mock.propose",
                "state": state,
                "reserved": 1,
                "actual": 1 if state == "received" else None,
                "request": _encode({"prompt": "算术"}),
                "response": _encode({"value": 1}) if state == "received" else None,
            }
        ],
        "artifacts": [],
        "events": [],
        "actual_units": int(state == "received"),
        "reserved_units": int(state in {"reserved", "dispatched", "unknown"}),
        "unknown_units": int(state == "unknown"),
        "remaining_units": 2 if state == "abandoned" else 1,
    }
    _event(snapshot, "created", "", scope_ref="scope", budget=2)
    _event(snapshot, "claimed", owner="worker", epoch=1, policy="fifo")
    _event(
        snapshot, "reserved", call_id="call", action="mock.propose", units=1, epoch=1
    )
    if state not in {"reserved", "abandoned"}:
        _event(snapshot, "dispatched", call_id="call", authority={})
    if transition == "cancelled":
        _event(snapshot, "cancelled", "")
        snapshot["run"]["status"] = "cancelled"
    elif transition == "relinquished":
        _event(snapshot, "relinquished", epoch=1, reason="worker failed")
    elif transition == "expired":
        recovered_state = "abandoned" if state == "abandoned" else "unknown"
        _event(snapshot, "recovered_call", call_id="call", state=recovered_state)
        _event(snapshot, "lease_expired", epoch=1, unknown=state != "abandoned")
    if state == "received":
        _event(snapshot, "received", call_id="call", actual=1, driver_receipt=None)
    return _bytes(snapshot)


@pytest.mark.parametrize("state", ["received", "reserved", "dispatched"])
def test_known_receipt_and_inflight_reservation_are_distinct(state: str) -> None:
    result = reconcile_snapshot(_snapshot(state))
    assert result["profile"] == PROFILE
    assert result["validation_status"] == "VALID"
    assert result["actual_units"] == (state == "received")
    assert result["reserved_units"] == (state != "received")
    assert result["unknown_units"] == 0
    assert result["cost_status"] == ("KNOWN" if state == "received" else "UNRESOLVED")
    assert result["remaining_units"] == 1


@pytest.mark.parametrize("transition", ["expired", "cancelled", "relinquished"])
def test_unknown_dispatch_retains_budget_and_is_not_zero_cost(transition: str) -> None:
    result = reconcile_snapshot(_snapshot("unknown", transition=transition))
    assert result["validation_status"] == "VALID"
    assert result["actual_units"] == 0
    assert result["reserved_units"] == result["unknown_units"] == 1
    assert result["cost_status"] == "UNRESOLVED"
    assert result["remaining_units"] == 1


@pytest.mark.parametrize("transition", ["expired", "cancelled", "relinquished"])
def test_late_receipt_replaces_unknown_reservation_without_double_charge(
    transition: str,
) -> None:
    result = reconcile_snapshot(_snapshot("received", transition=transition))
    assert result["validation_status"] == "VALID"
    assert result["actual_units"] == 1
    assert result["reserved_units"] == result["unknown_units"] == 0
    assert result["cost_status"] == "KNOWN"
    assert result["run_status"] == (
        "cancelled" if transition == "cancelled" else "running"
    )


@pytest.mark.parametrize("transition", ["expired", "cancelled", "relinquished"])
def test_abandoned_undispatched_reservation_is_released(transition: str) -> None:
    result = reconcile_snapshot(_snapshot("abandoned", transition=transition))
    assert result["validation_status"] == "VALID"
    assert (
        result["actual_units"]
        == result["reserved_units"]
        == result["unknown_units"]
        == 0
    )
    assert result["remaining_units"] == 2


@pytest.mark.parametrize(
    "field",
    [
        "actual_units",
        "reserved_units",
        "unknown_units",
        "remaining_units",
        "payload_bytes",
        "event_bytes",
    ],
)
def test_aggregates_cannot_override_record_evidence(field: str) -> None:
    snapshot = _snapshot()
    snapshot[field] += 1
    result = reconcile_snapshot(snapshot)
    assert result["validation_status"] == "INVALID_ABORT"
    assert any(field in diagnostic for diagnostic in result["diagnostics"])
    assert result["actual_units"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_call",
        "duplicate_call",
        "missing_dispatch",
        "duplicate_dispatch",
        "missing_receipt",
        "duplicate_receipt",
        "reordered_events",
        "wrong_call_state",
        "wrong_receipt_units",
        "wrong_task",
        "nonfinite_json",
    ],
)
def test_broken_records_abort_even_if_byte_aggregates_are_recomputed(
    mutation: str,
) -> None:
    snapshot = _snapshot()
    if mutation == "missing_call":
        snapshot["calls"] = []
    elif mutation == "duplicate_call":
        snapshot["calls"].append(deepcopy(snapshot["calls"][0]))
    elif mutation.startswith("missing_"):
        snapshot["events"].pop(-1 if mutation == "missing_receipt" else -2)
    elif mutation.startswith("duplicate_"):
        snapshot["events"].append(
            deepcopy(snapshot["events"][-1 if mutation == "duplicate_receipt" else -2])
        )
    elif mutation == "reordered_events":
        snapshot["events"][-1], snapshot["events"][-2] = (
            snapshot["events"][-2],
            snapshot["events"][-1],
        )
    elif mutation == "wrong_call_state":
        snapshot["calls"][0]["state"] = "reserved"
        snapshot["calls"][0]["actual"] = snapshot["calls"][0]["response"] = None
    elif mutation == "wrong_receipt_units":
        payload = json.loads(snapshot["events"][-1]["payload"])
        payload["lineage"]["actual"] = 0
        snapshot["events"][-1]["payload"] = _encode(payload)
    elif mutation == "wrong_task":
        snapshot["calls"][0]["task_id"] = "missing"
    else:
        snapshot["calls"][0]["request"] = '{"value": NaN}'
    # Repair numbering to challenge lifecycle reconciliation, not only gap checks.
    for index, event in enumerate(snapshot["events"], 1):
        event["seq"] = index
    result = reconcile_snapshot(_bytes(snapshot))
    assert result["validation_status"] == "INVALID_ABORT"
    assert result["diagnostics"]


@pytest.mark.parametrize(
    "snapshot", [None, [], {}, {"run": None}, {"run": {"budget": True}}]
)
def test_malformed_schema_returns_diagnostics_instead_of_raising(
    snapshot: object,
) -> None:
    result = reconcile_snapshot(snapshot)
    assert result["validation_status"] == "INVALID_ABORT"
    assert result["diagnostics"]


def test_input_is_unchanged() -> None:
    snapshot = _snapshot("unknown", transition="cancelled")
    original = deepcopy(snapshot)
    reconcile_snapshot(snapshot)
    assert snapshot == original


def test_call_cannot_dispatch_after_cancellation() -> None:
    snapshot = _snapshot("unknown", transition="cancelled")
    snapshot["events"][-1], snapshot["events"][-2] = (
        snapshot["events"][-2],
        snapshot["events"][-1],
    )
    for index, event in enumerate(snapshot["events"], 1):
        event["seq"] = index
    assert reconcile_snapshot(_bytes(snapshot))["validation_status"] == "INVALID_ABORT"


def test_a_later_release_cannot_hide_an_overbudget_reservation() -> None:
    snapshot = _snapshot("abandoned", transition="cancelled")
    second = deepcopy(snapshot["calls"][0])
    second["id"] = "second"
    third = deepcopy(second)
    third["id"] = "third"
    snapshot["calls"].extend([second, third])
    cancellation = snapshot["events"].pop()
    for identity in ("second", "third"):
        _event(
            snapshot,
            "reserved",
            call_id=identity,
            action="mock.propose",
            units=1,
            epoch=1,
        )
    cancellation["seq"] = len(snapshot["events"]) + 1
    snapshot["events"].append(cancellation)
    # End-state totals are zero but three simultaneous reservations exceeded two.
    result = reconcile_snapshot(_bytes(snapshot))
    assert result["validation_status"] == "INVALID_ABORT"
    assert "exceeded available budget" in result["diagnostics"][0]


def test_missing_response_is_not_a_zero_cost_receipt() -> None:
    snapshot = _snapshot()
    snapshot["calls"][0]["response"] = None
    assert reconcile_snapshot(_bytes(snapshot))["validation_status"] == "INVALID_ABORT"


def test_original_event_sequence_gap_is_invalid() -> None:
    snapshot = _snapshot()
    snapshot["events"][1]["seq"] += 1
    assert reconcile_snapshot(snapshot)["validation_status"] == "INVALID_ABORT"


@pytest.mark.parametrize(
    "wire", ['{"value": 1, "value": 2}', '{"nested": {"value": 1, "value": 2}}']
)
def test_duplicate_json_keys_are_rejected_at_any_depth(wire: str) -> None:
    snapshot = _snapshot()
    snapshot["calls"][0]["request"] = wire
    assert reconcile_snapshot(_bytes(snapshot))["validation_status"] == "INVALID_ABORT"


@pytest.mark.parametrize("field", ["units", "epoch", "budget"])
def test_boolean_lineage_cannot_masquerade_as_integer(field: str) -> None:
    snapshot = _snapshot()
    index = 0 if field == "budget" else 2
    if field == "budget":
        snapshot["run"]["budget"] = 1
        snapshot["remaining_units"] = 0
    payload = json.loads(snapshot["events"][index]["payload"])
    payload["lineage"][field] = True
    snapshot["events"][index]["payload"] = _encode(payload)
    result = reconcile_snapshot(_bytes(snapshot))
    assert result["validation_status"] == "INVALID_ABORT"
    assert "nonnegative integer required" in result["diagnostics"][0]


@pytest.mark.parametrize("field", ["state", "task_id", "action"])
def test_unhashable_call_values_return_diagnostics(field: str) -> None:
    snapshot = _snapshot()
    snapshot["calls"][0][field] = {}
    result = reconcile_snapshot(snapshot)
    assert result["validation_status"] == "INVALID_ABORT"
    assert result["diagnostics"]
