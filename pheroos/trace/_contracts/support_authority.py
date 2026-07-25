"""Closed Trace ABI for the durable Support v2 ledger.

The validators in this module are Trace-owned.  They intentionally reproduce
the portable Support identities from declared lineage instead of importing a
Governance producer as an implementation oracle.
"""

from __future__ import annotations

from hashlib import sha256
import json
import re

from pheroos.trace._contracts.authority import (
    _COMMON_FIELDS,
    _SESSION_FIELDS,
    _authority_stream_ref,
    _require_choice,
    _require_integer,
    _require_root,
    _require_root_value,
    _require_session_targets,
    _require_text,
    _validate_authority_envelope,
    _validate_session_event,
)
from pheroos.trace._contracts.base import TraceEventContract
from pheroos.trace._validation_core import TraceEventView


_SUPPORT_TRANSITION = re.compile(r"transition:support-v2:[0-9a-f]{64}\Z")
_MEMBERSHIP_STREAM = re.compile(r"authority:membership-v2:[0-9a-f]{64}\Z")
_MEMBERSHIP_TRANSITION = re.compile(r"transition:membership-v2:[0-9a-f]{64}\Z")
_PROFILES_BY_ASSURANCE = {
    "advisory": frozenset({"pheroos-commit-integrity-v1"}),
    "evidence_bound": frozenset(
        {"pheroos-commit-integrity-v1", "pheroos-hybrid-commit-v1"}
    ),
    "certified": frozenset({"pheroos-certified-commit-v1"}),
    "distributed": frozenset({"pheroos-distributed-commit-v1"}),
}
_MUTATION_KINDS = frozenset({"initialize", "issue", "revoke", "switch"})
_MAX_TEXT_BYTES = 4096
_MAX_LEASES = 16_384
_MAX_TRACE_ROOTS = 1024
_MAX_REASON_CODES = 128
_CANONICAL_VERSION = "pheroos-authority-canonical-v2"
_ROOT_PREFIX = "pheroos-governance-authority-v2:support-v2:"

_SUPPORT_COMMON_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | frozenset(
        "profile assurance manifest_root commit_policy_root authority_policy_root "
        "protocol_ref target_ref mutation_issuer_ref".split()
    )
)
_SUPPORT_STATE_FIELDS = _SUPPORT_COMMON_FIELDS | frozenset(
    (
        "mutation_kind revision initialized_at_step current_step "
        "mutation_provenance_root mutation_trace_roots mutation_delta_root "
        "evicted_lease_roots parent_revision parent_transition_id "
        "parent_snapshot_root parent_history_root parent_history_count history_root "
        "history_count parent_head_root snapshot_root lease_set_root "
        "active_lease_count issued_lease_root revoked_lease_root revocation_root "
        "membership_stream_ref membership_transition_id membership_snapshot_root "
        "source_context_root source_verification_root read_set_root"
    ).split()
)
_SUPPORT_ISSUED_FIELDS = _SUPPORT_COMMON_FIELDS | frozenset(
    (
        "lease_root lease_ref mutation_transition_id proposal_root candidate_ref "
        "claim_root epoch principal_ref principal_cluster_ref "
        "membership_principal_root principal_verification_root membership_stream_ref "
        "membership_transition_id membership_snapshot_root membership_root "
        "positive_observation_set_root prior_lease_root issuance_issuer_ref "
        "issued_at_step expires_at_step proposal_provenance_root proposal_trace_roots "
        "issuance_provenance_root issuance_trace_roots read_set_root"
    ).split()
)
_SUPPORT_REVOKED_FIELDS = _SUPPORT_COMMON_FIELDS | frozenset(
    (
        "revocation_root revocation_ref mutation_transition_id lease_root "
        "candidate_ref claim_root epoch principal_ref principal_cluster_ref "
        "lease_issuance_issuer_ref revocation_issuer_ref reason_codes "
        "revoked_at_step provenance_root source_trace_roots read_set_root"
    ).split()
)


def _support_root(kind: str, body: object) -> str:
    payload = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    prefix = (_ROOT_PREFIX + kind).encode("utf-8")
    return "sha256:" + sha256(prefix + b"\x00" + payload).hexdigest()


