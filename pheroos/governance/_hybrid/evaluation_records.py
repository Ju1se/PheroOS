"""Canonical Hybrid Commit result and diagnostic records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from pheroos.governance._certificate.records import (
    EvidenceCommitCertificate,
    OutcomeCertificate,
)
from pheroos.governance._commit.local_receipt import LocalCommitReceipt
from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    CommitFinalityVerification,
    DecisionOutcome,
    DecisionProgress,
)
from pheroos.governance.distributed_commit import (
    DistributedCommitCertificate,
    DistributedCommitState,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.output import CommitOutputAuthorization
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAssurance,
)
from pheroos.trace import TraceEvent


HYBRID_COMMIT_EVALUATION_VERSION = "pheroos-hybrid-commit-evaluation-v1"
HYBRID_COMMIT_EVALUATION_REQUEST_VERSION = "pheroos-hybrid-commit-evaluation-request-v1"
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
            hybrid_commit_diagnostic_payload(item) for item in evaluation.diagnostics
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
    if (
        evaluation.profile
        not in COMMIT_PROFILES_BY_ASSURANCE[evaluation.assurance.value]
    ):
        raise GovernanceError("Hybrid Commit evaluation profile/assurance mismatch")
    for name in ("protocol_id", "run_id", "target"):
        require_commit_text(
            getattr(evaluation, name), f"Hybrid Commit evaluation {name}"
        )
    require_commit_step(evaluation.epoch, "Hybrid Commit evaluation epoch")
    require_commit_step(
        evaluation.current_step, "Hybrid Commit evaluation current_step"
    )
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
    require_commit_fingerprint(
        evaluation.evaluation_root, "Hybrid Commit evaluation_root"
    )
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
            raise GovernanceError(
                "authoritative Hybrid evaluation lacks authority refs"
            )
        if evaluation.status is HybridCommitEvaluationStatus.PROGRESS:
            if (
                evaluation.terminal
                or not evaluation.progress_ref
                or evaluation.outcome_ref
            ):
                raise GovernanceError("Hybrid progress envelope is inconsistent")
        else:
            if (
                not evaluation.terminal
                or not evaluation.outcome_ref
                or evaluation.progress_ref
            ):
                raise GovernanceError("Hybrid terminal envelope is inconsistent")
    elif evaluation.status is not HybridCommitEvaluationStatus.INVALID:
        raise GovernanceError("non-authoritative Hybrid evaluation must be invalid")
    if evaluation.trace_event_ids != tuple(
        event.lineage["event_id"] for event in evaluation.trace_events
    ):
        raise GovernanceError("Hybrid evaluation trace ids do not match trace events")


def _has_exact_attention_channel_diagnostic(
    diagnostics: Sequence[HybridCommitDiagnostic],
) -> bool:
    channel = tuple(
        item for item in diagnostics if item.code == _ATTENTION_CHANNEL_DIAGNOSTIC_CODE
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


__all__ = [
    "HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION",
    "HYBRID_COMMIT_EVALUATION_REQUEST_VERSION",
    "HYBRID_COMMIT_EVALUATION_VERSION",
    "HybridCommitAttentionStatus",
    "HybridCommitDiagnostic",
    "HybridCommitDiagnosticSeverity",
    "HybridCommitEvaluation",
    "HybridCommitEvaluationStatus",
    "hybrid_commit_diagnostic_payload",
    "hybrid_commit_evaluation_fingerprint",
    "hybrid_commit_evaluation_payload",
]
