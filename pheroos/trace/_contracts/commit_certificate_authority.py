"""Independent Trace ABI validation for durable Commit Certificate v2."""

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
_LEAF_SCHEMA = "pheroos-commit-certificate-authority-leaf-v2"
_MAX_TEXT_BYTES = 4_096
_MAX_INTEGER = (2**53) - 1
_ROOT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TRANSITION_PATTERN = re.compile(r"transition:commit-certificate-v2:[0-9a-f]{64}\Z")
_PROFILES = {
    "certified": "pheroos-certified-commit-v1",
    "distributed": "pheroos-distributed-commit-v1",
}
_ROLES = frozenset(
    {
        "replay",
        "risk",
        "membership",
        "principal_verification",
        "evidence",
        "support",
        "stop",
        "permission",
    }
)
_LEAF_FIELDS = frozenset(
    {
        "schema",
        "role",
        "stream_ref",
        "revision",
        "transition_id",
        "snapshot_root",
        "head_root",
        "receipt_root",
        "leaf_root",
    }
)
_ROOT_FIELDS = (
    "parent_snapshot_root",
    "parent_head_root",
    "snapshot_root",
    "state_root",
    "history_root",
    "manifest_root",
    "commit_policy_root",
    "decision_snapshot_root",
    "decision_head_root",
    "decision_receipt_root",
    "decision_inclusion_root",
    "seal_snapshot_root",
    "seal_receipt_root",
    "seal_head_root",
    "seal_inclusion_root",
    "seal_root",
    "window_root",
    "frozen_dependency_root",
    "assessment_root",
    "claim_root",
    "evidence_root",
    "challenge_root",
    "lease_root",
    "output_contract_root",
    "output_payload_root",
    "authority_leaf_set_root",
    "certificate_body_root",
    "certificate_envelope_root",
    "source_context_root",
    "read_set_root",
)
_TEXT_FIELDS = (
    "parent_transition_id",
    "protocol_ref",
    "target_ref",
    "profile",
    "assurance",
    "decision_stream_ref",
    "decision_transition_id",
    "seal_transition_id",
    "candidate_ref",
    "certificate_id",
    "issuer_ref",
    "provenance_ref",
    "mutation_issuer_ref",
    "mutation_kind",
    "status",
)
_INTEGER_FIELDS = (
    "revision",
    "parent_revision",
    "history_count",
    "epoch",
    "current_step",
    "decision_revision",
    "seal_revision",
    "issued_at_step",
)
_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | frozenset(_ROOT_FIELDS)
    | frozenset(_TEXT_FIELDS)
    | frozenset(_INTEGER_FIELDS)
    | frozenset(
        {
            "authority_leaves",
            "attestation_refs",
            "reason_codes",
        }
    )
)
COMMIT_CERTIFICATE_EVENT_TYPES = frozenset(
    {"commit_certificate_verified_v2", "commit_certificate_conflict_v2"}
)


def _contract(event_type: str) -> TraceEventContract:
    def validate(event: TraceEventView) -> None:
        _validate_authority_envelope(event, required=_FIELDS)
        if set(event.lineage) != _FIELDS:
            raise ValueError(f"{event.event_type} trace lineage fields are not exact")
        _validate_certificate_event(event)

    return TraceEventContract(
        event_type=event_type,
        required_fields=_FIELDS,
        validator=validate,
        authority_relevant=True,
        schema_condition=True,
    )


COMMIT_CERTIFICATE_AUTHORITY_TRACE_EVENT_CONTRACTS = tuple(
    _contract(event_type) for event_type in COMMIT_CERTIFICATE_EVENT_TYPES
)


def _validate_certificate_event(event: TraceEventView) -> None:
    lineage = cast(dict[str, object], event.lineage)
    _validate_session_event(event, operation="evaluate_quorum")
    _require_session_bounds(
        event,
        targets=(cast(str, lineage["target_ref"]),),
        actions=(),
    )
    for field in _TEXT_FIELDS:
        value = _require_text(event.event_type, event.lineage, field)
        if len(value.encode("utf-8")) > _MAX_TEXT_BYTES or "\x00" in value:
            raise ValueError(f"{event.event_type} trace {field} exceeds its bound")
    for field in _ROOT_FIELDS:
        _require_root(event.event_type, event.lineage, field)
    counts = {
        field: _require_integer(event.event_type, event.lineage, field)
        for field in _INTEGER_FIELDS
    }
    _validate_identity(event, counts)
    _validate_status(event)
    leaves = _validate_leaves(event)
    _validate_text_arrays(event)
    _validate_derived_roots(event, leaves)