_SUPPORT_GENESIS_SNAPSHOT_ROOT = _support_root(
    "genesis-parent",
    {
        "schema": "pheroos-support-snapshot-v2",
        "canonical_version": _CANONICAL_VERSION,
    },
)
_SUPPORT_GENESIS_HISTORY_ROOT = _support_root(
    "history-genesis",
    {"canonical_version": _CANONICAL_VERSION},
)
_EMPTY_LEASE_SET_ROOT = _support_root("lease-set", {"leases": []})


def _contract(event_type: str, required: frozenset[str]) -> TraceEventContract:
    def validate(event: TraceEventView) -> None:
        _validate_authority_envelope(event, required=required)
        unknown = sorted(set(event.lineage) - required)
        if unknown:
            raise ValueError(
                f"{event.event_type} trace lineage contains unknown fields: "
                + ", ".join(unknown)
            )
        _validate_support_common(event)
        if event.event_type == "support_state_advanced":
            _validate_support_state(event)
        elif event.event_type == "support_lease_issued_v2":
            _validate_support_issued(event)
        else:
            _validate_support_revoked(event)

    return TraceEventContract(
        event_type=event_type,
        required_fields=required,
        validator=validate,
        authority_relevant=True,
        schema_condition=True,
    )


SUPPORT_AUTHORITY_TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    _contract("support_state_advanced", _SUPPORT_STATE_FIELDS),
    _contract("support_lease_issued_v2", _SUPPORT_ISSUED_FIELDS),
    _contract("support_lease_revoked_v2", _SUPPORT_REVOKED_FIELDS),
)


