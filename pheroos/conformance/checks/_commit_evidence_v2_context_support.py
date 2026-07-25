"""Public-ABI fixtures for durable Commit Evidence v2 Conformance."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Sequence

from pheroos.conformance.checks._support_v2_context_support import (
    SupportV2ConformanceContext,
    SupportV2Upstreams,
    capability_v2,
    context_v2,
    rebind_store_v2,
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
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.commit_evidence_v2 import (
    ChallengeResultV2,
    CommitEvidenceAdvanceRequestV2,
    CommitEvidenceAttestationV2,
    CommitEvidenceKindV2,
    VerifiedCommitEvidenceSourceV2,
    advance_commit_evidence_state_v2,
    commit_evidence_replay_receipts_for_proposals_v2,
    open_commit_evidence_authority_session_v2,
    prepare_commit_evidence_advance_v2,
)
from pheroos.governance.commit_state_v2 import (
    CommitReplayAdvanceRequestV2,
    VerifiedCommitReplayStateV2,
    advance_commit_replay_state_v2,
    open_commit_replay_authority_session_v2,
    prepare_commit_replay_advance_v2,
    rehydrate_commit_replay_state_v2,
)
from pheroos.governance.support_v2 import (
    PrincipalVerificationRecordV2,
    advance_principal_verification_set_v2,
    commit_membership_epoch_v2,
    open_membership_authority_session_v2,
    open_principal_verification_authority_session_v2,
    prepare_membership_commit_v2,
    prepare_principal_verification_set_v2,
    rehydrate_membership_state_v2,
    rehydrate_principal_verification_set_state_v2,
)
from pheroos.protocol import (
    CollectiveCommitPolicy,
    CommitAssurance,
    ScopedProtocolManifestV2,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint


CANDIDATE_REF = "candidate:support-v2:accept"


@dataclass(frozen=True, slots=True)
class CommitEvidenceV2ConformanceContext:
    support: SupportV2ConformanceContext
    upstreams: SupportV2Upstreams
    replay_grant: GovernanceIssuerGrantV2


def root_v2(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def context_v2_for_evidence(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    suffix: str,
    *,
    scope_ref: str | None = None,
    profile: str = PROFILE,
    assurance: CommitAssurance = CommitAssurance.EVIDENCE_BOUND,
    grant_action_refs: tuple[str, ...] = (),
    manifest_transform: Callable[[ScopedProtocolManifestV2], ScopedProtocolManifestV2]
    | None = None,
) -> CommitEvidenceV2ConformanceContext:
    support = context_v2(
        adapter,
        f"commit-evidence:{suffix}",
        scope_ref=scope_ref,
        profile=profile,
        assurance=assurance,
        grant_action_refs=grant_action_refs,
        manifest_transform=manifest_transform,
    )
    upstreams = _commit_two_principal_upstreams_v2(
        support,
        label=f"commit-evidence:{suffix}",
    )
    replay_grant = GovernanceIssuerGrantV2(
        domain_root=support.domain.domain_root,
        scope_ref=support.domain.scope_ref,
        issuer_ref="issuer:commit-evidence:replay",
        grant_ref="grant:commit-evidence:replay",
        grant_binding_ref=root_v2(
            f"grant-binding:{support.domain.scope_ref}:commit-evidence:replay"
        ),
        operations=(GovernanceIssuerOperationV2.ADVANCE_REPLAY,),
        target_refs=(TARGET_REF,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100_000,
        revocation_generation=0,
    )
    activated = activate_governance_issuer_grant_v2(
        support.store,
        support.domain,
        replay_grant,
        f"transition:grant:commit-evidence:replay:{suffix}",
        1,
    )
    if activated.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Commit Evidence v2 replay grant activation failed")
    return CommitEvidenceV2ConformanceContext(support, upstreams, replay_grant)


def rebind_context_v2(
    context: CommitEvidenceV2ConformanceContext,
    store: GovernanceStateStoreV2,
) -> CommitEvidenceV2ConformanceContext:
    return replace(context, support=rebind_store_v2(context.support, store))


def _commit_two_principal_upstreams_v2(
    context: SupportV2ConformanceContext,
    *,
    label: str,
) -> SupportV2Upstreams:
    records = tuple(
        PrincipalVerificationRecordV2(
            principal_ref=f"principal:{principal}",
            cluster_ref=f"cluster:{principal}",
            failure_domain_ref=f"failure-domain:{principal}",
            verification_method="external-attestation-v2",
            verification_issuer_ref="identity:verifier",
            attestation_root=root_v2(f"attestation:{principal}:{label}"),
            evidence_roots=(root_v2(f"verification:{principal}:{label}"),),
            issued_at_step=1,
            expires_at_step=90_000,
            provenance_ref=f"urn:pheroos:verification:{principal}:{label}",
            source_trace_roots=(root_v2(f"verification-trace:{principal}:{label}"),),
        )
        for principal in ("alpha", "beta")
    )
    verification, verification_source = prepare_principal_verification_set_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=context.profile,
        assurance=context.assurance,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=1,
        observed_epoch=11,
        advance_ref=f"advance:verification:{label}",
        snapshot_ref=f"snapshot:verification:{label}",
        current_step=1,
        expires_at_step=80_000,
        mutation_issuer_ref=context.grant.issuer_ref,
        records=records,
    )
    verification_session = open_principal_verification_authority_session_v2(
        capability_v2(context, verification.observed_epoch),
        verification,
    )
    verification_attempt = advance_principal_verification_set_v2(
        verification,
        source=verification_source,
        authority_session=verification_session,
    )
    if verification_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Commit Evidence v2 verification advance failed")
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
        epoch=1,
        observed_epoch=21,
        request_ref=f"request:membership:{label}",
        snapshot_ref=f"snapshot:membership:{label}",
        current_step=2,
        expires_at_step=70_000,
        mutation_issuer_ref=context.grant.issuer_ref,
        membership_method="store-current-verification-set-v2",
        provenance_ref=f"urn:pheroos:membership:{label}",
        source_trace_roots=(root_v2(f"membership-trace:{label}"),),
        verification_state=verification_state,
    )
    membership_session = open_membership_authority_session_v2(
        capability_v2(context, membership.observed_epoch),
        membership,
    )
    membership_attempt = commit_membership_epoch_v2(
        membership,
        source=membership_source,
        authority_session=membership_session,
    )
    if membership_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Commit Evidence v2 membership advance failed")
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


def attestations_v2(
    label: str,
    *,
    claim_root: str | None = None,
    include_second_positive: bool = True,
    expires_at_step: int = 10,
) -> tuple[CommitEvidenceAttestationV2, ...]:
    claim = root_v2(f"claim:{label}") if claim_root is None else claim_root
    positive = CommitEvidenceAttestationV2(
        evidence_ref=f"evidence:positive:{label}",
        kind=CommitEvidenceKindV2.POSITIVE,
        candidate_ref=CANDIDATE_REF,
        claim_root=claim,
        epoch=1,
        principal_ref="principal:alpha",
        payload_root=root_v2(f"payload:positive:{label}"),
        source_ref=f"source:independent:{label}",
        independence_ref=f"independence:{label}",
        reported_quality_ppm=1_000_000,
        reported_relevance_ppm=1_000_000,
        reported_materiality_ppm=0,
        reported_criticality_ppm=0,
        category_ref="",
        execution_method="",
        execution_attestation_root="",
        execution_root="",
        challenge_result=ChallengeResultV2.NONE,
        result_root="",
        result_observation_roots=(),
        nonce=f"nonce:positive:{label}",
        observed_at_step=3,
        expires_at_step=expires_at_step,
        provenance_root=root_v2(f"provenance:positive:{label}"),
        trace_roots=(root_v2(f"trace:positive:{label}"),),
    )
    challenge = CommitEvidenceAttestationV2(
        evidence_ref=f"evidence:challenge:{label}",
        kind=CommitEvidenceKindV2.CHALLENGE,
        candidate_ref=CANDIDATE_REF,
        claim_root=claim,
        epoch=1,
        principal_ref="principal:alpha",
        payload_root=root_v2(f"payload:challenge:{label}"),
        source_ref="",
        independence_ref="",
        reported_quality_ppm=0,
        reported_relevance_ppm=0,
        reported_materiality_ppm=0,
        reported_criticality_ppm=0,
        category_ref="independent_replication",
        execution_method="deterministic-challenge-v2",
        execution_attestation_root=root_v2(f"execution-attestation:challenge:{label}"),
        execution_root=root_v2(f"execution:challenge:{label}"),
        challenge_result=ChallengeResultV2.NO_COUNTEREVIDENCE,
        result_root=root_v2(f"result:challenge:{label}"),
        result_observation_roots=(),
        nonce=f"nonce:challenge:{label}",
        observed_at_step=3,
        expires_at_step=expires_at_step,
        provenance_root=root_v2(f"provenance:challenge:{label}"),
        trace_roots=(root_v2(f"trace:challenge:{label}"),),
    )
    second = replace(
        positive,
        evidence_ref=f"evidence:positive:second:{label}",
        principal_ref="principal:beta",
        payload_root=root_v2(f"payload:positive:second:{label}"),
        source_ref=f"source:independent:second:{label}",
        independence_ref=f"independence:second:{label}",
        nonce=f"nonce:positive:second:{label}",
        provenance_root=root_v2(f"provenance:positive:second:{label}"),
        trace_roots=(root_v2(f"trace:positive:second:{label}"),),
        attestation_root="",
    )
    return (
        (positive, second, challenge)
        if include_second_positive
        else (positive, challenge)
    )


def commit_replay_v2(
    context: CommitEvidenceV2ConformanceContext,
    attestations: Sequence[CommitEvidenceAttestationV2],
    *,
    advance_ref: str,
) -> tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplayStateV2]:
    support = context.support
    commit_policy = support.manifest.collective_commit_policy
    if type(commit_policy) is not CollectiveCommitPolicy:
        raise RuntimeError("Commit Evidence v2 requires collective commit policy")
    request, source = prepare_commit_replay_advance_v2(
        domain_root=support.domain.domain_root,
        scope_ref=support.domain.scope_ref,
        manifest_root=support.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(
            commit_policy,
            profile=support.profile,
        ),
        profile=support.profile,
        assurance=support.assurance,
        protocol_ref=support.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=1,
        advance_ref=advance_ref,
        current_step=3,
        receipt_additions=commit_evidence_replay_receipts_for_proposals_v2(
            attestations,
            (),
            target_ref=TARGET_REF,
        ),
    )
    capability = bind_governance_issuer_capability_v2(
        support.store,
        support.domain,
        context.replay_grant,
        RUN_REF,
        request.observed_epoch,
    )
    session = open_commit_replay_authority_session_v2(capability, request)
    attempt = advance_commit_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Commit Evidence v2 replay advance failed")
    return request, rehydrate_commit_replay_state_v2(
        request.to_dict(),
        domain=support.domain,
        state_reader=support.store,
    )


def request_v2(
    context: CommitEvidenceV2ConformanceContext,
    replay_state: VerifiedCommitReplayStateV2,
    attestations: Sequence[CommitEvidenceAttestationV2],
    *,
    advance_ref: str,
) -> tuple[CommitEvidenceAdvanceRequestV2, VerifiedCommitEvidenceSourceV2]:
    support = context.support
    return prepare_commit_evidence_advance_v2(
        domain_root=support.domain.domain_root,
        scope_ref=support.domain.scope_ref,
        manifest=support.manifest,
        profile=support.profile,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=1,
        observed_epoch=30,
        advance_ref=advance_ref,
        current_step=4,
        mutation_issuer_ref=support.grant.issuer_ref,
        mutation_provenance_root=root_v2(f"mutation:{advance_ref}"),
        mutation_trace_roots=(root_v2(f"trace:{advance_ref}"),),
        principal_verification_state=context.upstreams.verification_state,
        membership_state=context.upstreams.membership_state,
        commit_replay_state=replay_state,
        attestations=attestations,
        dispositions=(),
    )


def advance_v2(
    context: CommitEvidenceV2ConformanceContext,
    request: CommitEvidenceAdvanceRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    session = open_commit_evidence_authority_session_v2(
        capability_v2(context.support, request.observed_epoch),
        request,
    )
    return advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )


__all__: tuple[str, ...] = ()