def _validate_identity(event: TraceEventView, counts: dict[str, int]) -> None:
    lineage = cast(dict[str, object], event.lineage)
    if (
        counts["revision"] < 1
        or counts["parent_revision"] != counts["revision"] - 1
        or counts["history_count"] != counts["revision"]
        or counts["decision_revision"] < counts["seal_revision"]
        or counts["seal_revision"] < 1
        or counts["issued_at_step"] != counts["current_step"]
        or counts["epoch"] != lineage["observed_epoch"]
    ):
        raise ValueError(f"{event.event_type} trace revision lineage is invalid")
    assurance = cast(str, lineage["assurance"])
    if assurance not in _PROFILES or lineage["profile"] != _PROFILES[assurance]:
        raise ValueError(f"{event.event_type} trace profile is mismatched")
    material = b"\x00".join(
        cast(str, lineage[field]).encode("utf-8")
        for field in ("scope_ref", "protocol_ref", "run_ref", "target_ref")
    )
    stream = "authority:commit-certificate-v2:" + sha256(material).hexdigest()
    transition = (
        "transition:commit-certificate-v2:"
        + sha256(
            stream.encode("utf-8")
            + b"\x00"
            + cast(str, lineage["request_ref"]).encode("utf-8")
        ).hexdigest()
    )
    if lineage["stream_ref"] != stream or lineage["transition_id"] != transition:
        raise ValueError(f"{event.event_type} trace identity is not canonical")
    if event.target != lineage["target_ref"]:
        raise ValueError(f"{event.event_type} trace target is mismatched")
    if lineage["issuer_ref"] != lineage["mutation_issuer_ref"]:
        raise ValueError(f"{event.event_type} trace issuer is mismatched")
    if counts["revision"] == 1:
        genesis = _root(
            "genesis-snapshot",
            {"schema": "pheroos-commit-certificate-snapshot-v2"},
        )
        if (
            lineage["parent_transition_id"] != "genesis"
            or lineage["parent_snapshot_root"] != genesis
        ):
            raise ValueError(f"{event.event_type} trace genesis parent is invalid")
    elif (
        _TRANSITION_PATTERN.fullmatch(cast(str, lineage["parent_transition_id"]))
        is None
    ):
        raise ValueError(f"{event.event_type} trace parent is invalid")


def _validate_status(event: TraceEventView) -> None:
    lineage = cast(dict[str, object], event.lineage)
    mutation = lineage["mutation_kind"]
    status = lineage["status"]
    if event.event_type == "commit_certificate_conflict_v2":
        if mutation != "conflict" or status != "conflict":
            raise ValueError("commit certificate conflict trace is inconsistent")
    elif mutation not in {"verified", "semantic_retry"} or status != "verified":
        raise ValueError("commit certificate verified trace is inconsistent")


def _validate_leaves(event: TraceEventView) -> list[dict[str, object]]:
    raw = event.lineage["authority_leaves"]
    if type(raw) is not list or len(raw) != len(_ROLES):
        raise ValueError(f"{event.event_type} trace authority leaves are incomplete")
    leaves = [_validate_leaf(event, item) for item in raw]
    roles = [cast(str, item["role"]) for item in leaves]
    streams = [cast(str, item["stream_ref"]) for item in leaves]
    if (
        frozenset(roles) != _ROLES
        or roles != sorted(roles, key=lambda item: item.encode("utf-8"))
        or len(streams) != len(set(streams))
    ):
        raise ValueError(f"{event.event_type} trace authority leaves collide")
    return leaves


def _validate_leaf(event: TraceEventView, raw: object) -> dict[str, object]:
    if type(raw) is not dict or set(raw) != _LEAF_FIELDS:
        raise ValueError(f"{event.event_type} trace authority leaf fields are invalid")
    item = cast(dict[str, object], raw)
    if item["schema"] != _LEAF_SCHEMA or item["role"] not in _ROLES:
        raise ValueError(f"{event.event_type} trace authority leaf version is invalid")
    for field in ("stream_ref", "transition_id"):
        _text_value(event, f"authority_leaves.{field}", item[field])
    revision = _integer_value(event, "authority_leaves.revision", item["revision"])
    if revision < 1:
        raise ValueError(f"{event.event_type} trace leaf revision is invalid")
    for field in ("snapshot_root", "head_root", "receipt_root"):
        _root_value(event, f"authority_leaves.{field}", item[field])
    body = {key: item[key] for key in _LEAF_FIELDS if key != "leaf_root"}
    if item["leaf_root"] != _root("authority-leaf", body):
        raise ValueError(f"{event.event_type} trace authority leaf root is invalid")
    return item


