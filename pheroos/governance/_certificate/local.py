from __future__ import annotations

"""Local commit receipt issuance, matching, and finality verification."""

from pheroos.governance._certificate.invariants import (
    _issue_typed_finality_verification,
    _validate_policy_binding,
    output_payload_fingerprint,
)
from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._commit.certificate_contracts import (
    LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
    LOCAL_COMMIT_RECEIPT_VERSION,
)
from pheroos.governance._commit.local_receipt import (
    LocalCommitReceipt,
    bind_local_commit_receipt_authority as _register_local_receipt,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    local_commit_receipt_payload,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit import (
    CommitAssessment,
    CommitAssessmentStatus,
    CommitEvaluationContext,
    commit_assessment_fingerprint,
    commit_assessment_is_authoritative,
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
)
from pheroos.governance.commit_state import (
    AuthorityScope,
    CommitFinalityVerification,
    CommitReplayState,
    CommitWindowState,
    _seal_commit_window_from_local_receipt,
    commit_replay_state_fingerprint,
    commit_replay_state_matches,
    commit_window_ready,
    commit_window_seal_matches_receipt,
    commit_window_state_fingerprint,
    commit_window_state_is_authoritative,
    commit_window_state_is_current,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    commit_threshold_snapshot_fingerprint,
    commit_threshold_snapshot_matches,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_fingerprint,
)
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLeaseReplayState,
    eligible_membership_epoch_state_fingerprint,
    eligible_principal_snapshot_fingerprint,
    eligible_principal_snapshot_matches,
    support_lease_replay_state_fingerprint,
    support_lease_replay_state_is_current,
)
from pheroos.protocol.commit_models import CollectiveCommitPolicy, CommitAssurance


