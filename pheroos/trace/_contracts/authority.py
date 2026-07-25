"""Static Trace ABI contracts for scoped-authority v2 transitions.

Trace deliberately validates these portable lineage projections without
importing Governance.  The small independent derivations below are also useful
conformance anchors: an authority event cannot become valid merely because the
producer and validator share one implementation helper.
"""

from __future__ import annotations

from hashlib import sha256
import re
from typing import Any, Callable, cast
import unicodedata

from pheroos.trace._contracts.base import TraceEventContract
from pheroos.trace._validation_core import TraceEventView


_AUTHORITY_PROTOCOL_ID = "pheroos.protocol.v2"
_AUTHORITY_LOCAL_PROFILE = "pheroos-scoped-authority-local-v2"
_AUTHORITY_AUTHENTICATED_PROFILE = "pheroos-scoped-authority-authenticated-v2"
_AUTHORITY_LIFECYCLE_STREAM = "authority:domain-lifecycle"
_MAX_AUTHORITY_INTEGER = (2**53) - 1
_ROOT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_HYBRID_REPLAY_TRANSITION_PATTERN = re.compile(
    r"transition:hybrid-replay-v2:[0-9a-f]{64}\Z"
)
_COMMIT_REPLAY_TRANSITION_PATTERN = re.compile(
    r"transition:commit-replay-v2:[0-9a-f]{64}\Z"
)
_COMMIT_REPLAY_PROFILES_BY_ASSURANCE = {
    "advisory": frozenset({"pheroos-commit-integrity-v1"}),
    "evidence_bound": frozenset(
        {"pheroos-commit-integrity-v1", "pheroos-hybrid-commit-v1"}
    ),
    "certified": frozenset({"pheroos-certified-commit-v1"}),
    "distributed": frozenset({"pheroos-distributed-commit-v1"}),
}

_COMMON_FIELDS = frozenset({"domain_root", "scope_ref", "stream_ref", "transition_id"})
_GRANT_FIELDS = frozenset(
    {
        "profile",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
        "observed_epoch",
        "revocation_generation",
    }
)
_SESSION_FIELDS = frozenset(
    {
        "run_ref",
        "request_ref",
        "request_root",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
        "operation",
        "observed_epoch",
        "session_binding",
    }
)
_SESSION_BINDING_FIELDS = frozenset(
    {
        "domain_root",
        "scope_ref",
        "run_ref",
        "request_ref",
        "request_root",
        "operation",
        "observed_epoch",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
        "grant_expected_revision",
        "grant_expected_root",
        "lifecycle_expected_revision",
        "lifecycle_expected_root",
        "target_refs",
        "action_refs",
    }
)
_BASELINE_OUTPUT_EVENT_TYPES = frozenset(
    {
        "baseline_manifest_activated",
        "baseline_evidence_qualified",
        "baseline_stop_resolved",
        "baseline_decision_evaluated",
        "baseline_action_permission_issued",
        "baseline_output_committed",
    }
)
_BASELINE_COMMON_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | frozenset(
        {
            "target_ref",
            "action_ref",
            "manifest_root",
            "output_policy_root",
        }
    )
)
_BASELINE_DECISION_FIELDS = frozenset(
    {
        "evidence_root",
        "stop_root",
        "decision_root",
        "candidate_ref",
        "terminal_status",
    }
)
_BASELINE_PERMISSION_FIELDS = _BASELINE_DECISION_FIELDS | frozenset(
    {
        "effect",
        "output_payload_root",
        "permission_root",
        "permission_disposition",
        "expires_at_epoch",
    }
)
_BASELINE_OUTPUT_FIELDS = _BASELINE_DECISION_FIELDS | frozenset(
    {
        "effect",
        "output_payload_root",
        "permission_root",
        "result_root",
        "delivery_disposition",
        "action_disposition",
        "read_set_root",
    }
)
_BASELINE_EFFECTS = frozenset({"publish", "execute"})
_BASELINE_TERMINAL_STATUSES = frozenset({"evidence_commit", "safe_fallback", "blocked"})
_BASELINE_ACTION_DISPOSITIONS = frozenset({"authorized", "denied"})
_HYBRID_REPLAY_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | frozenset(
        {
            "target_ref",
            "advance_ref",
            "protocol_ref",
            "manifest_root",
            "candidate_set_root",
            "hybrid_policy_root",
            "effective_policy_root",
            "topology_root",
            "revision",
            "current_step",
            "parent_transition_id",
            "parent_snapshot_root",
            "parent_head_root",
            "snapshot_root",
            "memory_root",
            "replay_receipt_root",
            "source_step_root",
            "source_trace_root",
            "read_set_root",
        }
    )
)
_COMMIT_REPLAY_FIELDS = (
    _COMMON_FIELDS
    | _SESSION_FIELDS
    | frozenset(
        {
            "target_ref",
            "advance_ref",
            "protocol_ref",
            "manifest_root",
            "commit_policy_root",
            "profile",
            "assurance",
            "revision",
            "current_step",
            "parent_transition_id",
            "parent_snapshot_root",
            "parent_head_root",
            "snapshot_root",
            "replay_receipt_root",
            "receipt_addition_root",
            "source_context_root",
            "read_set_root",
        }
    )
)


