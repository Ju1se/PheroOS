"""Store-verified upstream material for Commit Decision v2 sources."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._commit_decision_v2.assessment_records import CommitAssessmentV2
from pheroos.governance._commit_decision_v2.common import _root
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    canonical_commit_decision_dependencies_v2,
    commit_decision_dependency_set_root_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionDependencyRoleV2,
)
from pheroos.governance._commit_decision_v2.evaluation import (
    derive_commit_assessment_v2,
)
from pheroos.governance._commit_decision_v2.gate_status import (
    CommitDecisionGateStatusV2,
)
from pheroos.governance._commit_decision_v2.proposals import (
    CommitDecisionCandidateProposalV2,
)
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2
from pheroos.governance._commit_decision_v2.state_handle import (
    VerifiedCommitDecisionStateV2,
    _verified_state_view_v2 as _verified_decision_view_v2,
)
from pheroos.governance._commit_decision_v2.state_records import _head_from_view_v2
from pheroos.governance._commit_decision_v2.upstream_inputs import (
    _collect_decision_upstream_material_v2,
    _gate_dependencies_match_v2,
)
from pheroos.governance._commit_evidence_owner_v2.context_adapter import (
    _CommitEvidenceContextMaterialV2,
    _VerifiedCommitEvidenceContextV2,
    _verified_commit_evidence_assessment_v2,
    _verified_commit_evidence_context_material_v2,
    _verified_commit_evidence_context_v2,
)
from pheroos.governance._commit_evidence_v2 import (
    CommitEvidenceEvaluationV2,
    CommitEvidenceProjectionV2,
)
from pheroos.governance._commit_gate_v2.permission_contracts import (
    CommitPermissionSnapshotV2,
)
from pheroos.governance._commit_gate_v2.permission_operations import (
    require_current_commit_permission_state_v2,
)
from pheroos.governance._commit_gate_v2.state_handle import (
    _verified_state_view_v2 as _verified_gate_view_v2,
)
from pheroos.governance._commit_gate_v2.stop_contracts import CommitStopSnapshotV2
from pheroos.governance._commit_gate_v2.stop_operations import (
    require_current_commit_stop_state_v2,
)
from pheroos.governance._risk_v2.contracts import RiskStateSnapshotV2
from pheroos.governance._support_v2.membership_contracts import (
    MembershipSnapshotV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitPositionV2,
)


@dataclass(frozen=True, slots=True)
class _CommitDecisionInputMaterialV2:
    domain: AuthorityDomainV2
    parent: CommitDecisionSnapshotV2
    dependencies: tuple[CommitDecisionDependencyV2, ...]
    assessment: CommitAssessmentV2
    gate_status: CommitDecisionGateStatusV2
    required_stability_steps: int
    evidence_context_root: str


type _CommitGateSnapshotV2 = CommitStopSnapshotV2 | CommitPermissionSnapshotV2


def _collect_commit_decision_inputs_v2(
    *,
    parent_state: object,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    current_step: int,
    proposals: Sequence[CommitDecisionCandidateProposalV2],
    commit_replay_state: object,
    risk_state: object,
    membership_state: object,
    support_state: object,
    evidence_state: object,
    stop_state: object,
    permission_state: object,
) -> _CommitDecisionInputMaterialV2:
    domain, parent, parent_dependency = _current_parent_v2(parent_state)
    effective_proposals = _effective_candidate_proposals_v2(parent, proposals)
    policy = manifest.collective_commit_policy
    if policy is None:
        raise ValueError("commit decision manifest has no commit policy")
    assurance = CommitAssurance(policy.assurance)
    authority_observed_epoch = max(
        parent.epoch,
        cast(int, getattr(getattr(membership_state, "snapshot"), "observed_epoch")),
        cast(int, getattr(getattr(support_state, "snapshot"), "observed_epoch")),
    )
    upstream = _collect_decision_upstream_material_v2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        manifest_root=manifest.manifest_root,
        commit_policy_root=parent.commit_policy_root,
        profile=profile,
        assurance=assurance,
        protocol_ref=parent.protocol_ref,
        run_ref=parent.run_ref,
        target_ref=parent.target_ref,
        observed_epoch=authority_observed_epoch,
        current_step=current_step,
        commit_replay_state=commit_replay_state,
        risk_state=risk_state,
        membership_state=membership_state,
        support_state=support_state,
    )
    evidence_context = _verified_commit_evidence_context_v2(
        evidence_state,
        commit_replay_state,
        current_step=current_step,
    )
    evidence = _verified_commit_evidence_context_material_v2(evidence_context)
    preconditions = {item.stream_ref: item for item in upstream.preconditions}
    _require_same_precondition(evidence.replay_precondition, preconditions)
    _require_same_precondition(evidence.membership_precondition, preconditions)
    _require_same_precondition(evidence.verification_precondition, preconditions)
    evaluations = _evidence_evaluations_v2(evidence_context, evidence)
    stop, stop_dependency = _current_gate_v2(
        stop_state,
        role=CommitDecisionDependencyRoleV2.STOP,
        expected_type=CommitStopSnapshotV2,
    )
    permission, permission_dependency = _current_gate_v2(
        permission_state,
        role=CommitDecisionDependencyRoleV2.PERMISSION,
        expected_type=CommitPermissionSnapshotV2,
    )
    _validate_gate_context(stop, parent, manifest=manifest, profile=profile)
    _validate_gate_context(permission, parent, manifest=manifest, profile=profile)
    stop_dependencies_current = _gate_dependencies_match_v2(
        stop.dependencies,
        upstream,
    )
    permission_dependencies_current = _gate_dependencies_match_v2(
        permission.dependencies,
        upstream,
    )
    dependencies = canonical_commit_decision_dependencies_v2(
        (
            parent_dependency,
            _dependency_from_precondition(
                CommitDecisionDependencyRoleV2.REPLAY,
                upstream.replay,
                evidence.replay_precondition,
                evidence.replay_receipt_root,
            ),
            _dependency_from_precondition(
                CommitDecisionDependencyRoleV2.RISK,
                upstream.risk,
                preconditions[upstream.risk.stream_ref],
                cast(str, getattr(risk_state, "receipt_root")),
            ),
            _dependency_from_precondition(
                CommitDecisionDependencyRoleV2.MEMBERSHIP,
                upstream.membership,
                evidence.membership_precondition,
                evidence.membership_receipt_root,
            ),
            _verification_dependency_v2(upstream.membership, evidence),
            _dependency_from_precondition(
                CommitDecisionDependencyRoleV2.SUPPORT,
                upstream.support,
                preconditions[upstream.support.stream_ref],
                cast(str, getattr(support_state, "receipt_root")),
            ),
            _evidence_dependency_v2(evidence),
            stop_dependency,
            permission_dependency,
        )
    )
    dependency_root = commit_decision_dependency_set_root_v2(dependencies)
    evaluation_context_root = _root(
        "evaluation-context",
        {
            "evidence_context_root": evidence.context_root,
            "stop_snapshot_root": stop.snapshot_root,
            "permission_snapshot_root": permission.snapshot_root,
            "stop_dependencies_current": stop_dependencies_current,
            "permission_dependencies_current": permission_dependencies_current,
            "dependency_set_root": dependency_root,
            "current_step": current_step,
        },
    )
    assessment = derive_commit_assessment_v2(
        manifest=manifest,
        current_step=current_step,
        epoch=parent.epoch,
        proposals=effective_proposals,
        authoritative_subjects=evidence.active_subjects,
        evidence_evaluations=evaluations,
        risk=upstream.risk,
        membership_state=membership_state,
        support_state=support_state,
        stop=cast(CommitStopSnapshotV2, stop),
        permission=cast(CommitPermissionSnapshotV2, permission),
        stop_dependencies_current=stop_dependencies_current,
        permission_dependencies_current=permission_dependencies_current,
        dependency_set_root=dependency_root,
        evaluation_context_root=evaluation_context_root,
    )
    gate_status = _gate_status_v2(
        parent,
        assessment=assessment,
        risk=upstream.risk,
        membership=upstream.membership,
        evidence_material=evidence,
        current_step=current_step,
    )
    return _CommitDecisionInputMaterialV2(
        domain=domain,
        parent=parent,
        dependencies=dependencies,
        assessment=assessment,
        gate_status=gate_status,
        required_stability_steps=max(
            policy.commit_window.minimum_stability_steps,
            upstream.risk.threshold.stability_steps,
        ),
        evidence_context_root=evidence.context_root,
    )


def _effective_candidate_proposals_v2(
    parent: CommitDecisionSnapshotV2,
    proposals: Sequence[CommitDecisionCandidateProposalV2],
) -> tuple[CommitDecisionCandidateProposalV2, ...]:
    """Reassess the parent's closed candidate set for proposal-free commands."""

    supplied = tuple(proposals)
    if supplied or parent.assessment is None:
        return supplied
    return tuple(
        CommitDecisionCandidateProposalV2(
            candidate_ref=item.candidate_ref,
            claim_root=item.claim_root,
            evidence=(),
        )
        for item in parent.assessment.candidate_metrics
    )


