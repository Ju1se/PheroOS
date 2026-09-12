"""Read-only accounting adapter for the G1 mock SQLite snapshot profile.

VALID means that call records, lifecycle events and unit/byte totals reconcile.
It does not verify authority signatures, artifact correctness or scheduler logic.
An internally consistent unresolved call remains an unknown cost, never zero.
"""

from __future__ import annotations

import json

PROFILE = "g1_mock_sqlite_v1"
_PREFIX = "ext.runtime."
_KINDS = {
    "created",
    "claimed",
    "reserved",
    "dispatched",
    "received",
    "recovered_call",
    "lease_expired",
    "reconciled",
    "published",
    "cancelled",
    "relinquished",
}
_ACTIVE = {"reserved", "dispatched", "unknown"}


class _Invalid(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise _Invalid(message)


def _integer(value: object, label: str) -> int:
    _require(
        type(value) is int and value >= 0, f"{label}: nonnegative integer required"
    )
    return value


def _mapping(value: object, label: str) -> dict:
    _require(isinstance(value, dict), f"{label}: object required")
    return value


def _wire(value: object, label: str) -> dict:
    _require(isinstance(value, str), f"{label}: serialized JSON object required")

    def reject_constant(token: str) -> None:
        raise ValueError(f"non-finite JSON number: {token}")

    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result

    try:
        decoded = json.loads(
            value, parse_constant=reject_constant, object_pairs_hook=unique_object
        )
        # G1 serialization rejects NaN/Infinity, including nested occurrences.
        json.dumps(decoded, allow_nan=False)
    except (ValueError, TypeError) as error:
        raise _Invalid(f"{label}: invalid JSON") from error
    return _mapping(decoded, label)


def _rows(snapshot: dict, key: str, id_key: str) -> dict[str, dict]:
    rows = snapshot.get(key)
    _require(isinstance(rows, list), f"{key}: list required")
    result = {}
    for row in rows:
        row = _mapping(row, key)
        identity = row.get(id_key)
        _require(
            isinstance(identity, str) and bool(identity), f"{key}: missing identifier"
        )
        _require(identity not in result, f"{key}: duplicate {identity}")
        result[identity] = row
    return result


def reconcile_snapshot(snapshot: dict) -> dict:
    """Return diagnostics; malformed snapshots cannot produce measurement evidence."""
    result = {
        "profile": PROFILE,
        "validation_status": "INVALID_ABORT",
        "cost_status": "UNAVAILABLE",
        "run_status": None,
        "actual_units": None,
        "reserved_units": None,
        "unknown_units": None,
        "remaining_units": None,
        "diagnostics": [],
    }
    try:
        totals = _reconcile(_mapping(snapshot, "snapshot"))
    except (_Invalid, KeyError, TypeError, ValueError) as error:
        result["diagnostics"].append(str(error))
        return result
    result.update(totals, validation_status="VALID")
    return result


def _reconcile(snapshot: dict) -> dict:
    run = _mapping(snapshot.get("run"), "run")
    budget = _integer(run.get("budget"), "run.budget")
    _require(
        run.get("status") in {"running", "completed", "cancelled"}, "invalid run status"
    )
    tasks = _rows(snapshot, "tasks", "id")
    calls = _rows(snapshot, "calls", "id")
    _require(bool(tasks), "tasks: empty G1 task inventory")
    payload_bytes = 0
    for identity, call in calls.items():
        _require(call.get("task_id") in tasks, f"{identity}: unknown task")
        _require(
            call.get("action") in {"mock.propose", "tool.evaluate"},
            f"{identity}: unsupported action",
        )
        _require(
            call.get("version") == 1 and type(call.get("version")) is int,
            f"{identity}: unsupported version",
        )
        _require(
            _integer(call.get("epoch"), f"{identity}.epoch") > 0,
            f"{identity}: missing lease epoch",
        )
        _require(
            type(call.get("reserved")) is int and call["reserved"] == 1,
            f"{identity}: G1 reservation must be one unit",
        )
        _require(
            call.get("state") in _ACTIVE | {"received", "abandoned"},
            f"{identity}: invalid call state",
        )
        _wire(call.get("request"), f"{identity}.request")
        payload_bytes += len(call["request"].encode("utf-8"))
        if call["state"] == "received":
            _require(
                type(call.get("actual")) is int and call["actual"] == 1,
                f"{identity}: G1 receipt must charge one unit",
            )
            _wire(call.get("response"), f"{identity}.response")
            payload_bytes += len(call["response"].encode("utf-8"))
        else:
            _require(
                call.get("actual") is None and call.get("response") is None,
                f"{identity}: unreceived call has a receipt",
            )

    events = snapshot.get("events")
    _require(
        isinstance(events, list) and bool(events), "events: nonempty list required"
    )
    states: dict[str, str] = {}
    receipts: set[str] = set()
    cancelled = False
    event_bytes = 0
    for sequence, event in enumerate(events, 1):
        event = _mapping(event, "event")
        _require(
            type(event.get("seq")) is int and event["seq"] == sequence,
            "events: missing, duplicate or reordered sequence",
        )
        payload = _wire(event.get("payload"), f"event {sequence}")
        event_bytes += len(event["payload"].encode("utf-8"))
        kind = event.get("event_type")
        _require(
            isinstance(kind, str) and kind.startswith(_PREFIX),
            "unsupported event namespace",
        )
        kind = kind.removeprefix(_PREFIX)
        _require(kind in _KINDS, f"unsupported G1 event {kind}")
        task = event.get("task_id")
        _require(task == "" or task in tasks, f"event {sequence}: unknown task")
        _require(
            payload.get("event_type") == event["event_type"]
            and payload.get("protocol_id") == "g1.local.mock",
            f"event {sequence}: incompatible trace envelope",
        )
        _require(
            payload.get("target") == (task or "run") and payload.get("reason") == kind,
            f"event {sequence}: mismatched trace envelope",
        )
        lineage = _mapping(payload.get("lineage"), f"event {sequence}.lineage")
        _require(
            not cancelled or kind == "received",
            "only late receipts may follow cancellation",
        )
        if kind == "created":
            _require(
                sequence == 1
                and task == ""
                and _integer(lineage.get("budget"), "created.budget") == budget
                and lineage.get("scope_ref") == run.get("scope_ref"),
                "created event mismatch",
            )
        else:
            _require(sequence > 1, "first event must be created")
        if kind in {
            "reserved",
            "dispatched",
            "received",
            "recovered_call",
            "reconciled",
        }:
            identity = lineage.get("call_id")
            _require(
                isinstance(identity, str) and identity in calls,
                f"event {sequence}: missing call record",
            )
            call = calls[identity]
            _require(call["task_id"] == task, f"{identity}: event task mismatch")
            previous = states.get(identity)
            if kind == "reserved":
                _require(
                    not cancelled and previous is None,
                    f"{identity}: duplicate or post-cancel reservation",
                )
                _require(
                    lineage.get("action") == call["action"]
                    and _integer(lineage.get("units"), f"{identity}.units") == 1
                    and _integer(lineage.get("epoch"), f"{identity}.epoch")
                    == call["epoch"],
                    f"{identity}: reservation event mismatch",
                )
                committed = sum(
                    state in _ACTIVE or state == "received" for state in states.values()
                )
                _require(
                    committed + 1 <= budget,
                    f"{identity}: reservation exceeded available budget",
                )
                states[identity] = "reserved"
            elif kind == "dispatched":
                _require(
                    not cancelled and previous == "reserved",
                    f"{identity}: dispatch without live reservation",
                )
                states[identity] = "dispatched"
            elif kind == "received":
                _require(
                    previous in {"dispatched", "unknown"} and identity not in receipts,
                    f"{identity}: missing dispatch or duplicate receipt",
                )
                _require(
                    type(lineage.get("actual")) is int
                    and lineage["actual"] == call.get("actual") == 1,
                    f"{identity}: receipt unit mismatch",
                )
                _require(
                    "driver_receipt" in lineage
                    and (
                        lineage["driver_receipt"] is None
                        or isinstance(lineage["driver_receipt"], dict)
                    ),
                    f"{identity}: malformed driver receipt",
                )
                receipts.add(identity)
                states[identity] = "received"
            elif kind == "recovered_call":
                expected = {"reserved": "abandoned", "dispatched": "unknown"}.get(
                    previous
                )
                _require(
                    expected is not None and lineage.get("state") == expected,
                    f"{identity}: invalid recovery transition",
                )
                states[identity] = expected
            else:
                _require(
                    not cancelled and previous == "received",
                    f"{identity}: reconciliation without receipt",
                )
        elif kind in {"cancelled", "relinquished"}:
            _require(
                not cancelled,
                f"event {sequence}: lifecycle mutation after cancellation",
            )
            if kind == "cancelled":
                _require(task == "", "cancelled event must target run")
                cancelled = True
            else:
                _require(task in tasks, "relinquished event must target task")
            for identity, state in states.items():
                if kind == "cancelled" or calls[identity]["task_id"] == task:
                    states[identity] = {
                        "reserved": "abandoned",
                        "dispatched": "unknown",
                    }.get(state, state)

    _require(set(states) == set(calls), "call records and reservation events differ")
    _require(
        cancelled == (run["status"] == "cancelled"),
        "run cancellation state disagrees with events",
    )
    for identity, state in states.items():
        _require(
            state == calls[identity]["state"],
            f"{identity}: record state disagrees with events",
        )
    actual = len(receipts)
    reserved = sum(state in _ACTIVE for state in states.values())
    unknown = sum(state == "unknown" for state in states.values())
    remaining = budget - actual - reserved
    _require(remaining >= 0, "actual plus reserved units exceeds budget")
    totals = {
        "actual_units": actual,
        "reserved_units": reserved,
        "unknown_units": unknown,
        "remaining_units": remaining,
        "payload_bytes": payload_bytes,
        "event_bytes": event_bytes,
    }
    for name, value in totals.items():
        _require(
            _integer(snapshot.get(name), name) == value,
            f"{name}: aggregate disagrees with records",
        )
    return totals | {
        "run_status": run["status"],
        "cost_status": "UNRESOLVED" if reserved else "KNOWN",
    }