def _contract(event_type: str, required: frozenset[str]) -> TraceEventContract:
    def validate(event: TraceEventView) -> None:
        _validate_authority_event(event, required=required)

    return TraceEventContract(
        event_type=event_type,
        required_fields=required,
        validator=validate,
        authority_relevant=True,
        schema_condition=True,
    )


AUTHORITY_TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    _contract(
        "issuer_grant_activated",
        _COMMON_FIELDS | _GRANT_FIELDS | frozenset({"verification_root"}),
    ),
    _contract("issuer_grant_revoked", _COMMON_FIELDS | _GRANT_FIELDS),
    _contract(
        "signal_verified",
        _COMMON_FIELDS
        | _SESSION_FIELDS
        | frozenset(
            {
                "target_ref",
                "signal_ref",
                "signal_root",
                "evidence_root",
            }
        ),
    ),
    _contract(
        "domain_retired",
        _COMMON_FIELDS
        | _SESSION_FIELDS
        | frozenset({"reason_ref", "final_heads_root", "seal_root"}),
    ),
    _contract(
        "baseline_manifest_activated",
        _BASELINE_COMMON_FIELDS | frozenset({"protocol_ref"}),
    ),
    _contract(
        "baseline_evidence_qualified",
        _BASELINE_COMMON_FIELDS
        | frozenset({"evidence_root", "qualified_signal_count"}),
    ),
    _contract(
        "baseline_stop_resolved",
        _BASELINE_COMMON_FIELDS | frozenset({"stop_root"}),
    ),
    _contract(
        "baseline_decision_evaluated",
        _BASELINE_COMMON_FIELDS | _BASELINE_DECISION_FIELDS,
    ),
    _contract(
        "baseline_action_permission_issued",
        _BASELINE_COMMON_FIELDS | _BASELINE_PERMISSION_FIELDS,
    ),
    _contract(
        "baseline_output_committed",
        _BASELINE_COMMON_FIELDS | _BASELINE_OUTPUT_FIELDS,
    ),
    _contract("hybrid_replay_advanced", _HYBRID_REPLAY_FIELDS),
    _contract("commit_replay_advanced", _COMMIT_REPLAY_FIELDS),
)


def _validate_authority_event(
    event: TraceEventView,
    *,
    required: frozenset[str],
) -> None:
    _validate_authority_envelope(event, required=required)
    _validate_authority_transition(event)


