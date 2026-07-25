"""Independent Trace ABI validation for Commit Evidence v2 authority."""

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
    _require_integer_value,
    _require_root,
    _require_root_value,
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
_EVIDENCE_TRANSITION = re.compile(r"transition:commit-evidence-v2:[0-9a-f]{64}\Z")
_PROFILES = {
    "advisory": frozenset({"pheroos-commit-integrity-v1"}),
    "evidence_bound": frozenset(
        {"pheroos-commit-integrity-v1", "pheroos-hybrid-commit-v1"}
    ),
    "certified": frozenset({"pheroos-certified-commit-v1"}),
    "distributed": frozenset({"pheroos-distributed-commit-v1"}),
}
_ROOT_ARRAY_FIELDS = (
    "mutation_trace_roots",
    "mutation_record_roots",
    "removed_record_roots",
    "revocation_roots",
    "attestation_roots",
    "disposition_roots",
)
_DEPENDENCY_NAMES = ("membership", "verification", "replay")
_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | frozenset(
        {
            "target_ref",
            "advance_ref",
            "protocol_ref",
            "manifest_root",
            "authority_policy_root",
            "commit_policy_root",
            "evidence_policy_root",
            "profile",
            "assurance",
            "epoch",
            "revision",
            "current_step",
            "expires_at_step",
            "parent_revision",
            "parent_epoch",
            "parent_transition_id",
            "parent_snapshot_root",
            "parent_history_root",
            "parent_history_count",
            "parent_head_root",
            "snapshot_root",
            "history_root",
            "history_count",
            "mutation_issuer_ref",
            "mutation_provenance_root",
            "mutation_trace_roots",
            "mutation_record_roots",
            "removed_record_roots",
            "revocation_roots",
            "attestation_roots",
            "disposition_roots",
            "record_count",
            "active_record_count",
            "record_set_root",
            "active_record_set_root",
            "mutation_delta_root",
            "membership_stream_ref",
            "membership_revision",
            "membership_transition_id",
            "membership_head_root",
            "membership_snapshot_root",
            "membership_root",
            "membership_current_step",
            "membership_expires_at_step",
            "verification_stream_ref",
            "verification_revision",
            "verification_transition_id",
            "verification_head_root",
            "verification_snapshot_root",
            "verification_set_root",
            "verification_current_step",
            "verification_expires_at_step",
            "replay_stream_ref",
            "replay_revision",
            "replay_transition_id",
            "replay_head_root",
            "replay_snapshot_root",
            "replay_receipt_root",
            "replay_current_step",
            "source_context_root",
            "read_set_root",
        }
    )
)


def _validate(event: TraceEventView) -> None:
    _validate_authority_envelope(event, required=_FIELDS)
    if set(event.lineage) != _FIELDS:
        raise ValueError("commit evidence trace fields are not exact")
    _validate_session_event(event, operation="qualify_evidence")
    lineage = event.lineage
    _require_session_bounds(event, targets=(lineage["target_ref"],), actions=())
    _validate_text_and_roots(event)
    _validate_identity(event)
    _validate_counts(event)
    _validate_arrays(event)
    _validate_derived_roots(event)


COMMIT_EVIDENCE_AUTHORITY_TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    TraceEventContract(
        event_type="commit_evidence_qualified_v2",
        required_fields=_FIELDS,
        validator=_validate,
        authority_relevant=True,
        schema_condition=True,
    ),
)


