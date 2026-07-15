from __future__ import annotations

"""Total-function orchestration for one Optimal Hybrid Commit logical step.

This module composes public governance APIs.  It does not reimplement the
Optimal Commit metric, window, finality, or output algorithms and it never
calls the legacy blended-score collective decision path.  The attention
channel is represented only by tamper-evident references in the authority
envelope, keeping floating-point exploration data outside Commit Wire truth.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.attention import (
    attention_breakdown_fingerprint,
    attention_breakdown_is_authoritative,
    exploration_directive_fingerprint,
    exploration_directive_is_authoritative,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.certificate import (
    EVIDENCE_COMMIT_CERTIFICATE_VERSION,
    LOCAL_COMMIT_RECEIPT_VERSION,
    OUTCOME_CERTIFICATE_VERSION,
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    OutcomeCertificate,
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_payload,
    issue_evidence_commit_certificate,
    issue_local_commit_receipt,
    issue_outcome_certificate,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    local_commit_receipt_payload,
    outcome_certificate_fingerprint,
    outcome_certificate_payload,
    verify_evidence_commit_certificate,
    verify_evidence_commit_finality,
    verify_local_commit_finality,
    verify_outcome_certificate,
)
from pheroos.governance.commit import (
    CandidateCommitMetrics,
    CommitAssessment,
    CommitEvaluationContext,
    candidate_commit_metrics_fingerprint,
    candidate_commit_metrics_payload,
    commit_assessment_fingerprint,
    commit_assessment_is_authoritative,
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    CommitFinalityVerification,
    CommitReplayState,
    CommitWindowState,
    DecisionOutcome,
    DecisionOutcomeKind,
    DecisionProgress,
    advance_commit_window_state,
    commit_finality_verification_fingerprint,
    commit_finality_verification_is_authoritative,
    commit_replay_state_fingerprint,
    commit_replay_state_is_authoritative,
    commit_replay_state_is_current,
    commit_window_ready,
    commit_window_seal_for_state,
    commit_window_state_fingerprint,
    commit_window_state_is_authoritative,
    commit_window_state_is_current,
    commit_window_state_payload,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
    decision_outcome_payload,
    decision_progress_fingerprint,
    decision_progress_is_authoritative,
    decision_progress_payload,
    issue_commit_liveness_input,
    reduce_commit_liveness,
)
from pheroos.governance.distributed_commit import (
    DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
    DISTRIBUTED_STATE_VERSION,
    WITNESS_VERIFICATION_VERSION,
    DistributedCommitCertificate,
    DistributedCommitState,
    distributed_commit_certificate_fingerprint,
    distributed_commit_certificate_is_current_final,
    distributed_commit_certificate_payload,
    distributed_commit_value_root,
    distributed_commit_state_fingerprint,
    distributed_commit_state_is_authoritative,
    distributed_commit_state_payload,
    distributed_commit_state_is_current,
    witness_verification_fingerprint,
    witness_verification_is_authoritative,
    witness_verification_payload,
    verify_distributed_commit_certificate,
    verify_distributed_commit_finality,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.output import (
    CommitOutputAuthorization,
    authorize_terminal_execution,
    authorize_terminal_publication,
    commit_output_authorization_fingerprint,
    commit_output_authorization_is_authoritative,
    commit_output_authorization_payload,
    deliver_terminal_outcome,
)
from pheroos.governance.permission import (
    ActionPermission,
    action_permission_fingerprint,
    action_permission_is_authoritative,
    action_permission_payload,
)
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    commit_threshold_snapshot_fingerprint,
    commit_threshold_snapshot_is_authoritative,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_chain_state_is_current,
    risk_assessment_fingerprint,
    risk_assessment_is_authoritative,
)
from pheroos.governance.stop_signal import (
    StopResolutionVerification,
    stop_resolution_verification_fingerprint,
    stop_resolution_verification_is_authoritative,
    stop_resolution_verification_payload,
)
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLeaseReplayState,
    eligible_membership_epoch_state_is_current,
    eligible_membership_epoch_state_fingerprint,
    eligible_principal_snapshot_fingerprint,
    eligible_principal_snapshot_is_authoritative,
    support_lease_replay_state_fingerprint,
    support_lease_replay_state_is_current,
)
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.trace import TraceEvent, make_commit_trace_event
from pheroos.trace.commit_contracts import replay_commit_trace


HYBRID_COMMIT_EVALUATION_VERSION = "pheroos-hybrid-commit-evaluation-v1"
HYBRID_COMMIT_EVALUATION_REQUEST_VERSION = (
    "pheroos-hybrid-commit-evaluation-request-v1"
)
HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION = (
    "pheroos-hybrid-commit-evaluation-diagnostic-v1"
)

_HYBRID_COMMIT_EVALUATION_ISSUANCE = object()
_ZERO_ROOT = "sha256:" + "0" * 64
_ATTENTION_CHANNEL_DIAGNOSTIC_CODE = "attention_channel_unavailable"
_ATTENTION_CHANNEL_MESSAGES = {
    "attention": "Hybrid attention input is missing or non-authoritative",
    "exploration_directive": (
        "Hybrid exploration directive is missing, non-authoritative, or does not "
        "match attention"
    ),
    "channel_binding": (
        "Hybrid attention cannot be bound to the authoritative CommitAssessment"
    ),
}


class HybridCommitEvaluationStatus(StrEnum):
    PROGRESS = "progress"
    OUTCOME = "outcome"
    INVALID = "invalid"


class HybridCommitAttentionStatus(StrEnum):
    """Availability of the non-authoritative attention projection."""

    VERIFIED = "verified"
    UNAVAILABLE = "unavailable"


class HybridCommitDiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class HybridCommitDiagnostic:
    code: str
    severity: HybridCommitDiagnosticSeverity
    stage: str
    message: str
    fatal: bool
    references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_commit_text(self.code, "Hybrid Commit diagnostic code")
        if type(self.severity) is not HybridCommitDiagnosticSeverity:
            raise GovernanceError("Hybrid Commit diagnostic severity is invalid")
        require_commit_text(self.stage, "Hybrid Commit diagnostic stage")
        require_commit_text(self.message, "Hybrid Commit diagnostic message")
        if type(self.fatal) is not bool:
            raise GovernanceError("Hybrid Commit diagnostic fatal must be boolean")
        object.__setattr__(
            self,
            "references",
            tuple(
                sorted(
                    require_commit_fingerprint(
                        item,
                        "Hybrid Commit diagnostic reference",
                    )
                    for item in self.references
                )
            ),
        )


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
                raise GovernanceError(f"Hybrid Commit evaluation {name} must be a mapping")
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


@dataclass(frozen=True)
class HybridCommitEvaluation:
    evaluation_version: str
    request_ref: str
    status: HybridCommitEvaluationStatus
    authoritative: bool
    terminal: bool
    assurance_downgraded: bool
    profile: str
    assurance: CommitAssurance
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    current_step: int
    attention_status: HybridCommitAttentionStatus
    binding_step_ref: str
    attention_ref: str
    exploration_directive_ref: str
    assessment_ref: str
    context_ref: str
    window_state_ref: str
    window_root: str
    replay_state_ref: str
    replay_root: str
    progress_ref: str
    outcome_ref: str
    local_receipt_ref: str
    evidence_certificate_ref: str
    distributed_state_ref: str
    distributed_certificate_ref: str
    outcome_certificate_ref: str
    finality_verification_ref: str
    deliver_authorization_ref: str
    publish_authorization_ref: str
    execute_authorization_ref: str
    trace_event_ids: tuple[str, ...]
    trace_root: str
    diagnostics: tuple[HybridCommitDiagnostic, ...]
    evaluation_root: str
    binding_step: object | None = field(default=None, repr=False, compare=False)
    attention: object | None = field(default=None, repr=False, compare=False)
    exploration_directive: object | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    commit_assessment: object | None = field(default=None, repr=False, compare=False)
    commit_window_state: object | None = field(default=None, repr=False, compare=False)
    commit_replay_state: object | None = field(default=None, repr=False, compare=False)
    decision_progress: DecisionProgress | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    decision_outcome: DecisionOutcome | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    local_receipt: LocalCommitReceipt | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    evidence_certificate: EvidenceCommitCertificate | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    distributed_state: DistributedCommitState | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    distributed_certificate: DistributedCommitCertificate | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    outcome_certificate: OutcomeCertificate | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    finality_verification: CommitFinalityVerification | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    deliver_authorization: CommitOutputAuthorization | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    publish_authorization: CommitOutputAuthorization | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    execute_authorization: CommitOutputAuthorization | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    trace_events: tuple[TraceEvent, ...] = field(
        default=(),
        repr=False,
        compare=False,
    )
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_event_ids", tuple(self.trace_event_ids))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "trace_events", tuple(self.trace_events))
        _validate_hybrid_commit_evaluation_shape(self)


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


def hybrid_commit_diagnostic_payload(
    diagnostic: HybridCommitDiagnostic,
) -> dict[str, object]:
    if type(diagnostic) is not HybridCommitDiagnostic:
        raise GovernanceError("Hybrid Commit diagnostic must be canonical")
    return {
        "code": diagnostic.code,
        "severity": diagnostic.severity,
        "stage": diagnostic.stage,
        "message": diagnostic.message,
        "fatal": diagnostic.fatal,
        "references": diagnostic.references,
    }


def hybrid_commit_evaluation_payload(
    evaluation: HybridCommitEvaluation,
) -> dict[str, object]:
    if type(evaluation) is not HybridCommitEvaluation:
        raise GovernanceError("Hybrid Commit evaluation must be canonical")
    _validate_hybrid_commit_evaluation_shape(evaluation)
    return _hybrid_commit_evaluation_payload(evaluation, include_root=True)


def hybrid_commit_evaluation_fingerprint(
    evaluation: HybridCommitEvaluation,
) -> str:
    return commit_payload_fingerprint(
        hybrid_commit_evaluation_payload(evaluation),
        schema=HYBRID_COMMIT_EVALUATION_VERSION,
        profile=evaluation.profile,
    )


def hybrid_commit_evaluation_is_authoritative(value: object) -> bool:
    if type(value) is not HybridCommitEvaluation or not value.authoritative:
        return False
    try:
        issuance = value._issuance
        if not (
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _HYBRID_COMMIT_EVALUATION_ISSUANCE
            and issuance[1] == hybrid_commit_evaluation_fingerprint(value)
        ):
            return False
        if not (
            commit_assessment_is_authoritative(value.commit_assessment)
            and commit_assessment_fingerprint(value.commit_assessment)
            == value.assessment_ref
        ):
            return False
        if not (
            commit_window_state_is_authoritative(value.commit_window_state)
            and commit_window_state_fingerprint(value.commit_window_state)
            == value.window_state_ref
            and value.commit_window_state.window_root == value.window_root
        ):
            return False
        if not (
            commit_replay_state_is_authoritative(value.commit_replay_state)
            and commit_replay_state_fingerprint(value.commit_replay_state)
            == value.replay_state_ref
            and value.commit_replay_state.receipt_root == value.replay_root
        ):
            return False
        from pheroos.governance.hybrid_commit import (
            hybrid_commit_step_fingerprint,
            hybrid_commit_step_is_authoritative,
        )

        if value.attention_status is HybridCommitAttentionStatus.UNAVAILABLE:
            if any(
                (
                    value.binding_step is not None,
                    bool(value.binding_step_ref),
                    value.attention is not None,
                    bool(value.attention_ref),
                    value.exploration_directive is not None,
                    bool(value.exploration_directive_ref),
                )
            ):
                return False
            if not _has_exact_attention_channel_diagnostic(value.diagnostics):
                return False
        elif value.attention_status is HybridCommitAttentionStatus.VERIFIED:
            if not (
                value.binding_step_ref
                and hybrid_commit_step_is_authoritative(value.binding_step)
                and hybrid_commit_step_fingerprint(value.binding_step)
                == value.binding_step_ref
                and value.attention_ref
                and attention_breakdown_is_authoritative(value.attention)
                and attention_breakdown_fingerprint(value.attention)
                == value.attention_ref
                and value.exploration_directive_ref
                and exploration_directive_is_authoritative(
                    value.exploration_directive,
                    attention=value.attention,
                )
                and exploration_directive_fingerprint(
                    value.exploration_directive
                )
                == value.exploration_directive_ref
                and not any(
                    item.code == _ATTENTION_CHANNEL_DIAGNOSTIC_CODE
                    for item in value.diagnostics
                )
            ):
                return False
        else:
            return False
        if value.attention_status is HybridCommitAttentionStatus.VERIFIED:
            for runtime, ref, authoritative, fingerprint in (
                (
                    value.attention,
                    value.attention_ref,
                    attention_breakdown_is_authoritative,
                    attention_breakdown_fingerprint,
                ),
                (
                    value.exploration_directive,
                    value.exploration_directive_ref,
                    exploration_directive_is_authoritative,
                    exploration_directive_fingerprint,
                ),
            ):
                if runtime is None:
                    return False
                if not (ref and authoritative(runtime) and fingerprint(runtime) == ref):
                    return False
        if value.status is HybridCommitEvaluationStatus.PROGRESS:
            if not (
                decision_progress_is_authoritative(value.decision_progress)
                and decision_progress_fingerprint(value.decision_progress)
                == value.progress_ref
                and value.decision_outcome is None
                and not value.outcome_ref
            ):
                return False
        elif not (
            decision_outcome_is_authoritative(value.decision_outcome)
            and decision_outcome_fingerprint(value.decision_outcome)
            == value.outcome_ref
            and value.decision_progress is None
            and not value.progress_ref
        ):
            return False

        optional_records = (
            (
                value.local_receipt,
                value.local_receipt_ref,
                LocalCommitReceipt,
                local_commit_receipt_fingerprint,
                local_commit_receipt_is_authoritative,
            ),
            (
                value.evidence_certificate,
                value.evidence_certificate_ref,
                EvidenceCommitCertificate,
                evidence_commit_certificate_fingerprint,
                None,
            ),
            (
                value.distributed_state,
                value.distributed_state_ref,
                DistributedCommitState,
                distributed_commit_state_fingerprint,
                distributed_commit_state_is_authoritative,
            ),
            (
                value.distributed_certificate,
                value.distributed_certificate_ref,
                DistributedCommitCertificate,
                distributed_commit_certificate_fingerprint,
                None,
            ),
            (
                value.outcome_certificate,
                value.outcome_certificate_ref,
                OutcomeCertificate,
                outcome_certificate_fingerprint,
                None,
            ),
            (
                value.finality_verification,
                value.finality_verification_ref,
                CommitFinalityVerification,
                commit_finality_verification_fingerprint,
                commit_finality_verification_is_authoritative,
            ),
        )
        for runtime, ref, expected_type, fingerprint, authoritative in optional_records:
            if runtime is None:
                if ref:
                    return False
                continue
            if not (type(runtime) is expected_type and ref):
                return False
            if authoritative is not None and not authoritative(runtime):
                return False
            if fingerprint(runtime) != ref:
                return False
        if value.distributed_certificate is not None and not (
            value.distributed_state is not None
            and distributed_commit_value_root(value.distributed_certificate.proposal)
            == value.distributed_certificate.commit_value_root
            == value.distributed_certificate.proposal.commit_value_root
            and _distributed_certificate_registered_final(
                value.distributed_certificate,
                value.distributed_state,
            )
        ):
            return False

        authorizations = (
            (value.deliver_authorization, value.deliver_authorization_ref),
            (value.publish_authorization, value.publish_authorization_ref),
            (value.execute_authorization, value.execute_authorization_ref),
        )
        for authorization, ref in authorizations:
            if authorization is None:
                if ref:
                    return False
                continue
            if not (
                ref
                and commit_output_authorization_is_authoritative(authorization)
                and commit_output_authorization_fingerprint(authorization) == ref
            ):
                return False
        if value.terminal:
            if any(item is None for item, _ in authorizations):
                return False
        elif any(item is not None or ref for item, ref in authorizations):
            return False
        trace_ids = tuple(event.lineage["event_id"] for event in value.trace_events)
        if trace_ids != value.trace_event_ids:
            return False
        if commit_payload_fingerprint(
            {"event_ids": trace_ids},
            schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
            profile=value.profile,
        ) != value.trace_root:
            return False
        for event in value.trace_events:
            event.validate()
        replay_commit_trace(
            value.trace_events,
            require_complete=value.terminal,
        )
        return True
    except Exception:
        return False


def evaluate_hybrid_commit_evaluation(
    request: object,
) -> HybridCommitEvaluation:
    """Evaluate one logical step as a diagnostic total function.

    A canonical request with a usable governance authority envelope always
    reaches the official liveness reducer.  Malformed runtime facts are
    converted into the reducer's issued ``invalid`` outcome.  If even the
    authority envelope cannot be established, the function still returns a
    deterministic non-authoritative invalid diagnostic envelope.
    """

    if type(request) is not HybridCommitEvaluationRequest:
        return _non_authoritative_invalid(
            request,
            _diagnostic(
                "invalid_evaluation_request",
                "request",
                "Hybrid Commit evaluation requires the canonical request record",
                fatal=True,
            ),
        )

    try:
        authority = _establish_authority_envelope(request)
    except Exception as exc:
        return _non_authoritative_invalid(
            request,
            _diagnostic_from_exception(
                "authority_envelope_unavailable",
                "authority",
                exc,
                fatal=True,
            ),
        )

    assessment = authority["assessment"]
    context = authority["context"]
    window_state = authority["window_state"]
    replay_state = authority["replay_state"]
    policy = authority["commit_policy"]
    diagnostics: list[HybridCommitDiagnostic] = []
    binding_step: object | None = None
    prior_trace: tuple[TraceEvent, ...] = ()

    binding_step, attention_diagnostic = _bind_attention_channel(
        request,
        assessment=assessment,
    )
    if attention_diagnostic is not None:
        diagnostics.append(attention_diagnostic)

    try:
        window_state = _advance_window_if_required(
            request,
            assessment=assessment,
            window_state=window_state,
            commit_policy=policy,
        )
    except Exception as exc:
        diagnostics.append(
            _diagnostic_from_exception(
                "invalid_window_transition",
                "window",
                exc,
                fatal=True,
            )
        )

    try:
        prior_trace = _validated_prior_trace(request, assessment=assessment)
    except Exception as exc:
        diagnostics.append(
            _diagnostic_from_exception(
                "invalid_prior_commit_trace",
                "trace",
                exc,
                fatal=True,
            )
        )

    local_receipt: LocalCommitReceipt | None = None
    evidence_certificate: EvidenceCommitCertificate | None = None
    distributed_state: DistributedCommitState | None = None
    distributed_certificate: DistributedCommitCertificate | None = None
    finality_verification: CommitFinalityVerification | None = None
    finality_status = CommitFinalityStatus.NOT_REQUIRED
    finality_reasons: tuple[str, ...] = ()
    next_required: set[str] = set()

    if not _has_fatal(diagnostics):
        try:
            (
                local_receipt,
                evidence_certificate,
                distributed_state,
                distributed_certificate,
                finality_verification,
                finality_status,
                finality_reasons,
                finality_required,
            ) = _resolve_declared_finality(
                request,
                context=context,
                assessment=assessment,
                window_state=window_state,
                replay_state=replay_state,
                commit_policy=policy,
            )
            next_required.update(finality_required)
        except Exception as exc:
            diagnostics.append(
                _diagnostic_from_exception(
                    "invalid_finality_record",
                    "finality",
                    exc,
                    fatal=True,
                    references=_exception_references(request),
                )
            )
            finality_status = CommitFinalityStatus.PENDING

    fatal_codes = tuple(item.code for item in diagnostics if item.fatal)
    try:
        liveness_input = issue_commit_liveness_input(
            window_state,
            assessment=assessment,
            replay_state=replay_state,
            risk_chain_state=request.risk_chain_state,
            risk_assessment=request.risk_assessment,
            threshold_snapshot=request.threshold_snapshot,
            membership_snapshot=request.membership_snapshot,
            membership_epoch_state=request.membership_epoch_state,
            support_replay_state=request.support_replay_state,
            commit_policy=policy,
            previous_progress=(
                request.previous_progress
                if type(request.previous_progress) is DecisionProgress
                else None
            ),
            current_step=request.current_step,
            finality_status=finality_status,
            finality_verification=finality_verification,
            invalid_reason_codes=fatal_codes,
            finality_reason_codes=finality_reasons,
            next_required_inputs=tuple(next_required),
            input_id=request.request_id,
            issuer_id=request.issuer_id,
            authority=request.authority,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:liveness",
        )
        decision = reduce_commit_liveness(
            window_state,
            commit_policy=policy,
            liveness_input=liveness_input,
        )
    except Exception as exc:
        return _non_authoritative_invalid(
            request,
            *diagnostics,
            _diagnostic_from_exception(
                "liveness_authority_unavailable",
                "liveness",
                exc,
                fatal=True,
            ),
            authority=authority,
            window_state=window_state,
        )

    progress = decision if type(decision) is DecisionProgress else None
    outcome = decision if type(decision) is DecisionOutcome else None
    outcome_certificate: OutcomeCertificate | None = None
    deliver: CommitOutputAuthorization | None = None
    publish: CommitOutputAuthorization | None = None
    execute: CommitOutputAuthorization | None = None

    if outcome is not None:
        if (
            outcome.kind is not DecisionOutcomeKind.EVIDENCE_COMMIT
            and (prior_trace or not _has_fatal(diagnostics))
        ):
            try:
                outcome_certificate = _resolve_outcome_certificate(
                    request,
                    outcome=outcome,
                    window_state=window_state,
                    context=context,
                    assessment=assessment,
                    commit_policy=policy,
                )
            except Exception as exc:
                diagnostics.append(
                    _diagnostic_from_exception(
                        "outcome_certificate_unavailable",
                        "outcome_certificate",
                        exc,
                        fatal=False,
                    )
                )
        deliver = deliver_terminal_outcome(
            outcome,
            output_payload_fingerprint=request.output_payload_fingerprint,
        )
        action_certificate = _certificate_for_outcome(
            outcome,
            local_receipt=local_receipt,
            evidence_certificate=evidence_certificate,
            distributed_certificate=distributed_certificate,
            outcome_certificate=outcome_certificate,
        )
        publish = authorize_terminal_publication(
            outcome,
            commit_policy=policy,
            threshold_snapshot=request.threshold_snapshot,
            certificate=action_certificate,  # type: ignore[arg-type]
            output_payload_fingerprint=request.output_payload_fingerprint,
            stop_resolution=request.publish_stop_resolution,  # type: ignore[arg-type]
            permission=request.publish_permission,  # type: ignore[arg-type]
            current_step=request.current_step,
            trusted_issuer_attestations=request.trusted_issuer_attestations,
            distributed_state=distributed_state,
            portable_certificate=evidence_certificate,
            trusted_witness_attestations=request.trusted_witness_attestations,
        )
        execute = authorize_terminal_execution(
            outcome,
            commit_policy=policy,
            threshold_snapshot=request.threshold_snapshot,
            certificate=action_certificate,  # type: ignore[arg-type]
            output_payload_fingerprint=request.output_payload_fingerprint,
            stop_resolution=request.execute_stop_resolution,  # type: ignore[arg-type]
            permission=request.execute_permission,  # type: ignore[arg-type]
            current_step=request.current_step,
            trusted_issuer_attestations=request.trusted_issuer_attestations,
            distributed_state=distributed_state,
            portable_certificate=evidence_certificate,
            trusted_witness_attestations=request.trusted_witness_attestations,
        )
        if not deliver.authorized:
            diagnostics.append(
                _diagnostic(
                    "terminal_delivery_denied",
                    "output",
                    "authoritative terminal outcome was not deliverable",
                    fatal=True,
                )
            )

    trace_events: tuple[TraceEvent, ...]
    try:
        trace_events = _build_evaluation_trace(
            request,
            prior_trace=prior_trace,
            assessment=assessment,
            window_state=window_state,
            progress=progress,
            outcome=outcome,
            local_receipt=local_receipt,
            evidence_certificate=evidence_certificate,
            distributed_state=distributed_state,
            distributed_certificate=distributed_certificate,
            outcome_certificate=outcome_certificate,
            deliver=deliver,
            publish=publish,
            execute=execute,
            invalid_path=_has_fatal(diagnostics),
        )
    except Exception as exc:
        diagnostics.append(
            _diagnostic_from_exception(
                "commit_trace_generation_failed",
                "trace",
                exc,
                fatal=True,
            )
        )
        trace_events = ()

    if outcome is not None and (deliver is None or not deliver.authorized):
        return _non_authoritative_invalid(
            request,
            *diagnostics,
            _diagnostic(
                "terminal_delivery_totality_failed",
                "output",
                "terminal result could not satisfy mandatory delivery",
                fatal=True,
            ),
            authority=authority,
            window_state=window_state,
        )
    if _has_fatal(diagnostics) and (
        outcome is None or outcome.kind is not DecisionOutcomeKind.INVALID
    ):
        return _non_authoritative_invalid(
            request,
            *diagnostics,
            _diagnostic(
                "fail_closed_outcome_unavailable",
                "evaluation",
                "fatal diagnostics did not reduce to an issued invalid outcome",
                fatal=True,
            ),
            authority=authority,
            window_state=window_state,
        )

    if not trace_events:
        return _non_authoritative_invalid(
            request,
            *diagnostics,
            _diagnostic(
                "authoritative_trace_unavailable",
                "trace",
                "Hybrid Commit evaluation could not verify an authoritative trace",
                fatal=True,
            ),
            authority=authority,
            window_state=window_state,
        )

    issued = _issue_evaluation(
        request,
        binding_step=binding_step,
        assessment=assessment,
        context=context,
        window_state=window_state,
        replay_state=replay_state,
        progress=progress,
        outcome=outcome,
        local_receipt=local_receipt,
        evidence_certificate=evidence_certificate,
        distributed_state=distributed_state,
        distributed_certificate=distributed_certificate,
        outcome_certificate=outcome_certificate,
        finality_verification=finality_verification,
        deliver=deliver,
        publish=publish,
        execute=execute,
        trace_events=trace_events,
        diagnostics=tuple(diagnostics),
    )
    if not hybrid_commit_evaluation_is_authoritative(issued):
        return _non_authoritative_invalid(
            request,
            *diagnostics,
            _diagnostic(
                "issued_evaluation_self_verification_failed",
                "evaluation",
                "issued Hybrid Commit evaluation failed authority self-verification",
                fatal=True,
            ),
            authority=authority,
            window_state=window_state,
        )
    return issued


def _establish_authority_envelope(
    request: HybridCommitEvaluationRequest,
) -> dict[str, object]:
    assessment = request.commit_assessment
    context = request.context
    window_state = request.window_state
    replay_state = request.replay_state
    policy = request.commit_policy
    if type(assessment) is not CommitAssessment or not (
        commit_assessment_is_authoritative(assessment)
    ):
        raise GovernanceError("CommitAssessment authority is unavailable")
    if type(context) is not CommitEvaluationContext or not (
        commit_evaluation_context_is_authoritative(context)
    ):
        raise GovernanceError("CommitEvaluationContext authority is unavailable")
    if type(window_state) is not CommitWindowState or not (
        commit_window_state_is_current(window_state)
    ):
        raise GovernanceError("commit window current authority is unavailable")
    if type(replay_state) is not CommitReplayState or not (
        commit_replay_state_is_current(replay_state)
    ):
        raise GovernanceError("commit replay current authority is unavailable")
    if type(policy) is not CollectiveCommitPolicy:
        raise GovernanceError("collective commit policy is not canonical")
    if request.current_step < window_state.last_evaluated_step:
        raise GovernanceError("evaluation step precedes the commit window")
    exact = {
        "profile": assessment.profile,
        "assurance": assessment.assurance,
        "manifest_root": assessment.manifest_root,
        "commit_policy_root": assessment.commit_policy_root,
        "protocol_id": assessment.protocol_id,
        "run_id": assessment.run_id,
        "target": assessment.target,
        "epoch": assessment.epoch,
    }
    for source_name, source in (
        ("context", context),
        ("window", window_state),
    ):
        for name, expected in exact.items():
            if getattr(source, name) != expected:
                raise GovernanceError(
                    f"{source_name} {name} does not match CommitAssessment authority"
                )
    replay_exact = {
        name: exact[name]
        for name in (
            "profile",
            "assurance",
            "manifest_root",
            "commit_policy_root",
            "protocol_id",
            "run_id",
        )
    }
    for name, expected in replay_exact.items():
        if getattr(replay_state, name) != expected:
            raise GovernanceError(
                f"replay {name} does not match CommitAssessment authority"
            )
    if context.context_id == "" or (
        commit_evaluation_context_fingerprint(context)
        != assessment.context_fingerprint
    ):
        raise GovernanceError("assessment does not bind the supplied context")
    if policy.assurance != assessment.assurance.value or policy.target != assessment.target:
        raise GovernanceError("commit policy assurance/target does not match assessment")
    if (
        commit_policy_fingerprint(policy, profile=assessment.profile)
        != assessment.commit_policy_root
    ):
        raise GovernanceError("commit policy root does not match assessment")
    _validate_authority_heads(request, assessment=assessment)
    return {
        "assessment": assessment,
        "context": context,
        "window_state": window_state,
        "replay_state": replay_state,
        "commit_policy": policy,
    }


def _validate_authority_heads(
    request: HybridCommitEvaluationRequest,
    *,
    assessment: CommitAssessment,
) -> None:
    if type(request.risk_chain_state) is not RiskAssessmentChainState or not (
        risk_assessment_chain_state_is_current(request.risk_chain_state)
    ):
        raise GovernanceError("risk chain current head is unavailable")
    if type(request.risk_assessment) is not RiskAssessment or not (
        risk_assessment_is_authoritative(request.risk_assessment)
    ):
        raise GovernanceError("risk assessment authority is unavailable")
    if type(request.threshold_snapshot) is not CommitThresholdSnapshot or not (
        commit_threshold_snapshot_is_authoritative(request.threshold_snapshot)
    ):
        raise GovernanceError("threshold snapshot authority is unavailable")
    if type(request.membership_snapshot) is not EligiblePrincipalSnapshot or not (
        eligible_principal_snapshot_is_authoritative(request.membership_snapshot)
    ):
        raise GovernanceError("membership snapshot authority is unavailable")
    if type(request.membership_epoch_state) is not EligibleMembershipEpochState or not (
        eligible_membership_epoch_state_is_current(request.membership_epoch_state)
    ):
        raise GovernanceError("membership epoch current head is unavailable")
    if type(request.support_replay_state) is not SupportLeaseReplayState or not (
        support_lease_replay_state_is_current(request.support_replay_state)
    ):
        raise GovernanceError("support replay current head is unavailable")
    exact_roots = {
        "risk_chain_state_fingerprint": risk_assessment_chain_state_fingerprint(
            request.risk_chain_state
        ),
        "risk_assessment_fingerprint": risk_assessment_fingerprint(
            request.risk_assessment
        ),
        "threshold_fingerprint": commit_threshold_snapshot_fingerprint(
            request.threshold_snapshot
        ),
        "membership_snapshot_fingerprint": (
            eligible_principal_snapshot_fingerprint(request.membership_snapshot)
        ),
        "membership_epoch_state_fingerprint": (
            eligible_membership_epoch_state_fingerprint(
                request.membership_epoch_state
            )
        ),
        "support_replay_state_fingerprint": (
            support_lease_replay_state_fingerprint(request.support_replay_state)
        ),
    }
    for name, observed in exact_roots.items():
        if getattr(assessment, name) != observed:
            raise GovernanceError(f"authority head {name} does not match assessment")


def _advance_window_if_required(
    request: HybridCommitEvaluationRequest,
    *,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    commit_policy: CollectiveCommitPolicy,
) -> CommitWindowState:
    seal = commit_window_seal_for_state(window_state)
    deadline_reached = request.current_step >= min(
        window_state.absolute_deadline_step,
        window_state.absolute_run_deadline_step,
    )
    if (
        request.current_step > window_state.last_evaluated_step
        and seal is None
        and not deadline_reached
    ):
        if assessment.evaluated_at_step != request.current_step:
            raise GovernanceError(
                "unsealed window advance requires the current-step assessment"
            )
        return advance_commit_window_state(
            window_state,
            assessment=assessment,
            commit_policy=commit_policy,
            threshold_snapshot=request.threshold_snapshot,
            current_step=request.current_step,
        )
    if window_state.last_assessment_ref and (
        window_state.last_assessment_ref != commit_assessment_fingerprint(assessment)
    ):
        raise GovernanceError("window head does not bind the supplied assessment")
    if seal is not None and assessment.evaluated_at_step != seal.sealed_at_step:
        raise GovernanceError("sealed window assessment step changed")
    return window_state


def _resolve_declared_finality(
    request: HybridCommitEvaluationRequest,
    *,
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    replay_state: CommitReplayState,
    commit_policy: CollectiveCommitPolicy,
) -> tuple[
    LocalCommitReceipt | None,
    EvidenceCommitCertificate | None,
    DistributedCommitState | None,
    DistributedCommitCertificate | None,
    CommitFinalityVerification | None,
    CommitFinalityStatus,
    tuple[str, ...],
    tuple[str, ...],
]:
    assurance = assessment.assurance
    if assurance is CommitAssurance.ADVISORY:
        if any(
            item is not None
            for item in (
                request.local_receipt,
                request.evidence_certificate,
                request.distributed_certificate,
            )
        ):
            raise GovernanceError("advisory assurance cannot carry commit certificates")
        return None, None, None, None, None, CommitFinalityStatus.NOT_REQUIRED, (), ()

    stable = commit_window_ready(window_state)
    local_receipt: LocalCommitReceipt | None = None
    if request.local_receipt is not None:
        if type(request.local_receipt) is not LocalCommitReceipt or not (
            local_commit_receipt_is_authoritative(request.local_receipt)
        ):
            raise GovernanceError("supplied local receipt is malformed or forged")
        local_receipt = request.local_receipt
    elif stable and request.current_step == window_state.last_evaluated_step:
        local_receipt = issue_local_commit_receipt(
            context,
            assessment,
            window_state,
            commit_policy=commit_policy,
            risk_chain_state=request.risk_chain_state,  # type: ignore[arg-type]
            risk_assessment=request.risk_assessment,  # type: ignore[arg-type]
            threshold_snapshot=request.threshold_snapshot,  # type: ignore[arg-type]
            membership_snapshot=request.membership_snapshot,  # type: ignore[arg-type]
            membership_epoch_state=request.membership_epoch_state,  # type: ignore[arg-type]
            replay_state=replay_state,
            support_replay_state=request.support_replay_state,  # type: ignore[arg-type]
            output_payload_fingerprint=request.output_payload_fingerprint,
            receipt_id=f"{request.request_id}:local-receipt",
            issuer_id=request.issuer_id,
            authority=request.authority,
            current_step=request.current_step,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:local-receipt",
        )

    if local_receipt is None:
        if request.evidence_certificate is not None or request.distributed_certificate is not None:
            raise GovernanceError("higher-assurance certificate lacks a local receipt")
        return (
            None,
            None,
            None,
            None,
            None,
            CommitFinalityStatus.PENDING,
            (),
            ("local_commit_receipt",),
        )

    if assurance is CommitAssurance.EVIDENCE_BOUND:
        if request.evidence_certificate is not None or request.distributed_certificate is not None:
            raise GovernanceError("evidence-bound assurance cannot accept a higher proof")
        verification = verify_local_commit_finality(
            local_receipt,
            context,
            assessment,
            window_state,
            commit_policy=commit_policy,
            risk_chain_state=request.risk_chain_state,  # type: ignore[arg-type]
            risk_assessment=request.risk_assessment,  # type: ignore[arg-type]
            threshold_snapshot=request.threshold_snapshot,  # type: ignore[arg-type]
            membership_snapshot=request.membership_snapshot,  # type: ignore[arg-type]
            membership_epoch_state=request.membership_epoch_state,  # type: ignore[arg-type]
            replay_state=replay_state,
            support_replay_state=request.support_replay_state,  # type: ignore[arg-type]
            current_step=request.current_step,
            verifier_id=request.issuer_id,
            authority=request.authority,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:local-finality",
        )
        return (
            local_receipt,
            None,
            None,
            None,
            verification,
            CommitFinalityStatus.VERIFIED,
            (),
            (),
        )

    evidence_certificate: EvidenceCommitCertificate | None = None
    if request.evidence_certificate is not None:
        if type(request.evidence_certificate) is not EvidenceCommitCertificate:
            raise GovernanceError("portable evidence certificate is not canonical")
        evidence_certificate = request.evidence_certificate
    elif request.issuer_attestation_refs:
        evidence_certificate = issue_evidence_commit_certificate(
            local_receipt,
            commit_policy=commit_policy,
            certificate_id=f"{request.request_id}:evidence-certificate",
            issuer_attestation_refs=request.issuer_attestation_refs,
            trusted_issuer_attestations=request.trusted_issuer_attestations,
            issuer_id=request.issuer_id,
            authority=request.authority,
            issued_at_step=request.current_step,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:evidence-certificate",
        )
    if evidence_certificate is None:
        if request.distributed_certificate is not None:
            raise GovernanceError("distributed certificate lacks its portable proof")
        return (
            local_receipt,
            None,
            None,
            None,
            None,
            CommitFinalityStatus.PROVISIONAL,
            ("portable_certificate_pending",),
            ("evidence_commit_certificate",),
        )
    evidence_ref = evidence_commit_certificate_fingerprint(evidence_certificate)
    if not verify_evidence_commit_certificate(
        evidence_certificate,
        trusted_issuer_attestations=request.trusted_issuer_attestations,
        expected_certificate_ref=evidence_ref,
        expected_output_payload_fingerprint=request.output_payload_fingerprint,
    ):
        raise GovernanceError("portable evidence certificate verification failed")

    if assurance is CommitAssurance.CERTIFIED:
        if request.distributed_state is not None or request.distributed_certificate is not None:
            raise GovernanceError("certified assurance cannot accept distributed finality")
        verification = verify_evidence_commit_finality(
            evidence_certificate,
            local_receipt,
            context,
            assessment,
            window_state,
            commit_policy=commit_policy,
            risk_chain_state=request.risk_chain_state,  # type: ignore[arg-type]
            risk_assessment=request.risk_assessment,  # type: ignore[arg-type]
            threshold_snapshot=request.threshold_snapshot,  # type: ignore[arg-type]
            membership_snapshot=request.membership_snapshot,  # type: ignore[arg-type]
            membership_epoch_state=request.membership_epoch_state,  # type: ignore[arg-type]
            replay_state=replay_state,
            support_replay_state=request.support_replay_state,  # type: ignore[arg-type]
            trusted_issuer_attestations=request.trusted_issuer_attestations,
            current_step=request.current_step,
            verifier_id=request.issuer_id,
            authority=request.authority,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:certified-finality",
        )
        return (
            local_receipt,
            evidence_certificate,
            None,
            None,
            verification,
            CommitFinalityStatus.VERIFIED,
            (),
            (),
        )

    distributed_state = request.distributed_state
    distributed_certificate = request.distributed_certificate
    if distributed_state is None:
        if distributed_certificate is not None:
            raise GovernanceError("distributed certificate lacks its state head")
        return (
            local_receipt,
            evidence_certificate,
            None,
            None,
            None,
            CommitFinalityStatus.PROVISIONAL,
            ("distributed_state_pending",),
            ("distributed_commit_state",),
        )
    if type(distributed_state) is not DistributedCommitState or not (
        distributed_commit_state_is_current(distributed_state)
    ):
        raise GovernanceError("distributed state is malformed, forged, or stale")
    if distributed_state.frozen:
        return (
            local_receipt,
            evidence_certificate,
            distributed_state,
            None,
            None,
            CommitFinalityStatus.CONFLICT,
            ("distributed_epoch_frozen",),
            (),
        )
    if distributed_certificate is None:
        return (
            local_receipt,
            evidence_certificate,
            distributed_state,
            None,
            None,
            CommitFinalityStatus.PROVISIONAL,
            ("distributed_witness_quorum_pending",),
            ("distributed_commit_certificate",),
        )
    if type(distributed_certificate) is not DistributedCommitCertificate:
        raise GovernanceError("distributed certificate is not canonical")
    distributed_ref = distributed_commit_certificate_fingerprint(
        distributed_certificate
    )
    if not verify_distributed_commit_certificate(
        distributed_certificate,
        commit_policy=commit_policy,
        portable_certificate=evidence_certificate,
        trusted_issuer_attestations=request.trusted_issuer_attestations,
        trusted_witness_attestations=request.trusted_witness_attestations,
        expected_certificate_ref=distributed_ref,
        require_final=True,
    ):
        raise GovernanceError("distributed commit certificate verification failed")
    if not distributed_commit_certificate_is_current_final(
        distributed_certificate,
        distributed_state,
    ):
        raise GovernanceError("distributed final certificate is not current")
    verification = verify_distributed_commit_finality(
        distributed_certificate,
        distributed_state,
        local_receipt,
        current_step=request.current_step,
        verifier_id=request.issuer_id,
        authority=request.authority,
        provenance=request.provenance,
        trace_event_id=f"{request.trace_event_id}:distributed-finality",
    )
    return (
        local_receipt,
        evidence_certificate,
        distributed_state,
        distributed_certificate,
        verification,
        CommitFinalityStatus.VERIFIED,
        (),
        (),
    )


def _resolve_outcome_certificate(
    request: HybridCommitEvaluationRequest,
    *,
    outcome: DecisionOutcome,
    window_state: CommitWindowState,
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    commit_policy: CollectiveCommitPolicy,
) -> OutcomeCertificate | None:
    supplied = request.outcome_certificate
    if supplied is not None:
        if type(supplied) is not OutcomeCertificate:
            raise GovernanceError("outcome certificate is not canonical")
        certificate_ref = outcome_certificate_fingerprint(supplied)
        if (
            supplied.outcome_ref != decision_outcome_fingerprint(outcome)
            or supplied.outcome_kind is not outcome.kind
            or not verify_outcome_certificate(
                supplied,
                trusted_issuer_attestations=request.trusted_issuer_attestations,
                expected_certificate_ref=certificate_ref,
                expected_output_payload_fingerprint=(
                    request.output_payload_fingerprint
                ),
            )
        ):
            raise GovernanceError("outcome certificate verification failed")
        return supplied
    # Local outcome certificates need no external signer.  Portable outcome
    # certificates can also be issued here when the caller supplied exact
    # body-root-bound attestations; otherwise delivery remains available while
    # publication/execute are independently denied.
    try:
        return issue_outcome_certificate(
            outcome,
            window_state,
            commit_policy=commit_policy,
            output_payload_fingerprint=request.output_payload_fingerprint,
            certificate_id=f"{request.request_id}:outcome-certificate",
            context=context,
            assessment=assessment,
            issuer_attestation_refs=request.issuer_attestation_refs,
            trusted_issuer_attestations=request.trusted_issuer_attestations,
            issuer_id=request.issuer_id,
            authority=request.authority,
            issued_at_step=request.current_step,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:outcome-certificate",
        )
    except GovernanceError:
        if commit_policy.certificate.issuer_attestation_required:
            return None
        raise


def _certificate_for_outcome(
    outcome: DecisionOutcome,
    *,
    local_receipt: LocalCommitReceipt | None,
    evidence_certificate: EvidenceCommitCertificate | None,
    distributed_certificate: DistributedCommitCertificate | None,
    outcome_certificate: OutcomeCertificate | None,
) -> object | None:
    if outcome.kind is not DecisionOutcomeKind.EVIDENCE_COMMIT:
        return outcome_certificate
    if outcome.assurance is CommitAssurance.EVIDENCE_BOUND:
        return local_receipt
    if outcome.assurance is CommitAssurance.CERTIFIED:
        return evidence_certificate
    if outcome.assurance is CommitAssurance.DISTRIBUTED:
        return distributed_certificate
    return None


def _validated_prior_trace(
    request: HybridCommitEvaluationRequest,
    *,
    assessment: CommitAssessment,
) -> tuple[TraceEvent, ...]:
    events = tuple(request.prior_trace_events)
    if not events or any(type(item) is not TraceEvent for item in events):
        raise GovernanceError(
            "authoritative Hybrid Commit evaluation requires prior TraceEvent lineage"
        )
    replay = replay_commit_trace(events, require_complete=False)
    expected_identity = (
        assessment.protocol_id,
        assessment.run_id,
        assessment.target,
        assessment.profile,
        assessment.assurance.value,
        assessment.epoch,
    )
    observed_identity = (
        replay.protocol_id,
        replay.run_id,
        replay.target,
        replay.profile,
        replay.assurance,
        replay.epoch,
    )
    if observed_identity != expected_identity:
        raise GovernanceError("prior trace identity does not match CommitAssessment")
    if replay.complete or replay.outcome_ref or replay.output_ref:
        raise GovernanceError("prior trace already contains a terminal result")
    if replay.last_step > request.current_step:
        raise GovernanceError("prior trace is from a future logical step")
    by_type: dict[str, list[TraceEvent]] = {}
    for event in events:
        if event.event_type in {
            "principal_attested",
            "principal_verified",
            "risk_assessed",
            "membership_snapshot",
            "observation_recorded",
            "observation_verified",
            "counterevidence_disposed",
            "challenge_recorded",
            "evidence_bound",
            "support_lease_issued",
            "support_lease_revoked",
            "support_lease_expired",
            "support_equivocation",
            "stop_resolution_verified",
            "action_permission_issued",
            "commit_metrics",
            "commit_window_advanced",
            "commit_window_reset",
            "quorum_pending",
            "commit_certificate_issued",
            "quorum_witness",
            "commit_provisional",
            "certificate_conflict",
        }:
            by_type.setdefault(event.event_type, []).append(event)
    required_types = {
        "principal_attested",
        "principal_verified",
        "risk_assessed",
        "membership_snapshot",
        "observation_recorded",
        "observation_verified",
        "evidence_bound",
        "support_lease_issued",
        "stop_resolution_verified",
        "action_permission_issued",
    }
    missing = sorted(required_types - set(by_type))
    if missing:
        raise GovernanceError(
            "prior trace lacks required authority lineage: " + ", ".join(missing)
        )
    risk_ref = risk_assessment_fingerprint(request.risk_assessment)  # type: ignore[arg-type]
    membership_ref = eligible_principal_snapshot_fingerprint(
        request.membership_snapshot  # type: ignore[arg-type]
    )
    stop_ref = assessment.stop_resolution_fingerprint
    permission_ref = assessment.permission_fingerprint
    exact_refs = {
        "risk_assessed": risk_ref,
        "membership_snapshot": membership_ref,
        "stop_resolution_verified": stop_ref,
        "action_permission_issued": permission_ref,
    }
    for event_type, expected_ref in exact_refs.items():
        if not any(
            event.lineage["record_ref"] == expected_ref
            for event in by_type[event_type]
        ):
            raise GovernanceError(
                f"prior {event_type} trace does not bind the current authority head"
            )
    evidence_refs = {
        item.evidence_binding_fingerprint
        for item in assessment.candidate_metrics
    }
    observed_evidence = {
        event.lineage["record_ref"]
        for event in by_type["evidence_bound"]
    }
    if not evidence_refs.issubset(observed_evidence):
        raise GovernanceError("prior evidence trace does not cover assessed candidates")
    return events


def _issue_evaluation(
    request: HybridCommitEvaluationRequest,
    *,
    binding_step: object | None,
    assessment: CommitAssessment,
    context: CommitEvaluationContext,
    window_state: CommitWindowState,
    replay_state: CommitReplayState,
    progress: DecisionProgress | None,
    outcome: DecisionOutcome | None,
    local_receipt: LocalCommitReceipt | None,
    evidence_certificate: EvidenceCommitCertificate | None,
    distributed_state: DistributedCommitState | None,
    distributed_certificate: DistributedCommitCertificate | None,
    outcome_certificate: OutcomeCertificate | None,
    finality_verification: CommitFinalityVerification | None,
    deliver: CommitOutputAuthorization | None,
    publish: CommitOutputAuthorization | None,
    execute: CommitOutputAuthorization | None,
    trace_events: tuple[TraceEvent, ...],
    diagnostics: tuple[HybridCommitDiagnostic, ...],
) -> HybridCommitEvaluation:
    from pheroos.governance.hybrid_commit import hybrid_commit_step_fingerprint

    trace_ids = tuple(event.lineage["event_id"] for event in trace_events)
    trace_root = commit_payload_fingerprint(
        {"event_ids": trace_ids},
        schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
        profile=assessment.profile,
    )
    if progress is not None:
        status = HybridCommitEvaluationStatus.PROGRESS
        terminal = False
    elif outcome is not None and outcome.kind is DecisionOutcomeKind.INVALID:
        status = HybridCommitEvaluationStatus.INVALID
        terminal = True
    else:
        status = HybridCommitEvaluationStatus.OUTCOME
        terminal = True
    provisional = HybridCommitEvaluation(
        evaluation_version=HYBRID_COMMIT_EVALUATION_VERSION,
        request_ref=_issued_request_ref(request, diagnostics, profile=assessment.profile),
        status=status,
        authoritative=True,
        terminal=terminal,
        assurance_downgraded=False,
        profile=assessment.profile,
        assurance=assessment.assurance,
        protocol_id=assessment.protocol_id,
        run_id=assessment.run_id,
        target=assessment.target,
        epoch=assessment.epoch,
        current_step=request.current_step,
        attention_status=(
            HybridCommitAttentionStatus.VERIFIED
            if binding_step is not None
            else HybridCommitAttentionStatus.UNAVAILABLE
        ),
        binding_step_ref=(
            hybrid_commit_step_fingerprint(binding_step) if binding_step is not None else ""
        ),
        attention_ref=(
            attention_breakdown_fingerprint(request.attention)
            if binding_step is not None
            else ""
        ),
        exploration_directive_ref=(
            exploration_directive_fingerprint(request.exploration_directive)
            if binding_step is not None
            else ""
        ),
        assessment_ref=commit_assessment_fingerprint(assessment),
        context_ref=commit_evaluation_context_fingerprint(context),
        window_state_ref=commit_window_state_fingerprint(window_state),
        window_root=window_state.window_root,
        replay_state_ref=commit_replay_state_fingerprint(replay_state),
        replay_root=replay_state.receipt_root,
        progress_ref=(decision_progress_fingerprint(progress) if progress else ""),
        outcome_ref=(decision_outcome_fingerprint(outcome) if outcome else ""),
        local_receipt_ref=(
            local_commit_receipt_fingerprint(local_receipt) if local_receipt else ""
        ),
        evidence_certificate_ref=(
            evidence_commit_certificate_fingerprint(evidence_certificate)
            if evidence_certificate
            else ""
        ),
        distributed_state_ref=(
            distributed_commit_state_fingerprint(distributed_state)
            if distributed_state
            else ""
        ),
        distributed_certificate_ref=(
            distributed_commit_certificate_fingerprint(distributed_certificate)
            if distributed_certificate
            else ""
        ),
        outcome_certificate_ref=(
            outcome_certificate_fingerprint(outcome_certificate)
            if outcome_certificate
            else ""
        ),
        finality_verification_ref=(
            commit_finality_verification_fingerprint(finality_verification)
            if finality_verification
            else ""
        ),
        deliver_authorization_ref=(
            commit_output_authorization_fingerprint(deliver) if deliver else ""
        ),
        publish_authorization_ref=(
            commit_output_authorization_fingerprint(publish) if publish else ""
        ),
        execute_authorization_ref=(
            commit_output_authorization_fingerprint(execute) if execute else ""
        ),
        trace_event_ids=trace_ids,
        trace_root=trace_root,
        diagnostics=diagnostics,
        evaluation_root=_ZERO_ROOT,
        binding_step=binding_step,
        attention=(
            request.attention
            if binding_step is not None
            else None
        ),
        exploration_directive=(
            request.exploration_directive
            if binding_step is not None
            else None
        ),
        commit_assessment=assessment,
        commit_window_state=window_state,
        commit_replay_state=replay_state,
        decision_progress=progress,
        decision_outcome=outcome,
        local_receipt=local_receipt,
        evidence_certificate=evidence_certificate,
        distributed_state=distributed_state,
        distributed_certificate=distributed_certificate,
        outcome_certificate=outcome_certificate,
        finality_verification=finality_verification,
        deliver_authorization=deliver,
        publish_authorization=publish,
        execute_authorization=execute,
        trace_events=trace_events,
    )
    root = commit_payload_fingerprint(
        _hybrid_commit_evaluation_payload(provisional, include_root=False),
        schema=HYBRID_COMMIT_EVALUATION_VERSION,
        profile=assessment.profile,
    )
    result = _replace_evaluation_root(provisional, root)
    object.__setattr__(
        result,
        "_issuance",
        (
            _HYBRID_COMMIT_EVALUATION_ISSUANCE,
            hybrid_commit_evaluation_fingerprint(result),
        ),
    )
    return result


def _replace_evaluation_root(
    evaluation: HybridCommitEvaluation,
    root: str,
) -> HybridCommitEvaluation:
    return HybridCommitEvaluation(
        **{
            name: (root if name == "evaluation_root" else getattr(evaluation, name))
            for name, definition in evaluation.__dataclass_fields__.items()
            if definition.init
        }
    )


def _non_authoritative_invalid(
    request: object,
    *diagnostics: HybridCommitDiagnostic,
    authority: Mapping[str, object] | None = None,
    window_state: object | None = None,
) -> HybridCommitEvaluation:
    assessment = authority.get("assessment") if authority else None
    context = authority.get("context") if authority else None
    replay_state = authority.get("replay_state") if authority else None
    request_assessment = (
        request.commit_assessment
        if type(request) is HybridCommitEvaluationRequest
        else None
    )
    request_policy = (
        request.commit_policy
        if type(request) is HybridCommitEvaluationRequest
        else None
    )
    assurance = _safe_declared_assurance(request_policy, request_assessment)
    candidate_profile = _safe_diagnostic_profile(
        assessment if assessment is not None else request_assessment,
        assurance=assurance,
    )
    profile = (
        candidate_profile
        if candidate_profile in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]
        else sorted(COMMIT_PROFILES_BY_ASSURANCE[assurance.value])[0]
    )
    identity_source = assessment if assessment is not None else request_assessment
    protocol_id = _safe_diagnostic_text(
        getattr(identity_source, "protocol_id", None),
        "protocol:invalid-hybrid-commit-evaluation",
    )
    run_id = _safe_diagnostic_text(
        getattr(identity_source, "run_id", None),
        "run:invalid-hybrid-commit-evaluation",
    )
    target = _safe_diagnostic_text(
        getattr(identity_source, "target", None),
        "target:invalid-hybrid-commit-evaluation",
    )
    epoch = _safe_diagnostic_step(getattr(identity_source, "epoch", None))
    current_step = _safe_diagnostic_step(
        request.current_step
        if type(request) is HybridCommitEvaluationRequest
        else None
    )
    diagnostic_values = tuple(diagnostics) or (
        _diagnostic(
            "invalid_evaluation",
            "evaluation",
            "Hybrid Commit evaluation authority was unavailable",
            fatal=True,
        ),
    )
    diagnostic_values = _with_exact_attention_channel_diagnostic(
        diagnostic_values,
        request=request,
    )
    request_ref = commit_payload_fingerprint(
        {
            "diagnostic_codes": tuple(item.code for item in diagnostic_values),
            "request_id": _safe_diagnostic_text(
                request.request_id
                if type(request) is HybridCommitEvaluationRequest
                else None,
                "invalid-request",
            ),
        },
        schema="pheroos-hybrid-commit-invalid-request-v1",
        profile=profile,
    )
    window = window_state if type(window_state) is CommitWindowState else None
    replay = replay_state if type(replay_state) is CommitReplayState else None
    provisional = HybridCommitEvaluation(
        evaluation_version=HYBRID_COMMIT_EVALUATION_VERSION,
        request_ref=request_ref,
        status=HybridCommitEvaluationStatus.INVALID,
        authoritative=False,
        terminal=True,
        assurance_downgraded=False,
        profile=profile,
        assurance=assurance,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        current_step=current_step,
        attention_status=HybridCommitAttentionStatus.UNAVAILABLE,
        binding_step_ref="",
        attention_ref="",
        exploration_directive_ref="",
        assessment_ref=(
            commit_assessment_fingerprint(assessment)
            if type(assessment) is CommitAssessment
            else ""
        ),
        context_ref=(
            commit_evaluation_context_fingerprint(context)
            if type(context) is CommitEvaluationContext
            else ""
        ),
        window_state_ref=(
            commit_window_state_fingerprint(window) if window else ""
        ),
        window_root=(window.window_root if window else ""),
        replay_state_ref=(
            commit_replay_state_fingerprint(replay) if replay else ""
        ),
        replay_root=(replay.receipt_root if replay else ""),
        progress_ref="",
        outcome_ref="",
        local_receipt_ref="",
        evidence_certificate_ref="",
        distributed_state_ref="",
        distributed_certificate_ref="",
        outcome_certificate_ref="",
        finality_verification_ref="",
        deliver_authorization_ref="",
        publish_authorization_ref="",
        execute_authorization_ref="",
        trace_event_ids=(),
        trace_root=commit_payload_fingerprint(
            {"event_ids": ()},
            schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
            profile=profile,
        ),
        diagnostics=diagnostic_values,
        evaluation_root=_ZERO_ROOT,
        commit_assessment=assessment,
        commit_window_state=window,
        commit_replay_state=replay,
    )
    root = commit_payload_fingerprint(
        _hybrid_commit_evaluation_payload(provisional, include_root=False),
        schema=HYBRID_COMMIT_EVALUATION_VERSION,
        profile=profile,
    )
    return _replace_evaluation_root(provisional, root)


def _diagnostic(
    code: str,
    stage: str,
    message: str,
    *,
    fatal: bool,
    references: Sequence[str] = (),
) -> HybridCommitDiagnostic:
    return HybridCommitDiagnostic(
        code=code,
        severity=(
            HybridCommitDiagnosticSeverity.ERROR
            if fatal
            else HybridCommitDiagnosticSeverity.WARNING
        ),
        stage=stage,
        message=message,
        fatal=fatal,
        references=tuple(references),
    )


def _diagnostic_from_exception(
    code: str,
    stage: str,
    exc: Exception,
    *,
    fatal: bool,
    references: Sequence[str] = (),
) -> HybridCommitDiagnostic:
    message = str(exc).strip() or type(exc).__name__
    return _diagnostic(
        code,
        stage,
        message,
        fatal=fatal,
        references=references,
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
    if exploration_directive_is_authoritative(value, attention=attention):
        return "authoritative"
    return "provided_invalid"


def _attention_channel_diagnostic(
    stage: str,
    *,
    request: object,
) -> HybridCommitDiagnostic:
    if stage not in _ATTENTION_CHANNEL_MESSAGES:
        raise GovernanceError("attention channel diagnostic stage is invalid")
    references: list[str] = []
    if type(request) is HybridCommitEvaluationRequest:
        if stage in {"attention", "channel_binding"}:
            attention_ref = _safe_fingerprint(
                request.attention,
                attention_breakdown_fingerprint,
            )
            if attention_ref:
                references.append(attention_ref)
        if stage in {"exploration_directive", "channel_binding"}:
            directive_ref = _safe_fingerprint(
                request.exploration_directive,
                exploration_directive_fingerprint,
            )
            if directive_ref:
                references.append(directive_ref)
    return _diagnostic(
        _ATTENTION_CHANNEL_DIAGNOSTIC_CODE,
        stage,
        _ATTENTION_CHANNEL_MESSAGES[stage],
        fatal=False,
        references=tuple(references),
    )


def _bind_attention_channel(
    request: HybridCommitEvaluationRequest,
    *,
    assessment: CommitAssessment,
) -> tuple[object | None, HybridCommitDiagnostic | None]:
    """Bind advisory attention, quarantining every channel-local failure."""

    if not attention_breakdown_is_authoritative(request.attention):
        return None, _attention_channel_diagnostic("attention", request=request)
    if not exploration_directive_is_authoritative(
        request.exploration_directive,
        attention=request.attention,
    ):
        return None, _attention_channel_diagnostic(
            "exploration_directive",
            request=request,
        )
    try:
        from pheroos.governance.hybrid_commit import bind_hybrid_commit_channels

        return (
            bind_hybrid_commit_channels(
                attention=request.attention,
                exploration_directive=request.exploration_directive,
                commit_assessment=assessment,
            ),
            None,
        )
    except Exception:
        # The records are independently authoritative, so the remaining
        # failure is their binding to this assessment (scope, step, or
        # candidate coverage).  Do not expose exception text or object repr.
        return None, _attention_channel_diagnostic(
            "channel_binding",
            request=request,
        )


def _has_exact_attention_channel_diagnostic(
    diagnostics: Sequence[HybridCommitDiagnostic],
) -> bool:
    channel = tuple(
        item
        for item in diagnostics
        if item.code == _ATTENTION_CHANNEL_DIAGNOSTIC_CODE
    )
    if len(channel) != 1:
        return False
    diagnostic = channel[0]
    return bool(
        diagnostic.severity is HybridCommitDiagnosticSeverity.WARNING
        and diagnostic.fatal is False
        and diagnostic.stage in _ATTENTION_CHANNEL_MESSAGES
        and diagnostic.message == _ATTENTION_CHANNEL_MESSAGES[diagnostic.stage]
    )


def _with_exact_attention_channel_diagnostic(
    diagnostics: Sequence[HybridCommitDiagnostic],
    *,
    request: object,
) -> tuple[HybridCommitDiagnostic, ...]:
    retained = tuple(
        item
        for item in diagnostics
        if item.code != _ATTENTION_CHANNEL_DIAGNOSTIC_CODE
    )
    if type(request) is HybridCommitEvaluationRequest:
        if not attention_breakdown_is_authoritative(request.attention):
            stage = "attention"
        elif not exploration_directive_is_authoritative(
            request.exploration_directive,
            attention=request.attention,
        ):
            stage = "exploration_directive"
        else:
            stage = "channel_binding"
    else:
        stage = "channel_binding"
    return tuple(
        (
            *retained,
            _attention_channel_diagnostic(stage, request=request),
        )
    )


def _has_fatal(diagnostics: Sequence[HybridCommitDiagnostic]) -> bool:
    return any(item.fatal for item in diagnostics)


def _exception_references(
    request: HybridCommitEvaluationRequest,
) -> tuple[str, ...]:
    values = (
        _safe_fingerprint(request.local_receipt, local_commit_receipt_fingerprint),
        _safe_fingerprint(
            request.evidence_certificate,
            evidence_commit_certificate_fingerprint,
        ),
        _safe_fingerprint(
            request.distributed_certificate,
            distributed_commit_certificate_fingerprint,
        ),
    )
    return tuple(item for item in values if item)


def _build_evaluation_trace(
    request: HybridCommitEvaluationRequest,
    *,
    prior_trace: tuple[TraceEvent, ...],
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    progress: DecisionProgress | None,
    outcome: DecisionOutcome | None,
    local_receipt: LocalCommitReceipt | None,
    evidence_certificate: EvidenceCommitCertificate | None,
    distributed_state: DistributedCommitState | None,
    distributed_certificate: DistributedCommitCertificate | None,
    outcome_certificate: OutcomeCertificate | None,
    deliver: CommitOutputAuthorization | None,
    publish: CommitOutputAuthorization | None,
    execute: CommitOutputAuthorization | None,
    invalid_path: bool,
) -> tuple[TraceEvent, ...]:
    events = list(prior_trace)
    if invalid_path and not prior_trace:
        # No observation/evidence events are invented when the caller cannot
        # provide a valid upstream chain.  An issued invalid outcome and its
        # mandatory delivery remain traceable without claiming those facts.
        if outcome is None or deliver is None:
            raise GovernanceError("invalid trace path lacks outcome or delivery")
        outcome_event = _decision_outcome_trace_event(
            request,
            outcome,
            previous=(),
        )
        output_event = _output_trace_event(
            request,
            outcome=outcome,
            deliver=deliver,
            publish=publish,
            execute=execute,
            certificate=None,
            distributed_state=None,
            previous=(outcome_event,),
        )
        result = (outcome_event, output_event)
        replay_commit_trace(result, require_complete=True)
        return result

    metric_events: list[TraceEvent] = []
    predecessor_ids = tuple(
        event.lineage["event_id"]
        for event in events
    )
    for metrics in assessment.candidate_metrics:
        metrics_ref = candidate_commit_metrics_fingerprint(
            metrics,
            profile=assessment.profile,
        )
        existing = _find_trace_record(events, "commit_metrics", metrics_ref)
        if existing is not None:
            metric_events.append(existing)
            continue
        event = make_commit_trace_event(
            event_type="commit_metrics",
            protocol_id=assessment.protocol_id,
            target=assessment.target,
            reason="recorded authoritative Optimal Commit candidate metrics",
            profile=assessment.profile,
            assurance=assessment.assurance.value,
            manifest_root=assessment.manifest_root,
            commit_policy_root=assessment.commit_policy_root,
            run_id=assessment.run_id,
            epoch=assessment.epoch,
            step=max(assessment.evaluated_at_step, _last_trace_step(events)),
            record_schema="pheroos-candidate-commit-metrics-v1",
            record_payload=candidate_commit_metrics_payload(metrics),
            previous_event_ids=predecessor_ids,
            details={
                "assessment_ref": commit_assessment_fingerprint(assessment),
                "candidate_id": metrics.candidate_id,
                "net_evidence": metrics.net_evidence,
                "support_clusters": metrics.active_support_clusters,
                "source_diversity": metrics.source_diversity,
                "margin": metrics.margin,
                "ready_for_stability": metrics.ready_for_stability,
            },
        )
        events.append(event)
        metric_events.append(event)

    window_ref = commit_window_state_fingerprint(window_state)
    window_event = _find_trace_record(
        events,
        ("commit_window_advanced", "commit_window_reset"),
        window_ref,
    )
    if window_event is None:
        reset_count = (
            request.commit_policy.commit_window.maximum_leader_resets
            - window_state.remaining_reset_budget
        )
        is_reset = bool(
            window_state.previous_state_fingerprint
            and window_state.reset_reason
            not in {"", "none", "initialized"}
        )
        if is_reset:
            window_event = make_commit_trace_event(
                event_type="commit_window_reset",
                protocol_id=assessment.protocol_id,
                target=assessment.target,
                reason="reset authoritative commit stability window",
                profile=assessment.profile,
                assurance=assessment.assurance.value,
                manifest_root=assessment.manifest_root,
                commit_policy_root=assessment.commit_policy_root,
                run_id=assessment.run_id,
                epoch=assessment.epoch,
                step=request.current_step,
                record_schema="pheroos-commit-window-state-v1",
                record_payload=commit_window_state_payload(window_state),
                previous_event_ids=tuple(
                    event.lineage["event_id"] for event in events
                ),
                details={
                    "assessment_ref": commit_assessment_fingerprint(assessment),
                    "prior_window_ref": window_state.previous_state_fingerprint,
                    "reset_count": max(1, reset_count),
                    "remaining_reset_budget": window_state.remaining_reset_budget,
                    "reason_codes": [window_state.reset_reason],
                },
            )
        else:
            window_event = make_commit_trace_event(
                event_type="commit_window_advanced",
                protocol_id=assessment.protocol_id,
                target=assessment.target,
                reason="advanced authoritative commit stability window",
                profile=assessment.profile,
                assurance=assessment.assurance.value,
                manifest_root=assessment.manifest_root,
                commit_policy_root=assessment.commit_policy_root,
                run_id=assessment.run_id,
                epoch=assessment.epoch,
                step=request.current_step,
                record_schema="pheroos-commit-window-state-v1",
                record_payload=commit_window_state_payload(window_state),
                previous_event_ids=tuple(
                    event.lineage["event_id"] for event in metric_events
                ),
                details={
                    "assessment_ref": commit_assessment_fingerprint(assessment),
                    "leader_candidate_id": window_state.leader_candidate_id,
                    "stability_count": window_state.window_count,
                    "required_stability_steps": window_state.minimum_stability_steps,
                    "window_root": window_state.window_root,
                    "reset_count": max(0, reset_count),
                },
            )
        events.append(window_event)

    certificate_events: list[TraceEvent] = []
    for certificate, kind, final in (
        (
            local_receipt,
            "local_receipt",
            assessment.assurance is CommitAssurance.EVIDENCE_BOUND,
        ),
        (
            evidence_certificate,
            "evidence_commit",
            assessment.assurance is CommitAssurance.CERTIFIED,
        ),
    ):
        if certificate is None:
            continue
        cert_event = _certificate_trace_event(
            request,
            certificate=certificate,
            certificate_kind=kind,
            final=final,
            previous=(window_event,),
        )
        existing = _find_trace_record(
            events,
            "commit_certificate_issued",
            cert_event.lineage["record_ref"],
        )
        if existing is None:
            events.append(cert_event)
            certificate_events.append(cert_event)
        else:
            certificate_events.append(existing)

    distributed_lineage = _append_distributed_witness_trace(
        request,
        events=events,
        window_event=window_event,
        portable_certificate_event=next(
            (
                item
                for item in certificate_events
                if item.lineage["certificate_kind"] == "evidence_commit"
            ),
            None,
        ),
        distributed_state=distributed_state,
        distributed_certificate=distributed_certificate,
    )
    if distributed_certificate is not None:
        cert_event = _certificate_trace_event(
            request,
            certificate=distributed_certificate,
            certificate_kind="distributed_commit",
            final=True,
            previous=tuple((window_event, *distributed_lineage)),
        )
        existing = _find_trace_record(
            events,
            "commit_certificate_issued",
            cert_event.lineage["record_ref"],
        )
        if existing is None:
            events.append(cert_event)
            certificate_events.append(cert_event)
        else:
            certificate_events.append(existing)
    distributed_conflicts = _append_distributed_conflict_trace(
        events=events,
        distributed_state=distributed_state,
    )
    distributed_lineage = tuple((*distributed_lineage, *distributed_conflicts))

    if outcome_certificate is not None:
        cert_event = _certificate_trace_event(
            request,
            certificate=outcome_certificate,
            certificate_kind="outcome",
            final=True,
            previous=(window_event,),
        )
        existing = _find_trace_record(
            events,
            "commit_certificate_issued",
            cert_event.lineage["record_ref"],
        )
        if existing is None:
            events.append(cert_event)
            certificate_events.append(cert_event)
        else:
            certificate_events.append(existing)

    if progress is not None:
        progress_ref = decision_progress_fingerprint(progress)
        existing = _find_trace_record(events, "quorum_pending", progress_ref)
        if existing is None:
            details: dict[str, object] = {
                "assessment_ref": progress.assessment_ref,
                "phase": progress.phase.value,
                "unmet_gates": list(progress.unmet_gates),
                "absolute_deadline_step": progress.absolute_deadline_step,
            }
            if progress.seal_ref:
                details["sealed_window_ref"] = progress.seal_ref
            if progress.previous_progress_ref:
                details["previous_progress_ref"] = progress.previous_progress_ref
            progress_event = make_commit_trace_event(
                event_type="quorum_pending",
                protocol_id=progress.protocol_id,
                target=progress.target,
                reason="Optimal Commit remains non-terminal pending declared gates",
                profile=progress.profile,
                assurance=progress.assurance.value,
                manifest_root=progress.manifest_root,
                commit_policy_root=progress.commit_policy_root,
                run_id=progress.run_id,
                epoch=progress.epoch,
                step=progress.current_step,
                record_schema="pheroos-decision-progress-v1",
                record_payload=decision_progress_payload(progress),
                previous_event_ids=tuple(
                    item.lineage["event_id"]
                    for item in (
                        window_event,
                        *certificate_events,
                        *distributed_lineage,
                    )
                ),
                details=details,
            )
            events.append(progress_event)
        result = tuple(events)
        replay_commit_trace(result, require_complete=False)
        return result

    if outcome is None or deliver is None:
        raise GovernanceError("terminal evaluation trace lacks outcome or delivery")
    outcome_event = _decision_outcome_trace_event(
        request,
        outcome,
        previous=tuple(
            (*certificate_events, *distributed_lineage, window_event)
        ),
    )
    events.append(outcome_event)
    action_authority_events = _append_current_action_authority_trace(
        request,
        events=events,
        outcome_event=outcome_event,
    )
    action_certificate = _certificate_for_outcome(
        outcome,
        local_receipt=local_receipt,
        evidence_certificate=evidence_certificate,
        distributed_certificate=distributed_certificate,
        outcome_certificate=outcome_certificate,
    )
    output_event = _output_trace_event(
        request,
        outcome=outcome,
        deliver=deliver,
        publish=publish,
        execute=execute,
        certificate=action_certificate,
        distributed_state=distributed_state,
        previous=tuple((outcome_event, *action_authority_events)),
    )
    events.append(output_event)
    result = tuple(events)
    replay = replay_commit_trace(result, require_complete=True)
    if replay.outcome_ref != decision_outcome_fingerprint(outcome):
        raise GovernanceError("trace replay outcome does not match governance result")
    if outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT and (
        outcome.certificate_ref not in replay.certificate_refs
    ):
        raise GovernanceError("trace replay omits the exact commit certificate")
    return result


def _certificate_trace_event(
    request: HybridCommitEvaluationRequest,
    *,
    certificate: object,
    certificate_kind: str,
    final: bool,
    previous: tuple[TraceEvent, ...],
) -> TraceEvent:
    if type(certificate) is LocalCommitReceipt:
        payload = local_commit_receipt_payload(certificate)
        schema = LOCAL_COMMIT_RECEIPT_VERSION
        candidate_id = certificate.candidate_id
        claim = certificate.claim_fingerprint
        output = certificate.output_payload_fingerprint
        scope = certificate
    elif type(certificate) is EvidenceCommitCertificate:
        payload = evidence_commit_certificate_payload(certificate)
        schema = EVIDENCE_COMMIT_CERTIFICATE_VERSION
        candidate_id = certificate.candidate_id
        claim = certificate.claim_fingerprint
        output = certificate.output_payload_fingerprint
        scope = certificate
    elif type(certificate) is DistributedCommitCertificate:
        payload = distributed_commit_certificate_payload(certificate)
        schema = DISTRIBUTED_COMMIT_CERTIFICATE_VERSION
        candidate_id = certificate.candidate_id
        claim = certificate.proposal.claim_fingerprint
        output = certificate.proposal.output_payload_fingerprint
        scope = certificate
        commit_value_root = certificate.commit_value_root
    elif type(certificate) is OutcomeCertificate:
        payload = outcome_certificate_payload(certificate)
        schema = OUTCOME_CERTIFICATE_VERSION
        candidate_id = certificate.candidate_id
        claim = certificate.claim_fingerprint
        output = certificate.output_payload_fingerprint
        scope = certificate
    else:
        raise GovernanceError("commit certificate trace record is not canonical")
    details = {
        "certificate_kind": certificate_kind,
        "candidate_id": candidate_id,
        "claim_fingerprint": claim,
        "output_fingerprint": output,
        "final": final,
    }
    if type(certificate) is DistributedCommitCertificate:
        details["commit_value_root"] = commit_value_root
    return make_commit_trace_event(
        event_type="commit_certificate_issued",
        protocol_id=scope.protocol_id,
        target=scope.target,
        reason=f"recorded {certificate_kind} certificate",
        profile=scope.profile,
        assurance=scope.assurance.value,
        manifest_root=scope.manifest_root,
        commit_policy_root=scope.commit_policy_root,
        run_id=scope.run_id,
        epoch=scope.epoch,
        step=max(scope.issued_at_step, _last_trace_step(previous)),
        record_schema=schema,
        record_payload=payload,
        previous_event_ids=tuple(item.lineage["event_id"] for item in previous),
        details=details,
    )


def _append_distributed_witness_trace(
    request: HybridCommitEvaluationRequest,
    *,
    events: list[TraceEvent],
    window_event: TraceEvent,
    portable_certificate_event: TraceEvent | None,
    distributed_state: DistributedCommitState | None,
    distributed_certificate: DistributedCommitCertificate | None,
) -> tuple[TraceEvent, ...]:
    if distributed_state is None:
        return ()
    if portable_certificate_event is None:
        raise GovernanceError(
            "distributed trace requires the exact portable certificate event"
        )

    by_ref: dict[str, object] = {}
    for verification in (
        *distributed_state.witness_verifications,
        *(
            distributed_certificate.witnesses
            if distributed_certificate is not None
            else ()
        ),
    ):
        if not witness_verification_is_authoritative(verification):
            raise GovernanceError(
                "distributed trace witness verification is not authoritative"
            )
        by_ref[witness_verification_fingerprint(verification)] = verification
    verifications = tuple(by_ref[key] for key in sorted(by_ref))
    if not verifications:
        state_ref = distributed_commit_state_fingerprint(distributed_state)
        existing = _find_trace_record(events, "commit_provisional", state_ref)
        if existing is None:
            existing = make_commit_trace_event(
                event_type="commit_provisional",
                protocol_id=distributed_state.protocol_id,
                target=distributed_state.target,
                reason="distributed commit awaits its first verified witness",
                profile=distributed_state.profile,
                assurance=distributed_state.assurance.value,
                manifest_root=distributed_state.manifest_root,
                commit_policy_root=distributed_state.commit_policy_root,
                run_id=distributed_state.run_id,
                epoch=distributed_state.epoch,
                step=max(distributed_state.current_step, _last_trace_step(events)),
                record_schema=DISTRIBUTED_STATE_VERSION,
                record_payload=distributed_commit_state_payload(distributed_state),
                previous_event_ids=(
                    portable_certificate_event.lineage["event_id"],
                ),
                details={
                    "portable_certificate_ref": portable_certificate_event.lineage[
                        "certificate_ref"
                    ],
                    "candidate_id": portable_certificate_event.lineage[
                        "candidate_id"
                    ],
                    "witness_count": 0,
                    "witness_quorum": distributed_state.witness_quorum,
                    "final": False,
                },
            )
            events.append(existing)
        return (existing,)

    witness_events: list[TraceEvent] = []
    for verification in verifications:
        witness = verification.witness
        verification_ref = witness_verification_fingerprint(verification)
        existing = _find_trace_record(events, "quorum_witness", verification_ref)
        if existing is None:
            existing = make_commit_trace_event(
                event_type="quorum_witness",
                protocol_id=witness.protocol_id,
                target=witness.target,
                reason="verified distributed commit quorum witness",
                profile=witness.profile,
                assurance=witness.assurance.value,
                manifest_root=distributed_state.manifest_root,
                commit_policy_root=distributed_state.commit_policy_root,
                run_id=witness.run_id,
                epoch=witness.epoch,
                step=max(verification.verified_at_step, _last_trace_step(events)),
                record_schema=WITNESS_VERIFICATION_VERSION,
                record_payload=witness_verification_payload(verification),
                previous_event_ids=(
                    portable_certificate_event.lineage["event_id"],
                ),
                details={
                    "proposal_digest": witness.proposal_digest,
                    "commit_value_root": witness.commit_value_root,
                    "principal_cluster_id": witness.principal_cluster_id,
                    "failure_domain": witness.failure_domain,
                    "verified": True,
                    "expires_at_step": verification.expires_at_step,
                },
            )
            events.append(existing)
        witness_events.append(existing)

    included = tuple(
        item
        for item in verifications
        if item.witness.principal_cluster_id
        not in distributed_state.excluded_cluster_ids
    )
    commit_value_roots = {item.witness.commit_value_root for item in included}
    if len(commit_value_roots) != 1:
        if not distributed_state.frozen:
            raise GovernanceError(
                "non-frozen distributed trace has conflicting commit values"
            )
        return tuple(witness_events)
    grouped: dict[tuple[str, str, str], list[Any]] = {}
    for item in included:
        key = (
            item.witness.commit_value_root,
            item.witness.proposal_digest,
            item.witness.candidate_id,
        )
        grouped.setdefault(key, []).append(item)
    if not grouped:
        raise GovernanceError("distributed trace lacks an eligible witness group")
    if distributed_certificate is not None:
        selected_key = (
            distributed_certificate.commit_value_root,
            distributed_certificate.proposal_digest,
            distributed_certificate.candidate_id,
        )
        if selected_key not in grouped:
            raise GovernanceError(
                "distributed certificate lacks its exact witness proposal group"
            )
    else:
        selected_key = min(
            grouped,
            key=lambda key: (
                -len(
                    {
                        item.witness.principal_cluster_id
                        for item in grouped[key]
                    }
                ),
                key,
            ),
        )
    selected_group = tuple(grouped[selected_key])
    commit_value_root, proposal_digest, candidate_id = selected_key
    witness_count = len(
        {item.witness.principal_cluster_id for item in selected_group}
    )
    if witness_count >= distributed_state.witness_quorum:
        return tuple(witness_events)

    state_ref = distributed_commit_state_fingerprint(distributed_state)
    existing = _find_trace_record(events, "commit_provisional", state_ref)
    if existing is None:
        existing = make_commit_trace_event(
            event_type="commit_provisional",
            protocol_id=distributed_state.protocol_id,
            target=distributed_state.target,
            reason="distributed commit remains below declared witness quorum",
            profile=distributed_state.profile,
            assurance=distributed_state.assurance.value,
            manifest_root=distributed_state.manifest_root,
            commit_policy_root=distributed_state.commit_policy_root,
            run_id=distributed_state.run_id,
            epoch=distributed_state.epoch,
            step=max(distributed_state.current_step, _last_trace_step(events)),
            record_schema=DISTRIBUTED_STATE_VERSION,
            record_payload=distributed_commit_state_payload(distributed_state),
            previous_event_ids=tuple(
                item.lineage["event_id"] for item in witness_events
            ),
            details={
                "portable_certificate_ref": portable_certificate_event.lineage[
                    "certificate_ref"
                ],
                "proposal_digest": proposal_digest,
                "commit_value_root": commit_value_root,
                "candidate_id": candidate_id,
                "witness_count": witness_count,
                "witness_quorum": distributed_state.witness_quorum,
                "final": False,
            },
        )
        events.append(existing)
    return tuple((*witness_events, existing))


def _append_distributed_conflict_trace(
    *,
    events: list[TraceEvent],
    distributed_state: DistributedCommitState | None,
) -> tuple[TraceEvent, ...]:
    if distributed_state is None or not distributed_state.frozen:
        return ()
    state_ref = distributed_commit_state_fingerprint(distributed_state)
    result: list[TraceEvent] = []
    for finding in distributed_state.conflict_findings:
        certificate_events: list[TraceEvent] = []
        for certificate_ref in finding.certificate_refs:
            event = _find_trace_record(
                events,
                "commit_certificate_issued",
                certificate_ref,
            )
            if event is None:
                raise GovernanceError(
                    "frozen distributed state lacks exact conflicting certificate lineage"
                )
            certificate_events.append(event)
        payload = {
            "finding_id": finding.finding_id,
            "target": finding.target,
            "epoch": finding.epoch,
            "certificate_refs": finding.certificate_refs,
            "commit_value_roots": finding.commit_value_roots,
            "proposal_digests": finding.proposal_digests,
            "candidate_ids": finding.candidate_ids,
            "detected_at_step": finding.detected_at_step,
        }
        event = make_commit_trace_event(
            event_type="certificate_conflict",
            protocol_id=distributed_state.protocol_id,
            target=distributed_state.target,
            reason="detected conflicting final distributed certificates",
            profile=distributed_state.profile,
            assurance=distributed_state.assurance.value,
            manifest_root=distributed_state.manifest_root,
            commit_policy_root=distributed_state.commit_policy_root,
            run_id=distributed_state.run_id,
            epoch=distributed_state.epoch,
            step=max(finding.detected_at_step, _last_trace_step(events)),
            record_schema="pheroos-certificate-conflict-finding-v1",
            record_payload=payload,
            previous_event_ids=tuple(
                item.lineage["event_id"] for item in certificate_events
            ),
            details={
                "finding_id": finding.finding_id,
                "left_certificate_ref": finding.certificate_refs[0],
                "right_certificate_ref": finding.certificate_refs[1],
                "commit_value_roots": finding.commit_value_roots,
                "distributed_state_ref": state_ref,
                "frozen": True,
            },
        )
        existing = _find_trace_record(
            events,
            "certificate_conflict",
            event.lineage["record_ref"],
        )
        if existing is None:
            events.append(event)
            result.append(event)
        else:
            result.append(existing)
    if not result:
        raise GovernanceError(
            "frozen distributed state requires certificate conflict lineage"
        )
    return tuple(result)


def _decision_outcome_trace_event(
    request: HybridCommitEvaluationRequest,
    outcome: DecisionOutcome,
    *,
    previous: tuple[TraceEvent, ...],
) -> TraceEvent:
    details: dict[str, object] = {
        "kind": outcome.kind.value,
        "authoritative_commit": outcome.authoritative_commit,
        "epistemically_committed": outcome.epistemically_committed,
        "candidate_id": outcome.candidate_id,
        "reason_codes": sorted(set(outcome.reason_codes)),
    }
    if outcome.assessment_ref:
        details["assessment_ref"] = outcome.assessment_ref
    if outcome.certificate_ref:
        details["certificate_ref"] = outcome.certificate_ref
    if outcome.seal_ref:
        details["sealed_window_ref"] = outcome.seal_ref
    return make_commit_trace_event(
        event_type="decision_outcome",
        protocol_id=outcome.protocol_id,
        target=outcome.target,
        reason=f"issued terminal {outcome.kind.value} outcome",
        profile=outcome.profile,
        assurance=outcome.assurance.value,
        manifest_root=outcome.manifest_root,
        commit_policy_root=outcome.commit_policy_root,
        run_id=outcome.run_id,
        epoch=outcome.epoch,
        step=outcome.current_step,
        record_schema="pheroos-decision-outcome-v1",
        record_payload=decision_outcome_payload(outcome),
        previous_event_ids=tuple(item.lineage["event_id"] for item in previous),
        details=details,
    )


def _append_current_action_authority_trace(
    request: HybridCommitEvaluationRequest,
    *,
    events: list[TraceEvent],
    outcome_event: TraceEvent,
) -> tuple[TraceEvent, ...]:
    """Record the exact canonical publish/execute facts consumed by authorization.

    Cross-action, blocked, denied, and expired facts remain useful negative
    evidence and are therefore traced too.  Malformed or non-authoritative
    caller objects are never promoted into verified trace facts; the output
    authorizer records their fail-closed denial instead.
    """

    dependencies: list[TraceEvent] = []
    seen_ids: set[str] = set()
    facts = (
        request.publish_stop_resolution,
        request.publish_permission,
        request.execute_stop_resolution,
        request.execute_permission,
    )
    for fact in facts:
        if not _action_fact_matches_trace_identity(
            fact,
            request=request,
            outcome_event=outcome_event,
        ):
            continue
        if type(fact) is StopResolutionVerification:
            if not stop_resolution_verification_is_authoritative(fact):
                continue
            record_ref = stop_resolution_verification_fingerprint(fact)
            event_type = "stop_resolution_verified"
            record_schema = "pheroos-stop-resolution-verification-v1"
            record_payload = stop_resolution_verification_payload(fact)
            details = {
                "action": fact.action.value,
                "blocked": fact.blocked,
                "expires_at_step": fact.expires_at_step,
            }
            reason = f"recorded current {fact.action.value} stop resolution"
        elif type(fact) is ActionPermission:
            if not action_permission_is_authoritative(fact):
                continue
            record_ref = action_permission_fingerprint(fact)
            event_type = "action_permission_issued"
            record_schema = "pheroos-action-permission-v1"
            record_payload = action_permission_payload(fact)
            details = {
                "action": fact.action.value,
                "allowed": fact.allowed,
                "expires_at_step": fact.expires_at_step,
            }
            reason = f"recorded current {fact.action.value} action permission"
        else:
            continue

        existing = _find_trace_record(events, event_type, record_ref)
        if existing is None:
            existing = make_commit_trace_event(
                event_type=event_type,
                protocol_id=fact.protocol_id,
                target=fact.target,
                reason=reason,
                profile=fact.profile,
                assurance=fact.assurance.value,
                manifest_root=fact.manifest_root,
                commit_policy_root=fact.commit_policy_root,
                run_id=fact.run_id,
                epoch=fact.epoch,
                step=max(fact.issued_at_step, _last_trace_step(events)),
                record_schema=record_schema,
                record_payload=record_payload,
                previous_event_ids=(outcome_event.lineage["event_id"],),
                details=details,
            )
            events.append(existing)
        event_id = existing.lineage["event_id"]
        if event_id not in seen_ids:
            dependencies.append(existing)
            seen_ids.add(event_id)
    return tuple(dependencies)


def _action_fact_matches_trace_identity(
    fact: object,
    *,
    request: HybridCommitEvaluationRequest,
    outcome_event: TraceEvent,
) -> bool:
    if type(fact) not in {StopResolutionVerification, ActionPermission}:
        return False
    lineage = outcome_event.lineage
    try:
        return bool(
            fact.profile == lineage["profile"]
            and fact.assurance.value == lineage["assurance"]
            and fact.manifest_root == lineage["manifest_root"]
            and fact.commit_policy_root == lineage["commit_policy_root"]
            and fact.protocol_id == outcome_event.protocol_id
            and fact.run_id == lineage["run_id"]
            and fact.target == outcome_event.target
            and fact.epoch == lineage["epoch"]
            and fact.issued_at_step <= request.current_step
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _output_trace_event(
    request: HybridCommitEvaluationRequest,
    *,
    outcome: DecisionOutcome,
    deliver: CommitOutputAuthorization,
    publish: CommitOutputAuthorization | None,
    execute: CommitOutputAuthorization | None,
    certificate: object | None,
    distributed_state: DistributedCommitState | None,
    previous: tuple[TraceEvent, ...],
) -> TraceEvent:
    payload = {
        "outcome_ref": decision_outcome_fingerprint(outcome),
        "authorizations": {
            "deliver": commit_output_authorization_payload(deliver),
            "publish": (
                commit_output_authorization_payload(publish) if publish else None
            ),
            "execute": (
                commit_output_authorization_payload(execute) if execute else None
            ),
        },
    }
    reasons = set(deliver.reason_codes)
    if publish is not None:
        reasons.update(publish.reason_codes)
    if execute is not None:
        reasons.update(execute.reason_codes)
    details: dict[str, object] = {
        "outcome_ref": decision_outcome_fingerprint(outcome),
        "deliver": deliver.authorized,
        "publish": bool(publish and publish.authorized),
        "execute": bool(execute and execute.authorized),
        "reason_codes": sorted(reasons),
    }
    if certificate is not None:
        details["certificate_ref"] = _certificate_fingerprint(certificate)
    if distributed_state is not None:
        details["distributed_state_ref"] = distributed_commit_state_fingerprint(
            distributed_state
        )
    return make_commit_trace_event(
        event_type="output_decided",
        protocol_id=outcome.protocol_id,
        target=outcome.target,
        reason="evaluated mandatory delivery and independent action gates",
        profile=outcome.profile,
        assurance=outcome.assurance.value,
        manifest_root=outcome.manifest_root,
        commit_policy_root=outcome.commit_policy_root,
        run_id=outcome.run_id,
        epoch=outcome.epoch,
        step=outcome.current_step,
        record_schema="pheroos-commit-output-decision-v1",
        record_payload=payload,
        previous_event_ids=tuple(item.lineage["event_id"] for item in previous),
        details=details,
    )


def _certificate_fingerprint(certificate: object) -> str:
    if type(certificate) is LocalCommitReceipt:
        return local_commit_receipt_fingerprint(certificate)
    if type(certificate) is EvidenceCommitCertificate:
        return evidence_commit_certificate_fingerprint(certificate)
    if type(certificate) is DistributedCommitCertificate:
        return distributed_commit_certificate_fingerprint(certificate)
    if type(certificate) is OutcomeCertificate:
        return outcome_certificate_fingerprint(certificate)
    raise GovernanceError("output certificate is not canonical")


def _find_trace_record(
    events: Sequence[TraceEvent],
    event_types: str | tuple[str, ...],
    record_ref: str,
) -> TraceEvent | None:
    allowed = {event_types} if isinstance(event_types, str) else set(event_types)
    return next(
        (
            event
            for event in events
            if event.event_type in allowed
            and event.lineage["record_ref"] == record_ref
        ),
        None,
    )


def _last_trace_step(events: Sequence[TraceEvent]) -> int:
    return max((event.lineage["step"] for event in events), default=0)


def _hybrid_commit_evaluation_payload(
    evaluation: HybridCommitEvaluation,
    *,
    include_root: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "evaluation_version": evaluation.evaluation_version,
        "request_ref": evaluation.request_ref,
        "status": evaluation.status,
        "authoritative": evaluation.authoritative,
        "terminal": evaluation.terminal,
        "assurance_downgraded": evaluation.assurance_downgraded,
        "profile": evaluation.profile,
        "assurance": evaluation.assurance,
        "protocol_id": evaluation.protocol_id,
        "run_id": evaluation.run_id,
        "target": evaluation.target,
        "epoch": evaluation.epoch,
        "current_step": evaluation.current_step,
        "attention_status": evaluation.attention_status,
        "binding_step_ref": evaluation.binding_step_ref,
        "attention_ref": evaluation.attention_ref,
        "exploration_directive_ref": evaluation.exploration_directive_ref,
        "assessment_ref": evaluation.assessment_ref,
        "context_ref": evaluation.context_ref,
        "window_state_ref": evaluation.window_state_ref,
        "window_root": evaluation.window_root,
        "replay_state_ref": evaluation.replay_state_ref,
        "replay_root": evaluation.replay_root,
        "progress_ref": evaluation.progress_ref,
        "outcome_ref": evaluation.outcome_ref,
        "local_receipt_ref": evaluation.local_receipt_ref,
        "evidence_certificate_ref": evaluation.evidence_certificate_ref,
        "distributed_state_ref": evaluation.distributed_state_ref,
        "distributed_certificate_ref": evaluation.distributed_certificate_ref,
        "outcome_certificate_ref": evaluation.outcome_certificate_ref,
        "finality_verification_ref": evaluation.finality_verification_ref,
        "deliver_authorization_ref": evaluation.deliver_authorization_ref,
        "publish_authorization_ref": evaluation.publish_authorization_ref,
        "execute_authorization_ref": evaluation.execute_authorization_ref,
        "trace_event_ids": evaluation.trace_event_ids,
        "trace_root": evaluation.trace_root,
        "diagnostics": tuple(
            hybrid_commit_diagnostic_payload(item)
            for item in evaluation.diagnostics
        ),
    }
    if include_root:
        payload["evaluation_root"] = evaluation.evaluation_root
    return payload


def _validate_hybrid_commit_evaluation_shape(
    evaluation: HybridCommitEvaluation,
) -> None:
    if evaluation.evaluation_version != HYBRID_COMMIT_EVALUATION_VERSION:
        raise GovernanceError("Hybrid Commit evaluation version is invalid")
    if type(evaluation.status) is not HybridCommitEvaluationStatus:
        raise GovernanceError("Hybrid Commit evaluation status is invalid")
    if type(evaluation.attention_status) is not HybridCommitAttentionStatus:
        raise GovernanceError("Hybrid Commit attention status is invalid")
    for name in ("authoritative", "terminal", "assurance_downgraded"):
        if type(getattr(evaluation, name)) is not bool:
            raise GovernanceError(f"Hybrid Commit evaluation {name} must be boolean")
    if evaluation.assurance_downgraded:
        raise GovernanceError("Hybrid Commit evaluation cannot downgrade assurance")
    require_commit_profile(evaluation.profile, "Hybrid Commit evaluation profile")
    if type(evaluation.assurance) is not CommitAssurance:
        raise GovernanceError("Hybrid Commit evaluation assurance is invalid")
    if evaluation.profile not in COMMIT_PROFILES_BY_ASSURANCE[evaluation.assurance.value]:
        raise GovernanceError("Hybrid Commit evaluation profile/assurance mismatch")
    for name in ("protocol_id", "run_id", "target"):
        require_commit_text(getattr(evaluation, name), f"Hybrid Commit evaluation {name}")
    require_commit_step(evaluation.epoch, "Hybrid Commit evaluation epoch")
    require_commit_step(evaluation.current_step, "Hybrid Commit evaluation current_step")
    require_commit_fingerprint(evaluation.request_ref, "Hybrid Commit request_ref")
    for name in (
        "binding_step_ref",
        "attention_ref",
        "exploration_directive_ref",
        "assessment_ref",
        "context_ref",
        "window_state_ref",
        "window_root",
        "replay_state_ref",
        "replay_root",
        "progress_ref",
        "outcome_ref",
        "local_receipt_ref",
        "evidence_certificate_ref",
        "distributed_state_ref",
        "distributed_certificate_ref",
        "outcome_certificate_ref",
        "finality_verification_ref",
        "deliver_authorization_ref",
        "publish_authorization_ref",
        "execute_authorization_ref",
    ):
        value = getattr(evaluation, name)
        if value:
            require_commit_fingerprint(value, f"Hybrid Commit evaluation {name}")
    require_commit_fingerprint(evaluation.trace_root, "Hybrid Commit trace_root")
    require_commit_fingerprint(evaluation.evaluation_root, "Hybrid Commit evaluation_root")
    require_commit_labels(
        evaluation.trace_event_ids,
        "Hybrid Commit evaluation trace event ids",
        allow_empty=True,
    )
    if any(type(item) is not HybridCommitDiagnostic for item in evaluation.diagnostics):
        raise GovernanceError("Hybrid Commit evaluation diagnostics are invalid")
    channel_refs = (
        evaluation.binding_step_ref,
        evaluation.attention_ref,
        evaluation.exploration_directive_ref,
    )
    if evaluation.attention_status is HybridCommitAttentionStatus.VERIFIED:
        if not all(channel_refs):
            raise GovernanceError("verified Hybrid attention lacks binding refs")
        if any(
            item.code == _ATTENTION_CHANNEL_DIAGNOSTIC_CODE
            for item in evaluation.diagnostics
        ):
            raise GovernanceError(
                "verified Hybrid attention cannot claim channel unavailability"
            )
    else:
        if any(channel_refs):
            raise GovernanceError("unavailable Hybrid attention cannot expose refs")
        if not _has_exact_attention_channel_diagnostic(evaluation.diagnostics):
            raise GovernanceError(
                "unavailable Hybrid attention requires one canonical diagnostic"
            )
    if evaluation.authoritative:
        if not all(
            (
                evaluation.assessment_ref,
                evaluation.context_ref,
                evaluation.window_state_ref,
                evaluation.replay_state_ref,
            )
        ):
            raise GovernanceError("authoritative Hybrid evaluation lacks authority refs")
        if evaluation.status is HybridCommitEvaluationStatus.PROGRESS:
            if evaluation.terminal or not evaluation.progress_ref or evaluation.outcome_ref:
                raise GovernanceError("Hybrid progress envelope is inconsistent")
        else:
            if not evaluation.terminal or not evaluation.outcome_ref or evaluation.progress_ref:
                raise GovernanceError("Hybrid terminal envelope is inconsistent")
    elif evaluation.status is not HybridCommitEvaluationStatus.INVALID:
        raise GovernanceError("non-authoritative Hybrid evaluation must be invalid")
    if evaluation.trace_event_ids != tuple(
        event.lineage["event_id"] for event in evaluation.trace_events
    ):
        raise GovernanceError("Hybrid evaluation trace ids do not match trace events")


def _safe_fingerprint(value: object, fingerprint) -> str:
    try:
        return fingerprint(value)
    except Exception:
        return ""


def _distributed_certificate_registered_final(
    certificate: DistributedCommitCertificate,
    state: DistributedCommitState,
) -> bool:
    """Verify the immutable final-registration fact without current-head bias."""

    try:
        certificate_ref = distributed_commit_certificate_fingerprint(certificate)
        return bool(
            distributed_commit_state_is_authoritative(state)
            and certificate.status.value == "final"
            and not state.frozen
            and any(
                item.certificate_ref == certificate_ref
                and item.proposal_digest == certificate.proposal_digest
                and item.commit_value_root == certificate.commit_value_root
                for item in state.final_registrations
            )
        )
    except (AttributeError, GovernanceError, ValueError):
        return False


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
    "HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION",
    "HYBRID_COMMIT_EVALUATION_REQUEST_VERSION",
    "HYBRID_COMMIT_EVALUATION_VERSION",
    "HybridCommitDiagnostic",
    "HybridCommitDiagnosticSeverity",
    "HybridCommitAttentionStatus",
    "HybridCommitEvaluation",
    "HybridCommitEvaluationRequest",
    "HybridCommitEvaluationStatus",
    "evaluate_hybrid_commit_evaluation",
    "hybrid_commit_diagnostic_payload",
    "hybrid_commit_evaluation_fingerprint",
    "hybrid_commit_evaluation_is_authoritative",
    "hybrid_commit_evaluation_payload",
    "hybrid_commit_evaluation_request_fingerprint",
    "hybrid_commit_evaluation_request_payload",
]
