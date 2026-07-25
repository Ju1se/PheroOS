"""Independent Trace ABI validation for durable Commit Decision v2."""

from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import cast

from pheroos.trace._contracts.authority import (
    _COMMON_FIELDS,
    _SESSION_FIELDS,
    _authority_stream_ref,
    _require_integer,
    _require_root,
    _require_session_bounds,
    _require_text,
    _validate_authority_envelope,
    _validate_session_event,
)
from pheroos.trace._contracts.base import TraceEventContract
from pheroos.trace._validation_core import TraceEventView


_CANONICAL_VERSION = "pheroos-authority-canonical-v2"
_READ_SET_SCHEMA = "pheroos-governance-authority-read-set-v2"
_LIFECYCLE_STREAM = "authority:domain-lifecycle"
_DEPENDENCY_SCHEMA = "pheroos-commit-decision-dependency-v2"
_MAX_TEXT_BYTES = 4_096
_MAX_INTEGER = (2**53) - 1
_ROOT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TRANSITION_PATTERN = re.compile(r"transition:commit-decision-v2:[0-9a-f]{64}\Z")
_ROLES = frozenset(
    {
        "parent",
        "evidence",
        "replay",
        "risk",
        "membership",
        "principal_verification",
        "support",
        "stop",
        "permission",
        "certificate",
        "distributed",
    }
)
_MUTATIONS = frozenset(
    {
        "initialized",
        "assessed",
        "window_reset",
        "epoch_restarted",
        "sealed",
        "heartbeat",
        "finalized",
        "deadline_terminated",
    }
)
_COMMAND_MUTATIONS = {
    "initialize": frozenset({"initialized"}),
    "evaluate": frozenset(
        {"assessed", "window_reset", "heartbeat", "finalized", "deadline_terminated"}
    ),
    "seal": frozenset({"sealed", "window_reset", "deadline_terminated"}),
    "explicit_unseal": frozenset({"window_reset", "deadline_terminated"}),
    "epoch_restart": frozenset(
        {"epoch_restarted", "window_reset", "deadline_terminated"}
    ),
}
_PROFILES = {
    "advisory": frozenset({"pheroos-commit-integrity-v1"}),
    "evidence_bound": frozenset(
        {"pheroos-commit-integrity-v1", "pheroos-hybrid-commit-v1"}
    ),
    "certified": frozenset({"pheroos-certified-commit-v1"}),
    "distributed": frozenset({"pheroos-distributed-commit-v1"}),
}
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
        "observed_position",
        "dependency_root",
    }
)
_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | frozenset(
        {
            "mutation_ref",
            "command",
            "mutation_kind",
            "revision",
            "parent_revision",
            "parent_transition_id",
            "parent_snapshot_root",
            "parent_head_root",
            "snapshot_root",
            "state_root",
            "history_root",
            "history_count",
            "protocol_ref",
            "target_ref",
            "profile",
            "assurance",
            "manifest_root",
            "commit_policy_root",
            "epoch",
            "current_step",
            "evidence_deadline_step",
            "finality_deadline_step",
            "dependency_set_root",
            "source_context_root",
            "assessment_root",
            "window_root",
            "seal_root",
            "progress_root",
            "outcome_root",
            "mutation_issuer_ref",
            "read_set_root",
            "dependencies",
        }
    )
)
_EVENT_MUTATIONS = {
    "commit_decision_initialized_v2": frozenset({"initialized"}),
    "commit_assessment_evaluated_v2": frozenset({"assessed", "window_reset"}),
    "commit_window_advanced_v2": frozenset({"assessed"}),
    "commit_window_reset_v2": frozenset({"window_reset"}),
    "commit_epoch_restarted_v2": frozenset({"epoch_restarted"}),
    "commit_window_sealed_v2": frozenset({"sealed"}),
    "commit_decision_progressed_v2": _MUTATIONS
    - frozenset({"finalized", "deadline_terminated"}),
    "commit_decision_outcome_committed_v2": frozenset(
        {"finalized", "deadline_terminated"}
    ),
}
COMMIT_DECISION_EVENT_TYPES = frozenset(_EVENT_MUTATIONS)


def _contract(event_type: str) -> TraceEventContract:
    def validate(event: TraceEventView) -> None:
        _validate_authority_envelope(event, required=_FIELDS)
        if set(event.lineage) != _FIELDS:
            raise ValueError(f"{event.event_type} trace lineage fields are not exact")
        _validate_decision_event(event)

    return TraceEventContract(
        event_type=event_type,
        required_fields=_FIELDS,
        validator=validate,
        authority_relevant=True,
        schema_condition=True,
    )


COMMIT_DECISION_AUTHORITY_TRACE_EVENT_CONTRACTS = tuple(
    _contract(event_type) for event_type in COMMIT_DECISION_EVENT_TYPES
)