def _validate_text_arrays(event: TraceEventView) -> None:
    for field, minimum, maximum in (
        ("attestation_refs", 1, 32),
        ("reason_codes", 1, 64),
    ):
        raw = event.lineage[field]
        if type(raw) is not list or not minimum <= len(raw) <= maximum:
            raise ValueError(f"{event.event_type} trace {field} is not bounded")
        values = [_text_value(event, field, item) for item in raw]
        if values != sorted(values, key=lambda item: item.encode("utf-8")):
            raise ValueError(f"{event.event_type} trace {field} order is invalid")
        if len(values) != len(set(values)):
            raise ValueError(f"{event.event_type} trace {field} contains duplicates")


def _validate_derived_roots(
    event: TraceEventView, leaves: list[dict[str, object]]
) -> None:
    lineage = cast(dict[str, object], event.lineage)
    leaf_set = {
        "leaves": [
            {"role": item["role"], "leaf_root": item["leaf_root"]} for item in leaves
        ]
    }
    if lineage["authority_leaf_set_root"] != _root("authority-leaf-set", leaf_set):
        raise ValueError(f"{event.event_type} trace authority leaf set is invalid")
    source = _root(
        "source-context",
        {
            "request_root": lineage["request_root"],
            "manifest_root": lineage["manifest_root"],
            "decision_snapshot_root": lineage["decision_snapshot_root"],
            "decision_head_root": lineage["decision_head_root"],
            "seal_inclusion_root": lineage["seal_inclusion_root"],
            "parent_snapshot_root": (
                ""
                if lineage["parent_revision"] == 0
                else lineage["parent_snapshot_root"]
            ),
        },
    )
    if lineage["source_context_root"] != source:
        raise ValueError(f"{event.event_type} trace source context is invalid")
    if lineage["read_set_root"] != _read_set_root(lineage, leaves):
        raise ValueError(f"{event.event_type} trace read set is invalid")


def _read_set_root(lineage: dict[str, object], leaves: list[dict[str, object]]) -> str:
    binding = cast(dict[str, object], lineage["session_binding"])
    entries = [
        _precondition(
            cast(str, lineage["stream_ref"]),
            cast(int, lineage["parent_revision"]),
            cast(str, lineage["parent_head_root"]),
        ),
        _precondition(
            cast(str, lineage["decision_stream_ref"]),
            cast(int, lineage["decision_revision"]),
            cast(str, lineage["decision_head_root"]),
        ),
        *[
            _precondition(
                cast(str, item["stream_ref"]),
                cast(int, item["revision"]),
                cast(str, item["head_root"]),
            )
            for item in leaves
        ],
        _precondition(
            _authority_stream_ref(
                "issuer-grant",
                (cast(str, lineage["scope_ref"]), cast(str, lineage["grant_ref"])),
            ),
            cast(int, binding["grant_expected_revision"]),
            cast(str, binding["grant_expected_root"]),
        ),
        _precondition(
            _LIFECYCLE_STREAM,
            cast(int, binding["lifecycle_expected_revision"]),
            cast(str, binding["lifecycle_expected_root"]),
        ),
    ]
    entries.sort(key=lambda item: cast(str, item["stream_ref"]).encode("utf-8"))
    if len({item["stream_ref"] for item in entries}) != 12:
        raise ValueError("commit certificate trace read-set streams collide")
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


def _text_value(event: TraceEventView, field: str, value: object) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise ValueError(f"{event.event_type} trace {field} is invalid")
    result = value
    if len(result.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError(f"{event.event_type} trace {field} exceeds its bound")
    return result


def _integer_value(event: TraceEventView, field: str, value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_INTEGER:
        raise ValueError(f"{event.event_type} trace {field} is invalid")
    return value


def _root_value(event: TraceEventView, field: str, value: object) -> str:
    if type(value) is not str or _ROOT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{event.event_type} trace {field} is invalid")
    return value


def _root(kind: str, body: object) -> str:
    material = b"pheroos-commit-certificate-v2\x00" + kind.encode("utf-8")
    return "sha256:" + sha256(material + b"\x00" + _canonical_bytes(body)).hexdigest()


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__: tuple[str, ...] = ()
