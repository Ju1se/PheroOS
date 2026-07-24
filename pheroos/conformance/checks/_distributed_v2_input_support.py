"""Public-only governed inputs for Distributed Commit v2 verticals."""

from __future__ import annotations

from dataclasses import dataclass, replace

from pheroos.conformance.checks._commit_evidence_v2_context_support import (
    attestations_v2,
)
from pheroos.conformance.checks._distributed_v2_context_support import (
    ASSURANCE,
    CANDIDATE_REF,
    PROFILE,
    RUN_REF,
    TARGET_REF,
    DistributedV2Context,
    DistributedV2Identity,
    capability_v2,
)
from pheroos.conformance.checks._support_v2_manifest_support import root_v2
from pheroos.governance.authority_session_v2 import (
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import GovernanceCommitDispositionV2
from pheroos.governance.commit_evidence_v2 import (
    VerifiedCommitEvidenceStateV2,
    advance_commit_evidence_state_v2,
    commit_evidence_replay_receipts_for_proposals_v2,
    open_commit_evidence_authority_session_v2,
    prepare_commit_evidence_advance_v2,
    rehydrate_commit_evidence_state_v2,
)
from pheroos.governance.commit_gate_v2 import (
    VerifiedCommitPermissionStateV2,
    VerifiedCommitStopStateV2,
    issue_commit_permission_v2,
    open_commit_permission_authority_session_v2,
    open_commit_stop_authority_session_v2,
    prepare_commit_permission_issue_v2,
    prepare_commit_stop_resolution_v2,
    rehydrate_commit_permission_state_v2,
    rehydrate_commit_stop_state_v2,
    resolve_commit_stop_v2,
)
from pheroos.governance.commit_state_v2 import (
    VerifiedCommitReplayStateV2,
    advance_commit_replay_state_v2,
    open_commit_replay_authority_session_v2,
    prepare_commit_replay_advance_v2,
    rehydrate_commit_replay_state_v2,
)
from pheroos.governance.risk_v2 import (
    RiskBand,
    VerifiedRiskStateV2,
    advance_risk_state_v2,
    open_risk_authority_session_v2,
    prepare_risk_state_advance_v2,
    rehydrate_risk_state_v2,
)
from pheroos.governance.support_v2 import (
    SupportLeaseProposalV2,
    SupportObservationV2,
    VerifiedSupportStateV2,
    advance_support_state_v2,
    open_support_authority_session_v2,
    prepare_support_initialize_v2,
    prepare_support_issue_v2,
    rehydrate_support_state_v2,
)
from pheroos.protocol import CollectiveCommitPolicy
from pheroos.protocol.commit_wire import commit_policy_fingerprint


@dataclass(frozen=True, slots=True)
class DistributedV2DecisionInputs:
    replay: VerifiedCommitReplayStateV2
    risk: VerifiedRiskStateV2
    membership: object
    verification: object
    support: VerifiedSupportStateV2
    evidence: VerifiedCommitEvidenceStateV2
    stop: VerifiedCommitStopStateV2
    permission: VerifiedCommitPermissionStateV2


def decision_inputs_v2(
    context: DistributedV2Context,
    identity: DistributedV2Identity,
    *,
    label: str,
    claim_root: str,
) -> DistributedV2DecisionInputs:
    replay, evidence = _replay_and_evidence_v2(
        context, identity, label=label, claim_root=claim_root
    )
    support = _support_v2(
        context,
        identity,
        label=label,
        claim_root=claim_root,
    )
    risk, stop, permission = _risk_and_gates_v2(
        context,
        identity,
        replay,
        support,
        label=label,
        claim_root=claim_root,
    )
    return DistributedV2DecisionInputs(
        replay=replay,
        risk=risk,
        membership=identity.membership,
        verification=identity.verification,
        support=support,
        evidence=evidence,
        stop=stop,
        permission=permission,
    )


def _replay_and_evidence_v2(
    context: DistributedV2Context,
    identity: DistributedV2Identity,
    *,
    label: str,
    claim_root: str,
) -> tuple[VerifiedCommitReplayStateV2, VerifiedCommitEvidenceStateV2]:
    attestations = tuple(
        replace(item, expires_at_step=11, attestation_root="")
        for item in attestations_v2(
            f"distributed:{label}",
            claim_root=claim_root,
            include_second_positive=False,
        )
    )
    policy = context.manifest.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise RuntimeError("Distributed Commit v2 policy is unavailable")
    replay, replay_source = prepare_commit_replay_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest_root=context.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        profile=PROFILE,
        assurance=ASSURANCE,
        protocol_ref=context.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=1,
        advance_ref=f"advance:distributed:replay:{label}",
        current_step=3,
        receipt_additions=commit_evidence_replay_receipts_for_proposals_v2(
            attestations,
            (),
            target_ref=TARGET_REF,
        ),
    )
    replay_attempt = advance_commit_replay_state_v2(
        replay,
        source=replay_source,
        authority_session=open_commit_replay_authority_session_v2(
            bind_governance_issuer_capability_v2(
                context.store,
                context.domain,
                context.grant,
                RUN_REF,
                replay.observed_epoch,
            ),
            replay,
        ),
    )
    _require_committed(replay_attempt.disposition, "replay")
    replay_state = rehydrate_commit_replay_state_v2(
        replay.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    evidence, evidence_source = prepare_commit_evidence_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=1,
        observed_epoch=30,
        advance_ref=f"advance:distributed:evidence:{label}",
        current_step=4,
        mutation_issuer_ref=context.grant.issuer_ref,
        mutation_provenance_root=root_v2(f"distributed:evidence:mutation:{label}"),
        mutation_trace_roots=(root_v2(f"distributed:evidence:trace:{label}"),),
        principal_verification_state=identity.verification,
        membership_state=identity.membership,
        commit_replay_state=replay_state,
        attestations=attestations,
        dispositions=(),
    )
    evidence_attempt = advance_commit_evidence_state_v2(
        evidence,
        source=evidence_source,
        authority_session=open_commit_evidence_authority_session_v2(
            capability_v2(context, evidence.observed_epoch), evidence
        ),
    )
    _require_committed(evidence_attempt.disposition, "evidence")
    return replay_state, rehydrate_commit_evidence_state_v2(
        evidence.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )


