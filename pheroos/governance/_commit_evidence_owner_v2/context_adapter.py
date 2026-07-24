"""Opaque Decision adapter over current Commit Evidence dependencies."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
)
from pheroos.governance._commit_evidence_owner_v2.contracts import (
    CommitEvidenceAdvanceRequestV2,
    CommitEvidenceSnapshotV2,
)
from pheroos.governance._commit_evidence_owner_v2.replay_projection import (
    commit_evidence_replay_receipts_for_target_v2,
)
from pheroos.governance._commit_evidence_owner_v2.state_handle import (
    _projection_from_material,
    _verified_current_material,
)
from pheroos.governance._commit_evidence_projection_v2.common import (
    evidence_root_v2,
    require_count_v2,
    require_root_v2,
    require_text_v2,
)
from pheroos.governance._commit_evidence_projection_v2.evaluation import (
    CommitEvidenceEvaluationV2,
    evaluate_commit_evidence_projection_v2,
)
from pheroos.governance._commit_evidence_projection_v2.projection import (
    CommitEvidenceProjectionV2,
)
from pheroos.governance._commit_state_v2.operations import (
    VerifiedCommitReplayStateV2,
    _verified_state_view as _verified_replay_view,
    require_current_commit_replay_state_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
    GovernanceStateReaderV2,
)


@dataclass(frozen=True, slots=True)
class _CommitEvidenceSubjectConflictV2:
    candidate_ref: str
    claim_roots: tuple[str, ...]
    conflict_root: str


@dataclass(frozen=True, slots=True)
class _CommitEvidenceContextMaterialV2:
    projection: CommitEvidenceProjectionV2
    active_subjects: tuple[tuple[str, str], ...]
    active_subject_set_root: str
    subject_conflicts: tuple[_CommitEvidenceSubjectConflictV2, ...]
    evidence_current: bool
    membership_current: bool
    verification_current: bool
    evidence_precondition: GovernanceReadPreconditionV2
    evidence_receipt_root: str
    replay_precondition: GovernanceReadPreconditionV2
    replay_receipt_root: str
    membership_precondition: GovernanceReadPreconditionV2
    membership_receipt_root: str
    verification_precondition: GovernanceReadPreconditionV2
    verification_receipt_root: str
    context_root: str


@final
class _VerifiedCommitEvidenceContextV2:
    __slots__ = (
        "_anchor_root",
        "_current_step",
        "_evidence_state",
        "_replay_state",
    )

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> _VerifiedCommitEvidenceContextV2:
        raise TypeError("verified commit evidence context cannot be constructed")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("verified commit evidence context is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("verified commit evidence context is immutable")

    def __reduce__(self) -> NoReturn:
        raise TypeError("verified commit evidence context is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("verified commit evidence context is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("verified commit evidence context is not portable")


class _CommitEvidenceSubjectConflictErrorV2(ValueError):
    def __init__(self, conflict: _CommitEvidenceSubjectConflictV2) -> None:
        self.conflict = conflict
        super().__init__("candidate has multiple active commit evidence claims")


def _verified_commit_evidence_context_v2(
    evidence_state: object,
    replay_state: object,
    *,
    current_step: int,
) -> _VerifiedCommitEvidenceContextV2:
    """Create an opaque current context; portable roots grant no authority."""

    step = require_count_v2(current_step, "commit evidence assessment current_step")
    material = _context_material(evidence_state, replay_state, step)
    context = object.__new__(_VerifiedCommitEvidenceContextV2)
    object.__setattr__(context, "_evidence_state", evidence_state)
    object.__setattr__(context, "_replay_state", replay_state)
    object.__setattr__(context, "_current_step", step)
    object.__setattr__(context, "_anchor_root", material.context_root)
    return context


def _verified_commit_evidence_context_material_v2(
    context: object,
) -> _CommitEvidenceContextMaterialV2:
    if type(context) is not _VerifiedCommitEvidenceContextV2:
        raise TypeError("commit evidence context requires exact opaque context v2")
    try:
        evidence_state = object.__getattribute__(context, "_evidence_state")
        replay_state = object.__getattribute__(context, "_replay_state")
        current_step = object.__getattribute__(context, "_current_step")
        anchor_root = object.__getattribute__(context, "_anchor_root")
    except AttributeError as exc:
        raise TypeError("commit evidence context proof is incomplete") from exc
    material = _context_material(evidence_state, replay_state, current_step)
    if material.context_root != anchor_root:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/evidence_context",
        )
    return material


def _verified_commit_evidence_assessment_v2(
    context: object,
    *,
    candidate_ref: str,
    claim_root: str,
) -> tuple[_CommitEvidenceContextMaterialV2, CommitEvidenceEvaluationV2]:
    """Evaluate one unique authoritative subject from an opaque current context."""

    material = _verified_commit_evidence_context_material_v2(context)
    for is_current, path in (
        (material.evidence_current, "/evidence_state/current_step"),
        (material.membership_current, "/membership_state/current_step"),
        (material.verification_current, "/verification_state/current_step"),
    ):
        if not is_current:
            raise GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                path,
            )
    candidate = require_text_v2(candidate_ref, "commit evidence subject candidate")
    claim = require_root_v2(claim_root, "commit evidence subject claim_root")
    for conflict in material.subject_conflicts:
        if conflict.candidate_ref == candidate:
            raise _CommitEvidenceSubjectConflictErrorV2(conflict)
    if (candidate, claim) not in material.active_subjects:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/evidence_subject",
        )
    replay_state = object.__getattribute__(context, "_replay_state")
    replay = require_current_commit_replay_state_v2(replay_state)
    evaluation = evaluate_commit_evidence_projection_v2(
        material.projection,
        candidate_ref=candidate,
        claim_root=claim,
        replay_receipt_roots=tuple(item.receipt_root for item in replay.receipts),
    )
    return material, evaluation


def _context_material(
    evidence_state: object,
    replay_state: object,
    current_step: int,
) -> _CommitEvidenceContextMaterialV2:
    request, evidence_view, evidence_head = _verified_current_material(evidence_state)
    assert evidence_view.committed_transition is not None
    if type(replay_state) is not VerifiedCommitReplayStateV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/replay_state",
        )
    replay = require_current_commit_replay_state_v2(replay_state)
    _, replay_view = _verified_replay_view(replay_state)
    assert replay_view.committed_transition is not None
    replay_receipt = replay_view.committed_transition.receipt
    _validate_assessment_time(request.snapshot, replay, current_step)
    _validate_replay_context(request.snapshot, replay)
    projection = _projection_from_material(
        request,
        evidence_view,
        current_step=current_step,
    )
    if not all(_freshness(request.snapshot, current_step)):
        projection = replace(projection, records=(), projection_root="")
    for record in projection.records:
        commit_evidence_replay_receipts_for_target_v2(
            record,
            target_ref=projection.target_ref,
        )
    subjects, conflicts, subject_root = _subject_material(projection)
    evidence_precondition = GovernanceReadPreconditionV2(
        stream_ref=request.stream_ref,
        expected_revision=evidence_head.revision,
        expected_root=evidence_head.head_root,
    )
    replay_precondition = GovernanceReadPreconditionV2(
        stream_ref=replay.stream_ref,
        expected_revision=replay.revision,
        expected_root=replay_receipt.head_root,
    )
    membership_precondition = GovernanceReadPreconditionV2(
        stream_ref=request.snapshot.membership_stream_ref,
        expected_revision=request.snapshot.membership_revision,
        expected_root=request.snapshot.membership_head_root,
    )
    verification_precondition = GovernanceReadPreconditionV2(
        stream_ref=request.snapshot.verification_stream_ref,
        expected_revision=request.snapshot.verification_revision,
        expected_root=request.snapshot.verification_head_root,
    )
    return _build_material(
        evidence_state=evidence_state,
        request=request,
        evidence_receipt_root=evidence_view.committed_transition.receipt.receipt_root,
        replay_receipt_root=replay_receipt.receipt_root,
        projection=projection,
        subjects=subjects,
        conflicts=conflicts,
        subject_root=subject_root,
        preconditions=(
            evidence_precondition,
            replay_precondition,
            membership_precondition,
            verification_precondition,
        ),
        current_step=current_step,
    )


def _build_material(
    *,
    evidence_state: object,
    request: CommitEvidenceAdvanceRequestV2,
    evidence_receipt_root: str,
    replay_receipt_root: str,
    projection: CommitEvidenceProjectionV2,
    subjects: tuple[tuple[str, str], ...],
    conflicts: tuple[_CommitEvidenceSubjectConflictV2, ...],
    subject_root: str,
    preconditions: tuple[
        GovernanceReadPreconditionV2,
        GovernanceReadPreconditionV2,
        GovernanceReadPreconditionV2,
        GovernanceReadPreconditionV2,
    ],
    current_step: int,
) -> _CommitEvidenceContextMaterialV2:
    evidence_pre, replay_pre, membership_pre, verification_pre = preconditions
    reader = cast(
        GovernanceStateReaderV2,
        object.__getattribute__(evidence_state, "_reader"),
    )
    snapshot = request.snapshot
    freshness = _freshness(snapshot, current_step)
    membership_receipt = _dependency_receipt_root(
        reader,
        request.scope_ref,
        snapshot.membership_stream_ref,
        snapshot.membership_transition_id,
        membership_pre,
    )
    verification_receipt = _dependency_receipt_root(
        reader,
        request.scope_ref,
        snapshot.verification_stream_ref,
        snapshot.verification_transition_id,
        verification_pre,
    )
    context_root = evidence_root_v2(
        "verified-context",
        {
            "projection_root": projection.projection_root,
            "current_step": current_step,
            "active_subject_set_root": subject_root,
            "evidence_receipt_root": evidence_receipt_root,
            "replay_receipt_root": replay_receipt_root,
            "membership_receipt_root": membership_receipt,
            "verification_receipt_root": verification_receipt,
            "evidence_current": freshness[0],
            "membership_current": freshness[1],
            "verification_current": freshness[2],
            "preconditions": [item.to_dict() for item in preconditions],
        },
    )
    return _CommitEvidenceContextMaterialV2(
        projection=projection,
        active_subjects=subjects,
        active_subject_set_root=subject_root,
        subject_conflicts=conflicts,
        evidence_current=freshness[0],
        membership_current=freshness[1],
        verification_current=freshness[2],
        evidence_precondition=evidence_pre,
        evidence_receipt_root=evidence_receipt_root,
        replay_precondition=replay_pre,
        replay_receipt_root=replay_receipt_root,
        membership_precondition=membership_pre,
        membership_receipt_root=membership_receipt,
        verification_precondition=verification_pre,
        verification_receipt_root=verification_receipt,
        context_root=context_root,
    )


def _subject_material(
    projection: CommitEvidenceProjectionV2,
) -> tuple[
    tuple[tuple[str, str], ...],
    tuple[_CommitEvidenceSubjectConflictV2, ...],
    str,
]:
    subjects = tuple(
        sorted(
            {(item.candidate_ref, item.claim_root) for item in projection.records},
            key=lambda item: (item[0].encode("utf-8"), item[1]),
        )
    )
    by_candidate: dict[str, list[str]] = {}
    for candidate, claim in subjects:
        by_candidate.setdefault(candidate, []).append(claim)
    conflicts = tuple(
        _CommitEvidenceSubjectConflictV2(
            candidate_ref=candidate,
            claim_roots=tuple(claims),
            conflict_root=evidence_root_v2(
                "subject-conflict",
                {"candidate_ref": candidate, "claim_roots": claims},
            ),
        )
        for candidate, claims in sorted(by_candidate.items())
        if len(claims) > 1
    )
    subject_root = evidence_root_v2(
        "active-subject-set",
        {
            "projection_root": projection.projection_root,
            "subjects": [
                {"candidate_ref": candidate, "claim_root": claim}
                for candidate, claim in subjects
            ],
            "conflict_roots": [item.conflict_root for item in conflicts],
        },
    )
    return subjects, conflicts, subject_root


def _validate_assessment_time(
    evidence: CommitEvidenceSnapshotV2,
    replay: object,
    current_step: int,
) -> None:
    lower_bound = max(
        evidence.current_step,
        evidence.membership_current_step,
        evidence.verification_current_step,
        getattr(replay, "current_step"),
    )
    if current_step < lower_bound:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/current_step",
        )


def _freshness(
    evidence: CommitEvidenceSnapshotV2,
    current_step: int,
) -> tuple[bool, bool, bool]:
    return (
        evidence.current_step <= current_step < evidence.expires_at_step,
        evidence.membership_current_step
        <= current_step
        < evidence.membership_expires_at_step,
        evidence.verification_current_step
        <= current_step
        < evidence.verification_expires_at_step,
    )


def _dependency_receipt_root(
    reader: GovernanceStateReaderV2,
    scope_ref: str,
    stream_ref: str,
    transition_id: str,
    precondition: GovernanceReadPreconditionV2,
) -> str:
    try:
        view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(scope_ref, stream_ref, transition_id)
        )
    except Exception as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/dependencies",
        ) from exc
    if (
        view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.committed_transition is None
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/dependencies",
        )
    receipt = view.committed_transition.receipt
    if (
        receipt.stream_ref != stream_ref
        or receipt.transition_id != transition_id
        or receipt.revision != precondition.expected_revision
        or receipt.head_root != precondition.expected_root
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependencies",
        )
    return receipt.receipt_root


def _validate_replay_context(
    evidence: CommitEvidenceSnapshotV2,
    replay: object,
) -> None:
    fields = (
        "domain_root",
        "scope_ref",
        "manifest_root",
        "commit_policy_root",
        "profile",
        "assurance",
        "protocol_ref",
        "run_ref",
        "target_ref",
    )
    if any(getattr(evidence, field) != getattr(replay, field) for field in fields):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/replay_state",
        )
    if getattr(replay, "observed_epoch") != evidence.epoch:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/replay_state/observed_epoch",
        )


__all__: tuple[str, ...] = ()
