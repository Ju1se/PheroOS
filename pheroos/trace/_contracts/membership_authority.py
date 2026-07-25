"""Closed Trace ABI for durable principal verification and membership.

This module is deliberately Trace-owned.  Stream and transition identities are
derived independently from the portable lineage fields; Governance is not an
implementation oracle for Trace validation.
"""

from __future__ import annotations

from hashlib import sha256
import re

from pheroos.trace._contracts.authority import (
    _COMMON_FIELDS,
    _SESSION_FIELDS,
    _authority_stream_ref,
    _require_integer,
    _require_root,
    _require_root_value,
    _require_session_targets,
    _require_text,
    _validate_authority_envelope,
    _validate_session_event,
)
from pheroos.trace._contracts.base import TraceEventContract
from pheroos.trace._contracts.membership_integrity import (
    _expected_membership_read_set_root,
    _expected_membership_source_context_root,
)
from pheroos.trace._validation_core import TraceEventView


_PRINCIPAL_VERIFICATION_TRANSITION = re.compile(
    r"transition:principal-verification-v2:[0-9a-f]{64}\Z"
)
_MEMBERSHIP_TRANSITION = re.compile(r"transition:membership-v2:[0-9a-f]{64}\Z")
_PRINCIPAL_VERIFICATION_GENESIS_ROOT = (
    "sha256:250b6db081d9b7bd133f06b6c3192bb409c2f97e2bb462d2c0302d81bbda7ec5"
)
_MEMBERSHIP_GENESIS_ROOT = (
    "sha256:442d957d649f827ae3be2c4389d9ca281f25c86355f54fb1efc0895c61f3c797"
)
_PROFILES_BY_ASSURANCE = {
    "advisory": frozenset({"pheroos-commit-integrity-v1"}),
    "evidence_bound": frozenset(
        {"pheroos-commit-integrity-v1", "pheroos-hybrid-commit-v1"}
    ),
    "certified": frozenset({"pheroos-certified-commit-v1"}),
    "distributed": frozenset({"pheroos-distributed-commit-v1"}),
}
_MAX_VERIFICATIONS = 4096
_MAX_MEMBERSHIP_CLUSTERS = 1024
_MAX_MEMBERSHIP_PRINCIPALS = 4096
_MAX_SOURCE_TRACE_ROOTS = 256
_MAX_MEMBERSHIP_TEXT_BYTES = 4096

_DURABLE_CONTEXT_FIELDS = frozenset(
    {
        "target_ref",
        "protocol_ref",
        "profile",
        "assurance",
        "authority_policy_root",
        "manifest_root",
        "commit_policy_root",
        "epoch",
        "revision",
        "parent_revision",
        "parent_epoch",
        "parent_transition_id",
        "parent_snapshot_root",
        "parent_head_root",
        "snapshot_root",
        "mutation_issuer_ref",
        "grant_issuer_ref",
        "source_context_root",
        "read_set_root",
    }
)
_PRINCIPAL_VERIFICATION_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | _DURABLE_CONTEXT_FIELDS
    | frozenset(
        {
            "verification_policy_root",
            "verification_set_root",
            "record_count",
            "current_step",
            "expires_at_step",
            "verification_roots",
        }
    )
)
_MEMBERSHIP_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | _DURABLE_CONTEXT_FIELDS
    | frozenset(
        {
            "membership_policy_root",
            "membership_root",
            "cluster_count",
            "principal_count",
            "issued_at_step",
            "expires_at_step",
            "verification_stream_ref",
            "verification_transition_id",
            "verification_policy_root",
            "verification_request_ref",
            "verification_revision",
            "verification_head_root",
            "verification_snapshot_root",
            "verification_set_root",
            "verification_current_step",
            "verification_expires_at_step",
            "verification_record_count",
            "source_trace_roots",
        }
    )
)