def _support_v2(
    context: DistributedV2Context,
    identity: DistributedV2Identity,
    *,
    label: str,
    claim_root: str,
) -> VerifiedSupportStateV2:
    initialize, initialize_source = prepare_support_initialize_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        issuer_ref=context.grant.issuer_ref,
        observed_epoch=33,
        mutation_ref=f"mutation:distributed:support:initialize:{label}",
        current_step=3,
        provenance_root=root_v2(f"distributed:support:initialize:{label}"),
        source_trace_roots=(root_v2(f"distributed:support:trace:{label}"),),
    )
    initialize_attempt = advance_support_state_v2(
        initialize,
        source=initialize_source,
        authority_session=open_support_authority_session_v2(
            capability_v2(context, initialize.observed_epoch), initialize
        ),
    )
    _require_committed(initialize_attempt.disposition, "support initialize")
    state = rehydrate_support_state_v2(
        initialize.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    membership = identity.membership.snapshot
    policy = context.manifest.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise RuntimeError("Distributed Commit v2 policy is unavailable")
    policy_root = commit_policy_fingerprint(policy, profile=PROFILE)
    observation = SupportObservationV2(
        observation_ref=f"observation:distributed:{label}",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=context.manifest.manifest_root,
        commit_policy_root=policy_root,
        protocol_ref=context.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        candidate_ref=CANDIDATE_REF,
        claim_root=claim_root,
        epoch=membership.epoch,
        source_ref=f"source:distributed:{label}",
        evidence_root=root_v2(f"distributed:support:evidence:{label}"),
        observed_at_step=4,
        expires_at_step=1_004,
        provenance_root=root_v2(f"distributed:support:provenance:{label}"),
        source_trace_roots=(root_v2(f"distributed:support:observation:{label}"),),
    )
    proposal = SupportLeaseProposalV2(
        proposal_ref=f"proposal:distributed:support:{label}",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=context.manifest.manifest_root,
        commit_policy_root=policy_root,
        protocol_ref=context.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        candidate_ref=CANDIDATE_REF,
        claim_root=claim_root,
        epoch=membership.epoch,
        principal_ref="principal:alpha",
        positive_observation_roots=(observation.observation_root,),
        nonce=f"nonce:distributed:support:{label}",
        proposed_at_step=4,
        provenance_root=root_v2(f"distributed:support:proposal:{label}"),
        source_trace_roots=(root_v2(f"distributed:support:proposal-trace:{label}"),),
    )
    issue, issue_source = prepare_support_issue_v2(
        manifest=context.manifest,
        parent_state=state,
        membership_state=identity.membership,
        proposal=proposal,
        positive_observations=(observation,),
        issuer_ref=context.grant.issuer_ref,
        observed_epoch=34,
        mutation_ref=f"mutation:distributed:support:issue:{label}",
        current_step=4,
        issuance_provenance_root=root_v2(f"distributed:support:issue:{label}"),
        issuance_trace_roots=(root_v2(f"distributed:support:issue-trace:{label}"),),
    )
    issue_attempt = advance_support_state_v2(
        issue,
        source=issue_source,
        authority_session=open_support_authority_session_v2(
            capability_v2(context, issue.observed_epoch), issue
        ),
    )
    _require_committed(issue_attempt.disposition, "support issue")
    return rehydrate_support_state_v2(
        issue.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )


def _risk_and_gates_v2(
    context: DistributedV2Context,
    identity: DistributedV2Identity,
    replay: VerifiedCommitReplayStateV2,
    support: VerifiedSupportStateV2,
    *,
    label: str,
    claim_root: str,
) -> tuple[
    VerifiedRiskStateV2,
    VerifiedCommitStopStateV2,
    VerifiedCommitPermissionStateV2,
]:
    risk, risk_source = prepare_risk_state_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=1,
        advance_ref=f"advance:distributed:risk:{label}",
        current_step=4,
        assessment_ref=f"assessment:distributed:risk:{label}",
        risk_band=RiskBand.LOW,
        risk_input_roots=(root_v2(f"distributed:risk:input:{label}"),),
        rationale_codes=("risk:low",),
        assessment_method="deterministic-conformance-v2",
        issuer_ref=context.grant.issuer_ref,
        issued_at_step=4,
        expires_at_step=100,
        provenance_ref=f"urn:pheroos:conformance:distributed:risk:{label}",
        source_trace_roots=(root_v2(f"distributed:risk:trace:{label}"),),
    )
    risk_attempt = advance_risk_state_v2(
        risk,
        source=risk_source,
        authority_session=open_risk_authority_session_v2(
            capability_v2(context, risk.observed_epoch), risk
        ),
    )
    _require_committed(risk_attempt.disposition, "risk")
    risk_state = rehydrate_risk_state_v2(
        risk.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    stop, stop_source = prepare_commit_stop_resolution_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=50,
        resolution_ref=f"resolution:distributed:{label}",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
        blocked=False,
        reason_codes=("stop:clear",),
        issued_at_step=6,
        expires_at_step=30,
        commit_replay_state=replay,
        risk_state=risk_state,
        membership_state=identity.membership,
        support_state=support,
    )
    stop_attempt = resolve_commit_stop_v2(
        stop,
        source=stop_source,
        authority_session=open_commit_stop_authority_session_v2(
            capability_v2(context, stop.observed_epoch), stop
        ),
    )
    _require_committed(stop_attempt.disposition, "stop")
    stop_state = rehydrate_commit_stop_state_v2(
        stop.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    permission, permission_source = prepare_commit_permission_issue_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=50,
        permission_ref=f"permission:distributed:{label}",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
        allowed=True,
        claim_roots=(claim_root,),
        issued_at_step=6,
        expires_at_step=30,
        commit_replay_state=replay,
        risk_state=risk_state,
        membership_state=identity.membership,
        support_state=support,
    )
    permission_attempt = issue_commit_permission_v2(
        permission,
        source=permission_source,
        authority_session=open_commit_permission_authority_session_v2(
            capability_v2(context, permission.observed_epoch), permission
        ),
    )
    _require_committed(permission_attempt.disposition, "permission")
    return (
        risk_state,
        stop_state,
        rehydrate_commit_permission_state_v2(
            permission.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        ),
    )


def _require_committed(
    disposition: GovernanceCommitDispositionV2,
    label: str,
) -> None:
    if disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError(f"Distributed Commit v2 {label} setup failed")


__all__: tuple[str, ...] = ()