def _validate_support_common(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_session_event(event, operation="qualify_evidence")
    for field in (
        "scope_ref",
        "run_ref",
        "request_ref",
        "grant_ref",
        "profile",
        "assurance",
        "protocol_ref",
        "target_ref",
        "mutation_issuer_ref",
    ):
        _require_support_text(event, field)
    for field in (
        "domain_root",
        "request_root",
        "grant_root",
        "grant_binding_ref",
        "manifest_root",
        "commit_policy_root",
        "authority_policy_root",
    ):
        _require_root(event.event_type, lineage, field)
    _require_session_targets(event, expected=(lineage["target_ref"],))
    if event.target != lineage["target_ref"]:
        raise ValueError(f"{event.event_type} trace target must match target_ref")
    assurance = lineage["assurance"]
    if (
        assurance not in _PROFILES_BY_ASSURANCE
        or lineage["profile"] not in _PROFILES_BY_ASSURANCE[assurance]
    ):
        raise ValueError(
            f"{event.event_type} trace profile and assurance are mismatched"
        )
    expected_stream = _authority_stream_ref(
        "support-v2",
        (
            lineage["scope_ref"],
            lineage["profile"],
            lineage["assurance"],
            lineage["manifest_root"],
            lineage["commit_policy_root"],
            lineage["protocol_ref"],
            lineage["run_ref"],
            lineage["target_ref"],
        ),
    )
    if lineage["stream_ref"] != expected_stream:
        raise ValueError(f"{event.event_type} trace stream_ref is not canonical")
    material = (
        lineage["stream_ref"].encode("utf-8")
        + b"\x00"
        + lineage["request_ref"].encode("utf-8")
    )
    expected_transition = f"transition:support-v2:{sha256(material).hexdigest()}"
    if lineage["transition_id"] != expected_transition:
        raise ValueError(f"{event.event_type} trace transition_id is not canonical")
    _validate_session_text_bounds(event)


def _validate_support_state(event: TraceEventView) -> None:
    lineage = event.lineage
    kind = _require_choice(event.event_type, lineage, "mutation_kind", _MUTATION_KINDS)
    for field in (
        "mutation_provenance_root",
        "mutation_delta_root",
        "parent_snapshot_root",
        "parent_history_root",
        "history_root",
        "parent_head_root",
        "snapshot_root",
        "lease_set_root",
        "source_context_root",
        "source_verification_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    for field in ("parent_transition_id",):
        _require_support_text(event, field)
    values = {
        field: _require_integer(event.event_type, lineage, field)
        for field in (
            "revision",
            "initialized_at_step",
            "current_step",
            "parent_revision",
            "parent_history_count",
            "history_count",
            "active_lease_count",
        )
    }
    if values["revision"] < 1:
        raise ValueError(f"{event.event_type} trace revision is invalid")
    if values["parent_revision"] != values["revision"] - 1:
        raise ValueError(f"{event.event_type} trace parent revision is not contiguous")
    if values["initialized_at_step"] > values["current_step"]:
        raise ValueError(f"{event.event_type} trace time moves before initialization")
    if values["active_lease_count"] > _MAX_LEASES:
        raise ValueError(
            f"{event.event_type} trace active lease count exceeds its bound"
        )
    _require_root_list(
        event,
        "mutation_trace_roots",
        minimum=1,
        maximum=_MAX_TRACE_ROOTS,
    )
    evicted = _require_root_list(
        event,
        "evicted_lease_roots",
        minimum=0,
        maximum=_MAX_LEASES,
    )
    _validate_state_parent(event, kind=kind, values=values)
    _validate_mutation_presence(event, kind=kind, evicted=evicted)
    _validate_mutation_commitments(event, values=values)
    if values["active_lease_count"] == 0 and (
        lineage["lease_set_root"] != _EMPTY_LEASE_SET_ROOT
    ):
        raise ValueError(f"{event.event_type} trace empty lease set root is invalid")


def _validate_state_parent(
    event: TraceEventView,
    *,
    kind: str,
    values: dict[str, int],
) -> None:
    lineage = event.lineage
    revision = values["revision"]
    if revision == 1:
        if (
            kind != "initialize"
            or values["parent_revision"] != 0
            or lineage["parent_transition_id"] != "genesis"
            or lineage["parent_snapshot_root"] != _SUPPORT_GENESIS_SNAPSHOT_ROOT
            or lineage["parent_history_root"] != _SUPPORT_GENESIS_HISTORY_ROOT
            or values["parent_history_count"] != 0
            or values["initialized_at_step"] != values["current_step"]
        ):
            raise ValueError(f"{event.event_type} trace genesis parent is invalid")
    elif (
        kind == "initialize"
        or _SUPPORT_TRANSITION.fullmatch(lineage["parent_transition_id"]) is None
        or values["parent_history_count"] != revision - 1
    ):
        raise ValueError(f"{event.event_type} trace parent lineage is invalid")


def _validate_mutation_presence(
    event: TraceEventView,
    *,
    kind: str,
    evicted: list[str],
) -> None:
    lineage = event.lineage
    roots = tuple(lineage[field] for field in _MUTATION_ROOT_FIELDS)
    for field, value in zip(_MUTATION_ROOT_FIELDS, roots, strict=True):
        _require_optional_root(event, field, value)
    membership = tuple(lineage[field] for field in _MEMBERSHIP_FIELDS)
    _validate_optional_membership_binding(event, membership)
    present = tuple(bool(value) for value in roots)
    member_present = tuple(bool(value) for value in membership)
    valid = {
        "initialize": (present == (False, False, False) and not any(member_present)),
        "issue": (present == (True, False, False) and all(member_present)),
        "revoke": (present == (False, True, True) and not any(member_present)),
        "switch": (all(present) and all(member_present)),
    }[kind]
    if not valid:
        raise ValueError(f"{event.event_type} trace mutation delta is incomplete")
    if kind == "initialize" and evicted:
        raise ValueError(f"{event.event_type} trace initialization cannot evict")
    if lineage["revoked_lease_root"] in evicted:
        raise ValueError(f"{event.event_type} trace revoked lease is also evicted")
    if lineage["issued_lease_root"] in evicted:
        raise ValueError(f"{event.event_type} trace issued lease is also evicted")
    if kind == "switch" and roots[0] == roots[1]:
        raise ValueError(f"{event.event_type} trace switch reuses its revoked lease")
    if kind in {"issue", "switch"} and lineage["active_lease_count"] < 1:
        raise ValueError(f"{event.event_type} trace issued lease is not active")


_MUTATION_ROOT_FIELDS = (
    "issued_lease_root",
    "revoked_lease_root",
    "revocation_root",
)
_MEMBERSHIP_FIELDS = (
    "membership_stream_ref",
    "membership_transition_id",
    "membership_snapshot_root",
)


def _validate_mutation_commitments(
    event: TraceEventView,
    *,
    values: dict[str, int],
) -> None:
    lineage = event.lineage
    delta = _support_root(
        "mutation-delta",
        {
            "mutation_kind": lineage["mutation_kind"],
            "transition_id": lineage["transition_id"],
            "mutation_issuer_ref": lineage["mutation_issuer_ref"],
            "observed_epoch": lineage["observed_epoch"],
            "current_step": lineage["current_step"],
            "mutation_provenance_root": lineage["mutation_provenance_root"],
            "mutation_trace_roots": lineage["mutation_trace_roots"],
            "issued_lease_root": lineage["issued_lease_root"],
            "revoked_lease_root": lineage["revoked_lease_root"],
            "revocation_root": lineage["revocation_root"],
            "evicted_lease_roots": lineage["evicted_lease_roots"],
            "membership_stream_ref": lineage["membership_stream_ref"],
            "membership_transition_id": lineage["membership_transition_id"],
            "membership_snapshot_root": lineage["membership_snapshot_root"],
        },
    )
    if lineage["mutation_delta_root"] != delta:
        raise ValueError(f"{event.event_type} trace mutation delta root is invalid")
    expected_count = values["parent_history_count"] + 1
    history = _support_root(
        "history-link",
        {
            "parent_history_root": lineage["parent_history_root"],
            "parent_history_count": values["parent_history_count"],
            "transition_id": lineage["transition_id"],
            "mutation_delta_root": delta,
            "history_count": expected_count,
        },
    )
    if (
        lineage["history_root"] != history
        or values["history_count"] != expected_count
        or values["history_count"] != values["revision"]
    ):
        raise ValueError(f"{event.event_type} trace history commitment is invalid")


def _validate_support_issued(event: TraceEventView) -> None:
    lineage = event.lineage
    for field in (
        "lease_ref",
        "mutation_transition_id",
        "candidate_ref",
        "principal_ref",
        "principal_cluster_ref",
        "membership_stream_ref",
        "membership_transition_id",
        "issuance_issuer_ref",
    ):
        _require_support_text(event, field)
    for field in (
        "lease_root",
        "proposal_root",
        "claim_root",
        "membership_principal_root",
        "principal_verification_root",
        "membership_snapshot_root",
        "membership_root",
        "positive_observation_set_root",
        "proposal_provenance_root",
        "issuance_provenance_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    _require_optional_root(event, "prior_lease_root", lineage["prior_lease_root"])
    _require_root_list(
        event, "proposal_trace_roots", minimum=1, maximum=_MAX_TRACE_ROOTS
    )
    _require_root_list(
        event, "issuance_trace_roots", minimum=1, maximum=_MAX_TRACE_ROOTS
    )
    epoch = _require_integer(event.event_type, lineage, "epoch")
    issued = _require_integer(event.event_type, lineage, "issued_at_step")
    expires = _require_integer(event.event_type, lineage, "expires_at_step")
    if epoch < 0 or issued >= expires:
        raise ValueError(f"{event.event_type} trace lease lifetime is invalid")
    _require_membership_binding(event)
    if lineage["mutation_transition_id"] != lineage["transition_id"]:
        raise ValueError(f"{event.event_type} trace mutation transition is mismatched")
    if lineage["issuance_issuer_ref"] != lineage["mutation_issuer_ref"]:
        raise ValueError(f"{event.event_type} trace issuance issuer is mismatched")
    expected_ref = (
        "lease:support-v2:"
        + sha256(
            lineage["transition_id"].encode("utf-8")
            + b"\x00"
            + lineage["proposal_root"].encode("ascii")
        ).hexdigest()
    )
    if lineage["lease_ref"] != expected_ref:
        raise ValueError(f"{event.event_type} trace lease_ref is not canonical")


def _validate_support_revoked(event: TraceEventView) -> None:
    lineage = event.lineage
    for field in (
        "revocation_ref",
        "mutation_transition_id",
        "candidate_ref",
        "principal_ref",
        "principal_cluster_ref",
        "lease_issuance_issuer_ref",
        "revocation_issuer_ref",
    ):
        _require_support_text(event, field)
    for field in (
        "revocation_root",
        "lease_root",
        "claim_root",
        "provenance_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    _require_integer(event.event_type, lineage, "epoch")
    _require_integer(event.event_type, lineage, "revoked_at_step")
    _require_text_list(
        event,
        "reason_codes",
        minimum=1,
        maximum=_MAX_REASON_CODES,
    )
    _require_root_list(event, "source_trace_roots", minimum=1, maximum=_MAX_TRACE_ROOTS)
    if lineage["mutation_transition_id"] != lineage["transition_id"]:
        raise ValueError(f"{event.event_type} trace mutation transition is mismatched")
    if lineage["revocation_issuer_ref"] != lineage["mutation_issuer_ref"]:
        raise ValueError(f"{event.event_type} trace revocation issuer is mismatched")
    expected_ref = (
        "revocation:support-v2:"
        + sha256(
            lineage["transition_id"].encode("utf-8")
            + b"\x00"
            + lineage["lease_root"].encode("ascii")
        ).hexdigest()
    )
    if lineage["revocation_ref"] != expected_ref:
        raise ValueError(f"{event.event_type} trace revocation_ref is not canonical")


def _validate_optional_membership_binding(
    event: TraceEventView,
    values: tuple[object, object, object],
) -> None:
    stream, transition, snapshot = values
    if not any(values):
        if values != ("", "", ""):
            raise ValueError(f"{event.event_type} trace membership binding is invalid")
        return
    _require_membership_binding(event)
    _require_root_value(event.event_type, "membership_snapshot_root", snapshot)


def _require_membership_binding(event: TraceEventView) -> None:
    stream = _require_support_text(event, "membership_stream_ref")
    transition = _require_support_text(event, "membership_transition_id")
    if _MEMBERSHIP_STREAM.fullmatch(stream) is None:
        raise ValueError(f"{event.event_type} trace membership stream is not canonical")
    if _MEMBERSHIP_TRANSITION.fullmatch(transition) is None:
        raise ValueError(
            f"{event.event_type} trace membership transition is not canonical"
        )


def _require_support_text(
    event: TraceEventView,
    field: str,
    *,
    value: object | None = None,
) -> str:
    selected = event.lineage[field] if value is None else value
    text = _require_text(event.event_type, {field: selected}, field)
    if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError(f"{event.event_type} trace {field} exceeds its byte bound")
    return text


def _validate_session_text_bounds(event: TraceEventView) -> None:
    binding = event.lineage["session_binding"]
    for field in ("scope_ref", "run_ref", "request_ref", "operation", "grant_ref"):
        _require_support_text(event, field, value=binding[field])
    for field in ("target_refs", "action_refs"):
        for value in binding[field]:
            _require_support_text(event, field, value=value)


def _require_optional_root(event: TraceEventView, field: str, value: object) -> None:
    if value == "":
        return
    _require_root_value(event.event_type, field, value)


def _require_root_list(
    event: TraceEventView,
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> list[str]:
    values = event.lineage[field]
    if type(values) is not list or not minimum <= len(values) <= maximum:
        raise ValueError(f"{event.event_type} trace {field} count is invalid")
    for value in values:
        _require_root_value(event.event_type, field, value)
    if values != sorted(set(values), key=lambda item: item.encode("ascii")):
        raise ValueError(f"{event.event_type} trace {field} is not canonical")
    return values


def _require_text_list(
    event: TraceEventView,
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> None:
    values = event.lineage[field]
    if type(values) is not list or not minimum <= len(values) <= maximum:
        raise ValueError(f"{event.event_type} trace {field} count is invalid")
    normalized = [_require_support_text(event, field, value=value) for value in values]
    if normalized != sorted(set(normalized), key=lambda item: item.encode("utf-8")):
        raise ValueError(f"{event.event_type} trace {field} is not canonical")


__all__: tuple[str, ...] = ()