def issue_local_commit_receipt(
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    output_payload_fingerprint: str,
    receipt_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> LocalCommitReceipt:
    """Issue the evidence-bound local layer after all central gates are stable."""

    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("local commit receipt requires governance authority")
    current = require_commit_step(current_step, "local receipt current_step")
    leaves = _stable_commit_leaves(
        context,
        assessment,
        window_state,
        commit_policy=commit_policy,
        risk_chain_state=risk_chain_state,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold_snapshot,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        replay_state=replay_state,
        support_replay_state=support_replay_state,
        output_fingerprint=output_payload_fingerprint,
        current_step=current,
    )
    receipt = LocalCommitReceipt(
        schema_discriminator=LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
        receipt_version=LOCAL_COMMIT_RECEIPT_VERSION,
        wire_version=commit_policy.certificate.wire_version,
        canonicalization=commit_policy.certificate.canonicalization,
        hash_algorithm=commit_policy.certificate.hash_algorithm,
        receipt_id=require_commit_text(receipt_id, "local receipt receipt_id"),
        authority_scope=AuthorityScope.GOVERNANCE_LOCAL,
        issuer_id=require_commit_text(issuer_id, "local receipt issuer_id"),
        authority=authority,
        issued_at_step=current,
        provenance=require_commit_text(provenance, "local receipt provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "local receipt trace_event_id",
        ),
        **leaves,
    )
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    registered = _register_local_receipt(receipt, receipt_ref=receipt_ref)
    _seal_commit_window_from_local_receipt(window_state, registered)
    return registered

def local_commit_receipt_matches(
    receipt: LocalCommitReceipt | None,
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    current_step: int,
    expected_output_payload_fingerprint: str = "",
) -> bool:
    """Rebuild every central-commit leaf against the current authority heads."""

    try:
        if not local_commit_receipt_is_authoritative(receipt) or receipt is None:
            return False
        if expected_output_payload_fingerprint and (
            receipt.output_payload_fingerprint
            != require_commit_fingerprint(
                expected_output_payload_fingerprint,
                "expected local receipt output payload fingerprint",
            )
        ):
            return False
        expected = _stable_commit_leaves(
            context,
            assessment,
            window_state,
            commit_policy=commit_policy,
            risk_chain_state=risk_chain_state,
            risk_assessment=risk_assessment,
            threshold_snapshot=threshold_snapshot,
            membership_snapshot=membership_snapshot,
            membership_epoch_state=membership_epoch_state,
            replay_state=replay_state,
            support_replay_state=support_replay_state,
            output_fingerprint=receipt.output_payload_fingerprint,
            current_step=current_step,
        )
        return all(getattr(receipt, name) == value for name, value in expected.items())
    except (GovernanceError, TypeError, ValueError):
        return False

def verify_local_commit_finality(
    receipt: LocalCommitReceipt,
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    current_step: int,
    verifier_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitFinalityVerification:
    """Convert a verified local receipt into the liveness typed-finality ABI."""

    if receipt.assurance is not CommitAssurance.EVIDENCE_BOUND:
        raise GovernanceError(
            "local receipt finality is reserved for evidence-bound assurance"
        )
    if current_step != receipt.issued_at_step:
        raise GovernanceError(
            "evidence-bound local finality must be verified at the receipt step"
        )
    if not commit_window_seal_matches_receipt(window_state, receipt):
        raise GovernanceError(
            "evidence-bound local finality requires the current receipt seal"
        )
    if not local_commit_receipt_matches(
        receipt,
        context,
        assessment,
        window_state,
        commit_policy=commit_policy,
        risk_chain_state=risk_chain_state,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold_snapshot,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        replay_state=replay_state,
        support_replay_state=support_replay_state,
        current_step=current_step,
    ):
        raise GovernanceError("local receipt does not verify against current heads")
    return _issue_typed_finality_verification(
        receipt,
        certificate_kind=LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
        certificate_ref=local_commit_receipt_fingerprint(receipt),
        current_step=current_step,
        verifier_id=verifier_id,
        authority=authority,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )

def _stable_commit_leaves(
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    output_fingerprint: str,
    current_step: int,
) -> dict[str, object]:
    if not commit_evaluation_context_is_authoritative(context):
        raise GovernanceError("local receipt requires authoritative context")
    if not commit_assessment_is_authoritative(assessment):
        raise GovernanceError("local receipt requires authoritative assessment")
    if not commit_window_state_is_authoritative(window_state):
        raise GovernanceError("local receipt requires authoritative window state")
    if not commit_window_state_is_current(window_state):
        raise GovernanceError("local receipt requires the current window head")
    if not commit_window_ready(window_state):
        raise GovernanceError("local receipt requires a stable ready window")
    _validate_policy_binding(
        commit_policy,
        profile=context.profile,
        assurance=context.assurance,
        target=context.target,
        commit_policy_root=context.commit_policy_root,
    )
    if context.assurance is CommitAssurance.ADVISORY:
        raise GovernanceError("advisory assurance cannot issue a local commit receipt")
    if not commit_threshold_snapshot_matches(
        threshold_snapshot,
        assessment=risk_assessment,
        chain_state=risk_chain_state,
        commit_policy=commit_policy,
        current_step=current_step,
    ):
        raise GovernanceError(
            "local receipt risk assessment or threshold head is stale"
        )
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=context.target,
        epoch=context.epoch,
        current_step=current_step,
    ):
        raise GovernanceError("local receipt membership head is stale")
    if not commit_replay_state_matches(
        replay_state,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        current_step=current_step,
    ):
        raise GovernanceError("local receipt commit replay head is stale")
    if not (
        type(support_replay_state) is SupportLeaseReplayState
        and support_lease_replay_state_is_current(support_replay_state)
        and support_replay_state.profile == context.profile
        and support_replay_state.protocol_id == context.protocol_id
        and support_replay_state.last_issued_at_step <= current_step
    ):
        raise GovernanceError("local receipt support replay head is stale")
    current_head_fingerprints = {
        "risk_chain_state_fingerprint": risk_assessment_chain_state_fingerprint(
            risk_chain_state
        ),
        "risk_assessment_fingerprint": risk_assessment_fingerprint(
            risk_assessment
        ),
        "threshold_fingerprint": commit_threshold_snapshot_fingerprint(
            threshold_snapshot
        ),
        "membership_snapshot_fingerprint": eligible_principal_snapshot_fingerprint(
            membership_snapshot
        ),
        "membership_epoch_state_fingerprint": (
            eligible_membership_epoch_state_fingerprint(membership_epoch_state)
        ),
        "replay_state_fingerprint": commit_replay_state_fingerprint(
            replay_state
        ),
        "support_replay_state_fingerprint": (
            support_lease_replay_state_fingerprint(support_replay_state)
        ),
    }
    for name, observed in current_head_fingerprints.items():
        if getattr(context, name) != observed or getattr(assessment, name) != observed:
            raise GovernanceError(f"local receipt current {name} lineage mismatch")
    if (
        context.replay_receipt_root != replay_state.receipt_root
        or assessment.replay_receipt_root != replay_state.receipt_root
        or context.support_replay_root != support_replay_state.replay_root
        or assessment.support_replay_root != support_replay_state.replay_root
    ):
        raise GovernanceError("local receipt current replay roots mismatch")
    common = (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    )
    for name in common:
        expected = getattr(context, name)
        if getattr(assessment, name) != expected or getattr(window_state, name) != expected:
            raise GovernanceError(f"local receipt {name} lineage mismatch")
    for window_name, assessment_name in (
        ("risk_chain_state_root", "risk_chain_state_fingerprint"),
        ("risk_assessment_root", "risk_assessment_fingerprint"),
        ("risk_policy_root", "risk_policy_root"),
        ("membership_snapshot_root", "membership_snapshot_fingerprint"),
        ("membership_epoch_state_root", "membership_epoch_state_fingerprint"),
        ("membership_root", "membership_root"),
        ("threshold_root", "threshold_fingerprint"),
        ("support_replay_state_root", "support_replay_state_fingerprint"),
        ("support_replay_root", "support_replay_root"),
        ("collective_evidence_root", "collective_evidence_root"),
        ("collective_challenge_root", "collective_challenge_root"),
        ("collective_lease_root", "collective_lease_root"),
        ("stop_resolution_root", "stop_resolution_fingerprint"),
        ("permission_root", "permission_fingerprint"),
    ):
        if getattr(window_state, window_name) != getattr(
            assessment,
            assessment_name,
        ):
            raise GovernanceError(
                f"local receipt window {window_name} lineage mismatch"
            )
    context_ref = commit_evaluation_context_fingerprint(context)
    assessment_ref = commit_assessment_fingerprint(assessment)
    if assessment.context_fingerprint != context_ref:
        raise GovernanceError("local receipt assessment/context lineage mismatch")
    if assessment.status is not CommitAssessmentStatus.READY:
        raise GovernanceError("local receipt assessment is not READY")
    if not (
        assessment.unique_leader
        and assessment.leader_ready_for_stability
        and assessment.leader_candidate_id
    ):
        raise GovernanceError("local receipt has no declared ready leader")
    if (
        assessment.blocker_references
        or assessment.equivocation_finding_ids
        or assessment.replay_conflict_references
    ):
        raise GovernanceError("local receipt cannot contain a safety finding")
    if (
        window_state.last_assessment_ref != assessment_ref
        or window_state.last_context_ref != context_ref
        or window_state.leader_candidate_id != assessment.leader_candidate_id
        or window_state.last_assessment_status != CommitAssessmentStatus.READY.value
        or window_state.last_evaluated_step != current_step
    ):
        raise GovernanceError("local receipt does not bind the stable window head")
    claim = next(
        (
            item
            for item in context.candidate_claims
            if item.candidate_id == assessment.leader_candidate_id
        ),
        None,
    )
    if claim is None or claim.safe_fallback:
        raise GovernanceError("local receipt leader is not a substantive declaration")
    metrics = next(
        (
            item
            for item in assessment.candidate_metrics
            if item.candidate_id == assessment.leader_candidate_id
        ),
        None,
    )
    if (
        metrics is None
        or not metrics.ready_for_stability
        or metrics.claim_fingerprint != claim.claim_fingerprint
    ):
        raise GovernanceError("local receipt leader metrics are not commit-ready")
    if (
        window_state.candidate_evidence_root != metrics.evidence_root
        or window_state.candidate_challenge_root != metrics.challenge_root
        or window_state.candidate_lease_root != metrics.lease_root
    ):
        raise GovernanceError("local receipt leader metric roots mismatch")
    output_ref = require_commit_fingerprint(
        output_fingerprint,
        "local receipt output_payload_fingerprint",
    )
    return {
        "profile": context.profile,
        "assurance": context.assurance,
        "manifest_root": context.manifest_root,
        "commit_policy_root": context.commit_policy_root,
        "protocol_id": context.protocol_id,
        "run_id": context.run_id,
        "target": context.target,
        "epoch": context.epoch,
        "candidate_id": assessment.leader_candidate_id,
        "claim_fingerprint": claim.claim_fingerprint,
        "output_payload_fingerprint": output_ref,
        "risk_chain_state_root": assessment.risk_chain_state_fingerprint,
        "risk_assessment_root": assessment.risk_assessment_fingerprint,
        "risk_policy_root": assessment.risk_policy_root,
        "membership_snapshot_root": assessment.membership_snapshot_fingerprint,
        "membership_epoch_state_root": assessment.membership_epoch_state_fingerprint,
        "membership_root": assessment.membership_root,
        "threshold_root": assessment.threshold_fingerprint,
        "replay_state_root": assessment.replay_state_fingerprint,
        "replay_root": assessment.replay_receipt_root,
        "support_replay_state_root": assessment.support_replay_state_fingerprint,
        "support_replay_root": assessment.support_replay_root,
        "candidate_evidence_root": metrics.evidence_root,
        "candidate_challenge_root": metrics.challenge_root,
        "candidate_lease_root": metrics.lease_root,
        "evidence_root": assessment.collective_evidence_root,
        "challenge_root": assessment.collective_challenge_root,
        "lease_root": assessment.collective_lease_root,
        "window_state_root": commit_window_state_fingerprint(window_state),
        "window_root": window_state.window_root,
        "stop_resolution_root": assessment.stop_resolution_fingerprint,
        "permission_root": assessment.permission_fingerprint,
        "context_root": context_ref,
        "assessment_root": assessment_ref,
    }

def _current_authority_heads_match_receipt(
    receipt: LocalCommitReceipt,
    *,
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    commit_policy: CollectiveCommitPolicy,
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    current_step: int,
) -> bool:
    """Recheck mutable heads while preserving the sealed commit proof."""

    try:
        current = require_commit_step(current_step, "portable finality current_step")
        if current < receipt.issued_at_step:
            return False
        if not (
            commit_evaluation_context_is_authoritative(context)
            and commit_assessment_is_authoritative(assessment)
            and commit_window_state_is_authoritative(window_state)
        ):
            return False
        if not commit_threshold_snapshot_matches(
            threshold_snapshot,
            assessment=risk_assessment,
            chain_state=risk_chain_state,
            commit_policy=commit_policy,
            current_step=current,
        ):
            return False
        if not eligible_principal_snapshot_matches(
            membership_snapshot,
            epoch_state=membership_epoch_state,
            profile=receipt.profile,
            assurance=receipt.assurance,
            manifest_root=receipt.manifest_root,
            commit_policy_root=receipt.commit_policy_root,
            protocol_id=receipt.protocol_id,
            run_id=receipt.run_id,
            target=receipt.target,
            epoch=receipt.epoch,
            current_step=current,
        ):
            return False
        if not commit_replay_state_matches(
            replay_state,
            profile=receipt.profile,
            assurance=receipt.assurance,
            manifest_root=receipt.manifest_root,
            commit_policy_root=receipt.commit_policy_root,
            protocol_id=receipt.protocol_id,
            run_id=receipt.run_id,
            current_step=current,
        ):
            return False
        if not (
            support_lease_replay_state_is_current(support_replay_state)
            and support_replay_state.profile == receipt.profile
            and support_replay_state.protocol_id == receipt.protocol_id
            and support_replay_state.last_issued_at_step <= current
            and commit_window_state_is_current(window_state)
            and commit_window_state_fingerprint(window_state)
            == receipt.window_state_root
            and window_state.window_root == receipt.window_root
            and window_state.leader_candidate_id == receipt.candidate_id
            and window_state.last_assessment_ref == receipt.assessment_root
            and commit_evaluation_context_fingerprint(context)
            == receipt.context_root
            and commit_assessment_fingerprint(assessment)
            == receipt.assessment_root
        ):
            return False
        current_roots = {
            "risk_chain_state_root": risk_assessment_chain_state_fingerprint(
                risk_chain_state
            ),
            "risk_assessment_root": risk_assessment_fingerprint(risk_assessment),
            "threshold_root": commit_threshold_snapshot_fingerprint(
                threshold_snapshot
            ),
            "membership_snapshot_root": eligible_principal_snapshot_fingerprint(
                membership_snapshot
            ),
            "membership_epoch_state_root": (
                eligible_membership_epoch_state_fingerprint(
                    membership_epoch_state
                )
            ),
            "membership_root": membership_snapshot.membership_root,
            "replay_state_root": commit_replay_state_fingerprint(replay_state),
            "replay_root": replay_state.receipt_root,
            "support_replay_state_root": (
                support_lease_replay_state_fingerprint(support_replay_state)
            ),
            "support_replay_root": support_replay_state.replay_root,
        }
        return all(
            getattr(receipt, name) == value for name, value in current_roots.items()
        )
    except (AttributeError, GovernanceError, TypeError, ValueError):
        return False


__all__ = [
    "LocalCommitReceipt",
    "issue_local_commit_receipt",
    "local_commit_receipt_fingerprint",
    "local_commit_receipt_is_authoritative",
    "local_commit_receipt_matches",
    "local_commit_receipt_payload",
    "verify_local_commit_finality",
]