def _current_parent_v2(
    state: object,
) -> tuple[AuthorityDomainV2, CommitDecisionSnapshotV2, CommitDecisionDependencyV2]:
    if type(state) is not VerifiedCommitDecisionStateV2:
        raise TypeError("commit decision successor requires verified parent state")
    _, snapshot, view = _verified_decision_view_v2(state)
    if (
        view.position_observation is None
        or view.position_observation.position is not GovernanceCommitPositionV2.CURRENT
        or view.committed_transition is None
    ):
        raise ValueError("commit decision successor parent is not current")
    domain = object.__getattribute__(state, "_domain")
    if type(domain) is not AuthorityDomainV2:
        raise TypeError("commit decision parent domain is invalid")
    head = _head_from_view_v2(view, domain)
    dependency = CommitDecisionDependencyV2(
        role=CommitDecisionDependencyRoleV2.PARENT,
        stream_ref=head.stream_ref,
        revision=head.revision,
        transition_id=head.transition_id,
        snapshot_root=snapshot.snapshot_root,
        head_root=head.head_root,
        receipt_root=view.committed_transition.receipt.receipt_root,
        observed_position=GovernanceCommitPositionV2.CURRENT,
    )
    return domain, snapshot, dependency


def _dependency_from_precondition(
    role: CommitDecisionDependencyRoleV2,
    snapshot: object,
    precondition: GovernanceReadPreconditionV2,
    receipt_root: str,
) -> CommitDecisionDependencyV2:
    return CommitDecisionDependencyV2(
        role=role,
        stream_ref=precondition.stream_ref,
        revision=precondition.expected_revision,
        transition_id=cast(str, getattr(snapshot, "transition_id")),
        snapshot_root=cast(str, getattr(snapshot, "snapshot_root")),
        head_root=precondition.expected_root,
        receipt_root=receipt_root,
        observed_position=GovernanceCommitPositionV2.CURRENT,
    )


