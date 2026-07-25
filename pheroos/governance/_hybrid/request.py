"""Hybrid Commit request record, canonical projection, and safe diagnostics."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from pheroos.governance._certificate.local import local_commit_receipt_fingerprint
from pheroos.governance._certificate.outcome import outcome_certificate_fingerprint
from pheroos.governance._certificate.portable import (
    evidence_commit_certificate_fingerprint,
)
from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._hybrid.evaluation_records import (
    HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
    HybridCommitDiagnostic,
)
from pheroos.governance.attention import (
    AttentionBreakdown,
    attention_breakdown_fingerprint,
    attention_breakdown_is_authoritative,
    exploration_directive_fingerprint,
    exploration_directive_is_authoritative,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit import (
    CommitAssessment,
    commit_assessment_fingerprint,
    commit_evaluation_context_fingerprint,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    commit_replay_state_fingerprint,
    commit_window_state_fingerprint,
    decision_progress_fingerprint,
)
from pheroos.governance.distributed_commit import (
    distributed_commit_certificate_fingerprint,
    distributed_commit_state_fingerprint,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.permission import action_permission_fingerprint
from pheroos.governance.risk import (
    commit_threshold_snapshot_fingerprint,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_fingerprint,
)
from pheroos.governance.stop_signal import (
    stop_resolution_verification_fingerprint,
)
from pheroos.governance.support_lease import (
    eligible_membership_epoch_state_fingerprint,
    eligible_principal_snapshot_fingerprint,
    support_lease_replay_state_fingerprint,
)
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.trace import TraceEvent


@dataclass(frozen=True)
class HybridCommitEvaluationRequest:
    """Strict runtime request whose authority leaves are official ABI records.

    Optional certificates are facts, not downgrade selectors.  Omitting the
    proof required by the declared assurance yields progress (or a deadline
    non-commit), while supplying a malformed proof yields a fail-closed invalid
    outcome whenever the underlying governance authority envelope is usable.
    """

    request_version: str
    request_id: str
    attention: object
    exploration_directive: object
    commit_assessment: object
    context: object
    window_state: object
    replay_state: object
    commit_policy: object
    risk_chain_state: object
    risk_assessment: object
    threshold_snapshot: object
    membership_snapshot: object
    membership_epoch_state: object
    support_replay_state: object
    current_step: int
    output_payload_fingerprint: str
    issuer_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str
    previous_progress: object | None = None
    local_receipt: object | None = None
    evidence_certificate: object | None = None
    distributed_state: object | None = None
    distributed_certificate: object | None = None
    outcome_certificate: object | None = None
    publish_stop_resolution: object | None = None
    publish_permission: object | None = None
    execute_stop_resolution: object | None = None
    execute_permission: object | None = None
    issuer_attestation_refs: tuple[str, ...] = ()
    trusted_issuer_attestations: Mapping[str, str] = field(default_factory=dict)
    trusted_witness_attestations: Mapping[str, str] = field(default_factory=dict)
    prior_trace_events: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        if self.request_version != HYBRID_COMMIT_EVALUATION_REQUEST_VERSION:
            raise GovernanceError("Hybrid Commit evaluation request version is invalid")
        require_commit_text(self.request_id, "Hybrid Commit evaluation request_id")
        require_commit_step(self.current_step, "Hybrid Commit evaluation current_step")
        require_commit_fingerprint(
            self.output_payload_fingerprint,
            "Hybrid Commit evaluation output payload fingerprint",
        )
        require_commit_text(self.issuer_id, "Hybrid Commit evaluation issuer_id")
        if type(self.authority) is not AuthorityLevel or not can_verify(self.authority):
            raise GovernanceError(
                "Hybrid Commit evaluation request requires governance authority"
            )
        require_commit_text(self.provenance, "Hybrid Commit evaluation provenance")
        require_commit_text(
            self.trace_event_id,
            "Hybrid Commit evaluation trace_event_id",
        )
        object.__setattr__(
            self,
            "issuer_attestation_refs",
            require_commit_labels(
                self.issuer_attestation_refs,
                "Hybrid Commit evaluation issuer attestation refs",
                allow_empty=True,
            ),
        )
        for name in (
            "trusted_issuer_attestations",
            "trusted_witness_attestations",
        ):
            mapping = getattr(self, name)
            if not isinstance(mapping, Mapping):
                raise GovernanceError(
                    f"Hybrid Commit evaluation {name} must be a mapping"
                )
            normalized: dict[str, str] = {}
            for key, value in mapping.items():
                normalized[require_commit_text(key, f"{name} key")] = (
                    require_commit_fingerprint(value, f"{name} value")
                )
            object.__setattr__(
                self,
                name,
                MappingProxyType(dict(sorted(normalized.items()))),
            )
        object.__setattr__(self, "prior_trace_events", tuple(self.prior_trace_events))
        for event in self.prior_trace_events:
            if type(event) is not TraceEvent:
                raise GovernanceError(
                    "Hybrid Commit prior trace must contain canonical TraceEvent records"
                )
            event.validate()
            require_commit_fingerprint(
                event.lineage.get("event_id"),
                "Hybrid Commit prior trace event_id",
            )


def hybrid_commit_evaluation_request_payload(
    request: HybridCommitEvaluationRequest,
) -> dict[str, object]:
    """Return a root-only request projection; runtime objects are never serialized."""

    if type(request) is not HybridCommitEvaluationRequest:
        raise GovernanceError("Hybrid Commit evaluation request must be canonical")
    profile = _request_profile(request)
    return {
        "request_version": request.request_version,
        "request_id": request.request_id,
        "attention_input_status": _attention_input_status(request.attention),
        "attention_ref": _safe_fingerprint(
            request.attention,
            attention_breakdown_fingerprint,
        ),
        "exploration_directive_input_status": _exploration_directive_input_status(
            request.exploration_directive,
            attention=request.attention,
        ),
        "exploration_directive_ref": _safe_fingerprint(
            request.exploration_directive,
            exploration_directive_fingerprint,
        ),
        "assessment_ref": _safe_fingerprint(
            request.commit_assessment,
            commit_assessment_fingerprint,
        ),
        "context_ref": _safe_fingerprint(
            request.context,
            commit_evaluation_context_fingerprint,
        ),
        "window_state_ref": _safe_fingerprint(
            request.window_state,
            commit_window_state_fingerprint,
        ),
        "replay_state_ref": _safe_fingerprint(
            request.replay_state,
            commit_replay_state_fingerprint,
        ),
        "commit_policy_ref": _safe_fingerprint(
            request.commit_policy,
            lambda value: commit_policy_fingerprint(value, profile=profile),
        ),
        "risk_chain_state_ref": _safe_fingerprint(
            request.risk_chain_state,
            risk_assessment_chain_state_fingerprint,
        ),
        "risk_assessment_ref": _safe_fingerprint(
            request.risk_assessment,
            risk_assessment_fingerprint,
        ),
        "threshold_snapshot_ref": _safe_fingerprint(
            request.threshold_snapshot,
            commit_threshold_snapshot_fingerprint,
        ),
        "membership_snapshot_ref": _safe_fingerprint(
            request.membership_snapshot,
            eligible_principal_snapshot_fingerprint,
        ),
        "membership_epoch_state_ref": _safe_fingerprint(
            request.membership_epoch_state,
            eligible_membership_epoch_state_fingerprint,
        ),
        "support_replay_state_ref": _safe_fingerprint(
            request.support_replay_state,
            support_lease_replay_state_fingerprint,
        ),
        "current_step": request.current_step,
        "output_payload_fingerprint": request.output_payload_fingerprint,
        "previous_progress_present": request.previous_progress is not None,
        "local_receipt_ref": _safe_fingerprint(
            request.local_receipt,
            local_commit_receipt_fingerprint,
        ),
        "local_receipt_present": request.local_receipt is not None,
        "evidence_certificate_ref": _safe_fingerprint(
            request.evidence_certificate,
            evidence_commit_certificate_fingerprint,
        ),
        "evidence_certificate_present": request.evidence_certificate is not None,
        "distributed_state_ref": _safe_fingerprint(
            request.distributed_state,
            distributed_commit_state_fingerprint,
        ),
        "distributed_state_present": request.distributed_state is not None,
        "distributed_certificate_ref": _safe_fingerprint(
            request.distributed_certificate,
            distributed_commit_certificate_fingerprint,
        ),
        "distributed_certificate_present": (
            request.distributed_certificate is not None
        ),
        "outcome_certificate_ref": _safe_fingerprint(
            request.outcome_certificate,
            outcome_certificate_fingerprint,
        ),
        "outcome_certificate_present": request.outcome_certificate is not None,
        "previous_progress_ref": _safe_fingerprint(
            request.previous_progress,
            decision_progress_fingerprint,
        ),
        "publish_stop_resolution_ref": _safe_fingerprint(
            request.publish_stop_resolution,
            stop_resolution_verification_fingerprint,
        ),
        "publish_stop_resolution_present": (
            request.publish_stop_resolution is not None
        ),
        "publish_permission_ref": _safe_fingerprint(
            request.publish_permission,
            action_permission_fingerprint,
        ),
        "publish_permission_present": request.publish_permission is not None,
        "execute_stop_resolution_ref": _safe_fingerprint(
            request.execute_stop_resolution,
            stop_resolution_verification_fingerprint,
        ),
        "execute_stop_resolution_present": (
            request.execute_stop_resolution is not None
        ),
        "execute_permission_ref": _safe_fingerprint(
            request.execute_permission,
            action_permission_fingerprint,
        ),
        "execute_permission_present": request.execute_permission is not None,
        "issuer_id": request.issuer_id,
        "authority": request.authority,
        "provenance": request.provenance,
        "trace_event_id": request.trace_event_id,
        "issuer_attestation_refs": request.issuer_attestation_refs,
        "trusted_issuer_attestations": tuple(
            {
                "attestation_ref": key,
                "body_root": value,
            }
            for key, value in sorted(request.trusted_issuer_attestations.items())
        ),
        "trusted_witness_attestations": tuple(
            {
                "attestation_ref": key,
                "body_root": value,
            }
            for key, value in sorted(request.trusted_witness_attestations.items())
        ),
        "prior_trace_event_ids": tuple(
            _strict_trace_event_id(item) for item in request.prior_trace_events
        ),
    }


def hybrid_commit_evaluation_request_fingerprint(
    request: HybridCommitEvaluationRequest,
) -> str:
    return commit_payload_fingerprint(
        hybrid_commit_evaluation_request_payload(request),
        schema=HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
        profile=_request_profile(request),
    )


def _attention_input_status(value: object) -> str:
    if value is None:
        return "missing"
    if attention_breakdown_is_authoritative(value):
        return "authoritative"
    return "provided_invalid"


def _exploration_directive_input_status(
    value: object,
    *,
    attention: object,
) -> str:
    if value is None:
        return "missing"
    canonical_attention: AttentionBreakdown | None
    if attention is None:
        canonical_attention = None
    elif type(attention) is AttentionBreakdown:
        canonical_attention = attention
    else:
        return "provided_invalid"
    if exploration_directive_is_authoritative(
        value,
        attention=canonical_attention,
    ):
        return "authoritative"
    return "provided_invalid"


def _safe_fingerprint(value: object, fingerprint: Callable[..., str]) -> str:
    try:
        return fingerprint(value)
    except Exception:
        return ""


def _issued_request_ref(
    request: HybridCommitEvaluationRequest,
    diagnostics: Sequence[HybridCommitDiagnostic],
    *,
    profile: str,
) -> str:
    """Bind valid requests exactly and malformed issued-invalid inputs safely.

    The normal path is the strict, all-leaf request ABI.  The fallback exists
    only after governance has already classified a malformed runtime record.
    It binds every extractable authority root, presence bit, input position,
    and diagnostic code without serializing arbitrary caller objects or their
    address-bearing ``repr`` values.
    """

    try:
        return hybrid_commit_evaluation_request_fingerprint(request)
    except Exception:
        pass

    runtime_refs = {
        "attention_ref": _safe_fingerprint(
            request.attention,
            attention_breakdown_fingerprint,
        ),
        "exploration_directive_ref": _safe_fingerprint(
            request.exploration_directive,
            exploration_directive_fingerprint,
        ),
        "assessment_ref": _safe_fingerprint(
            request.commit_assessment,
            commit_assessment_fingerprint,
        ),
        "context_ref": _safe_fingerprint(
            request.context,
            commit_evaluation_context_fingerprint,
        ),
        "window_state_ref": _safe_fingerprint(
            request.window_state,
            commit_window_state_fingerprint,
        ),
        "replay_state_ref": _safe_fingerprint(
            request.replay_state,
            commit_replay_state_fingerprint,
        ),
        "commit_policy_ref": _safe_fingerprint(
            request.commit_policy,
            lambda value: commit_policy_fingerprint(value, profile=profile),
        ),
        "risk_chain_state_ref": _safe_fingerprint(
            request.risk_chain_state,
            risk_assessment_chain_state_fingerprint,
        ),
        "risk_assessment_ref": _safe_fingerprint(
            request.risk_assessment,
            risk_assessment_fingerprint,
        ),
        "threshold_snapshot_ref": _safe_fingerprint(
            request.threshold_snapshot,
            commit_threshold_snapshot_fingerprint,
        ),
        "membership_snapshot_ref": _safe_fingerprint(
            request.membership_snapshot,
            eligible_principal_snapshot_fingerprint,
        ),
        "membership_epoch_state_ref": _safe_fingerprint(
            request.membership_epoch_state,
            eligible_membership_epoch_state_fingerprint,
        ),
        "support_replay_state_ref": _safe_fingerprint(
            request.support_replay_state,
            support_lease_replay_state_fingerprint,
        ),
        "previous_progress_ref": _safe_fingerprint(
            request.previous_progress,
            decision_progress_fingerprint,
        ),
        "local_receipt_ref": _safe_fingerprint(
            request.local_receipt,
            local_commit_receipt_fingerprint,
        ),
        "evidence_certificate_ref": _safe_fingerprint(
            request.evidence_certificate,
            evidence_commit_certificate_fingerprint,
        ),
        "distributed_state_ref": _safe_fingerprint(
            request.distributed_state,
            distributed_commit_state_fingerprint,
        ),
        "distributed_certificate_ref": _safe_fingerprint(
            request.distributed_certificate,
            distributed_commit_certificate_fingerprint,
        ),
        "outcome_certificate_ref": _safe_fingerprint(
            request.outcome_certificate,
            outcome_certificate_fingerprint,
        ),
        "publish_stop_resolution_ref": _safe_fingerprint(
            request.publish_stop_resolution,
            stop_resolution_verification_fingerprint,
        ),
        "publish_permission_ref": _safe_fingerprint(
            request.publish_permission,
            action_permission_fingerprint,
        ),
        "execute_stop_resolution_ref": _safe_fingerprint(
            request.execute_stop_resolution,
            stop_resolution_verification_fingerprint,
        ),
        "execute_permission_ref": _safe_fingerprint(
            request.execute_permission,
            action_permission_fingerprint,
        ),
    }
    optional_names = (
        "previous_progress",
        "local_receipt",
        "evidence_certificate",
        "distributed_state",
        "distributed_certificate",
        "outcome_certificate",
        "publish_stop_resolution",
        "publish_permission",
        "execute_stop_resolution",
        "execute_permission",
    )
    prior_trace: list[dict[str, object]] = []
    for index, event in enumerate(request.prior_trace_events):
        event_id = ""
        if type(event) is TraceEvent:
            try:
                event.validate()
                event_id = require_commit_fingerprint(
                    event.lineage.get("event_id"),
                    "Hybrid Commit prior trace event id",
                )
            except Exception:
                pass
        prior_trace.append(
            {
                "index": index,
                "event_id": event_id,
                "runtime_type": _runtime_type_label(event),
            }
        )
    payload = {
        "request_version": (
            request.request_version
            if isinstance(request.request_version, str)
            else "invalid-request-version"
        ),
        "request_id": (
            request.request_id
            if isinstance(request.request_id, str) and request.request_id
            else "invalid-request-id"
        ),
        "current_step": (
            request.current_step
            if type(request.current_step) is int and request.current_step >= 0
            else 0
        ),
        "output_payload_fingerprint": (
            request.output_payload_fingerprint
            if isinstance(request.output_payload_fingerprint, str)
            else ""
        ),
        "issuer_id": (
            request.issuer_id
            if isinstance(request.issuer_id, str)
            else "invalid-issuer"
        ),
        "authority": (
            request.authority.value
            if type(request.authority) is AuthorityLevel
            else _runtime_type_label(request.authority)
        ),
        "provenance": (
            request.provenance
            if isinstance(request.provenance, str)
            else "invalid-provenance"
        ),
        "trace_event_id": (
            request.trace_event_id
            if isinstance(request.trace_event_id, str)
            else "invalid-trace-event-id"
        ),
        "runtime_refs": runtime_refs,
        "optional_presence": {
            name: getattr(request, name) is not None for name in optional_names
        },
        "prior_trace": tuple(prior_trace),
        "diagnostic_codes": tuple(sorted(item.code for item in diagnostics)),
    }
    return commit_payload_fingerprint(
        payload,
        schema="pheroos-hybrid-commit-invalid-request-ref-v1",
        profile=profile,
    )


def _runtime_type_label(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _strict_trace_event_id(value: object) -> str:
    if type(value) is not TraceEvent:
        raise GovernanceError("Hybrid Commit prior trace record is not canonical")
    value.validate()
    return require_commit_fingerprint(
        value.lineage.get("event_id"),
        "Hybrid Commit prior trace event id",
    )


def _request_profile(request: HybridCommitEvaluationRequest) -> str:
    assessment = request.commit_assessment
    if type(assessment) is CommitAssessment:
        try:
            return require_commit_profile(
                assessment.profile,
                "Hybrid Commit request profile",
            )
        except GovernanceError:
            pass
    return "pheroos-commit-integrity-v1"


def _safe_declared_assurance(
    policy: object,
    assessment: object,
) -> CommitAssurance:
    for candidate in (
        getattr(policy, "assurance", None)
        if type(policy) is CollectiveCommitPolicy
        else None,
        getattr(assessment, "assurance", None)
        if type(assessment) is CommitAssessment
        else None,
    ):
        try:
            if type(candidate) is CommitAssurance:
                return candidate
            if isinstance(candidate, str):
                return CommitAssurance(candidate)
        except (TypeError, ValueError):
            continue
    return CommitAssurance.ADVISORY


def _safe_diagnostic_profile(
    source: object,
    *,
    assurance: CommitAssurance,
) -> str:
    candidate = getattr(source, "profile", None)
    try:
        normalized = require_commit_profile(candidate, "diagnostic profile")
        if normalized in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
            return normalized
    except (AttributeError, GovernanceError, TypeError, ValueError):
        pass
    return sorted(COMMIT_PROFILES_BY_ASSURANCE[assurance.value])[0]


def _safe_diagnostic_text(value: object, fallback: str) -> str:
    try:
        return require_commit_text(value, "diagnostic identity")
    except (GovernanceError, TypeError, ValueError):
        return fallback


def _safe_diagnostic_step(value: object) -> int:
    try:
        return require_commit_step(value, "diagnostic step")
    except (GovernanceError, TypeError, ValueError):
        return 0


__all__ = [
    "HybridCommitEvaluationRequest",
    "hybrid_commit_evaluation_request_fingerprint",
    "hybrid_commit_evaluation_request_payload",
]
