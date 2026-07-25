"""Independent closed Trace ABI for durable Distributed Commit v2.

This validator intentionally imports no Governance implementation.  It
recomputes every portable root projected by the four fixed distributed lanes,
including dependencies, replacement state, history, request, and atomic read
set.  Trace remains evidence of the commit path, never Store authority.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import cast

from pheroos.trace._contracts.authority import (
    _COMMON_FIELDS,
    _SESSION_FIELDS,
    _require_integer,
    _require_root,
    _require_session_bounds,
    _require_text,
    _validate_authority_envelope,
    _validate_session_event,
)
from pheroos.trace._contracts.base import TraceEventContract
from pheroos.trace._contracts.distributed_authority_support import (
    _read_set_root,
    _request_body,
    _required_roles,
    _snapshot_body,
)
from pheroos.trace._validation_core import TraceEventView


_CANONICAL_VERSION = "pheroos-authority-canonical-v2"
_SNAPSHOT_SCHEMA = "pheroos-distributed-lane-snapshot-v2"
_STATE_SCHEMA = "pheroos-distributed-lane-state-v2"
_DEPENDENCY_SCHEMA = "pheroos-distributed-dependency-v2"
_MAX_TEXT_BYTES = 4_096
_MAX_ROOTS = 8_192
_LANES = frozenset({"epoch", "proposal", "witness", "certificate"})
_ROLES = frozenset(
    {
        "epoch",
        "proposal",
        "witness",
        "certificate",
        "decision",
        "central_certificate",
        "membership",
        "principal_verification",
    }
)
_DEPENDENCY_FIELDS = frozenset(
    {
        "schema",
        "role",
        "stream_ref",
        "revision",
        "transition_id",
        "snapshot_root",
        "head_root",
        "receipt_root",
        "inclusion_root",
        "dependency_root",
    }
)
_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | frozenset(
        {
            "protocol_ref",
            "target_ref",
            "lane",
            "mutation_kind",
            "status",
            "revision",
            "parent_revision",
            "parent_transition_id",
            "parent_snapshot_root",
            "parent_head_root",
            "current_epoch",
            "current_step",
            "lane_state_root",
            "lane_state_material",
            "dependencies",
            "dependency_set_root",
            "reason_codes",
            "source_context_root",
            "snapshot_state_root",
            "snapshot_root",
            "parent_history_root",
            "parent_history_count",
            "history_root",
            "history_count",
            "read_set_root",
            "mutation_issuer_ref",
        }
    )
)

DISTRIBUTED_AUTHORITY_EVENT_TYPES = frozenset(
    {
        "distributed_epoch_advanced_v2",
        "distributed_proposal_advanced_v2",
        "distributed_witness_advanced_v2",
        "distributed_certificate_advanced_v2",
        "distributed_witness_conflict_v2",
        "distributed_certificate_conflict_v2",
    }
)


def _contract(event_type: str) -> TraceEventContract:
    def validate(event: TraceEventView) -> None:
        _validate_authority_envelope(event, required=_FIELDS)
        if set(event.lineage) != _FIELDS:
            raise ValueError(f"{event.event_type} distributed lineage is not exact")
        _validate_distributed_event(event)

    return TraceEventContract(
        event_type=event_type,
        required_fields=_FIELDS,
        validator=validate,
        authority_relevant=True,
        schema_condition=True,
    )


DISTRIBUTED_AUTHORITY_TRACE_EVENT_CONTRACTS = tuple(
    _contract(event_type) for event_type in DISTRIBUTED_AUTHORITY_EVENT_TYPES
)


def _validate_distributed_event(event: TraceEventView) -> None:
    lineage = cast(dict[str, object], event.lineage)
    _validate_session_event(event, operation="evaluate_quorum")
    lane = _bounded_text(event, "lane")
    mutation = _bounded_text(event, "mutation_kind")
    status = _bounded_text(event, "status")
    if lane not in _LANES:
        raise ValueError(f"{event.event_type} distributed lane is unsupported")
    _validate_event_shape(event, lane, mutation, status)
    for field in (
        "protocol_ref",
        "target_ref",
        "parent_transition_id",
        "mutation_issuer_ref",
    ):
        _bounded_text(event, field)
    for field in (
        "parent_snapshot_root",
        "parent_head_root",
        "lane_state_root",
        "dependency_set_root",
        "source_context_root",
        "snapshot_state_root",
        "snapshot_root",
        "parent_history_root",
        "history_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    counts = {
        field: _require_integer(event.event_type, lineage, field)
        for field in (
            "revision",
            "parent_revision",
            "current_epoch",
            "current_step",
            "parent_history_count",
            "history_count",
        )
    }
    _validate_identity(event, lane, counts)
    reasons = _canonical_text_array(event, "reason_codes", 1, 128)
    if reasons != [mutation]:
        raise ValueError(f"{event.event_type} distributed reasons are inconsistent")
    material = _validate_lane_material(event, lane, status, counts["current_epoch"])
    dependencies = _validate_dependencies(event, lane)
    _validate_roots(event, lane, material, dependencies, counts)


def _validate_event_shape(
    event: TraceEventView, lane: str, mutation: str, status: str
) -> None:
    expected_lane = _event_lane(event.event_type)
    if lane != expected_lane:
        raise ValueError(f"{event.event_type} distributed event lane is mismatched")
    if lane == "epoch":
        allowed, expected_status = {"epoch_initialized", "epoch_transitioned"}, "active"
    elif lane == "proposal":
        allowed, expected_status = (
            {"proposal_recorded", "proposal_semantic_retry"},
            "active",
        )
    elif lane == "witness":
        allowed = (
            {"equivocation_frozen"}
            if event.event_type.endswith("conflict_v2")
            else {"witness_recorded", "witness_retry"}
        )
        expected_status = (
            "frozen" if event.event_type.endswith("conflict_v2") else "active"
        )
    else:
        allowed = (
            {"certificate_conflict_frozen"}
            if event.event_type.endswith("conflict_v2")
            else {"certificate_verified", "certificate_retry"}
        )
        expected_status = (
            "frozen" if event.event_type.endswith("conflict_v2") else "verified"
        )
    if mutation not in allowed or status != expected_status:
        raise ValueError(f"{event.event_type} distributed mutation/status is invalid")


def _event_lane(event_type: str) -> str:
    for lane in _LANES:
        if event_type == f"distributed_{lane}_advanced_v2":
            return lane
    if event_type == "distributed_witness_conflict_v2":
        return "witness"
    if event_type == "distributed_certificate_conflict_v2":
        return "certificate"
    raise ValueError(f"unsupported distributed event: {event_type}")


def _validate_identity(
    event: TraceEventView, lane: str, counts: dict[str, int]
) -> None:
    lineage = cast(dict[str, object], event.lineage)
    if (
        event.target != lineage["target_ref"]
        or lineage["request_ref"] == ""
        or lineage["observed_epoch"] != counts["current_epoch"]
        or counts["revision"] < 1
        or counts["parent_revision"] != counts["revision"] - 1
        or counts["history_count"] != counts["parent_history_count"] + 1
        or counts["history_count"] != counts["revision"]
    ):
        raise ValueError(f"{event.event_type} distributed identity is inconsistent")
    material = b"\x00".join(
        cast(str, lineage[field]).encode("utf-8")
        for field in ("scope_ref", "protocol_ref", "run_ref", "target_ref")
    )
    stream = (
        f"authority:distributed-{lane}-v2:"
        + sha256(material + b"\x00" + lane.encode("utf-8")).hexdigest()
    )
    transition = (
        "transition:distributed-v2:"
        + sha256(
            stream.encode("utf-8")
            + b"\x00"
            + cast(str, lineage["request_ref"]).encode("utf-8")
        ).hexdigest()
    )
    if lineage["stream_ref"] != stream or lineage["transition_id"] != transition:
        raise ValueError(f"{event.event_type} distributed stream identity is invalid")
    if counts["revision"] == 1:
        if (
            counts["parent_revision"] != 0
            or lineage["parent_transition_id"] != "genesis"
            or lineage["parent_snapshot_root"]
            != _root("genesis-snapshot", {"schema": _SNAPSHOT_SCHEMA, "lane": lane})
            or lineage["parent_history_root"]
            != _root("genesis-history", {"schema": _STATE_SCHEMA, "lane": lane})
            or counts["parent_history_count"] != 0
        ):
            raise ValueError(f"{event.event_type} distributed genesis is invalid")
        if lane == "epoch" and lineage["mutation_kind"] != "epoch_initialized":
            raise ValueError(
                f"{event.event_type} distributed genesis mutation is invalid"
            )
    elif lineage["parent_transition_id"] == "genesis":
        raise ValueError(f"{event.event_type} distributed parent is invalid")
    elif lane == "epoch" and lineage["mutation_kind"] != "epoch_transitioned":
        raise ValueError(f"{event.event_type} distributed epoch mutation is invalid")


def _validate_lane_material(
    event: TraceEventView, lane: str, status: str, epoch: int
) -> dict[str, object]:
    raw = event.lineage["lane_state_material"]
    if type(raw) is not dict:
        raise TypeError(f"{event.event_type} distributed lane material is invalid")
    material = cast(dict[str, object], raw)
    if lane == "epoch":
        _exact_fields(
            event, material, {"transition_certificate_root", "conflict_history_roots"}
        )
        _nested_root(event, material, "transition_certificate_root")
        _canonical_nested_roots(
            event, material, "conflict_history_roots", allow_empty=True
        )
    elif lane == "proposal":
        _exact_fields(event, material, {"epoch", "proposal_digests"})
        _nested_epoch(event, material, epoch)
        _canonical_nested_roots(event, material, "proposal_digests", maximum=256)
    elif lane == "witness":
        _exact_fields(event, material, {"epoch", "witness_roots", "finding_roots"})
        _nested_epoch(event, material, epoch)
        _canonical_nested_roots(event, material, "witness_roots")
        findings = _canonical_nested_roots(
            event, material, "finding_roots", allow_empty=True
        )
        if bool(findings) != (status == "frozen"):
            raise ValueError(
                f"{event.event_type} distributed witness freeze is invalid"
            )
    else:
        _exact_fields(event, material, {"epoch", "certificate_roots", "conflict_roots"})
        _nested_epoch(event, material, epoch)
        _canonical_nested_roots(event, material, "certificate_roots", maximum=64)
        conflicts = _canonical_nested_roots(
            event, material, "conflict_roots", allow_empty=True
        )
        if bool(conflicts) != (status == "frozen"):
            raise ValueError(
                f"{event.event_type} distributed certificate freeze is invalid"
            )
    expected = _root(f"{lane}-state", material)
    if event.lineage["lane_state_root"] != expected:
        raise ValueError(f"{event.event_type} distributed lane state root is invalid")
    return material


def _validate_dependencies(event: TraceEventView, lane: str) -> list[dict[str, object]]:
    raw = event.lineage["dependencies"]
    if type(raw) is not list:
        raise TypeError(f"{event.event_type} distributed dependencies are invalid")
    values = [_validate_dependency(event, item) for item in cast(list[object], raw)]
    roles = [cast(str, item["role"]) for item in values]
    streams = [cast(str, item["stream_ref"]) for item in values]
    if (
        frozenset(roles) != _required_roles(lane)
        or roles != sorted(roles, key=lambda item: item.encode("utf-8"))
        or len(roles) != len(set(roles))
        or len(streams) != len(set(streams))
    ):
        raise ValueError(f"{event.event_type} distributed dependency set is invalid")
    body = {
        "dependencies": [
            {"role": item["role"], "dependency_root": item["dependency_root"]}
            for item in values
        ]
    }
    if event.lineage["dependency_set_root"] != _root("dependency-set", body):
        raise ValueError(
            f"{event.event_type} distributed dependency set root is invalid"
        )
    return values


def _validate_dependency(event: TraceEventView, raw: object) -> dict[str, object]:
    if type(raw) is not dict or set(raw) != _DEPENDENCY_FIELDS:
        raise ValueError(
            f"{event.event_type} distributed dependency fields are invalid"
        )
    item = cast(dict[str, object], raw)
    if item["schema"] != _DEPENDENCY_SCHEMA or item["role"] not in _ROLES:
        raise ValueError(
            f"{event.event_type} distributed dependency version is invalid"
        )
    _nested_text(event, item, "stream_ref")
    revision = _nested_integer(event, item, "revision")
    _nested_root(event, item, "head_root")
    if revision == 0:
        if any(
            item[field] != ""
            for field in (
                "transition_id",
                "snapshot_root",
                "receipt_root",
                "inclusion_root",
            )
        ):
            raise ValueError(
                f"{event.event_type} distributed genesis dependency is invalid"
            )
    else:
        _nested_text(event, item, "transition_id")
        for field in ("snapshot_root", "receipt_root", "inclusion_root"):
            _nested_root(event, item, field)
    body = {
        field: item[field] for field in _DEPENDENCY_FIELDS if field != "dependency_root"
    }
    if item["dependency_root"] != _root("dependency", body):
        raise ValueError(f"{event.event_type} distributed dependency root is invalid")
    return item


def _validate_roots(
    event: TraceEventView,
    lane: str,
    material: dict[str, object],
    dependencies: list[dict[str, object]],
    counts: dict[str, int],
) -> None:
    lineage = cast(dict[str, object], event.lineage)
    state = {
        "lane": lane,
        "mutation_kind": lineage["mutation_kind"],
        "current_epoch": counts["current_epoch"],
        "current_step": counts["current_step"],
        "status": lineage["status"],
        "lane_state_root": lineage["lane_state_root"],
        "dependency_set_root": lineage["dependency_set_root"],
        "reason_codes": lineage["reason_codes"],
        "source_context_root": lineage["source_context_root"],
    }
    source = _root(
        "source-context",
        {
            "lane": lane,
            "mutation_ref": lineage["request_ref"],
            "current_epoch": counts["current_epoch"],
            "current_step": counts["current_step"],
            "lane_state_root": lineage["lane_state_root"],
            "dependency_set_root": lineage["dependency_set_root"],
        },
    )
    if lineage["source_context_root"] != source or lineage[
        "snapshot_state_root"
    ] != _root("snapshot-state", state):
        raise ValueError(f"{event.event_type} distributed source/state root is invalid")
    history = _root(
        "history",
        {
            "lane": lane,
            "parent_history_root": lineage["parent_history_root"],
            "parent_history_count": counts["parent_history_count"],
            "transition_id": lineage["transition_id"],
            "snapshot_state_root": lineage["snapshot_state_root"],
        },
    )
    if lineage["history_root"] != history:
        raise ValueError(f"{event.event_type} distributed history root is invalid")
    snapshot = _snapshot_body(lineage, lane, dependencies, counts)
    if lineage["snapshot_root"] != _root("snapshot", snapshot):
        raise ValueError(f"{event.event_type} distributed snapshot root is invalid")
    if lineage["request_root"] != _root(
        "advance-request", _request_body(lineage, counts)
    ):
        raise ValueError(f"{event.event_type} distributed request root is invalid")
    if lineage["read_set_root"] != _read_set_root(lineage, dependencies):
        raise ValueError(f"{event.event_type} distributed read set root is invalid")
    _validate_actions(event, lane, material)


def _validate_actions(
    event: TraceEventView, lane: str, material: dict[str, object]
) -> None:
    if lane != "epoch":
        actions: tuple[str, ...] = ()
    else:
        conflicts = cast(list[object], material["conflict_history_roots"])
        actions = (
            ("epoch_transition", "recovery") if conflicts else ("epoch_transition",)
        )
    _require_session_bounds(
        event, targets=(cast(str, event.lineage["target_ref"]),), actions=actions
    )


def _canonical_text_array(
    event: TraceEventView, field: str, minimum: int, maximum: int
) -> list[str]:
    raw = event.lineage[field]
    if type(raw) is not list or not minimum <= len(raw) <= maximum:
        raise ValueError(f"{event.event_type} distributed {field} is not bounded")
    values = [
        _nested_text_value(event, field, item) for item in cast(list[object], raw)
    ]
    if values != sorted(values, key=lambda item: item.encode("utf-8")) or len(
        values
    ) != len(set(values)):
        raise ValueError(f"{event.event_type} distributed {field} is not canonical")
    return values


def _canonical_nested_roots(
    event: TraceEventView,
    material: dict[str, object],
    field: str,
    *,
    maximum: int = _MAX_ROOTS,
    allow_empty: bool = False,
) -> list[str]:
    raw = material[field]
    if type(raw) is not list or len(raw) > maximum or (not allow_empty and not raw):
        raise ValueError(
            f"{event.event_type} distributed material {field} is not bounded"
        )
    values = [cast(str, item) for item in cast(list[object], raw)]
    for item in values:
        _nested_root_value(event, field, item)
    if values != sorted(values, key=lambda item: item.encode("utf-8")) or len(
        values
    ) != len(set(values)):
        raise ValueError(
            f"{event.event_type} distributed material {field} is not canonical"
        )
    return values


def _exact_fields(
    event: TraceEventView, value: dict[str, object], fields: set[str]
) -> None:
    if set(value) != fields:
        raise ValueError(
            f"{event.event_type} distributed lane material fields are invalid"
        )


def _nested_epoch(event: TraceEventView, value: dict[str, object], epoch: int) -> None:
    if _nested_integer(event, value, "epoch") != epoch:
        raise ValueError(f"{event.event_type} distributed material epoch is mismatched")


def _bounded_text(event: TraceEventView, field: str) -> str:
    value = _require_text(
        event.event_type,
        cast(dict[str, object], event.lineage),
        field,
    )
    if len(value.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError(f"{event.event_type} distributed {field} exceeds its bound")
    return value


def _nested_text(event: TraceEventView, item: dict[str, object], field: str) -> str:
    return _nested_text_value(event, field, item[field])


def _nested_text_value(event: TraceEventView, field: str, value: object) -> str:
    if (
        type(value) is not str
        or not value
        or "\x00" in value
        or len(value.encode("utf-8")) > _MAX_TEXT_BYTES
    ):
        raise ValueError(f"{event.event_type} distributed nested {field} is invalid")
    return value


def _nested_integer(event: TraceEventView, item: dict[str, object], field: str) -> int:
    value = item[field]
    if type(value) is not int or not 0 <= value <= (2**53 - 1):
        raise ValueError(f"{event.event_type} distributed nested {field} is invalid")
    return value


def _nested_root(event: TraceEventView, item: dict[str, object], field: str) -> str:
    return _nested_root_value(event, field, item[field])


def _nested_root_value(event: TraceEventView, field: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in value[7:])
    ):
        raise ValueError(f"{event.event_type} distributed nested {field} is invalid")
    return value


def _precondition(stream: str, revision: int, root: str) -> dict[str, object]:
    return {"expected_revision": revision, "expected_root": root, "stream_ref": stream}


def _root(kind: str, body: object) -> str:
    domain = b"pheroos-distributed-commit-v2\x00" + kind.encode("utf-8")
    return "sha256:" + sha256(domain + b"\x00" + _canonical_bytes(body)).hexdigest()


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = [
    "DISTRIBUTED_AUTHORITY_EVENT_TYPES",
    "DISTRIBUTED_AUTHORITY_TRACE_EVENT_CONTRACTS",
]
