"""Public-Governance fixtures for the durable Commit Decision v2 matrix."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from pheroos.conformance.checks._commit_evidence_v2_context_support import (
    CommitEvidenceV2ConformanceContext,
    advance_v2 as advance_evidence_v2,
    attestations_v2,
    commit_replay_v2,
    context_v2_for_evidence,
    request_v2 as evidence_request_v2,
    root_v2,
)
from pheroos.conformance.checks._support_v2_context_support import (
    SupportV2ConformanceContext,
    advance_support_v2,
    capability_v2,
    initialize_v2 as initialize_support_v2,
    issue_v2 as issue_support_v2,
    support_state_v2,
)
from pheroos.conformance.checks._support_v2_manifest_support import (
    PROFILE,
    RUN_REF,
    TARGET_REF,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
)
from pheroos.governance.commit_evidence_v2 import (
    VerifiedCommitEvidenceStateV2,
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
from pheroos.governance.commit_state_v2 import VerifiedCommitReplayStateV2
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
    VerifiedMembershipStateV2,
    VerifiedPrincipalVerificationSetStateV2,
    VerifiedSupportStateV2,
    prepare_support_issue_v2,
)
from pheroos.protocol import (
    CollectiveCommitPolicy,
    CommitAssurance,
    ScopedProtocolManifestV2,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint


CANDIDATE_REF = "candidate:support-v2:accept"
GATE_STEP = 6


@dataclass(frozen=True, slots=True)
class CommitDecisionV2ReadyContext:
    evidence_context: CommitEvidenceV2ConformanceContext
    gate_grant: GovernanceIssuerGrantV2
    replay_state: VerifiedCommitReplayStateV2
    risk_state: VerifiedRiskStateV2
    membership_state: VerifiedMembershipStateV2
    verification_state: VerifiedPrincipalVerificationSetStateV2
    support_state: VerifiedSupportStateV2
    evidence_state: VerifiedCommitEvidenceStateV2
    stop_state: VerifiedCommitStopStateV2
    permission_state: VerifiedCommitPermissionStateV2
    claim_root: str

    @property
    def support_context(self) -> SupportV2ConformanceContext:
        return self.evidence_context.support

    @property
    def manifest(self) -> ScopedProtocolManifestV2:
        return self.support_context.manifest

    @property
    def profile(self) -> str:
        return self.support_context.profile

    @property
    def assurance(self) -> CommitAssurance:
        return self.support_context.assurance


def ready_context_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
    *,
    scope_ref: str | None = None,
    profile: str = PROFILE,
    assurance: CommitAssurance = CommitAssurance.EVIDENCE_BOUND,
    grant_action_refs: tuple[str, ...] = (),
    attestation_expires_at_step: int = 10,
    gate_expires_at_step: int = GATE_STEP + 10,
    manifest_transform: Callable[[ScopedProtocolManifestV2], ScopedProtocolManifestV2]
    | None = None,
) -> CommitDecisionV2ReadyContext:
    evidence_context = context_v2_for_evidence(
        adapter,
        f"commit-decision:{label}",
        scope_ref=scope_ref,
        profile=profile,
        assurance=assurance,
        grant_action_refs=grant_action_refs,
        manifest_transform=manifest_transform,
    )
    support = evidence_context.support
    claim_root = root_v2(f"claim:commit-decision:{label}")
    attestations = attestations_v2(
        label,
        claim_root=claim_root,
        expires_at_step=attestation_expires_at_step,
    )
    _replay_request, replay = commit_replay_v2(
        evidence_context,
        attestations,
        advance_ref=f"advance:commit-decision:replay:{label}",
    )
    evidence_request, evidence_source = evidence_request_v2(
        evidence_context,
        replay,
        attestations,
        advance_ref=f"advance:commit-decision:evidence:{label}",
    )
    _require_committed(
        advance_evidence_v2(evidence_context, evidence_request, evidence_source),
        "Evidence",
    )
    evidence = rehydrate_commit_evidence_state_v2(
        evidence_request.to_dict(),
        domain=support.domain,
        state_reader=support.store,
    )
    risk = _risk_v2(support, label)
    support_state = _two_cluster_support_v2(
        support,
        evidence_context.upstreams.membership_state,
        label,
        claim_root=claim_root,
    )
    gate_grant = _activate_gate_grant_v2(support, label)
    stop, permission = _gate_states_v2(
        support,
        gate_grant,
        replay=replay,
        risk=risk,
        membership=evidence_context.upstreams.membership_state,
        support_state=support_state,
        claim_root=claim_root,
        label=label,
        expires_at_step=gate_expires_at_step,
    )
    return CommitDecisionV2ReadyContext(
        evidence_context=evidence_context,
        gate_grant=gate_grant,
        replay_state=replay,
        risk_state=risk,
        membership_state=evidence_context.upstreams.membership_state,
        verification_state=evidence_context.upstreams.verification_state,
        support_state=support_state,
        evidence_state=evidence,
        stop_state=stop,
        permission_state=permission,
        claim_root=claim_root,
    )


def decision_capability_v2(
    context: CommitDecisionV2ReadyContext,
    observed_epoch: int,
) -> GovernanceIssuerCapabilityV2:
    support = context.support_context
    return capability_v2(support, observed_epoch)


def _risk_v2(
    context: SupportV2ConformanceContext,
    label: str,
) -> VerifiedRiskStateV2:
    request, source = prepare_risk_state_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=context.profile,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=1,
        advance_ref=f"advance:commit-decision:risk:{label}",
        current_step=4,
        assessment_ref=f"assessment:commit-decision:{label}",
        risk_band=RiskBand.LOW,
        risk_input_roots=(root_v2(f"risk-input:commit-decision:{label}"),),
        rationale_codes=("risk:low",),
        assessment_method="deterministic-conformance-v2",
        issuer_ref=context.grant.issuer_ref,
        issued_at_step=4,
        expires_at_step=90_000,
        provenance_ref=f"urn:pheroos:conformance:commit-decision:risk:{label}",
        source_trace_roots=(root_v2(f"risk-trace:{label}"),),
    )
    session = open_risk_authority_session_v2(
        capability_v2(context, request.observed_epoch),
        request,
    )
    _require_committed(
        advance_risk_state_v2(
            request,
            source=source,
            authority_session=session,
        ),
        "Risk",
    )
    return rehydrate_risk_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )


def _two_cluster_support_v2(
    context: SupportV2ConformanceContext,
    membership: VerifiedMembershipStateV2,
    label: str,
    *,
    claim_root: str,
) -> VerifiedSupportStateV2:
    initialize, initialize_source = initialize_support_v2(context, label)
    _require_committed(
        advance_support_v2(context, initialize, initialize_source),
        "Support initialize",
    )
    state = support_state_v2(context, initialize)
    alpha, alpha_source = issue_support_v2(
        context,
        state,
        membership,
        f"commit-decision-alpha:{label}",
        current_step=5,
        candidate_ref=CANDIDATE_REF,
        claim_root=claim_root,
    )
    _require_committed(
        advance_support_v2(context, alpha, alpha_source),
        "Support alpha",
    )
    state = support_state_v2(context, alpha)
    observation = _beta_observation_v2(
        context,
        membership,
        label,
        claim_root=claim_root,
    )
    proposal = _beta_proposal_v2(
        context,
        membership,
        observation,
        label,
        claim_root=claim_root,
    )
    beta, beta_source = prepare_support_issue_v2(
        manifest=context.manifest,
        parent_state=state,
        membership_state=membership,
        proposal=proposal,
        positive_observations=(observation,),
        issuer_ref=context.grant.issuer_ref,
        observed_epoch=36,
        mutation_ref=f"mutation:support:commit-decision-beta:{label}",
        current_step=6,
        issuance_provenance_root=root_v2(f"support-beta-provenance:{label}"),
        issuance_trace_roots=(root_v2(f"support-beta-trace:{label}"),),
    )
    _require_committed(
        advance_support_v2(context, beta, beta_source),
        "Support beta",
    )
    return support_state_v2(context, beta)


def _beta_observation_v2(
    context: SupportV2ConformanceContext,
    membership_state: VerifiedMembershipStateV2,
    label: str,
    *,
    claim_root: str,
) -> SupportObservationV2:
    membership = membership_state.snapshot
    return SupportObservationV2(
        observation_ref=f"observation:commit-decision-beta:{label}",
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(
            cast(
                CollectiveCommitPolicy,
                context.manifest.collective_commit_policy,
            ),
            profile=context.profile,
        ),
        protocol_ref=context.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        candidate_ref=CANDIDATE_REF,
        claim_root=claim_root,
        epoch=membership.epoch,
        source_ref=f"source:commit-decision-beta:{label}",
        evidence_root=root_v2(f"support-beta-evidence:{label}"),
        observed_at_step=6,
        expires_at_step=min(membership.expires_at_step, 1_006),
        provenance_root=root_v2(f"support-beta-observation:{label}"),
        source_trace_roots=(root_v2(f"support-beta-observation-trace:{label}"),),
    )


def _beta_proposal_v2(
    context: SupportV2ConformanceContext,
    membership_state: VerifiedMembershipStateV2,
    observation: SupportObservationV2,
    label: str,
    *,
    claim_root: str,
) -> SupportLeaseProposalV2:
    membership = membership_state.snapshot
    return SupportLeaseProposalV2(
        proposal_ref=f"proposal:commit-decision-beta:{label}",
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(
            cast(
                CollectiveCommitPolicy,
                context.manifest.collective_commit_policy,
            ),
            profile=context.profile,
        ),
        protocol_ref=context.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        candidate_ref=CANDIDATE_REF,
        claim_root=claim_root,
        epoch=membership.epoch,
        principal_ref="principal:beta",
        positive_observation_roots=(observation.observation_root,),
        nonce=f"nonce:commit-decision-beta:{label}",
        proposed_at_step=6,
        provenance_root=root_v2(f"support-beta-proposal:{label}"),
        source_trace_roots=(root_v2(f"support-beta-proposal-trace:{label}"),),
    )


def _activate_gate_grant_v2(
    context: SupportV2ConformanceContext,
    label: str,
) -> GovernanceIssuerGrantV2:
    grant = GovernanceIssuerGrantV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        issuer_ref="issuer:commit-decision:gate",
        grant_ref=f"grant:commit-decision:gate:{label}",
        grant_binding_ref=root_v2(f"grant-binding:commit-decision:gate:{label}"),
        operations=(
            GovernanceIssuerOperationV2.RESOLVE_STOP,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
        ),
        target_refs=(TARGET_REF,),
        action_refs=("commit",),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100_000,
        revocation_generation=0,
    )
    _require_committed(
        activate_governance_issuer_grant_v2(
            context.store,
            context.domain,
            grant,
            f"transition:commit-decision:gate-grant:{label}",
            1,
        ),
        "Gate grant",
    )
    return grant


def _gate_states_v2(
    context: SupportV2ConformanceContext,
    grant: GovernanceIssuerGrantV2,
    *,
    replay: VerifiedCommitReplayStateV2,
    risk: VerifiedRiskStateV2,
    membership: VerifiedMembershipStateV2,
    support_state: VerifiedSupportStateV2,
    claim_root: str,
    label: str,
    expires_at_step: int,
) -> tuple[VerifiedCommitStopStateV2, VerifiedCommitPermissionStateV2]:
    stop_request, stop_source = prepare_commit_stop_resolution_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=context.profile,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=50,
        resolution_ref=f"resolution:commit-decision:{label}",
        current_step=GATE_STEP,
        mutation_issuer_ref=grant.issuer_ref,
        blocked=False,
        reason_codes=("stop:clear",),
        issued_at_step=GATE_STEP,
        expires_at_step=expires_at_step,
        commit_replay_state=replay,
        risk_state=risk,
        membership_state=membership,
        support_state=support_state,
    )
    stop_session = open_commit_stop_authority_session_v2(
        _gate_capability_v2(context, grant, stop_request.observed_epoch),
        stop_request,
    )
    _require_committed(
        resolve_commit_stop_v2(
            stop_request,
            source=stop_source,
            authority_session=stop_session,
        ),
        "Commit Stop",
    )
    stop = rehydrate_commit_stop_state_v2(
        stop_request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    permission_request, permission_source = prepare_commit_permission_issue_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=context.profile,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=50,
        permission_ref=f"permission:commit-decision:{label}",
        current_step=GATE_STEP,
        mutation_issuer_ref=grant.issuer_ref,
        allowed=True,
        claim_roots=(claim_root,),
        issued_at_step=GATE_STEP,
        expires_at_step=expires_at_step,
        commit_replay_state=replay,
        risk_state=risk,
        membership_state=membership,
        support_state=support_state,
    )
    permission_session = open_commit_permission_authority_session_v2(
        _gate_capability_v2(context, grant, permission_request.observed_epoch),
        permission_request,
    )
    _require_committed(
        issue_commit_permission_v2(
            permission_request,
            source=permission_source,
            authority_session=permission_session,
        ),
        "Commit Permission",
    )
    permission = rehydrate_commit_permission_state_v2(
        permission_request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    return stop, permission


def _gate_capability_v2(
    context: SupportV2ConformanceContext,
    grant: GovernanceIssuerGrantV2,
    observed_epoch: int,
) -> GovernanceIssuerCapabilityV2:
    return bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        grant,
        RUN_REF,
        observed_epoch,
    )


def _require_committed(
    attempt: GovernanceCommitAttemptV2,
    label: str,
) -> None:
    if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        detail = "" if attempt.failure is None else str(attempt.failure.to_dict())
        raise RuntimeError(f"Commit Decision v2 {label} setup failed: {detail}")


__all__: tuple[str, ...] = ()
