"""Static Trace ABI contracts for durable scoped-authority state.

The validators in this module deliberately depend only on Trace-owned helpers.
They independently derive stream and transition identities so a Governance
producer cannot make a malformed authority event valid by sharing its own
implementation oracle with Trace.
"""

from __future__ import annotations

from hashlib import sha256
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


_ROOT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RISK_TRANSITION_PATTERN = re.compile(r"transition:risk-v2:[0-9a-f]{64}\Z")
_RISK_GENESIS_SNAPSHOT_ROOT = (
    "sha256:c5a27a1c3b2313e09395f6fec7602b17e30e58334bc9a33b335a2135c1a55ec2"
)
_COMMIT_PROFILES_BY_ASSURANCE = {
    "advisory": frozenset({"pheroos-commit-integrity-v1"}),
    "evidence_bound": frozenset(
        {"pheroos-commit-integrity-v1", "pheroos-hybrid-commit-v1"}
    ),
    "certified": frozenset({"pheroos-certified-commit-v1"}),
    "distributed": frozenset({"pheroos-distributed-commit-v1"}),
}
_RISK_BANDS = frozenset({"LOW", "MODERATE", "HIGH", "CRITICAL"})
_MAX_RISK_TEXT_BYTES = 4096

_RISK_STATE_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | frozenset(
        {
            "target_ref",
            "advance_ref",
            "protocol_ref",
            "manifest_root",
            "commit_policy_root",
            "risk_policy_root",
            "profile",
            "assurance",
            "revision",
            "epoch",
            "parent_epoch",
            "current_step",
            "parent_transition_id",
            "parent_snapshot_root",
            "parent_head_root",
            "snapshot_root",
            "assessment_root",
            "threshold_root",
            "source_context_root",
            "read_set_root",
        }
    )
)
_RISK_ASSESSMENT_FIELDS = _RISK_STATE_FIELDS | frozenset(
    {
        "assessment_ref",
        "issuer_ref",
        "risk_band",
        "risk_input_roots",
        "rationale_codes",
        "assessment_method",
        "issued_at_step",
        "expires_at_step",
        "previous_assessment_root",
        "window_reset_required",
        "provenance_ref",
        "source_trace_roots",
    }
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
        _validate_risk_event(event)

    return TraceEventContract(
        event_type=event_type,
        required_fields=required,
        validator=validate,
        authority_relevant=True,
        schema_condition=True,
    )


DURABLE_AUTHORITY_TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    _contract("risk_state_advanced", _RISK_STATE_FIELDS),
    _contract("risk_assessed_v2", _RISK_ASSESSMENT_FIELDS),
)