def _validate_authority_envelope(
    event: TraceEventView,
    *,
    required: frozenset[str],
) -> None:
    if type(event.lineage) is not dict:
        raise ValueError("scoped-authority trace lineage must be an exact object")
    missing = sorted(required - set(event.lineage))
    if missing:
        raise ValueError(
            f"{event.event_type} trace lineage missing required fields: "
            + ", ".join(missing)
        )
    if event.event_type in {"hybrid_replay_advanced", "commit_replay_advanced"}:
        unknown = sorted(set(event.lineage) - required)
        if unknown:
            raise ValueError(
                "hybrid_replay_advanced trace lineage contains unknown fields: "
                + ", ".join(unknown)
            )
    if event.protocol_id != _AUTHORITY_PROTOCOL_ID:
        raise ValueError(
            f"{event.event_type} trace protocol_id must select scoped-authority v2"
        )
    lineage = event.lineage
    _require_root(event.event_type, lineage, "domain_root")
    for field in ("scope_ref", "stream_ref", "transition_id"):
        _require_text(event.event_type, lineage, field)
    if lineage["transition_id"] == "genesis":
        raise ValueError(f"{event.event_type} trace transition_id is reserved")


def _validate_authority_transition(event: TraceEventView) -> None:
    validators: dict[str, Callable[[TraceEventView], None]] = {
        "issuer_grant_activated": lambda item: _validate_grant_event(
            item,
            revoked=False,
        ),
        "issuer_grant_revoked": lambda item: _validate_grant_event(
            item,
            revoked=True,
        ),
        "signal_verified": _validate_signal_event,
        "domain_retired": _validate_retirement_event,
        **{
            event_type: _validate_baseline_output_event
            for event_type in _BASELINE_OUTPUT_EVENT_TYPES
        },
        "hybrid_replay_advanced": _validate_hybrid_replay_event,
        "commit_replay_advanced": _validate_commit_replay_event,
    }
    validators[event.event_type](event)


def _validate_baseline_output_event(event: TraceEventView) -> None:
    operation = (
        "authorize_output"
        if event.event_type == "baseline_output_committed"
        else "issue_action_permission"
    )
    _validate_session_event(event, operation=operation)
    _validate_baseline_common_fields(event)
    validators = {
        "baseline_manifest_activated": _validate_baseline_manifest_event,
        "baseline_evidence_qualified": _validate_baseline_evidence_event,
        "baseline_stop_resolved": _validate_baseline_stop_event,
        "baseline_decision_evaluated": _validate_baseline_decision_event,
        "baseline_action_permission_issued": _validate_action_permission_event,
        "baseline_output_committed": _validate_baseline_output_commit_event,
    }
    validators[event.event_type](event)