def _verification_dependency_v2(
    membership: MembershipSnapshotV2,
    evidence: _CommitEvidenceContextMaterialV2,
) -> CommitDecisionDependencyV2:
    return CommitDecisionDependencyV2(
        role=CommitDecisionDependencyRoleV2.PRINCIPAL_VERIFICATION,
        stream_ref=evidence.verification_precondition.stream_ref,
        revision=evidence.verification_precondition.expected_revision,
        transition_id=cast(str, getattr(membership, "verification_transition_id")),
        snapshot_root=cast(str, getattr(membership, "verification_snapshot_root")),
        head_root=evidence.verification_precondition.expected_root,
        receipt_root=evidence.verification_receipt_root,
        observed_position=GovernanceCommitPositionV2.CURRENT,
    )


def _evidence_dependency_v2(
    evidence: _CommitEvidenceContextMaterialV2,
) -> CommitDecisionDependencyV2:
    projection = evidence.projection
    return CommitDecisionDependencyV2(
        role=CommitDecisionDependencyRoleV2.EVIDENCE,
        stream_ref=evidence.evidence_precondition.stream_ref,
        revision=evidence.evidence_precondition.expected_revision,
        transition_id=projection.transition_id,
        snapshot_root=projection.snapshot_root,
        head_root=evidence.evidence_precondition.expected_root,
        receipt_root=evidence.evidence_receipt_root,
        observed_position=GovernanceCommitPositionV2.CURRENT,
    )


def _current_gate_v2(
    state: object,
    *,
    role: CommitDecisionDependencyRoleV2,
    expected_type: type[CommitStopSnapshotV2] | type[CommitPermissionSnapshotV2],
) -> tuple[_CommitGateSnapshotV2, CommitDecisionDependencyV2]:
    snapshot = (
        require_current_commit_stop_state_v2(state)
        if role is CommitDecisionDependencyRoleV2.STOP
        else require_current_commit_permission_state_v2(state)
    )
    if type(snapshot) is not expected_type:
        raise TypeError("commit decision gate snapshot has the wrong exact type")
    _, view = _verified_gate_view_v2(state)
    if view.committed_transition is None:
        raise ValueError("commit decision gate has no committed receipt")
    receipt = view.committed_transition.receipt
    typed_snapshot = snapshot
    return typed_snapshot, CommitDecisionDependencyV2(
        role=role,
        stream_ref=receipt.stream_ref,
        revision=receipt.revision,
        transition_id=receipt.transition_id,
        snapshot_root=cast(str, getattr(snapshot, "snapshot_root")),
        head_root=receipt.head_root,
        receipt_root=receipt.receipt_root,
        observed_position=GovernanceCommitPositionV2.CURRENT,
    )


