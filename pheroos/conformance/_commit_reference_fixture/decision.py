"""Private Commit reference fixture decision handlers."""

from __future__ import annotations

from collections.abc import Sequence

from typing import cast

from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.commit import (
    CandidateCommitInput,
    CommitAssessment,
    CommitEvaluationContext,
    assess_optimal_commit,
    build_commit_replay_receipts,
    commit_evaluation_context_fingerprint,
)

from pheroos.governance.commit_state import (
    CommitReplayState,
    commit_replay_state_fingerprint,
)

from pheroos.governance.evidence_binding import (
    evidence_binding_fingerprint,
)

from pheroos.governance.observation import (
    VerifiedObservation,
    verified_observation_fingerprint,
)

from pheroos.governance.permission import (
    ActionPermission,
    action_permission_fingerprint,
    issue_action_permission,
)

from pheroos.governance.principal import (
    PrincipalVerification,
)

from pheroos.governance.stop_signal import (
    StopResolution,
    StopResolutionVerification,
    stop_resolution_verification_fingerprint,
    verify_stop_resolution,
)

from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLease,
    SupportLeaseProposal,
    SupportLeaseReplayState,
    SupportLeaseRevocation,
    issue_support_lease,
    support_lease_replay_state_fingerprint,
)

from pheroos.protocol.commit_models import CommitAction, CommitAssurance

from pheroos.conformance._commit_reference_fixture.models import (
    ReferenceScenario,
    reference_fingerprint,
)

from pheroos.conformance._commit_reference_fixture.state import (
    _REFERENCE_ASSESSMENT_FIXTURES,
    _REFERENCE_ASSESSMENT_FIXTURES_LOCK,
)


def issue_reference_lease(
    namespace: str,
    *,
    index: int,
    principal: PrincipalVerification,
    observation: VerifiedObservation,
    candidate_id: str,
    claim_fingerprint: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    policy: object,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_state: EligibleMembershipEpochState,
    replay_state: SupportLeaseReplayState,
    prior_leases: Sequence[SupportLease],
    issuer_id: str | None = None,
    current_step: int = 4,
) -> tuple[SupportLease, SupportLeaseReplayState]:
    proposal = SupportLeaseProposal(
        proposal_id=f"support-proposal:{namespace}:{index}",
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        epoch=epoch,
        principal_id=principal.principal_id,
        positive_observation_fingerprints=(
            verified_observation_fingerprint(observation),
        ),
        nonce=f"nonce:lease:{namespace}:{index}",
        proposed_at_step=current_step - 1,
        provenance=f"urn:pheroos:tck:{namespace}:lease-proposal:{index}",
        trace_event_id=f"trace:{namespace}:lease-proposal:{index}",
    )
    return issue_support_lease(
        proposal,
        principal_verification=principal,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_state,
        replay_state=replay_state,
        positive_observations=(observation,),
        commit_policy=collective_commit_policy(policy),
        lease_id=f"lease:{namespace}:{index}",
        issuer_id=issuer_id or f"governance:tck:support:{namespace}",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=current_step,
        issuance_provenance=f"urn:pheroos:tck:{namespace}:lease:{index}",
        issuance_trace_event_id=f"trace:{namespace}:lease:{index}",
        prior_leases=tuple(prior_leases),
    )


