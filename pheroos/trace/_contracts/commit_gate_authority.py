"""Independent Trace ABI validation for durable Commit Gate v2 events."""

from __future__ import annotations

from collections.abc import Mapping
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
_ROOT_PREFIX = "pheroos-governance-authority-v2:"
_LIFECYCLE_STREAM = "authority:domain-lifecycle"
_MAX_TEXT_BYTES = 4096
_MAX_ITEMS = 4096
_PROFILES = {
    "advisory": frozenset({"pheroos-commit-integrity-v1"}),
    "evidence_bound": frozenset(
        {"pheroos-commit-integrity-v1", "pheroos-hybrid-commit-v1"}
    ),
    "certified": frozenset({"pheroos-certified-commit-v1"}),
    "distributed": frozenset({"pheroos-distributed-commit-v1"}),
}
_TRANSITION_PATTERNS = {
    "stop": re.compile(r"transition:commit-stop-v2:[0-9a-f]{64}\Z"),
    "permission": re.compile(r"transition:commit-permission-v2:[0-9a-f]{64}\Z"),
}
_DEPENDENCY_NAMES = ("replay", "risk", "verification", "membership", "support")
_DEPENDENCY_FIELDS = frozenset(
    f"{name}_{suffix}"
    for name in _DEPENDENCY_NAMES
    for suffix in (
        "stream_ref",
        "revision",
        "transition_id",
        "snapshot_root",
        "head_root",
    )
)
_GATE_COMMON_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | _DEPENDENCY_FIELDS
    | frozenset(
        {
            "target_ref",
            "protocol_ref",
            "manifest_root",
            "commit_policy_root",
            "policy_root",
            "profile",
            "assurance",
            "revision",
            "current_step",
            "parent_revision",
            "parent_transition_id",
            "parent_snapshot_root",
            "parent_head_root",
            "snapshot_root",
            "mutation_issuer_ref",
            "grant_issuer_ref",
            "issued_at_step",
            "expires_at_step",
            "dependency_root",
            "evaluation_context_root",
            "source_context_root",
            "read_set_root",
        }
    )
)
_STOP_FIELDS = _GATE_COMMON_FIELDS | frozenset(
    {"resolution_ref", "blocked", "reason_codes", "reason_root"}
)
_PERMISSION_FIELDS = _GATE_COMMON_FIELDS | frozenset(
    {
        "permission_ref",
        "allowed",
        "candidate_refs",
        "candidate_set_root",
        "claim_roots",
        "claims_root",
    }
)


def _contract(
    event_type: str, required: frozenset[str], kind: str
) -> TraceEventContract:
    def validate(event: TraceEventView) -> None:
        _validate_authority_envelope(event, required=required)
        unknown = sorted(set(event.lineage) - required)
        if unknown:
            raise ValueError(
                f"{event.event_type} trace lineage contains unknown fields: "
                + ", ".join(unknown)
            )
        _validate_commit_gate_event(event, kind=kind)

    return TraceEventContract(
        event_type=event_type,
        required_fields=required,
        validator=validate,
        authority_relevant=True,
        schema_condition=True,
    )


COMMIT_GATE_AUTHORITY_TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    _contract("commit_stop_resolved_v2", _STOP_FIELDS, "stop"),
    _contract("commit_permission_issued_v2", _PERMISSION_FIELDS, "permission"),
)