def _require_same_precondition(
    expected: GovernanceReadPreconditionV2,
    observed: dict[str, GovernanceReadPreconditionV2],
) -> None:
    actual = observed.get(expected.stream_ref)
    if actual is None or actual.to_dict() != expected.to_dict():
        raise ValueError("commit decision evidence dependency head is mismatched")


def _evidence_evaluations_v2(
    context: _VerifiedCommitEvidenceContextV2,
    material: _CommitEvidenceContextMaterialV2,
) -> tuple[tuple[CommitEvidenceProjectionV2, CommitEvidenceEvaluationV2], ...]:
    if not all(
        (
            material.evidence_current,
            material.membership_current,
            material.verification_current,
        )
    ):
        return ()
    conflicts = {item.candidate_ref for item in material.subject_conflicts}
    values = []
    for candidate_ref, claim_root in material.active_subjects:
        if candidate_ref in conflicts:
            continue
        checked, evaluation = _verified_commit_evidence_assessment_v2(
            context,
            candidate_ref=candidate_ref,
            claim_root=claim_root,
        )
        if checked.context_root != material.context_root:
            raise ValueError(
                "commit decision evidence context changed during assessment"
            )
        values.append((checked.projection, evaluation))
    return tuple(values)


def _validate_gate_context(
    snapshot: object,
    parent: CommitDecisionSnapshotV2,
    *,
    manifest: ScopedProtocolManifestV2,
    profile: str,
) -> None:
    observed = tuple(
        getattr(snapshot, field)
        for field in (
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
    )
    expected = (
        parent.domain_root,
        parent.scope_ref,
        manifest.manifest_root,
        parent.commit_policy_root,
        profile,
        parent.assurance,
        parent.protocol_ref,
        parent.run_ref,
        parent.target_ref,
    )
    if observed != expected:
        raise ValueError("commit decision gate context is mismatched")


def _gate_status_v2(
    parent: CommitDecisionSnapshotV2,
    *,
    assessment: CommitAssessmentV2,
    risk: RiskStateSnapshotV2,
    membership: MembershipSnapshotV2,
    evidence_material: _CommitEvidenceContextMaterialV2,
    current_step: int,
) -> CommitDecisionGateStatusV2:
    reasons: list[str] = []
    reasons.extend(
        reason
        for reason in assessment.reason_codes
        if reason.startswith(("invalid:", "safety:"))
    )
    if assessment.replay_conflict_refs:
        reasons.append("invalid:replay_conflict")
    if assessment.equivocation_refs:
        reasons.append("safety:support_equivocation")
    sealed_metrics = None
    if parent.seal is not None:
        sealed_metrics = next(
            (
                item
                for item in assessment.candidate_metrics
                if item.candidate_ref == parent.seal.candidate_ref
                and item.claim_root == parent.seal.claim_root
            ),
            None,
        )
    if parent.seal is not None and sealed_metrics is None:
        reasons.append("invalid:sealed_candidate_assessment_missing")
    evidence_current = (
        evidence_material.evidence_current
        and (parent.seal is None or sealed_metrics is not None)
        and (
            sealed_metrics is None
            or not any(
                reason.startswith(("evidence:", "input:evidence", "invalid:evidence"))
                for reason in sealed_metrics.reason_codes
            )
        )
    )
    support_current = (parent.seal is None or sealed_metrics is not None) and (
        sealed_metrics is None
        or not any(
            reason.startswith(("support:", "safety:support"))
            for reason in sealed_metrics.reason_codes
        )
    )
    risk_current = (
        risk.assessment.issued_at_step <= current_step < risk.assessment.expires_at_step
    )
    membership_current = (
        membership.issued_at_step <= current_step < membership.expires_at_step
    )
    verification_current = evidence_material.verification_current
    stop_clear = assessment.stop_clear
    permission_allowed = assessment.permission_allowed
    flags = (
        (risk_current, "risk:not_current"),
        (membership_current, "membership:not_current"),
        (verification_current, "verification:not_current"),
        (evidence_current, "evidence:not_current"),
        (support_current, "support:not_current"),
        (stop_clear, "stop:unresolved_or_expired"),
        (permission_allowed, "permission:unresolved_or_expired"),
    )
    reasons.extend(reason for clear, reason in flags if not clear)
    return CommitDecisionGateStatusV2(
        current_step=current_step,
        stop_clear=stop_clear,
        permission_allowed=permission_allowed,
        risk_current=risk_current,
        membership_current=membership_current,
        verification_current=verification_current,
        evidence_current=evidence_current,
        support_current=support_current,
        blocker_roots=(
            *assessment.blocker_refs,
            *assessment.equivocation_refs,
            *assessment.replay_conflict_refs,
        ),
        reason_codes=tuple(reasons),
    )


__all__: tuple[str, ...] = ()