def _validate_risk_event(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_session_event(event, operation="qualify_evidence")
    for field in (
        "target_ref",
        "advance_ref",
        "protocol_ref",
        "profile",
        "assurance",
        "parent_transition_id",
    ):
        _require_risk_text(event, field)
    for field in (
        "manifest_root",
        "commit_policy_root",
        "risk_policy_root",
        "parent_snapshot_root",
        "parent_head_root",
        "snapshot_root",
        "assessment_root",
        "threshold_root",
        "source_context_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    revision = _require_integer(event.event_type, lineage, "revision")
    epoch = _require_integer(event.event_type, lineage, "epoch")
    current_step = _require_integer(event.event_type, lineage, "current_step")
    if revision < 1:
        raise ValueError(f"{event.event_type} trace revision must be positive")
    if event.target != lineage["target_ref"]:
        raise ValueError(f"{event.event_type} trace target must match target_ref")
    if lineage["request_ref"] != lineage["advance_ref"]:
        raise ValueError(f"{event.event_type} trace request_ref must match advance_ref")
    if lineage["observed_epoch"] != epoch:
        raise ValueError(f"{event.event_type} trace epoch must match observed_epoch")
    _require_session_targets(event, expected=(lineage["target_ref"],))
    _validate_profile(event)
    _validate_risk_identity(event)
    _validate_risk_parent(event, revision, epoch)
    if event.event_type == "risk_assessed_v2":
        _validate_risk_assessment(event, revision=revision, current_step=current_step)


def _validate_profile(event: TraceEventView) -> None:
    assurance = event.lineage["assurance"]
    profile = event.lineage["profile"]
    if (
        assurance not in _COMMIT_PROFILES_BY_ASSURANCE
        or profile not in _COMMIT_PROFILES_BY_ASSURANCE[assurance]
    ):
        raise ValueError(
            f"{event.event_type} trace profile and assurance are mismatched"
        )


def _validate_risk_identity(event: TraceEventView) -> None:
    lineage = event.lineage
    expected_stream = _authority_stream_ref(
        "risk-v2",
        (
            lineage["scope_ref"],
            lineage["profile"],
            lineage["assurance"],
            lineage["manifest_root"],
            lineage["commit_policy_root"],
            lineage["risk_policy_root"],
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
        + lineage["advance_ref"].encode("utf-8")
    )
    expected_transition = f"transition:risk-v2:{sha256(material).hexdigest()}"
    if lineage["transition_id"] != expected_transition:
        raise ValueError(f"{event.event_type} trace transition_id is not canonical")


def _validate_risk_parent(event: TraceEventView, revision: int, epoch: int) -> None:
    lineage = event.lineage
    if revision == 1:
        if lineage["parent_epoch"] is not None:
            raise ValueError(
                f"{event.event_type} trace genesis parent epoch is invalid"
            )
        if lineage["parent_transition_id"] != "genesis":
            raise ValueError(f"{event.event_type} trace genesis parent is invalid")
        if lineage["parent_snapshot_root"] != _RISK_GENESIS_SNAPSHOT_ROOT:
            raise ValueError(f"{event.event_type} trace genesis parent root is invalid")
        return
    parent_epoch = _require_integer(event.event_type, lineage, "parent_epoch")
    if parent_epoch > epoch:
        raise ValueError(f"{event.event_type} trace epoch cannot move backwards")
    if _RISK_TRANSITION_PATTERN.fullmatch(lineage["parent_transition_id"]) is None:
        raise ValueError(
            f"{event.event_type} trace parent_transition_id is not canonical"
        )


def _validate_risk_assessment(
    event: TraceEventView,
    *,
    revision: int,
    current_step: int,
) -> None:
    lineage = event.lineage
    for field in (
        "assessment_ref",
        "issuer_ref",
        "assessment_method",
        "provenance_ref",
    ):
        _require_risk_text(event, field)
    _require_choice(event.event_type, lineage, "risk_band", _RISK_BANDS)
    _require_canonical_roots(
        event,
        "risk_input_roots",
        maximum=1024,
    )
    _require_canonical_texts(
        event,
        "rationale_codes",
        maximum=128,
    )
    _require_canonical_roots(
        event,
        "source_trace_roots",
        maximum=1024,
    )
    issued = _require_integer(event.event_type, lineage, "issued_at_step")
    expires = _require_integer(event.event_type, lineage, "expires_at_step")
    if not issued <= current_step < expires:
        raise ValueError(f"{event.event_type} trace assessment is not fresh")
    previous = lineage["previous_assessment_root"]
    reset = lineage["window_reset_required"]
    if type(reset) is not bool:
        raise ValueError(
            f"{event.event_type} trace window_reset_required must be an exact bool"
        )
    if revision == 1:
        if previous != "" or reset:
            raise ValueError(
                f"{event.event_type} trace initial assessment lineage is invalid"
            )
    else:
        _require_root_value(event.event_type, "previous_assessment_root", previous)
        parent_epoch = lineage["parent_epoch"]
        if type(parent_epoch) is int and parent_epoch != lineage["epoch"] and not reset:
            raise ValueError(
                f"{event.event_type} trace epoch change requires window reset"
            )


def _require_canonical_roots(
    event: TraceEventView,
    field: str,
    *,
    maximum: int,
) -> None:
    values = event.lineage[field]
    if type(values) is not list or not 1 <= len(values) <= maximum:
        raise ValueError(f"{event.event_type} trace {field} count is invalid")
    for value in values:
        if type(value) is not str or _ROOT_PATTERN.fullmatch(value) is None:
            raise ValueError(
                f"{event.event_type} trace {field} contains an invalid root"
            )
    if values != sorted(set(values), key=lambda value: value.encode("utf-8")):
        raise ValueError(f"{event.event_type} trace {field} is not canonical")


def _require_canonical_texts(
    event: TraceEventView,
    field: str,
    *,
    maximum: int,
) -> None:
    values = event.lineage[field]
    if type(values) is not list or not 1 <= len(values) <= maximum:
        raise ValueError(f"{event.event_type} trace {field} count is invalid")
    for value in values:
        if type(value) is not str:
            raise ValueError(f"{event.event_type} trace {field} contains invalid text")
        _require_risk_text(event, field, value=value)
    if values != sorted(set(values), key=lambda value: value.encode("utf-8")):
        raise ValueError(f"{event.event_type} trace {field} is not canonical")


def _require_risk_text(
    event: TraceEventView,
    field: str,
    *,
    value: object | None = None,
) -> str:
    selected = event.lineage[field] if value is None else value
    text = _require_text(event.event_type, {field: selected}, field)
    if len(text.encode("utf-8")) > _MAX_RISK_TEXT_BYTES:
        raise ValueError(f"{event.event_type} trace {field} exceeds its byte bound")
    return text


__all__: tuple[str, ...] = ()
