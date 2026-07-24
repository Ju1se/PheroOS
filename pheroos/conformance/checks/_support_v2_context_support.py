"""Public ABI fixtures for the durable Support v2 Conformance matrix."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import cast
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks._support_v2_manifest_support import (
    ISSUER_REF,
    PROFILE,
    RUN_REF,
    TARGET_REF,
    manifest_v2,
    root_v2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.support_v2 import (
    MembershipCommitRequestV2,
    MembershipSnapshotV2,
    PrincipalVerificationRecordV2,
    PrincipalVerificationSetAdvanceRequestV2,
    PrincipalVerificationSetSnapshotV2,
    SupportAdvanceRequestV2,
    SupportLeaseProposalV2,
    SupportObservationV2,
    VerifiedMembershipStateV2,
    VerifiedPrincipalVerificationSetStateV2,
    VerifiedSupportSourceV2,
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
    prepare_support_revoke_v2,
    prepare_support_switch_v2,
    rehydrate_membership_state_v2,
    rehydrate_principal_verification_set_state_v2,
    rehydrate_support_state_v2,
)
from pheroos.protocol import (
    CollectiveCommitPolicy,
    CommitAssurance,
    ScopedProtocolManifestV2,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint


@dataclass(frozen=True, slots=True)
class SupportV2ConformanceContext:
    adapter: GovernanceStateStoreConformanceAdapterV2
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    manifest: ScopedProtocolManifestV2
    profile: str = PROFILE
    assurance: CommitAssurance = CommitAssurance.EVIDENCE_BOUND


@dataclass(frozen=True, slots=True)
class SupportV2Upstreams:
    verification_request: PrincipalVerificationSetAdvanceRequestV2
    verification_state: VerifiedPrincipalVerificationSetStateV2
    membership_request: MembershipCommitRequestV2
    membership_state: VerifiedMembershipStateV2


def context_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    suffix: str,
    *,
    scope_ref: str | None = None,
    profile: str = PROFILE,
    assurance: CommitAssurance = CommitAssurance.EVIDENCE_BOUND,
    grant_action_refs: tuple[str, ...] = (),
    manifest_transform: Callable[[ScopedProtocolManifestV2], ScopedProtocolManifestV2]
    | None = None,
) -> SupportV2ConformanceContext:
    domain = adapter.create_domain_v2(
        f"scope:support-v2:{suffix}" if scope_ref is None else scope_ref
    )
    store = adapter.create_store_v2((domain,))
    grant = grant_v2(
        domain,
        issuer_ref=ISSUER_REF,
        grant_ref="grant:support-v2:a",
        action_refs=grant_action_refs,
    )
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        f"transition:support-v2:grant:{suffix}",
        1,
    )
    if activated.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Support v2 Conformance grant activation failed")
    manifest = manifest_v2(domain.profile)
    if manifest_transform is not None:
        manifest = manifest_transform(manifest)
    return SupportV2ConformanceContext(
        adapter=adapter,
        domain=domain,
        store=store,
        grant=grant,
        manifest=manifest,
        profile=profile,
        assurance=assurance,
    )


def rebind_store_v2(
    context: SupportV2ConformanceContext,
    store: GovernanceStateStoreV2,
) -> SupportV2ConformanceContext:
    return replace(context, store=store)


def grant_v2(
    domain: AuthorityDomainV2,
    *,
    issuer_ref: str,
    grant_ref: str,
    action_refs: tuple[str, ...] = (),
) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref=issuer_ref,
        grant_ref=grant_ref,
        grant_binding_ref=root_v2(f"binding:{domain.scope_ref}:{grant_ref}"),
        operations=(
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
        target_refs=(TARGET_REF,),
        action_refs=action_refs,
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100_000,
        revocation_generation=0,
    )


def capability_v2(
    context: SupportV2ConformanceContext,
    observed_epoch: int,
    *,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> GovernanceIssuerCapabilityV2:
    selected = context.grant if grant is None else grant
    return bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        selected,
        RUN_REF,
        observed_epoch,
    )


def activate_rotated_grant_v2(
    context: SupportV2ConformanceContext,
) -> GovernanceIssuerGrantV2:
    grant = grant_v2(
        context.domain,
        issuer_ref="issuer:support-v2:b",
        grant_ref="grant:support-v2:b",
    )
    result = activate_governance_issuer_grant_v2(
        context.store,
        context.domain,
        grant,
        "transition:support-v2:grant:b",
        2,
    )
    if result.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Support v2 Conformance rotated grant failed")
    return grant


def commit_upstreams_v2(
    context: SupportV2ConformanceContext,
    *,
    label: str,
    epoch: int = 1,
    grant: GovernanceIssuerGrantV2 | None = None,
    verification_parent: PrincipalVerificationSetSnapshotV2 | None = None,
    membership_parent: MembershipSnapshotV2 | None = None,
) -> SupportV2Upstreams:
    selected = context.grant if grant is None else grant
    record = PrincipalVerificationRecordV2(
        principal_ref="principal:alpha",
        cluster_ref="cluster:alpha",
        failure_domain_ref="failure-domain:alpha",
        verification_method="external-attestation-v2",
        verification_issuer_ref="identity:verifier",
        attestation_root=root_v2(f"attestation:{label}"),
        evidence_roots=(root_v2(f"verification-evidence:{label}"),),
        issued_at_step=1,
        expires_at_step=90_000,
        provenance_ref=f"urn:pheroos:conformance:verification:{label}",
        source_trace_roots=(root_v2(f"verification-trace:{label}"),),
    )
    verification, verification_source = prepare_principal_verification_set_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=context.profile,
        assurance=context.assurance,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=epoch,
        observed_epoch=10 + epoch,
        advance_ref=f"advance:verification:{label}",
        snapshot_ref=f"snapshot:verification:{label}",
        current_step=epoch,
        expires_at_step=80_000,
        mutation_issuer_ref=selected.issuer_ref,
        records=(record,),
        parent_snapshot=verification_parent,
    )
    verification_session = open_principal_verification_authority_session_v2(
        capability_v2(context, verification.observed_epoch, grant=selected),
        verification,
    )
    verification_attempt = advance_principal_verification_set_v2(
        verification,
        source=verification_source,
        authority_session=verification_session,
    )
    if verification_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Support v2 Conformance verification commit failed")
    verification_state = rehydrate_principal_verification_set_state_v2(
        verification.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    membership, membership_source = prepare_membership_commit_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=context.profile,
        assurance=context.assurance,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=epoch,
        observed_epoch=20 + epoch,
        request_ref=f"request:membership:{label}",
        snapshot_ref=f"snapshot:membership:{label}",
        current_step=epoch + 1,
        expires_at_step=70_000,
        mutation_issuer_ref=selected.issuer_ref,
        membership_method="store-current-verification-set-v2",
        provenance_ref=f"urn:pheroos:conformance:membership:{label}",
        source_trace_roots=(root_v2(f"membership-trace:{label}"),),
        verification_state=verification_state,
        parent_snapshot=membership_parent,
    )
    membership_session = open_membership_authority_session_v2(
        capability_v2(context, membership.observed_epoch, grant=selected),
        membership,
    )
    membership_attempt = commit_membership_epoch_v2(
        membership,
        source=membership_source,
        authority_session=membership_session,
    )
    if membership_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Support v2 Conformance membership commit failed")
    membership_state = rehydrate_membership_state_v2(
        membership.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    return SupportV2Upstreams(
        verification,
        verification_state,
        membership,
        membership_state,
    )


def initialize_v2(
    context: SupportV2ConformanceContext,
    label: str,
    *,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    selected = context.grant if grant is None else grant
    return prepare_support_initialize_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=context.profile,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        issuer_ref=selected.issuer_ref,
        observed_epoch=33,
        mutation_ref=f"mutation:support:initialize:{label}",
        current_step=3,
        provenance_root=root_v2(f"support-initialize-provenance:{label}"),
        source_trace_roots=(root_v2(f"support-initialize-trace:{label}"),),
    )


def advance_support_v2(
    context: SupportV2ConformanceContext,
    request: SupportAdvanceRequestV2,
    source: object,
    *,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> GovernanceCommitAttemptV2:
    session = open_support_authority_session_v2(
        capability_v2(context, request.observed_epoch, grant=grant),
        request,
    )
    return advance_support_state_v2(
        request,
        source=source,
        authority_session=session,
    )


def support_state_v2(
    context: SupportV2ConformanceContext,
    request: SupportAdvanceRequestV2,
) -> VerifiedSupportStateV2:
    return rehydrate_support_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )


def issue_v2(
    context: SupportV2ConformanceContext,
    parent_state: VerifiedSupportStateV2,
    membership_state: VerifiedMembershipStateV2,
    label: str,
    *,
    current_step: int,
    candidate_ref: str = "candidate:support-v2:accept",
    claim_root: str | None = None,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    selected = context.grant if grant is None else grant
    claim = root_v2(f"claim:{label}") if claim_root is None else claim_root
    membership = membership_state.snapshot
    observation = observation_v2(
        context,
        membership,
        label,
        current_step=current_step,
        candidate_ref=candidate_ref,
        claim_root=claim,
    )
    proposal = proposal_v2(
        context,
        membership,
        observation,
        label,
        current_step=current_step,
        candidate_ref=candidate_ref,
        claim_root=claim,
    )
    return prepare_support_issue_v2(
        manifest=context.manifest,
        parent_state=parent_state,
        membership_state=membership_state,
        proposal=proposal,
        positive_observations=(observation,),
        issuer_ref=selected.issuer_ref,
        observed_epoch=30 + current_step,
        mutation_ref=f"mutation:support:issue:{label}",
        current_step=current_step,
        issuance_provenance_root=root_v2(f"issue-provenance:{label}"),
        issuance_trace_roots=(root_v2(f"issue-trace:{label}"),),
    )


def switch_v2(
    context: SupportV2ConformanceContext,
    parent_state: VerifiedSupportStateV2,
    membership_state: VerifiedMembershipStateV2,
    prior_lease_root: str,
    label: str,
    *,
    current_step: int,
    claim_root: str,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    selected = context.grant if grant is None else grant
    membership = membership_state.snapshot
    candidate_ref = "candidate:support-v2:safe"
    observation = observation_v2(
        context,
        membership,
        label,
        current_step=current_step,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
    )
    proposal = proposal_v2(
        context,
        membership,
        observation,
        label,
        current_step=current_step,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
    )
    return prepare_support_switch_v2(
        manifest=context.manifest,
        parent_state=parent_state,
        membership_state=membership_state,
        prior_lease_root=prior_lease_root,
        proposal=proposal,
        positive_observations=(observation,),
        issuer_ref=selected.issuer_ref,
        revocation_reason_codes=("candidate-switch",),
        observed_epoch=30 + current_step,
        mutation_ref=f"mutation:support:switch:{label}",
        current_step=current_step,
        revocation_provenance_root=root_v2(f"switch-revoke:{label}"),
        revocation_trace_roots=(root_v2(f"switch-revoke-trace:{label}"),),
        issuance_provenance_root=root_v2(f"switch-issue:{label}"),
        issuance_trace_roots=(root_v2(f"switch-issue-trace:{label}"),),
    )


def revoke_v2(
    context: SupportV2ConformanceContext,
    parent_state: VerifiedSupportStateV2,
    lease_root: str,
    label: str,
    *,
    current_step: int,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    selected = context.grant if grant is None else grant
    return prepare_support_revoke_v2(
        manifest=context.manifest,
        parent_state=parent_state,
        lease_root=lease_root,
        reason_codes=("conformance-complete",),
        issuer_ref=selected.issuer_ref,
        observed_epoch=30 + current_step,
        mutation_ref=f"mutation:support:revoke:{label}",
        current_step=current_step,
        provenance_root=root_v2(f"revoke-provenance:{label}"),
        source_trace_roots=(root_v2(f"revoke-trace:{label}"),),
    )


def observation_v2(
    context: SupportV2ConformanceContext,
    membership: MembershipSnapshotV2,
    label: str,
    *,
    current_step: int,
    candidate_ref: str,
    claim_root: str,
) -> SupportObservationV2:
    return SupportObservationV2(
        observation_ref=f"observation:{label}",
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
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        epoch=membership.epoch,
        source_ref=f"source:{label}",
        evidence_root=root_v2(f"observation-evidence:{label}"),
        observed_at_step=current_step,
        expires_at_step=min(membership.expires_at_step, current_step + 1_000),
        provenance_root=root_v2(f"observation-provenance:{label}"),
        source_trace_roots=(root_v2(f"observation-trace:{label}"),),
    )


def proposal_v2(
    context: SupportV2ConformanceContext,
    membership: MembershipSnapshotV2,
    observation: SupportObservationV2,
    label: str,
    *,
    current_step: int,
    candidate_ref: str,
    claim_root: str,
) -> SupportLeaseProposalV2:
    return SupportLeaseProposalV2(
        proposal_ref=f"proposal:{label}",
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
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        epoch=membership.epoch,
        principal_ref="principal:alpha",
        positive_observation_roots=(observation.observation_root,),
        nonce=f"nonce:{label}",
        proposed_at_step=current_step,
        provenance_root=root_v2(f"proposal-provenance:{label}"),
        source_trace_roots=(root_v2(f"proposal-trace:{label}"),),
    )


__all__: tuple[str, ...] = ()
