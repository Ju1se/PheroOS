"""Public-only context and identity graph for Distributed Commit v2 TCKs."""

from __future__ import annotations

from dataclasses import dataclass, replace

from pheroos.conformance.checks._support_v2_manifest_support import (
    manifest_v2,
    root_v2,
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
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.support_v2 import (
    PrincipalVerificationRecordV2,
    VerifiedMembershipStateV2,
    VerifiedPrincipalVerificationSetStateV2,
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
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CertificatePolicy,
    CollectiveCommitPolicy,
    CommitAssurance,
    DistributedCommitPolicy,
    ScopedProtocolManifestV2,
)


PROFILE = DISTRIBUTED_COMMIT_PROFILE_VERSION
ASSURANCE = CommitAssurance.DISTRIBUTED
RUN_REF = "run:distributed-v2-conformance"
TARGET_REF = "decision:support-v2"
CANDIDATE_REF = "candidate:support-v2:accept"


@dataclass(frozen=True, slots=True)
class DistributedV2Context:
    adapter: GovernanceStateStoreConformanceAdapterV2
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    manifest: ScopedProtocolManifestV2


@dataclass(frozen=True, slots=True)
class DistributedV2Identity:
    verification: VerifiedPrincipalVerificationSetStateV2
    membership: VerifiedMembershipStateV2


def context_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
) -> DistributedV2Context:
    domain = adapter.create_domain_v2(f"scope:distributed-v2:{label}")
    store = adapter.create_store_v2((domain,))
    grant = _grant_v2(domain, label)
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        f"transition:distributed-v2:grant:{label}",
        1,
    )
    _require_committed(activated.disposition, "grant activation")
    return DistributedV2Context(
        adapter=adapter,
        domain=domain,
        store=store,
        grant=grant,
        manifest=_distributed_manifest_v2(domain.profile),
    )


def capability_v2(
    context: DistributedV2Context,
    observed_epoch: int,
) -> GovernanceIssuerCapabilityV2:
    return bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        context.grant,
        RUN_REF,
        observed_epoch,
    )


def identity_v2(context: DistributedV2Context, label: str) -> DistributedV2Identity:
    record = PrincipalVerificationRecordV2(
        principal_ref="principal:alpha",
        cluster_ref="cluster:alpha",
        failure_domain_ref="failure-domain:alpha",
        verification_method="external-attestation-v2",
        verification_issuer_ref="identity:verifier",
        attestation_root=root_v2(f"distributed:verification:attestation:{label}"),
        evidence_roots=(root_v2(f"distributed:verification:evidence:{label}"),),
        issued_at_step=1,
        expires_at_step=90_000,
        provenance_ref=f"urn:pheroos:conformance:distributed:verification:{label}",
        source_trace_roots=(root_v2(f"distributed:verification:trace:{label}"),),
    )
    verification, source = prepare_principal_verification_set_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        assurance=ASSURANCE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=1,
        observed_epoch=11,
        advance_ref=f"advance:distributed:verification:{label}",
        snapshot_ref=f"snapshot:distributed:verification:{label}",
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
            capability_v2(context, verification.observed_epoch), verification
        ),
    )
    _require_committed(attempt.disposition, "principal verification")
    verification_state = rehydrate_principal_verification_set_state_v2(
        verification.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    membership, membership_source = prepare_membership_commit_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        assurance=ASSURANCE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=1,
        observed_epoch=21,
        request_ref=f"request:distributed:membership:{label}",
        snapshot_ref=f"snapshot:distributed:membership:{label}",
        current_step=2,
        expires_at_step=80_000,
        mutation_issuer_ref=context.grant.issuer_ref,
        membership_method="store-current-verification-set-v2",
        provenance_ref=f"urn:pheroos:conformance:distributed:membership:{label}",
        source_trace_roots=(root_v2(f"distributed:membership:trace:{label}"),),
        verification_state=verification_state,
        parent_snapshot=None,
    )
    membership_attempt = commit_membership_epoch_v2(
        membership,
        source=membership_source,
        authority_session=open_membership_authority_session_v2(
            capability_v2(context, membership.observed_epoch), membership
        ),
    )
    _require_committed(membership_attempt.disposition, "membership")
    return DistributedV2Identity(
        verification=verification_state,
        membership=rehydrate_membership_state_v2(
            membership.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        ),
    )


def _distributed_manifest_v2(authority_profile: str) -> ScopedProtocolManifestV2:
    manifest = manifest_v2(authority_profile)
    policy = manifest.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise RuntimeError("Distributed Commit v2 requires collective commit policy")
    bands = {
        name: replace(
            band,
            minimum_positive_evidence=1,
            minimum_support_clusters=1,
            minimum_support_ratio_ppm=1,
            minimum_source_diversity=1,
            minimum_margin=1,
            minimum_assurance=ASSURANCE.value,
        )
        for name, band in policy.risk_bands.items()
    }
    distributed = replace(
        policy,
        assurance=ASSURANCE.value,
        evidence_qualification=replace(
            policy.evidence_qualification,
            minimum_positive_evidence=1,
            minimum_source_diversity=1,
        ),
        support_lease=replace(
            policy.support_lease,
            minimum_support_clusters=1,
            support_ratio_ppm=1,
            lease_ttl_steps=20,
        ),
        risk_bands=bands,
        certificate=CertificatePolicy(
            mode="distributed",
            wire_version=COMMIT_WIRE_VERSION,
            canonicalization=COMMIT_CANONICAL_VERSION,
            hash_algorithm="sha256",
            issuer_attestation_required=True,
            independent_verification_required=True,
        ),
        distributed=DistributedCommitPolicy(
            fault_model="byzantine_static_v1",
            membership_mode="static_epoch_verified_clusters_v1",
            membership_size=1,
            max_byzantine_faults=0,
            witness_quorum=1,
            witness_ttl_steps=20,
            minimum_failure_domain_diversity=1,
            epoch_transition_rule="prior_quorum_certificate_v1",
            conflict_rule="freeze_v1",
        ),
    )
    return replace(manifest, collective_commit_policy=distributed)


def _grant_v2(domain: AuthorityDomainV2, label: str) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:distributed-v2:a",
        grant_ref=f"grant:distributed-v2:{label}",
        grant_binding_ref=root_v2(f"binding:distributed-v2:{label}"),
        operations=(
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RESOLVE_STOP,
            GovernanceIssuerOperationV2.ADVANCE_REPLAY,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
        target_refs=(TARGET_REF,),
        action_refs=("commit", "epoch_transition", "recovery"),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100_000,
        revocation_generation=0,
    )


def _require_committed(
    disposition: GovernanceCommitDispositionV2,
    label: str,
) -> None:
    if disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError(f"Distributed Commit v2 {label} setup failed")


__all__: tuple[str, ...] = ()