def _contract(event_type: str, required: frozenset[str]) -> TraceEventContract:
    def validate(event: TraceEventView) -> None:
        _validate_authority_envelope(event, required=required)
        unknown = sorted(set(event.lineage) - required)
        if unknown:
            raise ValueError(
                f"{event.event_type} trace lineage contains unknown fields: "
                + ", ".join(unknown)
            )
        if event.event_type == "principal_verification_set_advanced":
            _validate_principal_verification(event)
        else:
            _validate_membership(event)

    return TraceEventContract(
        event_type=event_type,
        required_fields=required,
        validator=validate,
        authority_relevant=True,
        schema_condition=True,
    )


MEMBERSHIP_AUTHORITY_TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    _contract("principal_verification_set_advanced", _PRINCIPAL_VERIFICATION_FIELDS),
    _contract("membership_epoch_committed", _MEMBERSHIP_FIELDS),
)


def _validate_principal_verification(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_durable_context(
        event,
        operation="qualify_evidence",
        stream_kind="principal-verification-v2",
        policy_field="verification_policy_root",
        parent_pattern=_PRINCIPAL_VERIFICATION_TRANSITION,
        genesis_root=_PRINCIPAL_VERIFICATION_GENESIS_ROOT,
    )
    for field in ("verification_policy_root", "verification_set_root"):
        _require_root(event.event_type, lineage, field)
    record_count = _require_integer(event.event_type, lineage, "record_count")
    current_step = _require_integer(event.event_type, lineage, "current_step")
    expires_at_step = _require_integer(event.event_type, lineage, "expires_at_step")
    if record_count > _MAX_VERIFICATIONS:
        raise ValueError(f"{event.event_type} trace record_count exceeds its bound")
    if current_step >= expires_at_step:
        raise ValueError(f"{event.event_type} trace verification set is not fresh")
    _require_root_list(
        event,
        "verification_roots",
        minimum=record_count,
        maximum=record_count,
        bound=_MAX_VERIFICATIONS,
        canonical_order=True,
    )
    _validate_integrity_roots(event)


def _validate_membership(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_durable_context(
        event,
        operation="evaluate_quorum",
        stream_kind="membership-v2",
        policy_field="membership_policy_root",
        parent_pattern=_MEMBERSHIP_TRANSITION,
        genesis_root=_MEMBERSHIP_GENESIS_ROOT,
    )
    for field in (
        "membership_policy_root",
        "membership_root",
        "verification_policy_root",
        "verification_head_root",
        "verification_snapshot_root",
        "verification_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    issued_at_step = _require_integer(event.event_type, lineage, "issued_at_step")
    expires_at_step = _require_integer(event.event_type, lineage, "expires_at_step")
    if issued_at_step >= expires_at_step:
        raise ValueError(f"{event.event_type} trace membership is not fresh")
    _validate_membership_counts(event)
    _validate_verification_binding(
        event,
        issued_at_step=issued_at_step,
        expires_at_step=expires_at_step,
    )
    _require_root_list(
        event,
        "source_trace_roots",
        minimum=1,
        maximum=_MAX_SOURCE_TRACE_ROOTS,
        bound=_MAX_SOURCE_TRACE_ROOTS,
        canonical_order=True,
    )
    _validate_integrity_roots(event)


def _validate_durable_context(
    event: TraceEventView,
    *,
    operation: str,
    stream_kind: str,
    policy_field: str,
    parent_pattern: re.Pattern[str],
    genesis_root: str,
) -> None:
    lineage = event.lineage
    _validate_session_event(event, operation=operation)
    for field in (
        "scope_ref",
        "run_ref",
        "request_ref",
        "grant_ref",
        "target_ref",
        "protocol_ref",
        "profile",
        "assurance",
        "mutation_issuer_ref",
        "grant_issuer_ref",
        "parent_transition_id",
    ):
        _require_membership_text(event, field)
    for field in (
        "authority_policy_root",
        "manifest_root",
        "commit_policy_root",
        "parent_snapshot_root",
        "parent_head_root",
        "snapshot_root",
        "source_context_root",
        "read_set_root",
        policy_field,
    ):
        _require_root(event.event_type, lineage, field)
    revision = _require_integer(event.event_type, lineage, "revision")
    epoch = _require_integer(event.event_type, lineage, "epoch")
    if revision < 1:
        raise ValueError(f"{event.event_type} trace revision must be positive")
    if event.target != lineage["target_ref"]:
        raise ValueError(f"{event.event_type} trace target must match target_ref")
    if lineage["grant_issuer_ref"] != lineage["mutation_issuer_ref"]:
        raise ValueError(f"{event.event_type} trace issuer binding is mismatched")
    _require_session_targets(event, expected=(lineage["target_ref"],))
    _validate_session_text_bounds(event)
    _validate_profile(event)
    _validate_fixed_identity(event, stream_kind=stream_kind, policy_field=policy_field)
    _validate_parent(
        event,
        revision=revision,
        epoch=epoch,
        parent_pattern=parent_pattern,
        genesis_root=genesis_root,
    )


def _validate_profile(event: TraceEventView) -> None:
    assurance = event.lineage["assurance"]
    profile = event.lineage["profile"]
    if (
        assurance not in _PROFILES_BY_ASSURANCE
        or profile not in _PROFILES_BY_ASSURANCE[assurance]
    ):
        raise ValueError(
            f"{event.event_type} trace profile and assurance are mismatched"
        )


def _validate_fixed_identity(
    event: TraceEventView,
    *,
    stream_kind: str,
    policy_field: str,
) -> None:
    lineage = event.lineage
    expected_stream = _authority_stream_ref(
        stream_kind,
        (
            lineage["scope_ref"],
            lineage["profile"],
            lineage["assurance"],
            lineage["manifest_root"],
            lineage["commit_policy_root"],
            lineage[policy_field],
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
    expected_transition = f"transition:{stream_kind}:{sha256(material).hexdigest()}"
    if lineage["transition_id"] != expected_transition:
        raise ValueError(f"{event.event_type} trace transition_id is not canonical")


def _validate_parent(
    event: TraceEventView,
    *,
    revision: int,
    epoch: int,
    parent_pattern: re.Pattern[str],
    genesis_root: str,
) -> None:
    lineage = event.lineage
    parent_revision = _require_integer(event.event_type, lineage, "parent_revision")
    if revision == 1:
        if parent_revision != 0:
            raise ValueError(
                f"{event.event_type} trace genesis parent revision is invalid"
            )
        if lineage["parent_epoch"] is not None:
            raise ValueError(
                f"{event.event_type} trace genesis parent epoch is invalid"
            )
        if lineage["parent_transition_id"] != "genesis":
            raise ValueError(f"{event.event_type} trace genesis parent is invalid")
        if lineage["parent_snapshot_root"] != genesis_root:
            raise ValueError(f"{event.event_type} trace genesis parent root is invalid")
        return
    if parent_revision < 1 or revision != parent_revision + 1:
        raise ValueError(f"{event.event_type} trace revision must advance exactly")
    parent_epoch = _require_integer(event.event_type, lineage, "parent_epoch")
    if epoch <= parent_epoch:
        raise ValueError(f"{event.event_type} trace epoch must advance")
    if parent_pattern.fullmatch(lineage["parent_transition_id"]) is None:
        raise ValueError(
            f"{event.event_type} trace parent_transition_id is not canonical"
        )


def _validate_membership_counts(event: TraceEventView) -> None:
    cluster_count = _require_integer(event.event_type, event.lineage, "cluster_count")
    principal_count = _require_integer(
        event.event_type, event.lineage, "principal_count"
    )
    if cluster_count > _MAX_MEMBERSHIP_CLUSTERS:
        raise ValueError(f"{event.event_type} trace cluster_count exceeds its bound")
    if principal_count > _MAX_MEMBERSHIP_PRINCIPALS:
        raise ValueError(f"{event.event_type} trace principal_count exceeds its bound")
    if cluster_count > principal_count or (
        (cluster_count == 0) != (principal_count == 0)
    ):
        raise ValueError(f"{event.event_type} trace membership counts are mismatched")


def _validate_verification_binding(
    event: TraceEventView,
    *,
    issued_at_step: int,
    expires_at_step: int,
) -> None:
    lineage = event.lineage
    request_ref = _require_membership_text(event, "verification_request_ref")
    expected_stream = _authority_stream_ref(
        "principal-verification-v2",
        (
            lineage["scope_ref"],
            lineage["profile"],
            lineage["assurance"],
            lineage["manifest_root"],
            lineage["commit_policy_root"],
            lineage["verification_policy_root"],
            lineage["protocol_ref"],
            lineage["run_ref"],
            lineage["target_ref"],
        ),
    )
    if lineage["verification_stream_ref"] != expected_stream:
        raise ValueError(
            f"{event.event_type} trace verification_stream_ref is not canonical"
        )
    material = expected_stream.encode("utf-8") + b"\x00" + request_ref.encode("utf-8")
    expected_transition = (
        "transition:principal-verification-v2:" + sha256(material).hexdigest()
    )
    if lineage["verification_transition_id"] != expected_transition:
        raise ValueError(
            f"{event.event_type} trace verification_transition_id is not canonical"
        )
    if _require_integer(event.event_type, lineage, "verification_revision") < 1:
        raise ValueError(
            f"{event.event_type} trace verification_revision must be positive"
        )
    current_step = _require_integer(
        event.event_type, lineage, "verification_current_step"
    )
    verification_expiry = _require_integer(
        event.event_type, lineage, "verification_expires_at_step"
    )
    record_count = _require_integer(
        event.event_type, lineage, "verification_record_count"
    )
    if (
        current_step > issued_at_step
        or expires_at_step > verification_expiry
        or current_step >= verification_expiry
    ):
        raise ValueError(
            f"{event.event_type} trace verification timeline is mismatched"
        )
    if record_count != lineage["principal_count"]:
        raise ValueError(f"{event.event_type} trace verification count is mismatched")


def _validate_integrity_roots(event: TraceEventView) -> None:
    lineage = event.lineage
    expected_source = _expected_membership_source_context_root(
        event.event_type,
        lineage,
    )
    if lineage["source_context_root"] != expected_source:
        raise ValueError(
            f"{event.event_type} trace source_context_root is not canonical"
        )
    expected_read_set = _expected_membership_read_set_root(
        event.event_type,
        lineage,
    )
    if lineage["read_set_root"] != expected_read_set:
        raise ValueError(f"{event.event_type} trace read_set_root is not canonical")


def _require_membership_text(
    event: TraceEventView,
    field: str,
    *,
    value: object | None = None,
) -> str:
    selected = event.lineage[field] if value is None else value
    text = _require_text(event.event_type, {field: selected}, field)
    if len(text.encode("utf-8")) > _MAX_MEMBERSHIP_TEXT_BYTES:
        raise ValueError(f"{event.event_type} trace {field} exceeds its byte bound")
    return text


def _validate_session_text_bounds(event: TraceEventView) -> None:
    binding = event.lineage["session_binding"]
    for field in ("scope_ref", "run_ref", "request_ref", "operation", "grant_ref"):
        _require_membership_text(event, field, value=binding[field])
    for field in ("target_refs", "action_refs"):
        for value in binding[field]:
            _require_membership_text(event, field, value=value)


def _require_root_list(
    event: TraceEventView,
    field: str,
    *,
    minimum: int,
    maximum: int,
    bound: int,
    canonical_order: bool,
) -> None:
    values = event.lineage[field]
    if type(values) is not list or not minimum <= len(values) <= maximum:
        raise ValueError(f"{event.event_type} trace {field} count is invalid")
    for value in values:
        _require_root_value(event.event_type, field, value)
    if len(values) > bound or len(values) != len(set(values)):
        raise ValueError(f"{event.event_type} trace {field} count is invalid")
    if canonical_order and values != sorted(
        values, key=lambda value: value.encode("utf-8")
    ):
        raise ValueError(f"{event.event_type} trace {field} is not canonical")


__all__: tuple[str, ...] = ()
