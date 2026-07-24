"""Dedicated certified Store graph for Commit Certificate v2 tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256

from tests.governance import test_commit_evidence_v2_operations as evidence_fixture
from tests.governance import test_support_v2_operations as support_fixture

from pheroos.governance._commit_evidence_owner_v2.context import (
    commit_evidence_context_v2,
)
from pheroos.governance.authority_session_v2 import (
    activate_governance_issuer_grant_v2,
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
    PrincipalVerificationRecordV2,
    SupportLeaseProposalV2,
    SupportObservationV2,
    VerifiedMembershipStateV2,
    VerifiedPrincipalVerificationSetStateV2,
    VerifiedSupportStateV2,
    advance_principal_verification_set_v2,
    advance_support_state_v2,
    commit_membership_epoch_v2,
    open_membership_authority_session_v2,
    open_principal_verification_authority_session_v2,
    open_support_authority_session_v2,
    prepare_membership_commit_v2,
    prepare_principal_verification_set_v2,
    prepare_support_initialize_v2,
    prepare_support_issue_v2,
    rehydrate_membership_state_v2,
    rehydrate_principal_verification_set_state_v2,
    rehydrate_support_state_v2,
)
from pheroos.protocol.commit_models import (
    CERTIFIED_COMMIT_PROFILE_VERSION,
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    CertificatePolicy,
    CommitAssurance,
    CollectiveCommitPolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint


PROFILE = CERTIFIED_COMMIT_PROFILE_VERSION
ASSURANCE = CommitAssurance.CERTIFIED
RUN_REF = support_fixture.RUN_REF
TARGET = support_fixture.TARGET


@dataclass(frozen=True, slots=True)
class CertifiedDecisionInputs:
    replay: VerifiedCommitReplayStateV2
    risk: VerifiedRiskStateV2
    membership: VerifiedMembershipStateV2
    verification: VerifiedPrincipalVerificationSetStateV2
    support: VerifiedSupportStateV2
    evidence: VerifiedCommitEvidenceStateV2
    stop: VerifiedCommitStopStateV2
    permission: VerifiedCommitPermissionStateV2


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def certified_context(scope_ref: str):
    from tests.governance import test_commit_decision_v2_operations as fixture

    context = fixture._decision_context(scope_ref)
    policy = context.manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    bands = {
        name: replace(band, minimum_assurance=ASSURANCE.value)
        for name, band in policy.risk_bands.items()
    }
    policy = replace(
        policy,
        assurance=ASSURANCE.value,
        risk_bands=bands,
        certificate=CertificatePolicy(
            mode="portable",
            wire_version=COMMIT_WIRE_VERSION,
            canonicalization=COMMIT_CANONICAL_VERSION,
            hash_algorithm="sha256",
            issuer_attestation_required=True,
            independent_verification_required=True,
        ),
    )
    return replace(
        context,
        manifest=replace(context.manifest, collective_commit_policy=policy),
    )


def _capability(context, epoch: int):
    return bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        context.grant,
        RUN_REF,
        epoch,
    )


def _commit_identity_inputs(
    context,
    *,
    profile: str = PROFILE,
    assurance: CommitAssurance = ASSURANCE,
):
    record = PrincipalVerificationRecordV2(
        principal_ref="principal:alpha",
        cluster_ref="cluster:alpha",
        failure_domain_ref="failure-domain:alpha",
        verification_method="external-attestation-v2",
        verification_issuer_ref="identity:verifier",
        attestation_root=_root("certificate:verification:attestation"),
        evidence_roots=(_root("certificate:verification:evidence"),),
        issued_at_step=1,
        expires_at_step=90_000,
        provenance_ref="urn:test:certificate:verification",
        source_trace_roots=(_root("certificate:verification:trace"),),
    )
    verification, source = prepare_principal_verification_set_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=profile,
        assurance=assurance,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=1,
        observed_epoch=11,
        advance_ref="advance:certificate:verification",
        snapshot_ref="snapshot:certificate:verification",
        current_step=1,
        expires_at_step=90_000,
        mutation_issuer_ref=context.grant.issuer_ref,
        records=(record,),
        parent_snapshot=None,
    )
    attempt = advance_principal_verification_set_v2(
        verification,
        source=source,
        authority_session=open_principal_verification_authority_session_v2(
            _capability(context, verification.observed_epoch), verification
        ),
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    verification_state = rehydrate_principal_verification_set_state_v2(
        verification,
        domain=context.domain,
        state_reader=context.store,
    )
    membership, membership_source = prepare_membership_commit_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=profile,
        assurance=assurance,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=1,
        observed_epoch=21,
        request_ref="request:certificate:membership",
        snapshot_ref="snapshot:certificate:membership",
        current_step=2,
        expires_at_step=80_000,
        mutation_issuer_ref=context.grant.issuer_ref,
        membership_method="store-current-verification-set-v2",
        provenance_ref="urn:test:certificate:membership",
        source_trace_roots=(_root("certificate:membership:trace"),),
        verification_state=verification_state,
        parent_snapshot=None,
    )
    membership_attempt = commit_membership_epoch_v2(
        membership,
        source=membership_source,
        authority_session=open_membership_authority_session_v2(
            _capability(context, membership.observed_epoch), membership
        ),
    )
    assert membership_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    membership_state = rehydrate_membership_state_v2(
        membership,
        domain=context.domain,
        state_reader=context.store,
    )
    return verification_state, membership_state


def _commit_replay_and_evidence(
    context,
    verification,
    membership,
    claim_root: str,
    *,
    profile: str = PROFILE,
    assurance: CommitAssurance = ASSURANCE,
):
    attestations = evidence_fixture._attestations(claim_root=claim_root)
    policy = commit_evidence_context_v2(
        context.manifest,
        profile=profile,
        target_ref=TARGET,
    )
    replay_grant = evidence_fixture._replay_grant(context)
    activated = activate_governance_issuer_grant_v2(
        context.store,
        context.domain,
        replay_grant,
        "transition:certificate:replay-grant",
        1,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    receipts = commit_evidence_replay_receipts_for_proposals_v2(
        attestations,
        (),
        target_ref=TARGET,
    )
    replay, replay_source = prepare_commit_replay_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest_root=policy.manifest_root,
        commit_policy_root=policy.commit_policy_root,
        profile=profile,
        assurance=assurance,
        protocol_ref=policy.protocol_ref,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        advance_ref="advance:certificate:replay",
        current_step=3,
        receipt_additions=receipts,
    )
    replay_capability = bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        replay_grant,
        RUN_REF,
        1,
    )
    replay_attempt = advance_commit_replay_state_v2(
        replay,
        source=replay_source,
        authority_session=open_commit_replay_authority_session_v2(
            replay_capability, replay
        ),
    )
    assert replay_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    replay_state = rehydrate_commit_replay_state_v2(
        replay,
        domain=context.domain,
        state_reader=context.store,
    )
    evidence, evidence_source = prepare_commit_evidence_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=profile,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=1,
        observed_epoch=30,
        advance_ref="advance:certificate:evidence",
        current_step=4,
        mutation_issuer_ref=context.grant.issuer_ref,
        mutation_provenance_root=_root("certificate:evidence:mutation"),
        mutation_trace_roots=(_root("certificate:evidence:trace"),),
        principal_verification_state=verification,
        membership_state=membership,
        commit_replay_state=replay_state,
        attestations=attestations,
        dispositions=(),
    )
    evidence_attempt = advance_commit_evidence_state_v2(
        evidence,
        source=evidence_source,
        authority_session=open_commit_evidence_authority_session_v2(
            _capability(context, evidence.observed_epoch), evidence
        ),
    )
    assert evidence_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    evidence_state = rehydrate_commit_evidence_state_v2(
        evidence,
        domain=context.domain,
        state_reader=context.store,
    )
    return replay_state, evidence_state


def _commit_support(
    context,
    membership,
    claim_root: str,
    *,
    profile: str = PROFILE,
    assurance: CommitAssurance = ASSURANCE,
):
    initialize, initialize_source = prepare_support_initialize_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=profile,
        run_ref=RUN_REF,
        target_ref=TARGET,
        issuer_ref=context.grant.issuer_ref,
        observed_epoch=33,
        mutation_ref="mutation:certificate:support:initialize",
        current_step=3,
        provenance_root=_root("certificate:support:initialize:provenance"),
        source_trace_roots=(_root("certificate:support:initialize:trace"),),
    )
    initialize_attempt = advance_support_state_v2(
        initialize,
        source=initialize_source,
        authority_session=open_support_authority_session_v2(
            _capability(context, initialize.observed_epoch), initialize
        ),
    )
    assert initialize_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    state = rehydrate_support_state_v2(
        initialize,
        domain=context.domain,
        state_reader=context.store,
    )
    membership_snapshot = membership.snapshot
    policy = context.manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    policy_root = commit_policy_fingerprint(policy, profile=profile)
    observation = SupportObservationV2(
        observation_ref="observation:certificate",
        profile=profile,
        assurance=assurance,
        manifest_root=context.manifest.manifest_root,
        commit_policy_root=policy_root,
        protocol_ref=context.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        epoch=membership_snapshot.epoch,
        source_ref="source:certificate",
        evidence_root=_root("certificate:support:observation:evidence"),
        observed_at_step=4,
        expires_at_step=1_004,
        provenance_root=_root("certificate:support:observation:provenance"),
        source_trace_roots=(_root("certificate:support:observation:trace"),),
    )
    proposal = SupportLeaseProposalV2(
        proposal_ref="proposal:certificate",
        profile=profile,
        assurance=assurance,
        manifest_root=context.manifest.manifest_root,
        commit_policy_root=policy_root,
        protocol_ref=context.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        epoch=membership_snapshot.epoch,
        principal_ref="principal:alpha",
        positive_observation_roots=(observation.observation_root,),
        nonce="nonce:certificate:support",
        proposed_at_step=4,
        provenance_root=_root("certificate:support:proposal:provenance"),
        source_trace_roots=(_root("certificate:support:proposal:trace"),),
    )
    issue, issue_source = prepare_support_issue_v2(
        manifest=context.manifest,
        parent_state=state,
        membership_state=membership,
        proposal=proposal,
        positive_observations=(observation,),
        issuer_ref=context.grant.issuer_ref,
        observed_epoch=34,
        mutation_ref="mutation:certificate:support:issue",
        current_step=4,
        issuance_provenance_root=_root("certificate:support:issue:provenance"),
        issuance_trace_roots=(_root("certificate:support:issue:trace"),),
    )
    issue_attempt = advance_support_state_v2(
        issue,
        source=issue_source,
        authority_session=open_support_authority_session_v2(
            _capability(context, issue.observed_epoch), issue
        ),
    )
    assert issue_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return rehydrate_support_state_v2(
        issue,
        domain=context.domain,
        state_reader=context.store,
    )


def _commit_risk_and_gates(
    context,
    replay,
    membership,
    support,
    claim_root: str,
    *,
    profile: str = PROFILE,
    assurance: CommitAssurance = ASSURANCE,
):
    risk, risk_source = prepare_risk_state_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=profile,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=1,
        advance_ref="advance:certificate:risk",
        current_step=4,
        assessment_ref="assessment:certificate:risk",
        risk_band=RiskBand.LOW,
        risk_input_roots=(_root("certificate:risk:input"),),
        rationale_codes=("risk:low",),
        assessment_method="deterministic-test-v2",
        issuer_ref=context.grant.issuer_ref,
        issued_at_step=4,
        expires_at_step=100,
        provenance_ref="urn:test:certificate:risk",
        source_trace_roots=(_root("certificate:risk:trace"),),
    )
    risk_attempt = advance_risk_state_v2(
        risk,
        source=risk_source,
        authority_session=open_risk_authority_session_v2(_capability(context, 1), risk),
    )
    assert risk_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    risk_state = rehydrate_risk_state_v2(
        risk,
        domain=context.domain,
        state_reader=context.store,
    )
    stop, stop_source = prepare_commit_stop_resolution_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=profile,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=50,
        resolution_ref="resolution:certificate",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
        blocked=False,
        reason_codes=("stop:clear",),
        issued_at_step=6,
        expires_at_step=30,
        commit_replay_state=replay,
        risk_state=risk_state,
        membership_state=membership,
        support_state=support,
        parent_snapshot=None,
    )
    stop_attempt = resolve_commit_stop_v2(
        stop,
        source=stop_source,
        authority_session=open_commit_stop_authority_session_v2(
            _capability(context, 50), stop
        ),
    )
    assert stop_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    stop_state = rehydrate_commit_stop_state_v2(
        stop,
        domain=context.domain,
        state_reader=context.store,
    )
    permission, permission_source = prepare_commit_permission_issue_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=profile,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=50,
        permission_ref="permission:certificate",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
        allowed=True,
        claim_roots=(claim_root,),
        issued_at_step=6,
        expires_at_step=30,
        commit_replay_state=replay,
        risk_state=risk_state,
        membership_state=membership,
        support_state=support,
        parent_snapshot=None,
    )
    permission_attempt = issue_commit_permission_v2(
        permission,
        source=permission_source,
        authority_session=open_commit_permission_authority_session_v2(
            _capability(context, 50), permission
        ),
    )
    assert permission_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    permission_state = rehydrate_commit_permission_state_v2(
        permission,
        domain=context.domain,
        state_reader=context.store,
    )
    return risk_state, stop_state, permission_state


def certified_inputs(
    context,
    claim_root: str,
    *,
    profile: str = PROFILE,
    assurance: CommitAssurance = ASSURANCE,
) -> CertifiedDecisionInputs:
    if type(profile) is not str or not profile:
        raise TypeError("commit fixture profile must be non-empty text")
    if type(assurance) is not CommitAssurance:
        raise TypeError("commit fixture assurance must be exact CommitAssurance")
    verification, membership = _commit_identity_inputs(
        context,
        profile=profile,
        assurance=assurance,
    )
    replay, evidence = _commit_replay_and_evidence(
        context,
        verification,
        membership,
        claim_root,
        profile=profile,
        assurance=assurance,
    )
    support = _commit_support(
        context,
        membership,
        claim_root,
        profile=profile,
        assurance=assurance,
    )
    risk, stop, permission = _commit_risk_and_gates(
        context,
        replay,
        membership,
        support,
        claim_root,
        profile=profile,
        assurance=assurance,
    )
    return CertifiedDecisionInputs(
        replay=replay,
        risk=risk,
        membership=membership,
        verification=verification,
        support=support,
        evidence=evidence,
        stop=stop,
        permission=permission,
    )


__all__: tuple[str, ...] = ()