def _validate_text_and_roots(event: TraceEventView) -> None:
    lineage = event.lineage
    for field in (
        "scope_ref",
        "run_ref",
        "request_ref",
        "target_ref",
        "advance_ref",
        "protocol_ref",
        "profile",
        "assurance",
        "parent_transition_id",
        "mutation_issuer_ref",
        "membership_stream_ref",
        "membership_transition_id",
        "verification_stream_ref",
        "verification_transition_id",
        "replay_stream_ref",
        "replay_transition_id",
    ):
        _require_text(event.event_type, lineage, field)
    for field in (
        "manifest_root",
        "authority_policy_root",
        "commit_policy_root",
        "evidence_policy_root",
        "parent_snapshot_root",
        "parent_history_root",
        "parent_head_root",
        "snapshot_root",
        "history_root",
        "mutation_provenance_root",
        "record_set_root",
        "active_record_set_root",
        "mutation_delta_root",
        "membership_head_root",
        "membership_snapshot_root",
        "membership_root",
        "verification_head_root",
        "verification_snapshot_root",
        "verification_set_root",
        "replay_head_root",
        "replay_snapshot_root",
        "replay_receipt_root",
        "source_context_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    if event.target != lineage["target_ref"]:
        raise ValueError("commit evidence trace target is mismatched")


def _validate_identity(event: TraceEventView) -> None:
    lineage = event.lineage
    assurance = lineage["assurance"]
    if assurance not in _PROFILES or lineage["profile"] not in _PROFILES[assurance]:
        raise ValueError("commit evidence trace profile is mismatched")
    expected_stream = _authority_stream_ref(
        "commit-evidence-v2",
        (
            lineage["scope_ref"],
            lineage["protocol_ref"],
            lineage["run_ref"],
            lineage["target_ref"],
        ),
    )
    if lineage["stream_ref"] != expected_stream:
        raise ValueError("commit evidence trace stream_ref is not canonical")
    transition = (
        "transition:commit-evidence-v2:"
        + sha256(
            expected_stream.encode("utf-8")
            + b"\x00"
            + lineage["advance_ref"].encode("utf-8")
        ).hexdigest()
    )
    if lineage["transition_id"] != transition:
        raise ValueError("commit evidence trace transition_id is not canonical")


def _validate_counts(event: TraceEventView) -> None:
    lineage = event.lineage
    values = {
        field: _require_integer(event.event_type, lineage, field)
        for field in (
            "epoch",
            "revision",
            "current_step",
            "expires_at_step",
            "parent_revision",
            "parent_history_count",
            "history_count",
            "record_count",
            "active_record_count",
            "membership_revision",
            "membership_current_step",
            "membership_expires_at_step",
            "verification_revision",
            "verification_current_step",
            "verification_expires_at_step",
            "replay_revision",
            "replay_current_step",
        )
    }
    parent_epoch = lineage["parent_epoch"]
    if parent_epoch is not None:
        _require_integer_value(event.event_type, "parent_epoch", parent_epoch)
    if (
        values["revision"] < 1
        or values["parent_revision"] != values["revision"] - 1
        or values["history_count"] != values["revision"]
        or values["parent_history_count"] != values["parent_revision"]
        or values["active_record_count"] > values["record_count"]
        or not values["current_step"] < values["expires_at_step"]
        or not values["membership_current_step"]
        <= values["current_step"]
        < values["membership_expires_at_step"]
        or not values["verification_current_step"]
        <= values["current_step"]
        < values["verification_expires_at_step"]
        or values["replay_current_step"] > values["current_step"]
    ):
        raise ValueError("commit evidence trace counts are inconsistent")
    if values["revision"] == 1:
        _validate_genesis(event)
    elif (
        parent_epoch is None
        or _EVIDENCE_TRANSITION.fullmatch(lineage["parent_transition_id"]) is None
    ):
        raise ValueError("commit evidence trace successor parent is invalid")


def _validate_genesis(event: TraceEventView) -> None:
    lineage = event.lineage
    snapshot_root = _evidence_root(
        "genesis-parent",
        {
            "schema": "pheroos-commit-evidence-snapshot-v2",
            "canonical_version": _CANONICAL_VERSION,
        },
    )
    history_root = _evidence_root(
        "history-genesis",
        {"canonical_version": _CANONICAL_VERSION},
    )
    if (
        lineage["parent_epoch"] is not None
        or lineage["parent_transition_id"] != "genesis"
        or lineage["parent_snapshot_root"] != snapshot_root
        or lineage["parent_history_root"] != history_root
    ):
        raise ValueError("commit evidence trace genesis parent is invalid")


def _validate_arrays(event: TraceEventView) -> None:
    for field in _ROOT_ARRAY_FIELDS:
        value = event.lineage[field]
        if (
            type(value) is not list
            or value != sorted(value)
            or len(value) != len(set(value))
        ):
            raise ValueError(f"commit evidence trace {field} is not canonical")
        for index, item in enumerate(value):
            _require_root_value(event.event_type, f"{field}[{index}]", item)
    if not event.lineage["mutation_trace_roots"]:
        raise ValueError("commit evidence trace requires mutation trace lineage")


def _validate_derived_roots(event: TraceEventView) -> None:
    lineage = event.lineage
    mutation = _evidence_root(
        "mutation-delta",
        {
            "transition_id": lineage["transition_id"],
            "mutation_issuer_ref": lineage["mutation_issuer_ref"],
            "mutation_provenance_root": lineage["mutation_provenance_root"],
            "mutation_trace_roots": lineage["mutation_trace_roots"],
            "mutation_record_roots": lineage["mutation_record_roots"],
            "removed_record_roots": lineage["removed_record_roots"],
            "revocation_roots": lineage["revocation_roots"],
            "record_set_root": lineage["record_set_root"],
            "active_record_set_root": lineage["active_record_set_root"],
        },
    )
    history = _evidence_root(
        "history-successor",
        {
            "parent_history_root": lineage["parent_history_root"],
            "parent_history_count": lineage["parent_history_count"],
            "transition_id": lineage["transition_id"],
            "mutation_delta_root": mutation,
        },
    )
    if mutation != lineage["mutation_delta_root"] or history != lineage["history_root"]:
        raise ValueError("commit evidence trace history roots are mismatched")
    if _source_root(lineage) != lineage["source_context_root"]:
        raise ValueError("commit evidence trace source root is mismatched")
    if _read_set_root(lineage) != lineage["read_set_root"]:
        raise ValueError("commit evidence trace read set root is mismatched")


def _source_root(lineage: dict[str, object]) -> str:
    body = {
        "version": "pheroos-commit-evidence-source-v2",
        "request_root": lineage["request_root"],
        "manifest_root": lineage["manifest_root"],
        "authority_policy_root": lineage["authority_policy_root"],
        "commit_policy_root": lineage["commit_policy_root"],
        "evidence_policy_root": lineage["evidence_policy_root"],
        "membership_head_root": lineage["membership_head_root"],
        "membership_snapshot_root": lineage["membership_snapshot_root"],
        "membership_root": lineage["membership_root"],
        "verification_head_root": lineage["verification_head_root"],
        "verification_snapshot_root": lineage["verification_snapshot_root"],
        "verification_set_root": lineage["verification_set_root"],
        "replay_head_root": lineage["replay_head_root"],
        "replay_snapshot_root": lineage["replay_snapshot_root"],
        "replay_receipt_root": lineage["replay_receipt_root"],
        "attestation_roots": lineage["attestation_roots"],
        "disposition_roots": lineage["disposition_roots"],
        "revocation_roots": lineage["revocation_roots"],
    }
    return _evidence_root("source-context", body)


def _read_set_root(lineage: dict[str, object]) -> str:
    binding = _string_object(lineage["session_binding"], "session_binding")
    entries = [
        _precondition(
            _text(lineage, "stream_ref"),
            _count(lineage, "parent_revision"),
            _text(lineage, "parent_head_root"),
        ),
        _precondition(
            _authority_stream_ref(
                "issuer-grant",
                (_text(lineage, "scope_ref"), _text(lineage, "grant_ref")),
            ),
            _count(binding, "grant_expected_revision"),
            _text(binding, "grant_expected_root"),
        ),
        _precondition(
            _LIFECYCLE_STREAM,
            _count(binding, "lifecycle_expected_revision"),
            _text(binding, "lifecycle_expected_root"),
        ),
    ]
    for name in _DEPENDENCY_NAMES:
        entries.append(
            _precondition(
                _text(lineage, f"{name}_stream_ref"),
                _count(lineage, f"{name}_revision"),
                _text(lineage, f"{name}_head_root"),
            )
        )
    if len({item["stream_ref"] for item in entries}) != 6:
        raise ValueError("commit evidence trace dependency streams overlap")
    entries.sort(key=lambda item: _text(item, "stream_ref").encode("utf-8"))
    return (
        "sha256:"
        + sha256(
            _canonical(
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


def _string_object(value: object, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"commit evidence trace {label} is not an object")
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        raise ValueError(f"commit evidence trace {label} keys are invalid")
    return {cast(str, key): item for key, item in raw.items()}


def _text(value: dict[str, object], field: str) -> str:
    item = value[field]
    if type(item) is not str:
        raise ValueError(f"commit evidence trace {field} is invalid")
    return item


def _count(value: dict[str, object], field: str) -> int:
    item = value[field]
    if type(item) is not int:
        raise ValueError(f"commit evidence trace {field} is invalid")
    return item


def _evidence_root(kind: str, body: object) -> str:
    prefix = b"pheroos-commit-evidence-v2:" + kind.encode("ascii") + b"\x00"
    return "sha256:" + sha256(prefix + _canonical(body)).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__: tuple[str, ...] = ()