def issue_reference_action_gates(
    namespace: str,
    *,
    context: CommitEvaluationContext,
    action: CommitAction,
    blocked: bool,
    current_step: int,
    expires_at_step: int,
    suffix: str,
    target: str | None = None,
) -> tuple[StopResolutionVerification, ActionPermission]:
    selected_target = target or context.target
    context_ref = commit_evaluation_context_fingerprint(context)
    certificate_ref = (
        ""
        if action is CommitAction.COMMIT
        else reference_fingerprint(
            f"action-certificate:{namespace}:{suffix}:{action.value}"
        )
    )
    stop = verify_stop_resolution(
        StopResolution(
            target=selected_target,
            action=action,
            blocked=blocked,
            reason="hard_stop" if blocked else "all_hard_stops_resolved",
        ),
        resolution_id=f"stop:{namespace}:{suffix}",
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        epoch=context.epoch,
        decision_ref=context_ref,
        certificate_ref=certificate_ref,
        resolved_stop_root=reference_fingerprint(
            f"stop-root:{namespace}:{suffix}:{blocked}"
        ),
        verifier_id="governance:tck:stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=current_step,
        expires_at_step=expires_at_step,
        provenance=f"urn:pheroos:tck:{namespace}:stop:{suffix}",
        trace_event_id=f"trace:{namespace}:stop:{suffix}",
    )
    permission = issue_action_permission(
        permission_id=f"permission:{namespace}:{suffix}",
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=selected_target,
        action=action,
        epoch=context.epoch,
        decision_ref=context_ref,
        certificate_ref=certificate_ref,
        allowed=not blocked,
        reason_codes=("denied",) if blocked else ("policy_authorized",),
        issuer_id="governance:tck:permission",
        policy_ref="policy:tck:commit-action-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=current_step,
        expires_at_step=expires_at_step,
        provenance=f"urn:pheroos:tck:{namespace}:permission:{suffix}",
        trace_event_id=f"trace:{namespace}:permission:{suffix}",
    )
    return stop, permission


def assess_reference_scenario(
    scenario: ReferenceScenario,
    *,
    step: int,
    suffix: str,
    candidate_inputs: Sequence[CandidateCommitInput] | None = None,
    leases: Sequence[SupportLease] | None = None,
    revocations: Sequence[object] = (),
    stop_resolution: StopResolutionVerification | None = None,
    permission: ActionPermission | None = None,
    context: CommitEvaluationContext | None = None,
    replay_state: CommitReplayState | None = None,
    support_replay_state: SupportLeaseReplayState | None = None,
) -> CommitAssessment:
    selected_context = context or scenario.context
    selected_replay = replay_state or scenario.replay_state
    selected_support_replay = support_replay_state or scenario.support_replay_state
    selected_inputs = tuple(candidate_inputs or scenario.candidate_inputs)
    selected_leases = tuple(leases or scenario.leases)
    selected_revocations = cast(
        tuple[SupportLeaseRevocation, ...],
        tuple(revocations),
    )
    selected_stop = stop_resolution or scenario.stop_resolution
    selected_permission = permission or scenario.permission
    receipt_coordinates = tuple(
        (
            item.namespace.value,
            item.record_id,
            item.nonce,
            item.payload_fingerprint,
            item.target,
            item.candidate_id,
            item.epoch,
            item.principal_id,
        )
        for item in build_commit_replay_receipts(
            selected_inputs,
            selected_leases,
            selected_revocations,
        )
    )
    binding_coordinates = tuple(
        sorted(
            (
                item.candidate_id,
                item.claim_fingerprint,
                evidence_binding_fingerprint(item.evidence_binding),
            )
            for item in selected_inputs
        )
    )
    fixture_key = (
        f"assessment:{scenario.namespace}:{suffix}",
        step,
        commit_evaluation_context_fingerprint(selected_context),
        commit_replay_state_fingerprint(selected_replay),
        support_lease_replay_state_fingerprint(selected_support_replay),
        receipt_coordinates,
        binding_coordinates,
        stop_resolution_verification_fingerprint(selected_stop),
        action_permission_fingerprint(selected_permission),
    )
    with _REFERENCE_ASSESSMENT_FIXTURES_LOCK:
        cached = _REFERENCE_ASSESSMENT_FIXTURES.get(fixture_key)
        if cached is not None:
            return cached
    assessment = assess_optimal_commit(
        selected_context,
        manifest=scenario.manifest,
        candidate_inputs=selected_inputs,
        leases=selected_leases,
        revocations=selected_revocations,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=selected_replay,
        support_replay_state=selected_support_replay,
        stop_resolution=selected_stop,
        commit_permission=selected_permission,
        assessment_id=f"assessment:{scenario.namespace}:{suffix}",
        issuer_id="governance:tck:commit",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:assessment:{suffix}",
        trace_event_id=f"trace:{scenario.namespace}:assessment:{suffix}",
    )
    with _REFERENCE_ASSESSMENT_FIXTURES_LOCK:
        _REFERENCE_ASSESSMENT_FIXTURES[fixture_key] = assessment
    return assessment