def _validate_decision_event(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_session_event(event, operation="evaluate_quorum")
    _require_session_bounds(event, targets=(lineage["target_ref"],), actions=())
    for field in (
        "mutation_ref",
        "command",
        "mutation_kind",
        "parent_transition_id",
        "protocol_ref",
        "target_ref",
        "profile",
        "assurance",
        "mutation_issuer_ref",
    ):
        _bounded_text(event, field)
    for field in (
        "parent_snapshot_root",
        "parent_head_root",
        "snapshot_root",
        "state_root",
        "history_root",
        "manifest_root",
        "commit_policy_root",
        "dependency_set_root",
        "source_context_root",
        "window_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    for field in ("assessment_root", "seal_root", "progress_root", "outcome_root"):
        _optional_root(event, field)
    revision = _require_integer(event.event_type, lineage, "revision")
    parent_revision = _require_integer(event.event_type, lineage, "parent_revision")
    history_count = _require_integer(event.event_type, lineage, "history_count")
    for field in (
        "epoch",
        "current_step",
        "evidence_deadline_step",
        "finality_deadline_step",
    ):
        _require_integer(event.event_type, lineage, field)
    if revision < 1 or parent_revision != revision - 1 or history_count != revision:
        raise ValueError(f"{event.event_type} trace revision lineage is invalid")
    if lineage["evidence_deadline_step"] > lineage["finality_deadline_step"]:
        raise ValueError(f"{event.event_type} trace deadline lineage is invalid")
    if (
        event.target != lineage["target_ref"]
        or lineage["request_ref"] != lineage["mutation_ref"]
    ):
        raise ValueError(f"{event.event_type} trace target/request binding is invalid")
    _validate_profile(event)
    _validate_identity(event)
    _validate_mutation_shape(event)
    dependencies = _validate_dependencies(event)
    if _read_set_root(lineage, dependencies) != lineage["read_set_root"]:
        raise ValueError(f"{event.event_type} trace read_set_root is mismatched")


def _validate_profile(event: TraceEventView) -> None:
    assurance = event.lineage["assurance"]
    profile = event.lineage["profile"]
    if assurance not in _PROFILES or profile not in _PROFILES[assurance]:
        raise ValueError(f"{event.event_type} trace profile is mismatched")


def _validate_identity(event: TraceEventView) -> None:
    lineage = event.lineage
    material = b"\x00".join(
        cast(str, lineage[field]).encode("utf-8")
        for field in ("scope_ref", "protocol_ref", "run_ref", "target_ref")
    )
    stream = "authority:commit-decision-v2:" + sha256(material).hexdigest()
    transition = (
        "transition:commit-decision-v2:"
        + sha256(
            stream.encode("utf-8")
            + b"\x00"
            + cast(str, lineage["mutation_ref"]).encode("utf-8")
        ).hexdigest()
    )
    if lineage["stream_ref"] != stream or lineage["transition_id"] != transition:
        raise ValueError(f"{event.event_type} trace identity is not canonical")
    if lineage["revision"] == 1:
        if (
            lineage["parent_revision"] != 0
            or lineage["parent_transition_id"] != "genesis"
        ):
            raise ValueError(f"{event.event_type} trace genesis parent is invalid")
    elif (
        _TRANSITION_PATTERN.fullmatch(cast(str, lineage["parent_transition_id"]))
        is None
    ):
        raise ValueError(f"{event.event_type} trace parent transition is invalid")


def _validate_mutation_shape(event: TraceEventView) -> None:
    lineage = event.lineage
    command = lineage["command"]
    mutation = lineage["mutation_kind"]
    if command not in _COMMAND_MUTATIONS or mutation not in _COMMAND_MUTATIONS[command]:
        raise ValueError(f"{event.event_type} trace command mutation is invalid")
    if mutation not in _EVENT_MUTATIONS[event.event_type]:
        raise ValueError(f"{event.event_type} trace event mutation is invalid")
    has_assessment = bool(lineage["assessment_root"])
    has_seal = bool(lineage["seal_root"])
    has_progress = bool(lineage["progress_root"])
    has_outcome = bool(lineage["outcome_root"])
    if has_progress == has_outcome:
        raise ValueError(f"{event.event_type} trace terminal projection is invalid")
    if event.event_type == "commit_assessment_evaluated_v2" and not has_assessment:
        raise ValueError("commit assessment trace omits its assessment")
    if event.event_type == "commit_window_sealed_v2" and not has_seal:
        raise ValueError("commit seal trace omits its seal")
    if event.event_type == "commit_decision_progressed_v2" and not has_progress:
        raise ValueError("commit progress trace omits its progress")
    if event.event_type == "commit_decision_outcome_committed_v2" and not has_outcome:
        raise ValueError("commit outcome trace omits its outcome")


def _validate_dependencies(event: TraceEventView) -> list[dict[str, object]]:
    raw = event.lineage["dependencies"]
    if type(raw) is not list or not 1 <= len(raw) <= len(_ROLES):
        raise ValueError(f"{event.event_type} trace dependencies are not bounded")
    dependencies = [_validate_dependency(event, item) for item in raw]
    roles = [cast(str, item["role"]) for item in dependencies]
    streams = [cast(str, item["stream_ref"]) for item in dependencies]
    if roles != sorted(roles, key=lambda item: item.encode("utf-8")):
        raise ValueError(f"{event.event_type} trace dependency order is invalid")
    if len(roles) != len(set(roles)) or len(streams) != len(set(streams)):
        raise ValueError(f"{event.event_type} trace dependencies collide")
    body = {
        "dependencies": [
            {"role": item["role"], "root": item["dependency_root"]}
            for item in dependencies
        ]
    }
    if event.lineage["dependency_set_root"] != _root("dependency-set", body):
        raise ValueError(f"{event.event_type} trace dependency_set_root is mismatched")
    parent = [item for item in dependencies if item["role"] == "parent"]
    if len(parent) != 1 or (
        parent[0]["revision"],
        parent[0]["transition_id"],
        parent[0]["snapshot_root"],
    ) != (
        event.lineage["parent_revision"],
        event.lineage["parent_transition_id"],
        event.lineage["parent_snapshot_root"],
    ):
        raise ValueError(f"{event.event_type} trace parent dependency is mismatched")
    return dependencies


def _validate_dependency(event: TraceEventView, raw: object) -> dict[str, object]:
    if type(raw) is not dict or set(raw) != _DEPENDENCY_FIELDS:
        raise ValueError(f"{event.event_type} trace dependency fields are invalid")
    item = cast(dict[str, object], raw)
    if item["schema"] != _DEPENDENCY_SCHEMA or item["role"] not in _ROLES:
        raise ValueError(f"{event.event_type} trace dependency version is invalid")
    for field in ("stream_ref", "transition_id"):
        _bounded_value(event, f"dependencies.{field}", item[field])
    revision = _integer_value(event, "dependencies.revision", item["revision"])
    for field in ("snapshot_root", "head_root", "receipt_root"):
        _root_value(event, f"dependencies.{field}", item[field])
    if item["observed_position"] != "current":
        raise ValueError(f"{event.event_type} trace dependency is not current")
    if revision == 0 and item["transition_id"] != "genesis":
        raise ValueError(f"{event.event_type} trace genesis dependency is invalid")
    body = {key: item[key] for key in _DEPENDENCY_FIELDS if key != "dependency_root"}
    expected = _root("dependency", body)
    if item["dependency_root"] != expected:
        raise ValueError(f"{event.event_type} trace dependency_root is mismatched")
    return item


def _read_set_root(
    lineage: dict[str, object], dependencies: list[dict[str, object]]
) -> str:
    binding = cast(dict[str, object], lineage["session_binding"])
    entries = [
        _precondition(
            cast(str, item["stream_ref"]),
            cast(int, item["revision"]),
            cast(str, item["head_root"]),
        )
        for item in dependencies
    ]
    entries.extend(
        (
            _precondition(
                _authority_stream_ref(
                    "issuer-grant",
                    (
                        cast(str, lineage["scope_ref"]),
                        cast(str, lineage["grant_ref"]),
                    ),
                ),
                cast(int, binding["grant_expected_revision"]),
                cast(str, binding["grant_expected_root"]),
            ),
            _precondition(
                _LIFECYCLE_STREAM,
                cast(int, binding["lifecycle_expected_revision"]),
                cast(str, binding["lifecycle_expected_root"]),
            ),
        )
    )
    entries.sort(key=lambda item: cast(str, item["stream_ref"]).encode("utf-8"))
    if len({item["stream_ref"] for item in entries}) != len(entries):
        raise ValueError("commit decision trace read-set streams collide")
    return (
        "sha256:"
        + sha256(
            _canonical_bytes(
                {
                    "canonical_version": _CANONICAL_VERSION,
                    "entries": entries,
                    "schema": _READ_SET_SCHEMA,
                }
            )
        ).hexdigest()
    )


def _precondition(stream: str, revision: int, root: str) -> dict[str, object]:
    return {
        "expected_revision": revision,
        "expected_root": root,
        "stream_ref": stream,
    }


def _bounded_text(event: TraceEventView, field: str) -> str:
    value = _require_text(event.event_type, event.lineage, field)
    if len(value.encode("utf-8")) > _MAX_TEXT_BYTES or "\x00" in value:
        raise ValueError(f"{event.event_type} trace {field} exceeds its bound")
    return value


def _bounded_value(event: TraceEventView, field: str, value: object) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise ValueError(f"{event.event_type} trace {field} is invalid")
    result = value
    if len(result.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError(f"{event.event_type} trace {field} exceeds its bound")
    return result


def _integer_value(event: TraceEventView, field: str, value: object) -> int:
    if type(value) is not int or not 0 <= (value) <= _MAX_INTEGER:
        raise ValueError(f"{event.event_type} trace {field} is invalid")
    return value


def _root_value(event: TraceEventView, field: str, value: object) -> str:
    if type(value) is not str or _ROOT_PATTERN.fullmatch((value)) is None:
        raise ValueError(f"{event.event_type} trace {field} is invalid")
    return value


def _optional_root(event: TraceEventView, field: str) -> None:
    value = event.lineage[field]
    if value != "":
        _root_value(event, field, value)


def _root(kind: str, body: object) -> str:
    prefix = b"pheroos-commit-decision-v2:" + kind.encode("ascii")
    return "sha256:" + sha256(prefix + b"\x00" + _canonical_bytes(body)).hexdigest()


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__: tuple[str, ...] = ()