def _validate_commit_gate_event(event: TraceEventView, *, kind: str) -> None:
    lineage = event.lineage
    operation = "resolve_stop" if kind == "stop" else "issue_action_permission"
    _validate_session_event(event, operation=operation)
    for field in (
        "target_ref",
        "protocol_ref",
        "profile",
        "assurance",
        "parent_transition_id",
        "mutation_issuer_ref",
        "grant_issuer_ref",
    ):
        _require_gate_text(event, field)
    for field in (
        "manifest_root",
        "commit_policy_root",
        "policy_root",
        "parent_snapshot_root",
        "parent_head_root",
        "snapshot_root",
        "dependency_root",
        "evaluation_context_root",
        "source_context_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    revision = _require_integer(event.event_type, lineage, "revision")
    current_step = _require_integer(event.event_type, lineage, "current_step")
    parent_revision = _require_integer(event.event_type, lineage, "parent_revision")
    issued = _require_integer(event.event_type, lineage, "issued_at_step")
    expires = _require_integer(event.event_type, lineage, "expires_at_step")
    if revision < 1 or parent_revision != revision - 1:
        raise ValueError(f"{event.event_type} trace revision lineage is invalid")
    if not issued <= current_step < expires:
        raise ValueError(f"{event.event_type} trace gate is not fresh")
    if event.target != lineage["target_ref"]:
        raise ValueError(f"{event.event_type} trace target is mismatched")
    if lineage["grant_issuer_ref"] != lineage["mutation_issuer_ref"]:
        raise ValueError(f"{event.event_type} trace issuer binding is mismatched")
    _validate_profile(event)
    _require_session_bounds(
        event,
        targets=(lineage["target_ref"],),
        actions=() if kind == "stop" else ("commit",),
    )
    _validate_identity(event, kind=kind)
    dependency = _validate_dependencies(event)
    _validate_derived_roots(event, dependency, kind=kind)


def _validate_profile(event: TraceEventView) -> None:
    assurance = event.lineage["assurance"]
    profile = event.lineage["profile"]
    if assurance not in _PROFILES or profile not in _PROFILES[assurance]:
        raise ValueError(f"{event.event_type} trace profile is mismatched")


def _validate_identity(event: TraceEventView, *, kind: str) -> None:
    lineage = event.lineage
    request_field = "resolution_ref" if kind == "stop" else "permission_ref"
    request_ref = _require_gate_text(event, request_field)
    if lineage["request_ref"] != request_ref:
        raise ValueError(f"{event.event_type} trace request_ref is mismatched")
    material = (
        lineage["scope_ref"],
        lineage["protocol_ref"],
        lineage["run_ref"],
        lineage["target_ref"],
        "commit",
    )
    digest = sha256("\x00".join(material).encode("utf-8")).hexdigest()
    expected_stream = f"authority:commit-{kind}-v2:{digest}"
    if lineage["stream_ref"] != expected_stream:
        raise ValueError(f"{event.event_type} trace stream_ref is not canonical")
    transition = "transition:commit-{}-v2:{}".format(
        kind,
        sha256(
            expected_stream.encode("utf-8") + b"\x00" + request_ref.encode("utf-8")
        ).hexdigest(),
    )
    if lineage["transition_id"] != transition:
        raise ValueError(f"{event.event_type} trace transition_id is not canonical")
    if lineage["revision"] == 1:
        genesis = _root(
            f"{kind}-genesis-parent",
            {"schema": f"pheroos-commit-{kind}-snapshot-v2"},
        )
        if (
            lineage["parent_revision"] != 0
            or lineage["parent_transition_id"] != "genesis"
            or lineage["parent_snapshot_root"] != genesis
        ):
            raise ValueError(f"{event.event_type} trace genesis parent is invalid")
    elif _TRANSITION_PATTERNS[kind].fullmatch(lineage["parent_transition_id"]) is None:
        raise ValueError(f"{event.event_type} trace parent transition is invalid")


def _validate_dependencies(event: TraceEventView) -> dict[str, object]:
    lineage = event.lineage
    body: dict[str, object] = {
        "schema": "pheroos-commit-gate-dependencies-v2",
        "canonical_version": _CANONICAL_VERSION,
    }
    streams = []
    for name in _DEPENDENCY_NAMES:
        stream = _require_gate_text(event, f"{name}_stream_ref")
        streams.append(stream)
        revision = _require_integer(event.event_type, lineage, f"{name}_revision")
        if revision < 1:
            raise ValueError(f"{event.event_type} trace dependency revision is invalid")
        _require_gate_text(event, f"{name}_transition_id")
        _require_root(event.event_type, lineage, f"{name}_snapshot_root")
        _require_root(event.event_type, lineage, f"{name}_head_root")
        for suffix in (
            "stream_ref",
            "revision",
            "transition_id",
            "snapshot_root",
            "head_root",
        ):
            body[f"{name}_{suffix}"] = lineage[f"{name}_{suffix}"]
    if len(streams) != len(set(streams)):
        raise ValueError(f"{event.event_type} trace dependency streams collide")
    if lineage["dependency_root"] != _root("dependencies", body):
        raise ValueError(f"{event.event_type} trace dependency_root is mismatched")
    return body


def _validate_derived_roots(
    event: TraceEventView, dependency_body: dict[str, object], *, kind: str
) -> None:
    lineage = event.lineage
    policy = _root(
        f"{kind}-policy",
        {
            "policy_version": f"pheroos-commit-{kind}-policy-v2",
            "authority_operation": (
                "resolve_stop" if kind == "stop" else "issue_action_permission"
            ),
            "manifest_root": lineage["manifest_root"],
            "commit_policy_root": lineage["commit_policy_root"],
            "protocol_ref": lineage["protocol_ref"],
            "target_ref": lineage["target_ref"],
        },
    )
    if lineage["policy_root"] != policy:
        raise ValueError(f"{event.event_type} trace policy_root is mismatched")
    context = _root(
        "evaluation-context",
        {
            "version": "pheroos-commit-gate-context-v2",
            "domain_root": lineage["domain_root"],
            "scope_ref": lineage["scope_ref"],
            "manifest_root": lineage["manifest_root"],
            "commit_policy_root": lineage["commit_policy_root"],
            "profile": lineage["profile"],
            "assurance": lineage["assurance"],
            "protocol_ref": lineage["protocol_ref"],
            "run_ref": lineage["run_ref"],
            "target_ref": lineage["target_ref"],
            "observed_epoch": lineage["observed_epoch"],
            "current_step": lineage["current_step"],
            "dependency_root": lineage["dependency_root"],
        },
    )
    if lineage["evaluation_context_root"] != context:
        raise ValueError(
            f"{event.event_type} trace evaluation_context_root is mismatched"
        )
    source = _root(
        "source-context",
        {
            "kind": kind,
            "request_root": lineage["request_root"],
            "evaluation_context_root": context,
            "dependency_root": lineage["dependency_root"],
        },
    )
    if lineage["source_context_root"] != source:
        raise ValueError(f"{event.event_type} trace source_context_root is mismatched")
    decision_fields = _validate_decision_fields(event, kind=kind)
    snapshot = _snapshot_wire(lineage, dependency_body, decision_fields, kind=kind)
    if snapshot["snapshot_root"] != lineage["snapshot_root"]:
        raise ValueError(f"{event.event_type} trace snapshot_root is mismatched")
    request = _request_wire(lineage, snapshot, kind=kind)
    if request["request_root"] != lineage["request_root"]:
        raise ValueError(f"{event.event_type} trace request_root is mismatched")
    if _expected_read_set_root(lineage) != lineage["read_set_root"]:
        raise ValueError(f"{event.event_type} trace read_set_root is mismatched")


def _validate_decision_fields(event: TraceEventView, *, kind: str) -> dict[str, object]:
    lineage = event.lineage
    if kind == "stop":
        if type(lineage["blocked"]) is not bool:
            raise ValueError("commit stop trace blocked must be an exact bool")
        reasons = _canonical_text_array(event, "reason_codes", allow_empty=True)
        if lineage["blocked"] and not reasons:
            raise ValueError("blocked commit stop trace requires reasons")
        reason_root = _root("stop-reasons", {"reason_codes": reasons})
        if lineage["reason_root"] != reason_root:
            raise ValueError("commit stop trace reason_root is mismatched")
        return {
            "resolution_ref": lineage["resolution_ref"],
            "blocked": lineage["blocked"],
            "reason_codes": reasons,
            "reason_root": reason_root,
        }
    if type(lineage["allowed"]) is not bool:
        raise ValueError("commit permission trace allowed must be an exact bool")
    candidates = _canonical_text_array(event, "candidate_refs", allow_empty=False)
    claims = _canonical_root_array(
        event, "claim_roots", allow_empty=not lineage["allowed"]
    )
    candidate_root = _root("candidate-set", {"candidate_refs": candidates})
    claims_root = _root("claims", {"claim_roots": claims})
    if (
        lineage["candidate_set_root"] != candidate_root
        or lineage["claims_root"] != claims_root
    ):
        raise ValueError("commit permission trace set root is mismatched")
    return {
        "permission_ref": lineage["permission_ref"],
        "allowed": lineage["allowed"],
        "candidate_refs": candidates,
        "candidate_set_root": candidate_root,
        "claim_roots": claims,
        "claims_root": claims_root,
    }


def _snapshot_wire(
    lineage: Mapping[str, object],
    dependency_body: dict[str, object],
    decision: dict[str, object],
    *,
    kind: str,
) -> dict[str, object]:
    dependencies = {**dependency_body, "dependency_root": lineage["dependency_root"]}
    body = {
        "schema": f"pheroos-commit-{kind}-snapshot-v2",
        "state_schema": f"pheroos-commit-{kind}-state-v2",
        "canonical_version": _CANONICAL_VERSION,
        **{
            field: lineage[field]
            for field in (
                "domain_root",
                "scope_ref",
                "manifest_root",
                "commit_policy_root",
                "policy_root",
                "profile",
                "assurance",
                "protocol_ref",
                "run_ref",
                "target_ref",
                "observed_epoch",
                "current_step",
                "stream_ref",
                "transition_id",
                "revision",
                "parent_revision",
                "parent_transition_id",
                "parent_snapshot_root",
                "mutation_issuer_ref",
                "issued_at_step",
                "expires_at_step",
                "evaluation_context_root",
            )
        },
        "dependencies": dependencies,
        **decision,
    }
    snapshot_root = _root(f"{kind}-snapshot", body)
    return {**body, "snapshot_root": snapshot_root}


def _request_wire(
    lineage: Mapping[str, object], snapshot: dict[str, object], *, kind: str
) -> dict[str, object]:
    request_ref = "resolution_ref" if kind == "stop" else "permission_ref"
    body = {
        "schema": f"pheroos-commit-{kind}-request-v2",
        "canonical_version": _CANONICAL_VERSION,
        **{
            field: lineage[field]
            for field in (
                "domain_root",
                "scope_ref",
                "run_ref",
                "target_ref",
                "observed_epoch",
                "stream_ref",
                "transition_id",
            )
        },
        request_ref: lineage[request_ref],
        "snapshot": snapshot,
    }
    return {**body, "request_root": _root(f"{kind}-request", body)}


def _expected_read_set_root(lineage: Mapping[str, object]) -> str:
    binding = cast(dict[str, object], lineage["session_binding"])
    entries = [
        _precondition(
            cast(str, lineage["stream_ref"]),
            cast(int, lineage["parent_revision"]),
            cast(str, lineage["parent_head_root"]),
        ),
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
    ]
    for name in _DEPENDENCY_NAMES:
        entries.append(
            _precondition(
                cast(str, lineage[f"{name}_stream_ref"]),
                cast(int, lineage[f"{name}_revision"]),
                cast(str, lineage[f"{name}_head_root"]),
            )
        )
    entries.sort(key=lambda item: cast(str, item["stream_ref"]).encode("utf-8"))
    payload = {
        "canonical_version": _CANONICAL_VERSION,
        "entries": entries,
        "schema": _READ_SET_SCHEMA,
    }
    return "sha256:" + sha256(_canonical_bytes(payload)).hexdigest()


def _precondition(stream: str, revision: int, root: str) -> dict[str, object]:
    return {
        "expected_revision": revision,
        "expected_root": root,
        "stream_ref": stream,
    }


def _canonical_text_array(
    event: TraceEventView, field: str, *, allow_empty: bool
) -> list[str]:
    value = event.lineage[field]
    if type(value) is not list or len(value) > _MAX_ITEMS:
        raise ValueError(f"{event.event_type} trace {field} must be a bounded array")
    for item in value:
        if (
            type(item) is not str
            or not item
            or len(item.encode("utf-8")) > _MAX_TEXT_BYTES
        ):
            raise ValueError(f"{event.event_type} trace {field} text is invalid")
    if (not allow_empty and not value) or len(value) != len(set(value)):
        raise ValueError(f"{event.event_type} trace {field} cardinality is invalid")
    expected = sorted(value, key=lambda item: item.encode("utf-8"))
    if value != expected:
        raise ValueError(f"{event.event_type} trace {field} is not canonical")
    return cast(list[str], value)


def _canonical_root_array(
    event: TraceEventView, field: str, *, allow_empty: bool
) -> list[str]:
    values = _canonical_text_array(event, field, allow_empty=allow_empty)
    for value in values:
        if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
            raise ValueError(f"{event.event_type} trace {field} root is invalid")
    return values


def _require_gate_text(event: TraceEventView, field: str) -> str:
    value = _require_text(event.event_type, event.lineage, field)
    if len(value.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError(f"{event.event_type} trace {field} exceeds its byte bound")
    return value


def _root(kind: str, body: object) -> str:
    prefix = (_ROOT_PREFIX + "commit-gate-v2:" + kind).encode("utf-8")
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