def _validate_hybrid_replay_event(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_session_event(event, operation="advance_replay")
    for field in ("target_ref", "advance_ref", "protocol_ref"):
        _require_text(event.event_type, lineage, field)
    for field in (
        "manifest_root",
        "candidate_set_root",
        "hybrid_policy_root",
        "effective_policy_root",
        "topology_root",
        "parent_head_root",
        "snapshot_root",
        "memory_root",
        "replay_receipt_root",
        "source_step_root",
        "source_trace_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    revision = _require_integer(event.event_type, lineage, "revision")
    _require_integer(event.event_type, lineage, "current_step")
    if revision < 1:
        raise ValueError("hybrid_replay_advanced trace revision must be positive")
    if event.target != lineage["target_ref"]:
        raise ValueError("hybrid_replay_advanced trace target must match target_ref")
    if lineage["request_ref"] != lineage["advance_ref"]:
        raise ValueError(
            "hybrid_replay_advanced trace request_ref must match advance_ref"
        )
    _require_session_targets(event, expected=(lineage["target_ref"],))
    expected_stream = _authority_stream_ref(
        "hybrid-replay-v2",
        (
            lineage["scope_ref"],
            lineage["protocol_ref"],
            lineage["run_ref"],
            lineage["target_ref"],
        ),
    )
    if lineage["stream_ref"] != expected_stream:
        raise ValueError("hybrid_replay_advanced trace stream_ref is not canonical")
    expected_transition = _hybrid_replay_transition_id(
        lineage["stream_ref"], lineage["advance_ref"]
    )
    if lineage["transition_id"] != expected_transition:
        raise ValueError("hybrid_replay_advanced trace transition_id is not canonical")
    _validate_hybrid_replay_parent(event, revision)


def _validate_hybrid_replay_parent(event: TraceEventView, revision: int) -> None:
    parent_transition = event.lineage["parent_transition_id"]
    parent_snapshot = event.lineage["parent_snapshot_root"]
    if revision == 1:
        if parent_transition is not None or parent_snapshot is not None:
            raise ValueError("hybrid_replay_advanced trace genesis parent must be null")
    else:
        _require_text_value(
            event.event_type,
            "parent_transition_id",
            parent_transition,
        )
        if _HYBRID_REPLAY_TRANSITION_PATTERN.fullmatch(parent_transition) is None:
            raise ValueError(
                "hybrid_replay_advanced trace parent_transition_id is not canonical"
            )
        _require_root_value(
            event.event_type,
            "parent_snapshot_root",
            parent_snapshot,
        )


def _hybrid_replay_transition_id(stream_ref: str, advance_ref: str) -> str:
    payload = b"\x00".join((stream_ref.encode("utf-8"), advance_ref.encode("utf-8")))
    return f"transition:hybrid-replay-v2:{sha256(payload).hexdigest()}"


def _validate_commit_replay_event(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_session_event(event, operation="advance_replay")
    for field in (
        "target_ref",
        "advance_ref",
        "protocol_ref",
        "profile",
        "assurance",
        "parent_transition_id",
    ):
        _require_text(event.event_type, lineage, field)
    for field in (
        "manifest_root",
        "commit_policy_root",
        "parent_snapshot_root",
        "parent_head_root",
        "snapshot_root",
        "replay_receipt_root",
        "receipt_addition_root",
        "source_context_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    revision = _require_integer(event.event_type, lineage, "revision")
    _require_integer(event.event_type, lineage, "current_step")
    if revision < 1:
        raise ValueError("commit_replay_advanced trace revision must be positive")
    if event.target != lineage["target_ref"]:
        raise ValueError("commit_replay_advanced trace target must match target_ref")
    if lineage["request_ref"] != lineage["advance_ref"]:
        raise ValueError(
            "commit_replay_advanced trace request_ref must match advance_ref"
        )
    _require_session_targets(event, expected=(lineage["target_ref"],))
    _validate_commit_replay_profile(event)
    expected_stream = _authority_stream_ref(
        "commit-replay-v2",
        (
            lineage["scope_ref"],
            lineage["protocol_ref"],
            lineage["run_ref"],
            lineage["target_ref"],
        ),
    )
    if lineage["stream_ref"] != expected_stream:
        raise ValueError("commit_replay_advanced trace stream_ref is not canonical")
    payload = b"\x00".join(
        (
            lineage["stream_ref"].encode("utf-8"),
            lineage["advance_ref"].encode("utf-8"),
        )
    )
    expected_transition = f"transition:commit-replay-v2:{sha256(payload).hexdigest()}"
    if lineage["transition_id"] != expected_transition:
        raise ValueError("commit_replay_advanced trace transition_id is not canonical")
    _validate_commit_replay_parent(event, revision)


def _validate_commit_replay_parent(event: TraceEventView, revision: int) -> None:
    parent_transition = event.lineage["parent_transition_id"]
    if revision == 1:
        if parent_transition != "genesis":
            raise ValueError(
                "commit_replay_advanced trace genesis parent must be reserved genesis"
            )
    elif _COMMIT_REPLAY_TRANSITION_PATTERN.fullmatch(parent_transition) is None:
        raise ValueError(
            "commit_replay_advanced trace parent_transition_id is not canonical"
        )


def _validate_commit_replay_profile(event: TraceEventView) -> None:
    assurance = event.lineage["assurance"]
    profile = event.lineage["profile"]
    if (
        assurance not in _COMMIT_REPLAY_PROFILES_BY_ASSURANCE
        or profile not in _COMMIT_REPLAY_PROFILES_BY_ASSURANCE[assurance]
    ):
        raise ValueError(
            "commit_replay_advanced trace profile and assurance are mismatched"
        )


def _validate_baseline_common_fields(event: TraceEventView) -> None:
    lineage = event.lineage
    for field in ("target_ref", "action_ref"):
        _require_text(event.event_type, lineage, field)
    for field in ("manifest_root", "output_policy_root"):
        _require_root(event.event_type, lineage, field)
    if event.target != lineage["target_ref"]:
        raise ValueError(f"{event.event_type} trace target must match target_ref")
    _require_session_bounds(
        event,
        targets=(lineage["target_ref"],),
        actions=(lineage["action_ref"],),
    )


def _validate_baseline_manifest_event(event: TraceEventView) -> None:
    _require_text(event.event_type, event.lineage, "protocol_ref")


def _validate_baseline_evidence_event(event: TraceEventView) -> None:
    _require_root(event.event_type, event.lineage, "evidence_root")
    _require_integer(event.event_type, event.lineage, "qualified_signal_count")


def _validate_baseline_stop_event(event: TraceEventView) -> None:
    _require_root(event.event_type, event.lineage, "stop_root")


def _validate_baseline_decision_event(event: TraceEventView) -> None:
    _validate_baseline_decision_fields(event)


def _validate_action_permission_event(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_baseline_decision_fields(event)
    _require_choice(event.event_type, lineage, "effect", _BASELINE_EFFECTS)
    for field in ("output_payload_root", "permission_root"):
        _require_root(event.event_type, lineage, field)
    disposition = _require_choice(
        event.event_type,
        lineage,
        "permission_disposition",
        _BASELINE_ACTION_DISPOSITIONS,
    )
    _require_integer(event.event_type, lineage, "expires_at_epoch")
    _require_blocked_denial(event, disposition)


def _validate_baseline_output_commit_event(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_baseline_decision_fields(event)
    _require_choice(event.event_type, lineage, "effect", _BASELINE_EFFECTS)
    for field in (
        "output_payload_root",
        "permission_root",
        "result_root",
        "read_set_root",
    ):
        _require_root(event.event_type, lineage, field)
    if lineage["delivery_disposition"] != "deliverable":
        raise ValueError(
            "baseline_output_committed trace delivery_disposition is invalid"
        )
    disposition = _require_choice(
        event.event_type,
        lineage,
        "action_disposition",
        _BASELINE_ACTION_DISPOSITIONS,
    )
    _require_blocked_denial(event, disposition)


def _validate_baseline_decision_fields(event: TraceEventView) -> None:
    lineage = event.lineage
    for field in ("evidence_root", "stop_root", "decision_root"):
        _require_root(event.event_type, lineage, field)
    _require_text(event.event_type, lineage, "candidate_ref")
    _require_choice(
        event.event_type,
        lineage,
        "terminal_status",
        _BASELINE_TERMINAL_STATUSES,
    )


def _require_blocked_denial(event: TraceEventView, disposition: str) -> None:
    if event.lineage["terminal_status"] == "blocked" and disposition != "denied":
        raise ValueError(f"{event.event_type} trace blocked output cannot authorize")


def _validate_signal_event(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_session_event(event, operation="verify_signal")
    for field in ("target_ref", "signal_ref"):
        _require_text(event.event_type, lineage, field)
    for field in ("signal_root", "evidence_root"):
        _require_root(event.event_type, lineage, field)
    if event.target != lineage["target_ref"]:
        raise ValueError("signal_verified trace target must match target_ref")
    expected_stream = _authority_stream_ref(
        "verified-signal",
        (
            lineage["scope_ref"],
            lineage["signal_ref"],
            lineage["target_ref"],
        ),
    )
    if lineage["stream_ref"] != expected_stream:
        raise ValueError("signal_verified trace stream_ref is not canonical")
    _require_session_targets(event, expected=(lineage["target_ref"],))


def _validate_retirement_event(event: TraceEventView) -> None:
    lineage = event.lineage
    _validate_session_event(event, operation="retire_domain")
    _require_text(event.event_type, lineage, "reason_ref")
    for field in ("final_heads_root", "seal_root"):
        _require_root(event.event_type, lineage, field)
    if lineage["stream_ref"] != _AUTHORITY_LIFECYCLE_STREAM:
        raise ValueError("domain_retired trace stream_ref must be lifecycle")
    if event.target != lineage["scope_ref"]:
        raise ValueError("domain_retired trace target must match scope_ref")
    _require_session_targets(event, expected=())


def _validate_grant_event(event: TraceEventView, *, revoked: bool) -> None:
    lineage = event.lineage
    profile = _require_text(event.event_type, lineage, "profile")
    if profile not in {_AUTHORITY_LOCAL_PROFILE, _AUTHORITY_AUTHENTICATED_PROFILE}:
        raise ValueError(f"{event.event_type} trace profile is unsupported")
    grant_ref = _require_text(event.event_type, lineage, "grant_ref")
    for field in ("grant_root", "grant_binding_ref"):
        _require_root(event.event_type, lineage, field)
    _require_integer(event.event_type, lineage, "observed_epoch")
    generation = _require_integer(
        event.event_type,
        lineage,
        "revocation_generation",
    )
    if revoked and generation < 1:
        raise ValueError(
            "issuer_grant_revoked trace revocation_generation must advance"
        )
    if event.target != grant_ref:
        raise ValueError(f"{event.event_type} trace target must match grant_ref")
    expected_stream = _authority_stream_ref(
        "issuer-grant",
        (lineage["scope_ref"], grant_ref),
    )
    if lineage["stream_ref"] != expected_stream:
        raise ValueError(f"{event.event_type} trace stream_ref is not canonical")
    if not revoked:
        verification_root = lineage["verification_root"]
        if profile == _AUTHORITY_LOCAL_PROFILE:
            if verification_root is not None:
                raise ValueError(
                    "local issuer_grant_activated trace cannot claim verification"
                )
        else:
            _require_root_value(
                event.event_type,
                "verification_root",
                verification_root,
            )


def _validate_session_event(event: TraceEventView, *, operation: str) -> None:
    lineage = event.lineage
    for field in ("run_ref", "request_ref", "grant_ref", "operation"):
        _require_text(event.event_type, lineage, field)
    for field in ("request_root", "grant_root", "grant_binding_ref"):
        _require_root(event.event_type, lineage, field)
    _require_integer(event.event_type, lineage, "observed_epoch")
    if lineage["operation"] != operation:
        raise ValueError(f"{event.event_type} trace operation is mismatched")
    binding = _require_session_binding(event)
    _validate_session_binding_values(event, binding)
    _validate_session_binding_matches(event, binding)
    _validate_session_binding_refs(event, binding)


def _require_session_binding(event: TraceEventView) -> dict[str, Any]:
    binding = event.lineage["session_binding"]
    if type(binding) is not dict or set(binding) != _SESSION_BINDING_FIELDS:
        raise ValueError(f"{event.event_type} trace session_binding fields are invalid")
    return binding


def _validate_session_binding_values(
    event: TraceEventView,
    binding: dict[str, Any],
) -> None:
    for field in (
        "scope_ref",
        "run_ref",
        "request_ref",
        "operation",
        "grant_ref",
    ):
        _require_text_value(
            event.event_type, f"session_binding.{field}", binding[field]
        )
    for field in (
        "domain_root",
        "request_root",
        "grant_root",
        "grant_binding_ref",
        "grant_expected_root",
        "lifecycle_expected_root",
    ):
        _require_root_value(
            event.event_type,
            f"session_binding.{field}",
            binding[field],
        )
    for field in (
        "observed_epoch",
        "grant_expected_revision",
        "lifecycle_expected_revision",
    ):
        _require_integer_value(
            event.event_type,
            f"session_binding.{field}",
            binding[field],
        )


def _validate_session_binding_matches(
    event: TraceEventView,
    binding: dict[str, Any],
) -> None:
    lineage = event.lineage
    for field in (
        "domain_root",
        "scope_ref",
        "run_ref",
        "request_ref",
        "request_root",
        "operation",
        "observed_epoch",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
    ):
        if binding[field] != lineage[field]:
            raise ValueError(
                f"{event.event_type} trace session_binding.{field} is mismatched"
            )


def _validate_session_binding_refs(
    event: TraceEventView,
    binding: dict[str, Any],
) -> None:
    if (
        type(binding["target_refs"]) is not list
        or type(binding["action_refs"]) is not list
    ):
        raise ValueError(
            f"{event.event_type} trace session target/action refs must be arrays"
        )
    for field in ("target_refs", "action_refs"):
        for index, value in enumerate(binding[field]):
            _require_text_value(
                event.event_type,
                f"session_binding.{field}[{index}]",
                value,
            )
        if len(set(binding[field])) != len(binding[field]):
            raise ValueError(
                f"{event.event_type} trace session_binding.{field} contains duplicates"
            )
        if binding[field] != sorted(
            binding[field],
            key=lambda item: item.encode("utf-8"),
        ):
            raise ValueError(
                f"{event.event_type} trace session_binding.{field} "
                "must use canonical UTF-8 order"
            )


def _require_session_targets(
    event: TraceEventView,
    *,
    expected: tuple[str, ...],
) -> None:
    _require_session_bounds(event, targets=expected, actions=())


def _require_session_bounds(
    event: TraceEventView,
    *,
    targets: tuple[str, ...],
    actions: tuple[str, ...],
) -> None:
    binding = event.lineage["session_binding"]
    if binding["target_refs"] != list(targets) or binding["action_refs"] != list(
        actions
    ):
        raise ValueError(
            f"{event.event_type} trace session target/action bounds are mismatched"
        )


def _authority_stream_ref(kind: str, bindings: tuple[str, ...]) -> str:
    if any("\x00" in binding for binding in bindings):
        raise ValueError("authority trace stream bindings must not contain U+0000")
    payload = b"\x00".join(binding.encode("utf-8") for binding in bindings)
    return f"authority:{kind}:{sha256(payload).hexdigest()}"


def _require_text(event_type: str, lineage: dict[str, Any], field: str) -> str:
    value = lineage[field]
    _require_text_value(event_type, field, value)
    return cast(str, value)


def _require_text_value(event_type: str, field: str, value: object) -> None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or "\x00" in value
    ):
        raise ValueError(f"{event_type} trace {field} must be canonical text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{event_type} trace {field} must encode as UTF-8") from exc


def _require_root(event_type: str, lineage: dict[str, Any], field: str) -> str:
    value = lineage[field]
    _require_root_value(event_type, field, value)
    return cast(str, value)


def _require_root_value(event_type: str, field: str, value: object) -> None:
    if type(value) is not str or _ROOT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{event_type} trace {field} must be a lowercase SHA-256 root")


def _require_integer(event_type: str, lineage: dict[str, Any], field: str) -> int:
    value = lineage[field]
    _require_integer_value(event_type, field, value)
    return cast(int, value)


def _require_integer_value(event_type: str, field: str, value: object) -> None:
    if type(value) is not int or not 0 <= value <= _MAX_AUTHORITY_INTEGER:
        raise ValueError(
            f"{event_type} trace {field} must be a JSON-safe non-negative integer"
        )


def _require_choice(
    event_type: str,
    lineage: dict[str, Any],
    field: str,
    choices: frozenset[str],
) -> str:
    value = _require_text(event_type, lineage, field)
    if value not in choices:
        raise ValueError(f"{event_type} trace {field} is unsupported")
    return value


__all__: tuple[str, ...] = ()
